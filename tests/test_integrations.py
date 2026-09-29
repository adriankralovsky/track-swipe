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


def prepare_download():
    seed(status='approved')
    with db.connect() as c:
        c.execute('UPDATE tracks SET approved_video=?',('abcdefghijk',))


def test_three_retries_then_attention_without_hammering():
    from backend import retries
    prepare_download()
    now=1000
    assert retries.claim_next(now)['id']==1
    for count,delay in enumerate((30,120,300),1):
        assert retries.record_failure(1,ValueError('HTTP Error 429: Too Many Requests'),now)=='retrying'
        assert retries.claim_next(now+delay-1) is None
        with db.connect() as c:
            row=c.execute('SELECT * FROM download_retries').fetchone()
            assert row['retry_count']==count and row['next_retry_at']==now+delay
        now+=delay
        assert retries.claim_next(now)['id']==1
        assert retries.claim_next(now) is None  # Cannot claim an active job twice.
    assert retries.record_failure(1,'HTTP Error 429',now)=='failed'
    assert retries.claim_next(now+10000) is None
    row=TestClient(app).get('/api/tracks?view=queue').json()[0]
    assert row['status']=='failed' and row['retry_count']==3


@pytest.mark.parametrize('error',['Please sign in. Use --cookies for authentication.', 'No space left on device', 'Video unavailable', 'Permission denied'])
def test_non_transient_errors_need_attention_immediately(error):
    from backend import retries
    prepare_download();retries.claim_next(100)
    assert retries.record_failure(1,error,100)=='failed'
    assert retries.claim_next(1000) is None


def test_rate_limit_cools_down_entire_worker_and_respects_pause():
    from backend import retries
    prepare_download();retries.claim_next(100)
    importer.merge([(metadata(spotify_id='B'*22,title='Another'),'Gym')])
    with db.connect() as c:c.execute("UPDATE tracks SET status='approved',approved_video='secondvideo' WHERE id=2")
    retries.record_failure(1,'HTTP Error 429',100)
    assert retries.claim_next(101) is None
    configure(paused=True)
    assert retries.claim_next(150) is None
    configure(paused=False)
    assert retries.claim_next(150)['id']==1


def test_retry_schedule_survives_restart_and_manual_retry_resets_budget():
    from backend import retries
    prepare_download();retries.claim_next(100)
    retries.record_failure(1,'Connection reset by peer',100)
    db.init()
    assert retries.claim_next(129) is None
    assert retries.claim_next(130)['id']==1
    retries.record_failure(1,'Disk full',130)
    client=TestClient(app)
    assert client.post('/api/tracks/1/decision',json={'action':'retry'}).status_code==200
    assert client.get('/api/tracks').json()[0]['retry_count']==0
    assert retries.claim_next(131)['id']==1


def test_bulk_retry_only_failed_and_export_includes_schedule():
    from backend import retries
    prepare_download();retries.claim_next(100)
    retries.record_failure(1,'Connection timed out',100)
    client=TestClient(app)
    assert client.post('/api/downloads/retry-failed').json()['queued']==0
    exported=client.get('/api/export/json').json()
    assert exported['version']==2
    assert exported['tables']['download_retries'][0]['next_retry_at']==130
    with db.connect() as c:c.execute("UPDATE tracks SET status='failed'")
    assert client.post('/api/downloads/retry-failed').json()['queued']==1
    assert client.post('/api/downloads/retry-failed').json()['queued']==0
    assert client.get('/api/tracks').json()[0]['retry_count']==0


def test_schema_v1_migration_and_backup_restore(tmp_path):
    import sqlite3
    seed(status='skipped')
    legacy=tmp_path/'legacy.sqlite3'
    with db.connect() as source,sqlite3.connect(legacy) as dest:source.backup(dest)
    with sqlite3.connect(legacy) as c:
        c.execute('DROP TABLE download_retries')
        c.execute('PRAGMA user_version=1')
    configure(paused=True)
    client=TestClient(app)
    result=client.post('/api/restore',files={'file':('legacy.sqlite3',legacy.read_bytes(),'application/octet-stream')})
    assert result.status_code==200,result.text
    assert client.get('/api/tracks').json()[0]['status']=='skipped'
    with db.connect() as c:
        assert c.execute('PRAGMA user_version').fetchone()[0]==2
        assert c.execute('SELECT count(*) FROM download_retries').fetchone()[0]==0
        c.execute('DROP TABLE download_retries');c.execute('PRAGMA user_version=1')
    db.init()
    with db.connect() as c:
        assert c.execute('PRAGMA user_version').fetchone()[0]==2
        assert c.execute('SELECT status FROM tracks').fetchone()[0]=='skipped'


def test_retry_schedule_backup_restore(tmp_path):
    from backend import retries
    prepare_download();retries.claim_next(100)
    retries.record_failure(1,'HTTP Error 503',100)
    configure(paused=True)
    client=TestClient(app)
    backup=client.get('/api/export/database').content
    with db.connect() as c:retries.reset(c,1)
    response=client.post('/api/restore',files={'file':('backup.sqlite3',backup,'application/octet-stream')})
    assert response.status_code==200,response.text
    row=client.get('/api/tracks?view=queue').json()[0]
    assert row['retry_count']==1 and row['next_retry_at']==130 and row['status']=='retrying'
    assert retries.claim_next(500) is None  # Restore remains paused.
