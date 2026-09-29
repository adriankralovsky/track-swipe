import base64, json, os, re, shutil, subprocess, tempfile, uuid, logging, string
from pathlib import Path
import httpx, mutagen
from mutagen.id3 import ID3, TIT2, TPE1, TPE2, TALB, TRCK, TPOS, TDRC, TSRC, TXXX, APIC
from mutagen.mp4 import MP4, MP4Cover
from mutagen.flac import Picture
from .db import connect, settings, event
from . import youtube
from .importer import norm, spotify_id

EXTENSIONS={'.mp3','.m4a','.opus','.ogg','.flac','.aac','.wav','.wma','.aiff','.mp4'}

def read_tags(path):
    f=mutagen.File(path,easy=True)
    if f is None: return None
    def val(*keys):
        for key in keys:
            v=(f.tags or {}).get(key)
            if v: return str(v[0])
        return ''
    m=dict(title=val('title'),artists=list((f.tags or {}).get('artist',[])),album=val('album'),isrc=val('isrc'),spotify_id=val('spotify_id','spotifyid','spotify_track_id','spotify_uri'),duration=getattr(f.info,'length',0))
    raw=mutagen.File(path)
    if isinstance(raw,MP4):
        for key in ('spotify_id','isrc'):
            v=raw.tags.get('----:com.apple.iTunes:'+key.upper(),[])
            if v: m[key]=bytes(v[0]).decode('utf-8')
    elif raw and isinstance(raw.tags,ID3):
        for key in ('spotify_id','isrc'):
            v=raw.tags.get('TXXX:'+key.upper())
            if v: m[key]=str(v)
    m['spotify_id']=spotify_id(m.get('spotify_id',''))
    return m

def match_file(t,files):
    for field in ('isrc','spotify_id'):
        if t.get(field):
            for path,m in files:
                if norm(t[field])==norm(m.get(field)): return path
    for path,m in files:
        same=norm(t.get('title'))==norm(m.get('title')) and bool(t.get('artists')) and norm(t['artists'][0]) in [norm(a) for a in m.get('artists',[])]
        if t.get('isrc') and m.get('isrc') and norm(t['isrc'])!=norm(m['isrc']): continue
        if same and t.get('album') and norm(t['album'])==norm(m.get('album')): return path
    for path,m in files:
        same=norm(t.get('title'))==norm(m.get('title')) and bool(t.get('artists')) and norm(t['artists'][0]) in [norm(a) for a in m.get('artists',[])]
        if t.get('isrc') and m.get('isrc') and norm(t['isrc'])!=norm(m['isrc']): continue
        if same and t.get('duration') and m.get('duration') and abs(float(t['duration'])-float(m['duration']))<2: return path
    # Conservative fallback only when both title and artist exist in an otherwise untagged filename.
    for path,m in files:
        if not m.get('title') and t.get('artists') and norm(Path(path).stem)==norm(t['artists'][0]+' '+t.get('title','')): return path
    return None

def scan():
    root=Path(settings()['library_dir']).expanduser().resolve()
    if not root.is_dir(): raise ValueError('Music Library Directory does not exist. Create it or choose an existing directory in Settings.')
    files=[]; errors=[]
    for p in root.rglob('*'):
        if p.is_file() and p.suffix.lower() in EXTENSIONS:
            try:
                m=read_tags(p)
                if m: files.append((str(p),m))
            except Exception as e: errors.append(f'{p.name}: {e}')
    with connect() as c:
        c.execute('DELETE FROM files')
        c.executemany('INSERT INTO files VALUES(?,?)',[(p,json.dumps(m)) for p,m in files])
        matched=0
        for r in c.execute('SELECT * FROM tracks').fetchall():
            path=match_file(json.loads(r['metadata']),files)
            if path:
                matched+=1
                if r['status'] not in ('skipped','downloading'):
                    c.execute("UPDATE tracks SET status='existing',output_file=?,error=NULL WHERE id=?",(path,r['id']))
            elif r['status'] in ('existing','completed') and (not r['output_file'] or not Path(r['output_file']).is_file()):
                c.execute("UPDATE tracks SET status='waiting',output_file=NULL WHERE id=?",(r['id'],))
    return dict(files=len(files),matched=matched,errors=errors)

def safe(s,normalize=False):
    s=re.sub(r'[\x00-\x1f/\\:*?"<>|]', '_', str(s or '')).strip(' .')
    if normalize: s=re.sub(r'\s+','_',s)
    return s[:180] or 'Unknown'

def destination(t,ext,s):
    values={k:safe(t.get(k,''),s['normalize_filenames']) for k in ('title','album_artist','album','track_number','disc_number','spotify_id')}
    values['artist']=safe((t.get('artists') or ['Unknown Artist'])[0],s['normalize_filenames'])
    values['album_artist']=safe(t.get('album_artist') or (t.get('artists') or ['Unknown Artist'])[0],s['normalize_filenames'])
    values['album']=safe(t.get('album') or 'Singles',s['normalize_filenames'])
    values['year']=safe(str(t.get('release_date',''))[:4]); values['ext']=ext
    values['track_number']=str(t.get('track_number') or 0).zfill(2)
    template=s['output_template']
    if not t.get('album') and template=='{album_artist}/{album}/{track_number} - {title}.{ext}': template='{album_artist}/Singles/{title}.{ext}'
    for _,field,spec,conversion in string.Formatter().parse(template):
        if field is not None and (field not in values or spec or conversion): raise ValueError('Use only the listed template variables without format modifiers')
    relative=template.format(**values)
    root=Path(s['library_dir']).expanduser().resolve(); dest=(root/relative).resolve()
    if not dest.is_relative_to(root) or dest==root: raise ValueError('Output template escapes the library directory')
    return dest

def artwork(url):
    if not url or not url.startswith('https://'): return None
    from PIL import Image
    import io
    with httpx.stream('GET',url,timeout=15,follow_redirects=True) as response:
        response.raise_for_status(); chunks=[]; size=0
        for chunk in response.iter_bytes():
            size+=len(chunk)
            if size>15_000_000: raise ValueError('Artwork exceeds 15 MB')
            chunks.append(chunk)
    im=Image.open(io.BytesIO(b''.join(chunks))).convert('RGB'); im.thumbnail((1600,1600)); output=io.BytesIO(); im.save(output,'JPEG',quality=92)
    return output.getvalue()

def tag(path,t,playlists,s):
    f=mutagen.File(path)
    if f is None: raise ValueError('Unsupported audio container for metadata')
    if f.tags is None: f.add_tags()
    warnings=[]; art=None
    if s['embed_artwork']:
        try: art=artwork(t.get('artwork',''))
        except Exception as exc:
            warnings.append('Artwork could not be embedded: '+str(exc))
            logging.getLogger('trackswipe.media').warning(warnings[-1])
    fields={'TITLE':t['title'],'ARTIST':t.get('artists',[]),'ALBUMARTIST':t.get('album_artist',''),'ALBUM':t.get('album',''),'TRACKNUMBER':t.get('track_number',''),'DISCNUMBER':t.get('disc_number',''),'DATE':t.get('release_date',''),'ISRC':t.get('isrc',''),'SPOTIFY_ID':t.get('spotify_id',''),'PLAYLISTS':playlists,'EXPLICIT':str(t.get('explicit')).lower() if t.get('explicit') is not None else ''}
    if isinstance(f,MP4):
        if s['embed_metadata']:
            for key,code in [('TITLE','\xa9nam'),('ARTIST','\xa9ART'),('ALBUMARTIST','aART'),('ALBUM','\xa9alb'),('DATE','\xa9day')]:
                v=fields[key]; f[code]=v if isinstance(v,list) else [str(v)]
            for key,code in [('TRACKNUMBER','trkn'),('DISCNUMBER','disk')]:
                try: f[code]=[(int(str(fields[key]).split('/')[0]),0)]
                except ValueError: pass
            for key in ('ISRC','SPOTIFY_ID','PLAYLISTS','EXPLICIT'):
                v=fields[key]; f['----:com.apple.iTunes:'+key]=[('; '.join(v) if isinstance(v,list) else str(v)).encode()]
            if t.get('explicit') is not None: f['rtng']=[1 if t['explicit'] else 2]
        if art: f['covr']=[MP4Cover(art,imageformat=MP4Cover.FORMAT_JPEG)]
    elif isinstance(f.tags,ID3):
        if s['embed_metadata']:
            for cls,key in [(TIT2,'TITLE'),(TPE1,'ARTIST'),(TPE2,'ALBUMARTIST'),(TALB,'ALBUM'),(TRCK,'TRACKNUMBER'),(TPOS,'DISCNUMBER'),(TDRC,'DATE'),(TSRC,'ISRC')]:
                f.tags.add(cls(encoding=3,text=fields[key] if isinstance(fields[key],list) else str(fields[key])))
            for key in ('SPOTIFY_ID','PLAYLISTS','EXPLICIT'): f.tags.add(TXXX(encoding=3,desc=key,text=fields[key]))
        if art: f.tags.add(APIC(encoding=3,mime='image/jpeg',type=3,desc='Cover',data=art))
    else:
        if s['embed_metadata']:
            for k,v in fields.items(): f[k]=[str(x) for x in v] if isinstance(v,list) else [str(v)]
        if art:
            p=Picture(); p.data=art; p.type=3; p.mime='image/jpeg'
            if hasattr(f,'add_picture'): f.clear_pictures(); f.add_picture(p)
            else: f['metadata_block_picture']=[base64.b64encode(p.write()).decode()]
    f.save()
    return warnings

class YtDlpDownloader:
    def download(self,video_id,folder,s):
        import yt_dlp
        fmt=s['audio_format']
        if fmt!='best' and not s['allow_conversion']:
            selector={'m4a':'bestaudio[ext=m4a]','opus':'bestaudio[acodec=opus]','mp3':'bestaudio[ext=mp3]'}[fmt]
        else: selector='bestaudio'
        opts={'js_runtimes':{'node':{}},'format':selector,'outtmpl':str(folder/'source.%(ext)s'),'noplaylist':True,'quiet':True,'socket_timeout':30,'retries':3,'keepvideo':s['keep_original'],'postprocessors':[{'key':'FFmpegExtractAudio','preferredcodec':fmt,'preferredquality':'0'}]}
        if fmt=='best': opts['postprocessors'][0]['preferredcodec']='best'
        if not s['allow_conversion'] and fmt!='best': opts['postprocessors']=[]
        opts.update(youtube.options(s))
        try:
            with yt_dlp.YoutubeDL(opts) as y: y.extract_info('https://www.youtube.com/watch?v='+video_id,download=True)
        except Exception as error:
            raise ValueError(youtube.friendly_error(error)) from error
        paths=[p for p in folder.iterdir() if p.suffix.lower() in EXTENSIONS]
        if fmt!='best': paths.sort(key=lambda p:p.suffix!='.'+fmt)
        if not paths: raise ValueError('No supported audio output produced')
        return paths[0]

def download_track(r):
    s=settings(); t=json.loads(r['metadata'])
    if not t.get('title') or not t.get('artists'): raise ValueError('Complete title and artist metadata before downloading')
    scan()
    with connect() as c:
        files=[(x['path'],json.loads(x['metadata'])) for x in c.execute('SELECT * FROM files') if Path(x['path']).is_file()]
        existing=match_file(t,files)
        if existing: return existing,True
        playlists=[x[0] for x in c.execute('SELECT name FROM playlists JOIN track_playlists ON id=playlist_id WHERE track_id=?',(r['id'],))]
    temp=Path(s['temp_dir']).expanduser(); temp.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=temp,prefix='trackswipe-') as folder:
        source=YtDlpDownloader().download(r['approved_video'],Path(folder),s)
        if s['keep_original']:
            originals=temp/'originals'; originals.mkdir(exist_ok=True)
            shutil.copy2(source,originals/(str(r['id'])+'-'+uuid.uuid4().hex+source.suffix))
        if s['embed_metadata'] or s['embed_artwork']:
            warnings=tag(source,t,playlists,s)
            with connect() as c:
                for warning in warnings: event(c,r['id'],'artwork-warning',warning)
        if s['replay_gain']: raise ValueError('ReplayGain is not available with this installation')
        dest=destination(t,source.suffix[1:],s); dest.parent.mkdir(parents=True,exist_ok=True)
        # Stage on the destination filesystem, then atomically link without replacing.
        staged=dest.parent/('.trackswipe-'+uuid.uuid4().hex+'.part')
        try:
            with staged.open('xb') as out,source.open('rb') as inp:
                shutil.copyfileobj(inp,out); out.flush(); os.fsync(out.fileno())
            os.link(staged,dest)  # Fails atomically if the final path already exists.
        finally:
            staged.unlink(missing_ok=True)
        with connect() as c: c.execute('INSERT OR REPLACE INTO files VALUES(?,?)',(str(dest),json.dumps(t)))
        return str(dest),False
