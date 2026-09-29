"""Optional Spotify playlist import through the official API and PKCE authorization."""
import base64
import hashlib
import json
import os
import re
import secrets
import tempfile
import threading
import time
from urllib.parse import urlencode, urlsplit

import httpx
from . import db, importer

_lock = threading.RLock()
_pending = {}
CALLBACK = '/api/spotify/callback'
DEFAULT_REDIRECT = 'http://127.0.0.1:8765' + CALLBACK


def _load():
    path = db.DATA / 'spotify-connection.json'
    return json.loads(path.read_text()) if path.exists() else {}


def _save(value):
    fd, name = tempfile.mkstemp(prefix='.spotify-', dir=db.DATA)
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(value, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(name, db.DATA / 'spotify-connection.json')
    finally:
        if os.path.exists(name): os.unlink(name)


def status():
    with _lock:
        config = _load()
        return dict(client_id=config.get('client_id', ''), redirect_uri=config.get('redirect_uri', DEFAULT_REDIRECT), connected=bool(config.get('refresh_token')))


def authorize(client_id, redirect_uri):
    if not re.fullmatch(r'[a-fA-F0-9]{32}', client_id):
        raise ValueError('Enter the Client ID from your Spotify developer app (32 hexadecimal characters).')
    uri = urlsplit(redirect_uri)
    if (uri.path != CALLBACK or uri.query or uri.fragment or uri.username or uri.password
            or not uri.hostname or not (uri.scheme == 'https' or (uri.scheme == 'http' and uri.hostname in ('127.0.0.1', '::1')))):
        raise ValueError('Use an HTTPS callback, or http://127.0.0.1:8765/api/spotify/callback for a local install. Register that exact address in Spotify.')
    state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(64)
    with _lock:
        _pending.clear()
        _pending[state] = dict(client_id=client_id, redirect_uri=redirect_uri, verifier=verifier, created=time.time())
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
    return 'https://accounts.spotify.com/authorize?' + urlencode(dict(client_id=client_id, response_type='code', redirect_uri=redirect_uri, scope='playlist-read-private playlist-read-collaborative', state=state, code_challenge_method='S256', code_challenge=challenge))


def _token_request(data):
    try:
        response = httpx.post('https://accounts.spotify.com/api/token', data=data, timeout=30)
    except httpx.HTTPError:
        raise ValueError('Could not reach Spotify. Check your connection and try again.') from None
    if response.status_code != 200:
        raise ValueError('Spotify authorization expired or was refused. Connect Spotify again.')
    token = response.json()
    if not token.get('access_token'): raise ValueError('Spotify did not return an access token.')
    token['expires_at'] = time.time() + token.get('expires_in', 3600)
    return token


def callback(state, code, error=''):
    with _lock:
        pending = _pending.pop(state, None)
        if not pending or time.time() - pending['created'] > 600:
            raise ValueError('This Spotify connection request expired. Start again from Import.')
        if error or not code: raise ValueError('Spotify connection was cancelled. You can reconnect from Import.')
        token = _token_request(dict(grant_type='authorization_code', code=code, redirect_uri=pending['redirect_uri'], client_id=pending['client_id'], code_verifier=pending['verifier']))
        _save(dict(client_id=pending['client_id'], redirect_uri=pending['redirect_uri']) | token)


def disconnect():
    with _lock:
        config = _load()
        _save({k: config[k] for k in ('client_id', 'redirect_uri') if k in config})
        _pending.clear()


def _access_token(refresh=False):
    with _lock:
        config = _load()
        if not config.get('refresh_token'): raise ValueError('Connect Spotify in Import before importing a playlist URL.')
        if refresh or config.get('expires_at', 0) < time.time() + 60:
            token = _token_request(dict(grant_type='refresh_token', refresh_token=config['refresh_token'], client_id=config['client_id']))
            config.update(token)
            _save(config)
        return config['access_token']


def playlist_id(value):
    value = str(value).strip()
    match = re.fullmatch(r'spotify:playlist:([A-Za-z0-9]{22})', value)
    if match: return match[1]
    uri = urlsplit(value)
    if uri.scheme == 'https' and uri.netloc == 'open.spotify.com':
        match = re.fullmatch(r'/(?:intl-[a-zA-Z-]+/)?playlist/([A-Za-z0-9]{22})/?', uri.path)
        if match: return match[1]
    raise ValueError('Paste a full open.spotify.com/playlist/… URL or spotify:playlist:… URI. Short share links and track/album links are not playlist URLs.')


def _get(path, params=None):
    # Construct every URL ourselves; never forward authorization to a provider-supplied next URL.
    for attempt in range(2):
        token = _access_token(refresh=bool(attempt))
        try:
            response = httpx.get('https://api.spotify.com/v1/' + path, params=params, headers={'Authorization': 'Bearer ' + token}, timeout=30)
        except httpx.HTTPError:
            raise ValueError('Spotify request failed. Nothing was imported; please try again.') from None
        if response.status_code == 401 and attempt == 0: continue
        if response.status_code == 403:
            raise ValueError('Spotify denied access. Development apps can import playlists you own or collaborate on. Check your app access and account, or use a CSV export.')
        if response.status_code == 404: raise ValueError('Playlist not found or not accessible to your Spotify account.')
        if response.status_code == 429:
            delay = response.headers.get('Retry-After', 'a few')
            raise ValueError(f'Spotify rate limit reached. Retry in {delay} seconds; nothing was imported.')
        if response.status_code != 200: raise ValueError(f'Spotify returned HTTP {response.status_code}. Reconnect or try again later; nothing was imported.')
        return response.json()


def fetch_playlist(value):
    pid = playlist_id(value)
    info = _get('playlists/' + pid)
    name = info.get('name')
    if not isinstance(name, str) or not name.strip(): raise ValueError('Spotify returned a playlist without a name.')
    rows, omitted, offset, expected = [], 0, 0, None
    while True:
        page = _get(f'playlists/{pid}/items', {'limit': 50, 'offset': offset})
        items = page.get('items')
        total = page.get('total')
        if not isinstance(items, list) or not isinstance(total, int) or total < 0:
            raise ValueError('Spotify returned an incomplete playlist. Nothing was imported.')
        if expected is None: expected = total
        if total != expected: raise ValueError('The playlist changed during import. Try again to fetch a consistent copy.')
        for entry in items:
            track = (entry.get('item') or entry.get('track')) if isinstance(entry, dict) else None
            if not isinstance(track, dict) or track.get('type') != 'track' or track.get('is_local') or entry.get('is_local') or not importer.spotify_id(track.get('id')):
                omitted += 1
                continue
            rows.append((importer.normalize(track), name))
        offset += len(items)
        if offset >= expected: break
        if not items or offset > 100_000: raise ValueError('Spotify pagination was incomplete. Nothing was imported.')
    latest = _get('playlists/' + pid, {'fields': 'snapshot_id'})
    if info.get('snapshot_id') and latest.get('snapshot_id') != info['snapshot_id']:
        raise ValueError('The playlist changed during import. Try again to fetch a consistent copy.')
    return rows, dict(playlist=name, source_url='https://open.spotify.com/playlist/' + pid, omitted=omitted, total=expected)
