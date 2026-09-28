import csv, io, json, re, zipfile, hashlib
import httpx
from .db import connect, event

def norm(s):
    return re.sub(r'[^\w]+', ' ', str(s or '').casefold()).strip()

def spotify_id(s):
    m = re.search(r'(?:spotify:track:|open.spotify.com/track/)([A-Za-z0-9]{22})', str(s or ''))
    return m.group(1) if m else (s if re.fullmatch('[A-Za-z0-9]{22}',str(s or '')) else '')

def normalize(row):
    r = {re.sub(r'[^a-z0-9]','',k.lower()):v for k,v in row.items() if k}
    def get(*keys):
        return next((r[k] for k in keys if r.get(k) not in (None,'')), '')
    artists = get('artistnames','artists','artistname','artist','mastermetadataalbumartistname')
    if isinstance(artists,list): artists = [a.get('name','') if isinstance(a,dict) else str(a) for a in artists]
    else: artists = [x.strip() for x in re.split(r';',str(artists)) if x.strip()]
    dur = get('durationms','trackdurationms','duration','durationseconds')
    try:
        duration = float(dur or 0)
        if 'durationms' in r or 'trackdurationms' in r: duration /= 1000
    except (ValueError,TypeError):
        try: duration = sum(float(x)*60**i for i,x in enumerate(str(dur).split(':')[::-1]))
        except ValueError: duration = 0
    album = get('albumname','album','mastermetadataalbumalbumname')
    album_obj=album if isinstance(album,dict) else {}
    if album_obj: album=album_obj.get('name','')
    album_artists=album_obj.get('artists',[])
    album_artist=album_artists[0].get('name','') if album_artists else ''
    images=album_obj.get('images',[])
    image=images[0].get('url','') if images else ''
    return dict(spotify_id=spotify_id(get('trackuri','spotifytrackuri','spotifyid','uri','trackurl','url','id')), title=get('trackname','title','name','track','mastermetadatatrackname'), artists=artists, album=album, album_artist=get('albumartistname','albumartist') or album_artist or (artists[0] if artists else ''), track_number=get('tracknumber'), disc_number=get('discnumber'), release_date=get('albumreleasedate','releasedate','year') or album_obj.get('release_date',''), duration=duration, isrc=get('isrc') or (row.get('external_ids') or {}).get('isrc',''), explicit=(str(get('explicit')).lower() in ('true','1','yes')) if get('explicit')!='' else None, artwork=get('albumimageurl','artwork','imageurl','coverurl') or image)

def parse(data, name):
    results=[]
    if name.lower().endswith('.zip'):
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            if sum(i.file_size for i in z.infolist()) > 100_000_000: raise ValueError('Expanded ZIP exceeds 100 MB')
            for i in z.infolist():
                if i.filename.lower().endswith(('.json','.csv','.txt')):
                    results.extend(parse(z.read(i),i.filename))
        return results
    text=data.decode('utf-8-sig')
    source=name.rsplit('/',1)[-1].rsplit('.',1)[0]
    if name.lower().endswith('.json'):
        obj=json.loads(text)
        def walk(x, playlist=source):
            if isinstance(x,list):
                for v in x: walk(v,playlist)
            elif isinstance(x,dict):
                if 'playlists' in x: walk(x['playlists'],playlist)
                elif 'items' in x: walk(x['items'],x.get('name',playlist))
                elif isinstance(x.get('track'),dict): walk(x['track'],playlist)
                elif any(k in x for k in ('trackName','track','master_metadata_track_name','spotify_track_uri')) or (x.get('name') and (x.get('type')=='track' or spotify_id(x.get('uri')))):
                    results.append((normalize(x),playlist))
                elif 'tracks' in x: walk(x['tracks'],x.get('name',playlist))
        walk(obj)
    elif name.lower().endswith('.csv'):
        try: dialect=csv.Sniffer().sniff(text[:8192],delimiters=',;\t')
        except csv.Error: dialect=csv.excel
        for row in csv.DictReader(io.StringIO(text),dialect=dialect):
            results.append((normalize(row),row.get('Playlist Name') or row.get('Playlist') or source))
    else:
        for sid in re.findall(r'(?:spotify:track:|open.spotify.com/track/)([A-Za-z0-9]{22})',text):
            results.append((normalize({'spotifyid':sid}),source))
    return [(m,p) for m,p in results if m['title'] or m['spotify_id']]

def enrich(m):
    if m['title'] or not m['spotify_id']: return m
    # Public Spotify embed metadata supplies a title; artist/album may remain unresolved.
    try:
        r=httpx.get('https://open.spotify.com/oembed',params={'url':'https://open.spotify.com/track/'+m['spotify_id']},timeout=8)
        r.raise_for_status(); d=r.json(); m['title']=d.get('title',''); m['artwork']=d.get('thumbnail_url','')
    except Exception: pass
    return m

def merge(rows):
    added=0
    with connect() as c:
        for m, playlist in rows:
            identity='spotify:'+m['spotify_id'] if m['spotify_id'] else 'release:'+hashlib.sha256(json.dumps([norm(m['title']),[norm(a) for a in m['artists']],norm(m['album']),m['duration'],m['release_date']],sort_keys=True).encode()).hexdigest()
            old=c.execute('SELECT * FROM tracks WHERE identity=?',(identity,)).fetchone()
            if old:
                previous=json.loads(old['metadata']); previous.update({k:v for k,v in m.items() if v not in ('',None,[],0) or (k=='explicit' and v is not None)})
                c.execute('UPDATE tracks SET metadata=? WHERE id=?',(json.dumps(previous),old['id'])); tid=old['id']
            else:
                tid=c.execute('INSERT INTO tracks(identity,metadata) VALUES(?,?)',(identity,json.dumps(m))).lastrowid; added+=1
                event(c,tid,'imported',playlist)
            c.execute('INSERT OR IGNORE INTO playlists(name) VALUES(?)',(playlist,))
            c.execute('INSERT OR IGNORE INTO track_playlists VALUES(?,(SELECT id FROM playlists WHERE name=?))',(tid,playlist))
    return added
