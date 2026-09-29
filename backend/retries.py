"""Persistent, bounded download retries without sleeping inside the worker."""
import json
import time
from . import db, youtube

DELAYS = (30, 120, 300)  # Three retries after the initial attempt.


def error_kind(error):
    text = youtube.clean_error(error).lower()
    if youtube.auth_required(error):
        return 'authentication'
    if any(word in text for word in ('429', 'too many requests', 'rate limit', 'rate-limit', 'try again later')):
        return 'rate_limit'
    if any(word in text for word in ('timed out', 'timeout', 'connection reset', 'connection refused',
                                    'connection aborted', 'remote end closed', 'temporary failure',
                                    'temporarily unavailable', 'network is unreachable', 'name resolution',
                                    'http error 403', 'http error 500', 'http error 502',
                                    'http error 503', 'http error 504', 'incomplete read', 'incompleteread')):
        return 'temporary'
    return 'permanent'


def reset(c, track_id):
    c.execute('DELETE FROM download_retries WHERE track_id=?', (track_id,))


def record_failure(track_id, error, now=None):
    now = time.time() if now is None else now
    kind = error_kind(error)
    message = youtube.friendly_error(error)
    with db.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        row = c.execute('SELECT retry_count FROM download_retries WHERE track_id=?', (track_id,)).fetchone()
        count = row['retry_count'] if row else 0
        if kind in ('rate_limit', 'temporary') and count < len(DELAYS):
            due = now + DELAYS[count]
            count += 1
            status = 'retrying'
            detail = f'Automatic retry {count}/{len(DELAYS)} in {DELAYS[count-1]}s. {message}'
        else:
            due = 0
            status = 'failed'
            detail = f'Automatic retries exhausted. {message}' if count == len(DELAYS) else message
        c.execute('INSERT OR REPLACE INTO download_retries VALUES(?,?,?,?)', (track_id, count, due, kind))
        c.execute('UPDATE tracks SET status=?,error=? WHERE id=?', (status, message, track_id))
        db.event(c, track_id, 'retry-scheduled' if status == 'retrying' else 'failed', detail)
    return status


def claim_next(now=None):
    now = time.time() if now is None else now
    with db.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        paused = c.execute("SELECT value FROM settings WHERE key='paused'").fetchone()
        if paused and json.loads(paused[0]):
            return None
        # A provider-wide rate limit should cool down the whole download worker.
        cooldown = c.execute("SELECT max(r.next_retry_at) FROM download_retries r JOIN tracks t ON t.id=r.track_id WHERE t.status='retrying' AND r.kind='rate_limit'").fetchone()[0]
        if cooldown and cooldown > now:
            return None
        row = c.execute("""SELECT t.* FROM tracks t LEFT JOIN download_retries r ON r.track_id=t.id
            WHERE t.approved_video IS NOT NULL AND
              (t.status='approved' OR (t.status='retrying' AND r.next_retry_at<=?))
            ORDER BY CASE WHEN t.status='retrying' THEN 0 ELSE 1 END, t.id LIMIT 1""", (now,)).fetchone()
        if not row:
            return None
        c.execute("UPDATE tracks SET status='downloading',error=NULL WHERE id=?", (row['id'],))
        db.event(c, row['id'], 'downloading')
        return dict(row)
