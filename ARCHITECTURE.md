# TrackSwipe architecture

A single local FastAPI service owns SQLite and filesystem access. React/Vite serves the review experience, with production assets served by FastAPI. Bind to loopback; this is a personal tool, not a multi-user public service.

## Durable schema (migration 1)
- tracks: canonical Spotify/export metadata JSON, identity key, review/download state, approved video, output path, error.
- playlists + track_playlists: many-to-many membership, never duplicate audio for playlists.
- candidates: per-track video ID, provider metadata, scored explanation, persistent rejected flag.
- files: scanned filesystem metadata and identifiers.
- events: append-only decisions and download history.
- settings: persisted validated configuration.

Imports merge Spotify IDs first, then exact release metadata (not fuzzy titles). Scans reconcile existing files before review. A rejection affects only a candidate; skip affects the durable track. Approval and its event are transactional. A single resumable worker downloads approved tracks, stages audio, tags from canonical metadata, and publishes without overwriting. Interrupted downloads return to approved on restart.

Search adapters use YouTube Music song metadata and yt-dlp YouTube fallback. Ranking is deterministic and explainable; suspicious versions and duration mismatches reduce confidence. Auto-approval requires strict metadata evidence, not just a high numeric score. Preview uses the visible official YouTube iframe player, never extracted preview streams.

Backups use SQLite's online backup API. Restore validates schema/integrity before replacing data, with a pre-restore snapshot. JSON exports include all durable tables. Download implementation, tagging, import parsing, matching, and persistence remain separate modules.
