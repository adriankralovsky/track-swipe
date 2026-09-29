import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from backend import db, importer, matcher, autoapprove, playlists, youtube
from backend.main import app


@pytest.fixture(autouse=True)
def isolated(tmp_path,monkeypatch):
    monkeypatch.setattr(db,'DB',tmp_path/'test.sqlite3')
    monkeypatch.setattr(db,'DATA',tmp_path)
    monkeypatch.setitem(db.DEFAULTS,'library_dir',str(tmp_path/'music'))
    monkeypatch.setitem(db.DEFAULTS,'temp_dir',str(tmp_path/'temporary'))
    (tmp_path/'music').mkdir()
    db.init()


def metadata(**overrides):
    return dict(title='Song',artists=['Artist'],album='Album',album_artist='Artist',spotify_id='A'*22,isrc='',duration=222,artwork='',track_number=1,disc_number=1,release_date='2020',explicit=False)|overrides


def candidate(**overrides):
    return dict(video_id='abcdefghijk',title='Song',artists=['Artist'],album='Album',channel='Artist',duration=223,music=True)|overrides


def seed(status='waiting',rejected=False,**overrides):
    importer.merge([(metadata(),'Gym')])
    with db.connect() as c:
        c.execute('UPDATE tracks SET status=?',(status,))
        c.execute('INSERT INTO candidates VALUES(?,?,?,?)',(1,'abcdefghijk',json.dumps(candidate(**overrides)),int(rejected)))


def configure(**values):
    with db.connect() as c:
        for k,v in values.items():c.execute('INSERT OR REPLACE INTO settings VALUES(?,?)',(k,json.dumps(v)))


def test_music_artist_without_topic_can_auto_approve():
    scored=matcher.score(metadata(),candidate(),db.DEFAULTS)
    assert scored['confidence']>=98
    assert scored['auto_eligible'] and not scored['auto_blockers']


def test_topic_without_music_provider_can_auto_approve():
    scored=matcher.score(metadata(),candidate(channel='Artist - Topic',music=False),db.DEFAULTS)
    assert scored['auto_eligible']


@pytest.mark.parametrize('changes,reason',[
    ({'duration':0},'duration'),({'duration':227},'duration'),
    ({'title':'Song live'},'title'),({'artists':['Other'],'channel':'Other'},'artist'),
    ({'music':False,'channel':'Uploader'},'source')])
def test_auto_blockers_explain_unsafe_matches(changes,reason):
    scored=matcher.score(metadata(),candidate(**changes),db.DEFAULTS)
    assert not scored['auto_eligible']
    assert reason in ' '.join(scored['auto_blockers']).lower()


def test_saved_candidates_rechecked_when_mode_enabled():
    seed()
    client=TestClient(app)
    response=client.put('/api/settings',json={'auto_approve':True,'auto_threshold':98})
    assert response.status_code==200,response.text
    assert client.get('/api/tracks').json()[0]['status']=='approved'
    assert autoapprove.apply()==0
    with db.connect() as c: assert c.execute("SELECT count(*) FROM events WHERE action='auto-approved'").fetchone()[0]==1


def test_threshold_inclusive_and_rechecked_after_lowering():
    seed(album='Different')  # 98 rather than 100.
    configure(auto_approve=True,auto_threshold=99)
    assert autoapprove.apply()==0
    client=TestClient(app)
    assert client.put('/api/settings',json={'auto_threshold':98}).status_code==200
    assert client.get('/api/tracks').json()[0]['status']=='approved'


@pytest.mark.parametrize('status,rejected,paused',[('skipped',False,False),('waiting',True,False),('existing',False,False),('failed',False,False),('waiting',False,True)])
def test_auto_preserves_manual_decisions_and_pause(status,rejected,paused):
    seed(status,rejected)
    configure(auto_approve=True,paused=paused)
    assert autoapprove.apply()==0
    with db.connect() as c: assert c.execute('SELECT status FROM tracks').fetchone()[0]==status


def test_unpause_rechecks_saved_candidates():
    seed();configure(auto_approve=True,paused=True)
    client=TestClient(app)
    assert client.put('/api/settings',json={'paused':False}).status_code==200
    assert client.get('/api/tracks').json()[0]['status']=='approved'


def test_m3u_relative_unicode_no_duplicate_files(tmp_path):
    root=Path(db.DEFAULTS['library_dir'])
    audio=root/'Český interpret'/'Album'/'01 - Píseň.opus'
    audio.parent.mkdir(parents=True);audio.write_bytes(b'audio')
    importer.merge([(metadata(title='Píseň'),'Gym'),(metadata(title='Píseň'),'České')])
    with db.connect() as c:c.execute("UPDATE tracks SET status='existing',output_file=?",(str(audio),))
    result=playlists.sync()
    assert result['written']==2 and result['tracks']==2
    for path in (root/'Playlists').glob('*.m3u'):
        text=path.read_text(encoding='utf-8')
        relative=[line for line in text.splitlines() if not line.startswith('#')][0]
        assert (path.parent/relative).resolve()==audio
        assert str(root) not in text and 'Píseň' in text
    assert playlists.sync()['unchanged']==2
    audio.unlink()
    assert playlists.sync()['tracks']==0
    assert '#EXTINF' not in (root/'Playlists'/'Gym.m3u').read_text()


def test_playlist_name_collision_and_unmanaged_protection(tmp_path):
    importer.merge([(metadata(),'A/B'),(metadata(),'A:B')])
    assert playlists.sync()['written']==2
    assert len(list((Path(db.DEFAULTS['library_dir'])/'Playlists').glob('*.m3u')))==2
    importer.merge([(metadata(),'User')])
    path=Path(db.DEFAULTS['library_dir'])/'Playlists'/'User.m3u'
    path.write_text('#EXTM3U\nmy-own-song.mp3\n')
    with pytest.raises(ValueError,match='unmanaged'):playlists.sync()
    assert 'my-own-song' in path.read_text()


def test_playlist_directory_escape_rejected():
    configure(playlist_directory='../outside')
    with pytest.raises(ValueError):playlists.sync()


def test_authentication_options_no_secret_content(tmp_path):
    cookie=tmp_path/'cookies.txt';cookie.write_text('# Netscape HTTP Cookie File\n')
    options=youtube.options(db.DEFAULTS|{'youtube_auth':'file','youtube_cookies_file':str(cookie)})
    assert options['cookiefile']==str(cookie) and options['nocolor'] is True
    assert 'cookiesfrombrowser' not in options
    options=youtube.options(db.DEFAULTS|{'youtube_auth':'browser','youtube_browser':'firefox','youtube_browser_profile':'personal'})
    assert options['cookiesfrombrowser']==('firefox','personal',None,None)
    assert 'cookiefile' not in options


def test_missing_cookie_file_actionable():
    with pytest.raises(ValueError,match='cookies file not found'):
        youtube.options(db.DEFAULTS|{'youtube_auth':'file','youtube_cookies_file':'/does-not-exist'})


def test_ansi_stripped_and_only_auth_failures_retried():
    seed(status='failed')
    error='\x1b[0;31mERROR:\x1b[0m Please sign in. Use --cookies for authentication.'
    with db.connect() as c:c.execute('UPDATE tracks SET error=?,approved_video=?',(error,'abcdefghijk'))
    cleaned=youtube.friendly_error(error)
    assert '\x1b' not in cleaned and 'Settings → Audio' in cleaned
    assert '␛' not in youtube.clean_error('␛[0;31mERROR:␛[0m Test')
    client=TestClient(app)
    assert client.post('/api/downloads/retry-auth').json()['queued']==1
    with db.connect() as c:c.execute("UPDATE tracks SET status='failed',error='Disk full'")
    assert client.post('/api/downloads/retry-auth').json()['queued']==0
