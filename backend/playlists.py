"""Portable UTF-8 extended M3U playlists, auto-importable by Navidrome."""
import json
import logging
import os
import tempfile
import threading
from pathlib import Path
from . import db
from .media import safe

_lock = threading.Lock()
MARKER = '#TRACKSWIPE:managed-v1'


def line(value):
    return str(value).replace('\r', ' ').replace('\n', ' ')


def directory(settings):
    root = Path(settings['library_dir']).expanduser().resolve()
    target = (root / settings.get('playlist_directory', 'Playlists')).resolve()
    if not target.is_relative_to(root) or target == root:
        raise ValueError('Playlist directory must be a subdirectory of the music library')
    return root, target


def sync(force=False):
    with _lock:
        settings = db.settings()
        if not force and not settings.get('playlist_auto_export', True):
            return {'written': 0, 'unchanged': 0, 'tracks': 0, 'omitted': 0, 'disabled': True}
        root, target = directory(settings)
        target.mkdir(parents=True, exist_ok=True)
        result = {'written': 0, 'unchanged': 0, 'tracks': 0, 'omitted': 0, 'directory': str(target)}
        with db.connect() as c:
            entries=c.execute('SELECT * FROM playlists ORDER BY id').fetchall()
            names=[safe(p['name']).casefold() for p in entries]
            for playlist in entries:
                name=safe(playlist['name'])
                if names.count(name.casefold())>1: name+=f" [ts-{playlist['id']}]"
                dest=target/(name+'.m3u')
                lines = ['#EXTM3U', MARKER, '#PLAYLIST:' + line(playlist['name'])]
                seen = set()
                rows = c.execute('SELECT t.* FROM tracks t JOIN track_playlists tp ON tp.track_id=t.id WHERE tp.playlist_id=? ORDER BY tp.rowid', (playlist['id'],)).fetchall()
                for row in rows:
                    path = Path(row['output_file']).resolve() if row['output_file'] else None
                    if row['status'] == 'skipped' or not path or not path.is_file() or not path.is_relative_to(root):
                        result['omitted'] += 1
                        continue
                    if path in seen:
                        continue
                    relative = os.path.relpath(path, target).replace(os.sep, '/')
                    if '\n' in relative or '\r' in relative:
                        result['omitted'] += 1
                        continue
                    seen.add(path)
                    metadata = json.loads(row['metadata'])
                    label = ', '.join(metadata.get('artists', [])) + ' - ' + metadata.get('title', path.stem)
                    lines += [f"#EXTINF:{round(float(metadata.get('duration') or -1))},{line(label)}", relative]
                    result['tracks'] += 1
                content = '\n'.join(lines) + '\n'
                if dest.exists():
                    previous = dest.read_text(encoding='utf-8')
                    if MARKER not in previous.splitlines():
                        raise ValueError(f'Refusing to replace an unmanaged playlist: {dest.name}')
                    if previous == content:
                        result['unchanged'] += 1
                        continue
                fd, temporary = tempfile.mkstemp(prefix='.trackswipe-', suffix='.tmp', dir=target)
                try:
                    with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as output:
                        output.write(content); output.flush(); os.fsync(output.fileno())
                    os.chmod(temporary,0o644)  # Readable by a music server with a different container UID.
                    os.replace(temporary, dest)
                finally:
                    Path(temporary).unlink(missing_ok=True)
                result['written'] += 1
        return result


def sync_safely():
    try:
        return sync()
    except Exception as error:
        logging.getLogger('trackswipe.playlists').exception('Playlist export failed')
        with db.connect() as c:
            db.event(c, None, 'playlist-export-failed', str(error))
        return {'error': str(error)}
