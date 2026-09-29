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

## Auto-pick, playlists, and authentication

`autoapprove.py` transactionally re-scores non-rejected saved candidates for waiting tracks using the current settings. It runs after searches/settings changes and before the worker takes another download. The UI polls while auto-pick is enabled. Eligibility treats Topic channels and structured Music results as alternative source evidence; blocking reasons are exposed separately from numeric confidence.

`playlists.py` emits managed UTF-8 M3U files under the music root. Relative paths allow different container mounts; atomic updates preserve unchanged mtimes. Existing audio is referenced once per playlist, with no copied audio. Import/rescan/download/decision hooks trigger synchronization; failures go to history rather than marking successful audio as failed.

`youtube.py` supplies a shared yt-dlp configuration to matching, manual inspection, and downloads. Browser extraction or cookie-file access is explicit configuration, off by default. Cookie contents never enter SQLite or exports. UI errors strip ANSI escape sequences and explain the authentication recovery path.

## Download retry migration (version 2)

`download_retries` stores the per-track retry count, next eligible attempt timestamp, and error category. Existing version 1 databases migrate additively; backup restore still accepts version 1. The `retrying` track state stays visible in Queue. `retries.py` claims due jobs transactionally, honors pause, and applies a provider-wide cooldown on rate-limit failures. Temporary errors get three additional attempts (30/120/300 seconds); permanent/authentication errors and exhausted retries stay failed. Manual retry resets the budget; successful downloads clear it. Retry state is included in SQLite and JSON exports.

## Spotify URL imports and playlist display names

`spotify.py` owns optional official Spotify API access. Authorization uses PKCE, read-only playlist scopes, expiring single-use state, and an atomic owner-only token file outside the exported database. The browser receives connection status and the public Client ID, never access or refresh tokens. Tokens refresh on expiry or one unauthorized response. API URLs are constructed locally so pagination cannot forward credentials to another host.

URL imports fetch all item pages and compare playlist snapshots before merging anything. A failed or changing playlist leaves the library untouched. File and URL imports share the same merge/scan/export pipeline. Filename-derived playlist names replace underscores with spaces; explicit CSV/JSON/API names are preserved. Managed M3U headers contain playlist IDs so renaming a database playlist preserves its export path and avoids duplicate server imports. Existing server display names are independent of those files.
