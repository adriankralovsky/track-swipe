import json
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from fastapi.testclient import TestClient
from backend import db, importer, spotify, playlists
from backend.main import app


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(db, 'DB', tmp_path / 'test.sqlite3')
    monkeypatch.setattr(db, 'DATA', tmp_path)
    monkeypatch.setitem(db.DEFAULTS, 'library_dir', str(tmp_path / 'music'))
    (tmp_path / 'music').mkdir()
    spotify._pending.clear()
    db.init()


def track(sid='A' * 22):
    return dict(type='track', id=sid, name='A song', artists=[{'name': 'Artist'}], duration_ms=222000,
                album={'name': 'Album', 'artists': [{'name': 'Album Artist'}], 'release_date': '2024', 'images': [{'url': 'https://example.org/art.jpg'}]},
                external_ids={'isrc': 'XX1234567890'}, explicit=False, track_number=3, disc_number=1)


def test_filename_spaces_explicit_names_and_reimport():
    csv = b'Track URI,Track Name,Artist Name(s)\nspotify:track:AAAAAAAAAAAAAAAAAAAAAA,A song,Artist\n'
    rows = importer.parse(csv, 'we_go_jim.csv')
    assert rows[0][1] == 'we go jim'
    importer.merge(rows)
    importer.merge(rows)
    with db.connect() as c:
        assert c.execute('SELECT count(*) FROM playlists').fetchone()[0] == 1
        assert c.execute('SELECT count(*) FROM track_playlists').fetchone()[0] == 1
    explicit = csv.replace(b'Artist Name(s)', b'Artist Name(s),Playlist Name').replace(b'A song,Artist', b'A song,Artist,intentional_name')
    assert importer.parse(explicit, 'ignored_name.csv')[0][1] == 'intentional_name'


def test_playlist_rename_preserves_export_path():
    importer.merge([(importer.normalize(track()), 'Liked_Songs')])
    playlists.sync()
    path = db.DATA / 'music/Playlists/Liked_Songs.m3u'
    with db.connect() as c: c.execute("UPDATE playlists SET name='Liked Songs'")
    playlists.sync()
    assert '#PLAYLIST:Liked Songs\n' in path.read_text()
    assert len(list(path.parent.glob('*.m3u'))) == 1


@pytest.mark.parametrize('value', ['http://open.spotify.com/playlist/'+'A'*22, 'https://evil.test/playlist/'+'A'*22, 'https://open.spotify.com/track/'+'A'*22, 'https://open.spotify.com.evil.test/playlist/'+'A'*22])
def test_url_rejects_untrusted_hosts_and_wrong_types(value):
    with pytest.raises(ValueError): spotify.playlist_id(value)


def test_playlist_pages_metadata_and_omissions(monkeypatch):
    calls = []
    def get(path, params=None):
        calls.append((path, params))
        if not path.endswith('/items'): return {'name': 'Gym time', 'snapshot_id': 'v1'}
        if params['offset'] == 0:
            return {'total': 4, 'items': [{'item': track()}, {'item': None}]}
        return {'total': 4, 'items': [{'track': track('B'*22)}, {'item': {'type': 'episode'}}]}
    monkeypatch.setattr(spotify, '_get', get)
    rows, details = spotify.fetch_playlist('https://open.spotify.com/playlist/'+'A'*22+'?si=share')
    assert len(rows) == 2 and details['omitted'] == 2
    m, name = rows[0]
    assert name == 'Gym time'
    assert m['duration'] == 222 and m['album_artist'] == 'Album Artist'
    assert m['isrc'] == 'XX1234567890' and m['track_number'] == 3
    assert [p['offset'] for path,p in calls if path.endswith('/items')] == [0,2]


def test_failed_second_page_does_not_partially_import(monkeypatch):
    def get(path, params=None):
        if not path.endswith('/items'): return {'name': 'Gym', 'snapshot_id': 'v1'}
        if params['offset'] == 0: return {'total': 2, 'items': [{'item': track()}]}
        raise ValueError('Spotify rate limit reached')
    monkeypatch.setattr(spotify, '_get', get)
    response = TestClient(app).post('/api/import-url', json={'url': 'spotify:playlist:'+'A'*22})
    assert response.status_code == 400
    with db.connect() as c: assert c.execute('SELECT count(*) FROM tracks').fetchone()[0] == 0


def test_changed_snapshot_aborts(monkeypatch):
    def get(path, params=None):
        if path.endswith('/items'): return {'total': 1, 'items': [{'item': track()}]}
        return {'name': 'Gym', 'snapshot_id': 'v2' if params else 'v1'}
    monkeypatch.setattr(spotify, '_get', get)
    with pytest.raises(ValueError, match='changed'): spotify.fetch_playlist('spotify:playlist:'+'A'*22)


def test_pkce_state_expiration_single_use_and_secret_storage(monkeypatch):
    url = spotify.authorize('a'*32, spotify.DEFAULT_REDIRECT)
    query = parse_qs(urlsplit(url).query)
    assert query['code_challenge_method'] == ['S256']
    assert 'playlist-modify' not in query['scope'][0]
    with pytest.raises(ValueError): spotify.callback('wrong', 'code')
    sent = []
    def token(data):
        sent.append(data)
        return {'access_token': 'secret-access', 'refresh_token': 'secret-refresh', 'expires_at': 9999999999}
    monkeypatch.setattr(spotify, '_token_request', token)
    spotify.callback(query['state'][0], 'code')
    assert sent[0]['code_verifier'] and sent[0]['grant_type'] == 'authorization_code'
    assert spotify.status()['connected']
    assert 'secret-' not in json.dumps(spotify.status())
    assert (db.DATA / 'spotify-connection.json').stat().st_mode & 0o777 == 0o600
    with pytest.raises(ValueError): spotify.callback(query['state'][0], 'code')
    backup = TestClient(app).get('/api/export/json').text
    assert 'secret-access' not in backup and 'secret-refresh' not in backup
    spotify.disconnect()
    assert not spotify.status()['connected']
    assert 'secret-' not in (db.DATA / 'spotify-connection.json').read_text()


def test_expired_oauth_request_does_not_exchange_token(monkeypatch):
    query = parse_qs(urlsplit(spotify.authorize('a'*32, spotify.DEFAULT_REDIRECT)).query)
    spotify._pending[query['state'][0]]['created'] -= 601
    with pytest.raises(ValueError, match='expired'): spotify.callback(query['state'][0], 'code')


def test_refresh_retains_old_refresh_token_when_not_rotated(monkeypatch):
    spotify._save(dict(client_id='a'*32, access_token='old', refresh_token='keep', expires_at=0))
    monkeypatch.setattr(spotify, '_token_request', lambda data: dict(access_token='new', expires_at=9999999999))
    assert spotify._access_token() == 'new'
    assert spotify._load()['refresh_token'] == 'keep'


def test_rate_limit_message(monkeypatch):
    monkeypatch.setattr(spotify, '_access_token', lambda **kwargs: 'token')
    monkeypatch.setattr(httpx, 'get', lambda *args, **kwargs: httpx.Response(429, headers={'Retry-After': '120'}))
    with pytest.raises(ValueError, match='120 seconds'): spotify._get('playlists/'+'A'*22)


def test_url_reimport_keeps_skips_and_one_membership(monkeypatch):
    rows = [(importer.normalize(track()), 'Gym time')]
    monkeypatch.setattr(spotify, 'fetch_playlist', lambda url: (rows, {'playlist': 'Gym time', 'omitted': 0, 'total': 1}))
    client = TestClient(app)
    first = client.post('/api/import-url', json={'url': 'spotify:playlist:'+'A'*22})
    assert first.status_code == 200, first.text
    assert first.json()['imported'] == 1
    with db.connect() as c: c.execute("UPDATE tracks SET status='skipped'")
    second = client.post('/api/import-url', json={'url': 'spotify:playlist:'+'A'*22})
    assert second.status_code == 200 and second.json()['merged'] == 1
    with db.connect() as c:
        assert c.execute('SELECT status FROM tracks').fetchone()[0] == 'skipped'
        assert c.execute('SELECT count(*) FROM track_playlists').fetchone()[0] == 1


def test_unauthorized_request_refreshes_once_without_sending_token_elsewhere(monkeypatch):
    tokens, urls = [], []
    def access(refresh=False):
        tokens.append(refresh)
        return 'new' if refresh else 'old'
    def get(url, **kwargs):
        urls.append(url)
        return httpx.Response(401) if len(urls) == 1 else httpx.Response(200, json={'name': 'Gym'})
    monkeypatch.setattr(spotify, '_access_token', access)
    monkeypatch.setattr(httpx, 'get', get)
    assert spotify._get('playlists/'+'A'*22)['name'] == 'Gym'
    assert tokens == [False, True]
    assert all(url.startswith('https://api.spotify.com/v1/') for url in urls)
