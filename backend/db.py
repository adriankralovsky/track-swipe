import json, os, sqlite3, threading
from contextlib import contextmanager
from pathlib import Path

DATA = Path(os.getenv('TRACKSWIPE_DATA', './data')).resolve()
DATA.mkdir(parents=True, exist_ok=True)
DB = DATA / 'trackswipe.sqlite3'
LOCK = threading.RLock()
DEFAULTS = dict(library_dir=str(DATA / 'Music'), temp_dir=str(DATA / 'temporary'), import_dir='', output_template='{album_artist}/{album}/{track_number} - {title}.{ext}', audio_format='best', allow_conversion=True, embed_artwork=True, embed_metadata=True, normalize_filenames=False, keep_original=False, replay_gain=False, prefer_topic=True, prefer_music=True, penalize_video=True, max_duration_difference=15, candidate_count=12, auto_approve=False, auto_threshold=98, ignore_live=True, ignore_covers=True, ignore_remixes=True, ignore_speed=True, ignore_instrumental=True, show_existing=False, show_skipped=False, autoplay=False, volume=65, keyboard=True, animation_intensity=1, reduced_motion=False, paused=False)

@contextmanager
def connect():
    c = sqlite3.connect(DB, timeout=30)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    try:
        with c: yield c
    finally: c.close()

def init():
    with connect() as c:
        version=c.execute('PRAGMA user_version').fetchone()[0]
        if version not in (0,1): raise RuntimeError(f'Unsupported database version {version}')
        c.executescript('''
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS tracks(id INTEGER PRIMARY KEY, identity TEXT UNIQUE NOT NULL, metadata TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'waiting', approved_video TEXT, output_file TEXT, error TEXT, created TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS playlists(id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL);
        CREATE TABLE IF NOT EXISTS track_playlists(track_id INTEGER REFERENCES tracks(id) ON DELETE CASCADE, playlist_id INTEGER REFERENCES playlists(id) ON DELETE CASCADE, PRIMARY KEY(track_id,playlist_id));
        CREATE TABLE IF NOT EXISTS candidates(track_id INTEGER REFERENCES tracks(id) ON DELETE CASCADE, video_id TEXT, metadata TEXT NOT NULL, rejected INTEGER DEFAULT 0, PRIMARY KEY(track_id,video_id));
        CREATE TABLE IF NOT EXISTS files(path TEXT PRIMARY KEY, metadata TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, track_id INTEGER, action TEXT NOT NULL, detail TEXT, created TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        PRAGMA user_version=1;
        ''')
        c.execute("UPDATE tracks SET status='approved' WHERE status='downloading'")

def settings():
    with connect() as c:
        return DEFAULTS | {r['key']: json.loads(r['value']) for r in c.execute('SELECT * FROM settings')}

def event(c, tid, action, detail=''):
    c.execute('INSERT INTO events(track_id,action,detail) VALUES(?,?,?)', (tid,action,detail))

def track(r, c):
    d = dict(r); d['metadata'] = json.loads(d['metadata'])
    d['playlists'] = [x[0] for x in c.execute('SELECT name FROM playlists JOIN track_playlists ON playlists.id=playlist_id WHERE track_id=?', (d['id'],))]
    return d
