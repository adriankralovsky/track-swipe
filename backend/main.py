import asyncio, contextlib, json, logging, re, sqlite3, tempfile, threading, time
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, UploadFile, File, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from . import db, importer, matcher, media, metadata, autoapprove, youtube
from . import playlists as playlist_export

logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
log=logging.getLogger('trackswipe')
operation=threading.RLock()
stop=threading.Event()

def worker():
    while not stop.wait(1):
        if db.settings()['paused']: continue
        with operation:
            if db.settings()['paused']: continue
            autoapprove.apply()
            with db.connect() as c:
                r=c.execute("SELECT * FROM tracks WHERE status='approved' ORDER BY id LIMIT 1").fetchone()
                if not r: continue
                c.execute("UPDATE tracks SET status='downloading',error=NULL WHERE id=?",(r['id'],)); db.event(c,r['id'],'downloading')
            try:
                path,existing=media.download_track(r)
                with db.connect() as c:
                    status='existing' if existing else 'completed'
                    c.execute('UPDATE tracks SET status=?,output_file=?,error=NULL WHERE id=?',(status,path,r['id'])); db.event(c,r['id'],status,path)
                playlist_export.sync_safely()
            except Exception as e:
                log.exception('Download failed for track %s',r['id'])
                with db.connect() as c:
                    c.execute("UPDATE tracks SET status='failed',error=? WHERE id=?",(youtube.friendly_error(e),r['id'])); db.event(c,r['id'],'failed',youtube.friendly_error(e))

@asynccontextmanager
async def lifespan(app):
    db.init()
    s=db.settings()
    Path(s['library_dir']).expanduser().mkdir(parents=True,exist_ok=True)
    playlist_export.sync_safely()
    stop.clear(); thread=threading.Thread(target=worker,daemon=True); thread.start()
    yield
    stop.set()

app=FastAPI(title='TrackSwipe',lifespan=lifespan)

@app.middleware('http')
async def local_origin(request:Request,call_next):
    origin=request.headers.get('origin')
    if origin:
        from urllib.parse import urlparse
        if urlparse(origin).netloc!=request.headers.get('host'): return __import__('starlette.responses',fromlist=['JSONResponse']).JSONResponse({'detail':'Cross-origin requests are disabled'},403)
    return await call_next(request)

@app.exception_handler(Exception)
async def unexpected_error(request,exc):
    from fastapi.responses import JSONResponse
    log.exception('Request failed: %s',request.url.path,exc_info=exc)
    return JSONResponse(status_code=500,content={'detail':'Operation failed: '+str(exc)[:400]})

@app.exception_handler(ValueError)
async def value_error(request,exc):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=400,content={'detail':str(exc)})

def get_track(tid,c):
    r=c.execute('SELECT * FROM tracks WHERE id=?',(tid,)).fetchone()
    if not r: raise HTTPException(404,'Track not found')
    return r

@app.get('/api/status')
def status():
    with db.connect() as c:
        counts={r[0]:r[1] for r in c.execute('SELECT status,count(*) FROM tracks GROUP BY status')}
        return dict(total=sum(counts.values()),counts=counts,rejected=c.execute('SELECT count(*) FROM candidates WHERE rejected=1').fetchone()[0],paused=db.settings()['paused'])

@app.get('/api/tracks')
def tracks(view:str='all',q:str='',playlist:str=''):
    with db.connect() as c:
        rows=[db.track(r,c) for r in c.execute('SELECT * FROM tracks ORDER BY id')]
    for row in rows:
        if row.get('error'): row['error']=youtube.friendly_error(row['error'])
    if view=='review':
        allowed=['waiting']
        s=db.settings()
        if s['show_existing']: allowed+=['existing','completed']
        if s['show_skipped']: allowed+=['skipped']
        rows=[r for r in rows if r['status'] in allowed]
    elif view=='downloaded': rows=[r for r in rows if r['status'] in ('completed','existing')]
    elif view=='not_downloaded': rows=[r for r in rows if r['status'] not in ('completed','existing')]
    elif view=='queue': rows=[r for r in rows if r['status'] in ('approved','downloading','failed')]
    elif view!='all': rows=[r for r in rows if r['status']==view]
    if playlist: rows=[r for r in rows if playlist in r['playlists']]
    if q: rows=[r for r in rows if q.casefold() in json.dumps(r['metadata'],ensure_ascii=False).casefold()]
    return rows

@app.get('/api/playlists')
def playlists():
    with db.connect() as c:
        return [dict(r) for r in c.execute("SELECT p.id,p.name,count(t.id) total,sum(t.status IN ('completed','existing')) downloaded,sum(t.status='waiting') waiting,sum(t.status='skipped') skipped FROM playlists p LEFT JOIN track_playlists tp ON p.id=tp.playlist_id LEFT JOIN tracks t ON t.id=tp.track_id GROUP BY p.id ORDER BY p.name")]

@app.post('/api/import')
async def import_file(file:UploadFile=File(...)):
    data=await file.read(25_000_001)
    if len(data)>25_000_000: raise HTTPException(413,'Import exceeds 25 MB')
    return await asyncio.to_thread(import_data,data,file.filename or 'import.csv')

def import_data(data,name):
    rows=importer.parse(data,name)
    if not rows: raise ValueError('No Spotify tracks found. Use Exportify CSV, Spotify track links, or an account export with playlist/library records.')
    for m,_ in rows[:25]: importer.enrich(m)
    with operation:
        added=importer.merge(rows)
        scan=media.scan()
        playlist_export.sync_safely()
    return dict(imported=added,merged=len(rows)-added,scan=scan,unresolved=sum(not m['title'] or not m['artists'] for m,_ in rows))

@app.get('/api/import-files')
def import_files():
    configured=db.settings()['import_dir']
    if not configured: return []
    root=Path(configured).expanduser().resolve()
    if not root.is_dir(): raise ValueError('Configured import directory does not exist')
    return [p.name for p in sorted(root.iterdir()) if p.is_file() and p.suffix.lower() in ('.csv','.json','.zip','.txt')]

@app.post('/api/import-local')
def import_local(body:dict):
    configured=db.settings()['import_dir']
    if not configured: raise ValueError('Choose an import directory in Settings first')
    root=Path(configured).expanduser().resolve()
    path=(root/str(body.get('name',''))).resolve()
    if not path.is_relative_to(root) or not path.is_file(): raise ValueError('Import file is outside the configured directory')
    if path.stat().st_size>25_000_000: raise ValueError('Import exceeds 25 MB')
    return import_data(path.read_bytes(),path.name)

@app.post('/api/rescan')
def rescan():
    with operation:
        result=media.scan()
        result['playlists']=playlist_export.sync_safely()
        return result

@app.get('/api/tracks/{tid}/candidates')
def candidates(tid:int):
    with db.connect() as c:
        target=json.loads(get_track(tid,c)['metadata'])
        current=db.settings()
        return [matcher.score(target,json.loads(r['metadata']),current)|{'rejected':bool(r['rejected'])} for r in c.execute('SELECT * FROM candidates WHERE track_id=? ORDER BY json_extract(metadata,\'$.confidence\') DESC',(tid,))]

@app.post('/api/tracks/{tid}/search')
def search(tid:int,body:dict):
    if db.settings()['paused']: raise ValueError('Resume the process to search')
    with db.connect() as c: t=json.loads(get_track(tid,c)['metadata'])
    if not t.get('title') or not t.get('artists'): raise ValueError('This export has incomplete metadata. Add the song title and artist before searching.')
    search_settings=db.settings()
    with db.connect() as c: rejected=c.execute('SELECT count(*) FROM candidates WHERE track_id=? AND rejected=1',(tid,)).fetchone()[0]
    search_settings['candidate_count']=min(50,search_settings['candidate_count']+rejected)
    results,warnings=matcher.search(t,search_settings,body.get('query'))
    with db.connect() as c:
        for r in results:
            c.execute('INSERT INTO candidates(track_id,video_id,metadata) VALUES(?,?,?) ON CONFLICT(track_id,video_id) DO UPDATE SET metadata=excluded.metadata',(tid,r['video_id'],json.dumps(r)))
        db.event(c,tid,'searched','; '.join(warnings))
    autoapprove.apply(tid)
    return {'candidates':candidates(tid),'warnings':warnings}

@app.post('/api/tracks/{tid}/enrich')
def enrich_track(tid:int):
    with db.connect() as c: original=json.loads(get_track(tid,c)['metadata'])
    enriched,warnings=metadata.enrich(original)
    with db.connect() as c:
        current=json.loads(get_track(tid,c)['metadata'])
        for k,v in enriched.items():
            if not current.get(k) and v: current[k]=v
        c.execute('UPDATE tracks SET metadata=? WHERE id=?',(json.dumps(current),tid))
    return {'metadata':current,'warnings':warnings}

@app.post('/api/tracks/{tid}/manual')
def manual(tid:int,body:dict):
    import yt_dlp
    url=str(body.get('url',''))
    m=re.fullmatch(r'(?:https?://)?(?:www\.|music\.)?(?:youtube\.com/watch\?(?:[^#]*&)?v=|youtu\.be/)([\w-]{11})(?:[?&].*)?',url)
    if not m: raise ValueError('Enter a valid youtube.com/watch or youtu.be video URL')
    vid=m.group(1)
    with db.connect() as c: t=json.loads(get_track(tid,c)['metadata'])
    with yt_dlp.YoutubeDL(youtube.options(db.settings())) as y: r=y.extract_info('https://www.youtube.com/watch?v='+vid,download=False)
    item=matcher.score(t,dict(video_id=vid,title=r.get('title',''),channel=r.get('channel',''),duration=r.get('duration',0),thumbnail=r.get('thumbnail',''),artists=[r['artist']] if r.get('artist') else [],music=False),db.settings())
    with db.connect() as c:
        c.execute('INSERT INTO candidates(track_id,video_id,metadata,rejected) VALUES(?,?,?,0) ON CONFLICT(track_id,video_id) DO UPDATE SET rejected=0,metadata=excluded.metadata',(tid,vid,json.dumps(item)))
        db.event(c,tid,'manual-candidate',vid)
    return item

@app.post('/api/tracks/{tid}/decision')
def decision(tid:int,body:dict):
    action=body.get('action'); vid=body.get('video_id')
    with db.connect() as c:
        r=get_track(tid,c)
        if r['status']=='downloading': raise ValueError('Wait for the active download to finish')
        if action in ('accept','reject'):
            candidate=c.execute('SELECT * FROM candidates WHERE track_id=? AND video_id=?',(tid,vid)).fetchone()
            if not candidate: raise ValueError('Candidate not found')
            if action=='reject': c.execute('UPDATE candidates SET rejected=1 WHERE track_id=? AND video_id=?',(tid,vid))
            else:
                t=json.loads(r['metadata'])
                if not t.get('title') or not t.get('artists'): raise ValueError('Title and artist are required before approval')
                existing=bool(r['output_file'] and Path(r['output_file']).is_file())
                c.execute("UPDATE tracks SET status=?,approved_video=?,error=NULL WHERE id=?",('existing' if existing else 'approved',vid,tid))
        elif action=='skip': c.execute("UPDATE tracks SET status='skipped' WHERE id=?",(tid,))
        elif action=='restore': c.execute("UPDATE tracks SET status='waiting',error=NULL WHERE id=?",(tid,))
        elif action=='retry':
            if not r['approved_video']: raise ValueError('No approved match')
            c.execute("UPDATE tracks SET status='approved',error=NULL WHERE id=?",(tid,))
        else: raise ValueError('Unknown decision')
        db.event(c,tid,action,vid or '')
    playlist_export.sync_safely()
    return {'ok':True}

@app.patch('/api/tracks/{tid}')
def edit_track(tid:int,body:dict):
    with db.connect() as c:
        r=get_track(tid,c)
        if r['status']=='downloading': raise ValueError('Wait for the active download before editing metadata')
        m=json.loads(r['metadata'])
        for key in m:
            if key in body and key!='spotify_id': m[key]=body[key]
        if not isinstance(m['artists'],list) or not isinstance(m['title'],str): raise ValueError('Invalid title or artists')
        m['duration']=float(m.get('duration') or 0)
        c.execute('UPDATE tracks SET metadata=? WHERE id=?',(json.dumps(m),tid)); db.event(c,tid,'metadata-edited')
    return {'ok':True}

@app.post('/api/tracks/{tid}/repair')
def repair(tid:int):
    with operation,db.connect() as c:
        r=get_track(tid,c)
        if not r['output_file'] or not Path(r['output_file']).is_file(): raise ValueError('Existing audio file not found')
        p=Path(r['output_file']); backup=p.with_name(p.name+'.tags-backup')
        import shutil
        if backup.exists(): raise ValueError('A tag backup already exists; keep or remove it before repairing again')
        shutil.copy2(p,backup)
        try: media.tag(p,json.loads(r['metadata']),db.track(r,c)['playlists'],db.settings())
        except Exception:
            shutil.copy2(backup,p); raise
        db.event(c,tid,'metadata-repaired',str(backup))
    return {'ok':True,'backup':str(backup)}

@app.get('/api/settings')
def settings(): return db.settings()

@app.put('/api/settings')
def save_settings(body:dict):
    unknown=set(body)-set(db.DEFAULTS)
    if unknown: raise ValueError('Unknown settings: '+', '.join(unknown))
    merged=db.settings()|body
    for k,v in body.items():
        default=db.DEFAULTS[k]
        if isinstance(default,bool) and not isinstance(v,bool): raise ValueError(k+' must be boolean')
        if isinstance(default,str) and not isinstance(v,str): raise ValueError(k+' must be text')
    for k,lo,hi in [('candidate_count',1,50),('auto_threshold',90,100),('max_duration_difference',1,120),('volume',0,100),('animation_intensity',0,2)]:
        if not isinstance(merged[k],(int,float)) or not lo<=merged[k]<=hi: raise ValueError(f'{k} must be between {lo} and {hi}')
    if not isinstance(merged['candidate_count'],int): raise ValueError('Candidate count must be a whole number')
    if merged['audio_format'] not in ('best','m4a','opus','mp3'): raise ValueError('Unsupported audio format')
    if merged['youtube_auth'] not in ('none','file','browser'): raise ValueError('Invalid YouTube authentication mode')
    if merged['youtube_browser'] not in youtube.BROWSERS: raise ValueError('Unsupported browser')
    if merged['youtube_auth']=='file':
        youtube.options(merged)
    playlist_export.directory(merged)
    if merged['replay_gain']: raise ValueError('ReplayGain analysis is not installed')
    for k in ('library_dir','temp_dir'):
        p=Path(merged[k]).expanduser()
        if not p.is_absolute(): raise ValueError(k+' must be an absolute directory')
        p.mkdir(parents=True,exist_ok=True)
    if not merged['output_template'].endswith('.{ext}'): raise ValueError('Output template must end in .{ext}')
    try: media.destination({'title':'Example','artists':['Artist'],'album':'Album'},'m4a',merged)
    except (KeyError,ValueError) as e: raise ValueError('Invalid output template: '+str(e))
    with db.connect() as c:
        for k,v in body.items(): c.execute('INSERT OR REPLACE INTO settings VALUES(?,?)',(k,json.dumps(v)))
    autoapprove.apply()
    playlist_export.sync_safely()
    return merged

@app.get('/api/directories')
def directories(path:str=''):
    p=Path(path or db.settings()['library_dir']).expanduser().resolve()
    if not p.is_dir(): raise ValueError('Directory not found')
    try: children=sorted([str(x) for x in p.iterdir() if x.is_dir() and not x.name.startswith('.')])
    except PermissionError: raise ValueError('Cannot access this directory')
    return {'path':str(p),'parent':str(p.parent),'children':children}

@app.get('/api/history')
def history():
    with db.connect() as c: return [dict(r) for r in c.execute('SELECT e.*,json_extract(t.metadata,\'$.title\') title FROM events e LEFT JOIN tracks t ON t.id=e.track_id ORDER BY e.id DESC LIMIT 1000')]

@app.get('/api/export/json')
def export_json():
    from fastapi.responses import Response
    with db.connect() as c: data={table:[dict(r) for r in c.execute('SELECT * FROM '+table)] for table in ('tracks','playlists','track_playlists','candidates','files','events','settings')}
    for rows in data.values():
        for row in rows:
            if 'metadata' in row: row['metadata']=json.loads(row['metadata'])
    for row in data['settings']: row['value']=json.loads(row['value'])
    return Response(json.dumps({'version':1,'tables':data},ensure_ascii=False,indent=2),media_type='application/json',headers={'Content-Disposition':'attachment; filename="trackswipe-state.json"'})

@app.get('/api/export/database')
def export_database():
    from starlette.background import BackgroundTask
    fd,path=tempfile.mkstemp(suffix='.sqlite3',dir=db.DATA)
    import os; os.close(fd)
    with db.connect() as source,sqlite3.connect(path) as dest: source.backup(dest)
    return FileResponse(path,filename='trackswipe-backup.sqlite3',background=BackgroundTask(Path(path).unlink))

@app.post('/api/restore')
async def restore(file:UploadFile=File(...)):
    if not db.settings()['paused']: raise ValueError('Pause the process before restoring a backup')
    data=await file.read(100_000_001)
    if len(data)>100_000_000: raise ValueError('Backup exceeds 100 MB')
    def run():
        with operation:
            with tempfile.NamedTemporaryFile(dir=db.DATA,suffix='.sqlite3') as temp:
                temp.write(data); temp.flush()
                with sqlite3.connect(temp.name) as source:
                    if source.execute('PRAGMA integrity_check').fetchone()[0]!='ok': raise ValueError('Invalid SQLite backup')
                    if source.execute('PRAGMA user_version').fetchone()[0]!=1: raise ValueError('Unsupported backup schema version')
                    tables=('tracks','playlists','track_playlists','candidates','files','events','settings')
                    with db.connect() as current:
                        for table in tables:
                            expected=[r[1] for r in current.execute('PRAGMA table_info('+table+')')]
                            found=[r[1] for r in source.execute('PRAGMA table_info('+table+')')]
                            if found!=expected: raise ValueError('Invalid backup schema: '+table)
                        if source.execute('PRAGMA foreign_key_check').fetchone(): raise ValueError('Backup contains broken relationships')
                        backup=db.DATA/f'pre-restore-{time.time_ns()}.sqlite3'
                        with sqlite3.connect(backup) as dest: current.backup(dest)
                        # Restore rows only: never execute triggers/views from an uploaded database.
                        current.execute('PRAGMA foreign_keys=OFF')
                        for table in reversed(tables): current.execute('DELETE FROM '+table)
                        for table in tables:
                            rows=source.execute('SELECT * FROM '+table).fetchall()
                            if rows: current.executemany('INSERT INTO '+table+' VALUES('+','.join('?' for _ in rows[0])+')',rows)
                        current.execute("INSERT OR REPLACE INTO settings VALUES('paused','true')")
                        current.execute("UPDATE tracks SET status='approved' WHERE status='downloading'")
            return {'ok':True,'safety_backup':str(backup)}
    try: return await asyncio.to_thread(run)
    except sqlite3.DatabaseError as e: raise ValueError('Invalid database backup: '+str(e))

@app.post('/api/auto-approve')
def apply_auto_approval():
    return {'approved':autoapprove.apply()}

@app.post('/api/playlists/sync')
def sync_playlists():
    return playlist_export.sync(force=True)

@app.post('/api/downloads/retry-auth')
def retry_auth_downloads():
    count=0
    with db.connect() as c:
        for row in c.execute("SELECT * FROM tracks WHERE status='failed' AND approved_video IS NOT NULL").fetchall():
            if youtube.auth_required(row['error'] or ''):
                c.execute("UPDATE tracks SET status='approved',error=NULL WHERE id=?",(row['id'],))
                db.event(c,row['id'],'retry','YouTube authentication retry')
                count+=1
    return {'queued':count}

@app.get('/api/health')
def health():
    import shutil
    return {'status':'ok','ffmpeg':bool(shutil.which('ffmpeg')),'database':str(db.DB)}

assets=Path(__file__).resolve().parent.parent/'frontend'/'dist'
if assets.exists():
    app.mount('/assets',StaticFiles(directory=assets/'assets'),name='assets')
    @app.get('/{path:path}')
    def frontend(path:str): return FileResponse(assets/'index.html')
