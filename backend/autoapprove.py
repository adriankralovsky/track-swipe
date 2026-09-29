"""Re-evaluate saved evidence, never approve rejected, skipped, or existing audio."""
import json
from pathlib import Path
from . import db, matcher


def apply(track_id=None):
    approved = 0
    with db.connect() as c:
        # Serialize decisions with manual actions, imports, and concurrent auto passes.
        c.execute('BEGIN IMMEDIATE')
        settings = db.DEFAULTS | {r['key']: json.loads(r['value']) for r in c.execute('SELECT * FROM settings')}
        if not settings['auto_approve'] or settings['paused']:
            return 0
        sql = "SELECT * FROM tracks WHERE status='waiting'"
        rows = c.execute(sql + (' AND id=?' if track_id is not None else ''), (track_id,) if track_id is not None else ()).fetchall()
        for track in rows:
            metadata = json.loads(track['metadata'])
            if not metadata.get('title') or not metadata.get('artists'):
                continue
            if track['output_file'] and Path(track['output_file']).is_file():
                continue
            candidates = []
            for row in c.execute('SELECT * FROM candidates WHERE track_id=? AND rejected=0', (track['id'],)).fetchall():
                candidate = matcher.score(metadata, json.loads(row['metadata']), settings)
                c.execute('UPDATE candidates SET metadata=? WHERE track_id=? AND video_id=?',
                          (json.dumps(candidate), track['id'], row['video_id']))
                candidates.append(candidate)
            # Find the best ELIGIBLE result, not just the first result returned by a provider.
            eligible = [r for r in candidates if r['auto_eligible'] and r['confidence'] >= settings['auto_threshold']]
            if not eligible:
                continue
            best = max(eligible, key=lambda r: r['confidence'])
            c.execute("UPDATE tracks SET status='approved',approved_video=?,error=NULL WHERE id=? AND status='waiting'",
                      (best['video_id'], track['id']))
            db.event(c, track['id'], 'auto-approved', f"{best['video_id']} · {best['confidence']}%")
            approved += 1
    return approved
