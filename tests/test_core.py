import io, json, zipfile
from pathlib import Path
import pytest
from backend import db, importer, matcher, media

@pytest.fixture(autouse=True)
def isolated_db(tmp_path,monkeypatch):
    monkeypatch.setattr(db,'DB',tmp_path/'test.sqlite3'); monkeypatch.setattr(db,'DATA',tmp_path)
    monkeypatch.setitem(db.DEFAULTS,'library_dir',str(tmp_path/'music'))
    monkeypatch.setitem(db.DEFAULTS,'temp_dir',str(tmp_path/'temporary'))
    (tmp_path/'music').mkdir()
    db.init()
    return tmp_path

def target(**kwargs):
    return dict(title='Neviditelnej',artists=['Viktor Sheen','Calin','Kontrafakt'],album='Album',album_artist='Viktor Sheen',duration=222,isrc='CZ1234567890',spotify_id='A'*22,track_number=1,disc_number=1,release_date='2023',explicit=True,artwork='')|kwargs

def candidate(**kwargs):
    return dict(video_id='abcdefghijk',title='Neviditelnej',artists=['Viktor Sheen','Calin','Kontrafakt'],channel='Viktor Sheen - Topic',duration=223,music=True,album='Album')|kwargs

def test_topic_beats_video_and_cover():
    s=db.DEFAULTS
    clean=matcher.score(target(),candidate(),s)
    video=matcher.score(target(),candidate(title='Viktor Sheen - Neviditelnej (Official Video)',duration=300,channel='Viktor Sheen',music=False),s)
    cover=matcher.score(target(),candidate(title='Neviditelnej piano cover',channel='Random Piano',artists=[],music=False),s)
    assert clean['confidence']>=98 and clean['auto_eligible']
    assert clean['confidence']>video['confidence']
    assert cover['confidence']<30

def test_missing_duration_never_auto_approves():
    assert not matcher.score(target(),candidate(duration=0),db.DEFAULTS)['auto_eligible']

def test_requested_remix_not_penalized():
    r=matcher.score(target(title='Song Remix'),candidate(title='Song Remix'),db.DEFAULTS)
    assert any(x['label']=='No unexpected version keywords' and x['ok'] for x in r['reasons'])

def test_import_merge_preserves_skip_and_playlists():
    importer.merge([(target(),'Rap')])
    with db.connect() as c: c.execute("UPDATE tracks SET status='skipped'")
    assert importer.merge([(target(),'Gym'),(target(),'Favorites')])==0
    with db.connect() as c:
        assert c.execute('SELECT count(*) FROM tracks').fetchone()[0]==1
        assert c.execute('SELECT status FROM tracks').fetchone()[0]=='skipped'
        assert c.execute('SELECT count(*) FROM track_playlists').fetchone()[0]==3

def test_versions_not_merged():
    importer.merge([(target(spotify_id=''),'A'),(target(spotify_id='',title='Neviditelnej Remix'),'A')])
    with db.connect() as c: assert c.execute('SELECT count(*) FROM tracks').fetchone()[0]==2

def test_exportify_csv():
    data=b'Track URI,Track Name,Artist Name(s),Album Name,Duration (ms),ISRC\nspotify:track:AAAAAAAAAAAAAAAAAAAAAA,Song,Artist;Guest,Album,222000,CZ123\n'
    rows=importer.parse(data,'Gym.csv'); m,p=rows[0]
    assert m['duration']==222 and m['artists']==['Artist','Guest'] and p=='Gym'

def test_spotify_zip_playlists():
    data={'playlists':[{'name':'Gym','items':[{'track':{'trackName':'Song','artistName':'Artist','albumName':'Album','trackUri':'spotify:track:'+'A'*22}}]}]}
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w') as z: z.writestr('Playlist1.json',json.dumps(data))
    rows=importer.parse(out.getvalue(),'account.zip')
    assert rows[0][1]=='Gym' and rows[0][0]['title']=='Song'

def test_unicode_and_paths(tmp_path):
    s=db.DEFAULTS|{'library_dir':str(tmp_path)}
    p=media.destination(target(title='Příliš / krásná',album_artist='Viktor Sheen / Calin'),'m4a',s)
    assert p.is_relative_to(tmp_path) and 'Příliš' in str(p) and 'Viktor Sheen _ Calin' in str(p)
    with pytest.raises(ValueError): media.destination(target(),'mp3',s|{'output_template':'../{title}.{ext}'})

def test_existing_identifier_priority():
    t=target(); files=[('/wrong',target(isrc='WRONG',spotify_id='WRONG',title='Other')),('/right',target(title='Incomplete'))]
    assert media.match_file(t,files)=='/right'

def test_untagged_filename_not_fuzzy():
    assert media.match_file(target(),[('/songs/unrelated piano.mp3',{'title':'','artists':[]})]) is None

def test_api_rejection_and_restore():
    from fastapi.testclient import TestClient
    from backend.main import app
    # Do not start the downloader for isolated API decision tests.
    client=TestClient(app)
    importer.merge([(target(),'Gym')])
    with db.connect() as c:
        c.execute('INSERT INTO candidates VALUES(?,?,?,0)',(1,'abcdefghijk',json.dumps(candidate())))
    assert client.post('/api/tracks/1/decision',json={'action':'reject','video_id':'abcdefghijk'}).status_code==200
    assert client.get('/api/tracks').json()[0]['status']=='waiting'
    assert client.get('/api/tracks/1/candidates').json()[0]['rejected']
    client.post('/api/tracks/1/decision',json={'action':'skip'})
    importer.merge([(target(),'Other')])
    assert client.get('/api/tracks?view=review').json()==[]
    client.post('/api/tracks/1/decision',json={'action':'restore'})
    assert len(client.get('/api/tracks?view=review').json())==1

def test_cross_origin_write_blocked():
    from fastapi.testclient import TestClient
    from backend.main import app
    client=TestClient(app)
    assert client.put('/api/settings',json={'paused':False},headers={'origin':'https://evil.example'}).status_code==403

@pytest.mark.parametrize('ext,codec',[('mp3','libmp3lame'),('m4a','aac'),('opus','libopus'),('flac','flac')])
def test_real_audio_tagging_roundtrip(tmp_path,ext,codec):
    import subprocess
    path=tmp_path/('track.'+ext)
    subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-f','lavfi','-i','sine=frequency=440:duration=0.2','-c:a',codec,str(path)],check=True)
    t=target(title='Příliš krásná',artists=['Viktor Sheen','Calin'])
    media.tag(path,t,['Gym','Favorites'],db.DEFAULTS|{'embed_artwork':False})
    m=media.read_tags(path)
    assert m['title']==t['title'] and m['album']==t['album']
    assert m['isrc']==t['isrc'] and m['spotify_id']==t['spotify_id']
    assert m['artists']==t['artists']

def test_backup_restore_preserves_decisions(tmp_path):
    from fastapi.testclient import TestClient
    from backend.main import app
    client=TestClient(app)
    importer.merge([(target(),'Gym')])
    client.post('/api/tracks/1/decision',json={'action':'skip'})
    with db.connect() as c: c.execute("INSERT INTO settings VALUES('paused','true')")
    backup=client.get('/api/export/database')
    assert backup.status_code==200
    client.post('/api/tracks/1/decision',json={'action':'restore'})
    restored=client.post('/api/restore',files={'file':('backup.sqlite3',backup.content,'application/octet-stream')})
    assert restored.status_code==200,restored.text
    assert client.get('/api/tracks').json()[0]['status']=='skipped'
    assert client.get('/api/settings').json()['paused'] is True
    assert Path(restored.json()['safety_backup']).is_file()
    exported=client.get('/api/export/json').json()
    assert exported['tables']['track_playlists']==[{'track_id':1,'playlist_id':1}]

def test_invalid_backup_does_not_mutate_state():
    from fastapi.testclient import TestClient
    from backend.main import app
    client=TestClient(app)
    importer.merge([(target(),'Gym')])
    with db.connect() as c: c.execute("INSERT INTO settings VALUES('paused','true')")
    r=client.post('/api/restore',files={'file':('backup.sqlite3',b'not sqlite','application/octet-stream')})
    assert r.status_code==400
    assert len(client.get('/api/tracks').json())==1

def test_atomic_download_collision_preserves_existing(tmp_path,monkeypatch):
    import subprocess
    library=tmp_path/'music'; library.mkdir(exist_ok=True)
    s=db.DEFAULTS|{'library_dir':str(library),'temp_dir':str(tmp_path/'temp'),'embed_artwork':False}
    with db.connect() as c:
        for k,v in s.items(): c.execute('INSERT INTO settings VALUES(?,?)',(k,json.dumps(v)))
    t=target(); dest=media.destination(t,'mp3',s); dest.parent.mkdir(parents=True); dest.write_bytes(b'preserve existing bytes')
    def fake_download(self,vid,folder,settings):
        path=folder/'source.mp3'
        subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-f','lavfi','-i','sine=frequency=440:duration=0.2',str(path)],check=True)
        return path
    monkeypatch.setattr(media.YtDlpDownloader,'download',fake_download)
    with pytest.raises(FileExistsError): media.download_track({'id':1,'metadata':json.dumps(t),'approved_video':'abcdefghijk'})
    assert dest.read_bytes()==b'preserve existing bytes'
    assert list(dest.parent.glob('.trackswipe-*.part'))==[]

def test_rescan_skips_existing_and_recovers_removed_file(tmp_path):
    import subprocess
    library=tmp_path/'music'; library.mkdir(exist_ok=True)
    with db.connect() as c: c.execute('INSERT INTO settings VALUES(?,?)',('library_dir',json.dumps(str(library))))
    importer.merge([(target(),'Gym')])
    file=library/'song.mp3'
    subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-f','lavfi','-i','sine=frequency=440:duration=0.2',str(file)],check=True)
    media.tag(file,target(),['Gym'],db.DEFAULTS|{'embed_artwork':False})
    assert media.scan()['matched']==1
    with db.connect() as c: assert c.execute('SELECT status FROM tracks').fetchone()[0]=='existing'
    file.unlink()
    assert media.scan()['matched']==0
    with db.connect() as c: assert c.execute('SELECT status FROM tracks').fetchone()[0]=='waiting'

def test_spotify_api_json_metadata():
    row={'type':'track','name':'Song','uri':'spotify:track:'+'B'*22,'artists':[{'name':'Artist'}],'album':{'name':'Album','artists':[{'name':'Album Artist'}],'release_date':'2020-01-01','images':[{'url':'https://example.com/cover.jpg'}]},'duration_ms':123000,'external_ids':{'isrc':'ABC123'},'explicit':False}
    rows=importer.parse(json.dumps({'name':'Favorites','tracks':{'items':[{'track':row}]}}).encode(),'playlist.json')
    m,p=rows[0]
    assert p=='Favorites' and m['duration']==123 and m['album_artist']=='Album Artist'
    assert m['isrc']=='ABC123' and m['explicit'] is False and m['artwork']

def test_conflicting_isrc_not_matched_by_title():
    assert media.match_file(target(),[('/different',target(isrc='Different',spotify_id='Different'))]) is None

def test_full_staged_download_without_network(tmp_path,monkeypatch):
    import subprocess
    root=tmp_path/'library'; root.mkdir()
    s=db.DEFAULTS|{'library_dir':str(root),'temp_dir':str(tmp_path/'temporary'),'embed_artwork':False}
    with db.connect() as c:
        for k,v in s.items(): c.execute('INSERT INTO settings VALUES(?,?)',(k,json.dumps(v)))
    importer.merge([(target(),'Gym')])
    def source(self,video,folder,settings):
        output=folder/'source.m4a'
        subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-f','lavfi','-i','sine=frequency=440:duration=0.2','-c:a','aac',str(output)],check=True)
        return output
    monkeypatch.setattr(media.YtDlpDownloader,'download',source)
    row={'id':1,'metadata':json.dumps(target()),'approved_video':'abcdefghijk'}
    path,existing=media.download_track(row)
    assert not existing and Path(path).is_file()
    assert media.read_tags(path)['spotify_id']==target()['spotify_id']
    second,existing=media.download_track(row)
    assert existing and second==path
    assert len(list(root.rglob('*.m4a')))==1
