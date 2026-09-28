# TrackSwipe

**Your music. The right version.** A local-first Spotify-export library with a swipe review room, ranked YouTube / YouTube Music matches, persistent decisions, tagged audio downloads, and playlist browsing.

## Run locally on Fedora

Requires Python 3.11+, Node 22+, and ffmpeg on PATH. Install Python, Node/npm, and ffmpeg using your Fedora package configuration (ffmpeg availability depends on enabled repositories).

```bash
./dev.sh
```

Open **http://127.0.0.1:5173**. The API runs at port 8765. The first launch installs Python and JavaScript dependencies. Internet access is needed for dependencies, searches, artwork, and YouTube playback/downloads; the library and decisions remain local.

For a single production service:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
npm ci --prefix frontend
npm run build --prefix frontend
.venv/bin/uvicorn backend.main:app --host 127.0.0.1 --port 8765
```

Open **http://127.0.0.1:8765**. Do not expose this personal filesystem tool to the public internet. No user accounts or remote authentication are included. Requests reject foreign browser origins.

## Docker Compose

```bash
docker compose up --build -d
```

Open **http://127.0.0.1:8765**. State and music persist in `./data`. The Fedora SELinux volume uses `:Z`. To use `/hdd/Music`, add the commented `/music` bind mount in `compose.yaml`, recreate the container, then choose `/music` in Settings. An optional Import Directory lists available exports directly in the Import dialog. The browser directory picker browses the backend's filesystem; it cannot grant Docker access to an unmounted host folder.

## Import your Spotify export

1. Set **Settings → Library → Music Library Directory** to your existing library first.
2. Click **Import library**, then select an export:
   - Exportify / playlist CSV: track URI, name, artist name(s), album, milliseconds, release date, ISRC, and optional artwork/track/disc/album-artist columns. Semicolon-separated artist lists are preserved.
   - Spotify account ZIP / JSON: playlist `items[].track`, saved-library `tracks`, and streaming-history records containing track metadata. Podcasts and unrelated account files are ignored.
   - `.txt` containing Spotify track URLs or URIs.
3. Files are scanned before tracks enter review. Existing tagged recordings are marked **Already in library ✓**.
4. Review matches. Left rejects only the candidate; right approves the song; down skips the song; up cycles candidates; space opens or controls the visible YouTube player. Swipe horizontally on touch devices.
5. Approved tracks automatically download unless the process is paused. Review and queue state survive restarts.

CSV filenames become playlist names unless a Playlist / Playlist Name column exists. Account export playlist names are preserved. Re-imports merge Spotify IDs and union memberships while preserving skips and approvals. Without IDs, only exact normalized release metadata merges; no fuzzy title-only merging. Different Spotify releases remain separate records. ISRC is used for physical recording detection, not to erase release distinctions.

Spotify URL lists do not contain artist, album, duration, or ISRC. Public Spotify oEmbed enrichment is attempted for up to 25 unresolved tracks per import and lazily for missing artwork in Review; it may supply only a title/artwork. MusicBrainz enrichment uses an available ISRC and verifies title/artist before filling missing duration or exact-album release/artwork fields. Use Edit metadata → Enrich missing fields to retry. Edit missing canonical fields in Review before searching/downloading. Complete Exportify CSV is recommended for large libraries. The app never invents missing metadata or replaces it with a YouTube title.

## Matching and previews

The matcher combines YouTube Music song search (`ytmusicapi`, an unofficial public-interface client) and YouTube search (`yt-dlp`). It prefers structured song results and real `Artist - Topic` channels. Title/artist agreement, album, and duration contribute to confidence; unexpected version keywords and music-video duration differences reduce it. Rejected IDs stay rejected across future searches. Manual YouTube URLs explicitly restore the selected candidate for reconsideration.

Scores are ranking heuristics, **not statistical probabilities**. Repeated searches expand the candidate pool to account for rejected IDs, up to 50 results per provider. ISRC is retained from Spotify and local files; these search providers generally do not supply a reliable candidate ISRC, so it is not fabricated or claimed as verified. Featured artists are compared against candidate artist metadata and titles; strict auto-approval requires all featured artists to be accounted for. Auto mode is off by default and only runs when a review search executes, not an unattended whole-library crawl.

The visible official [YouTube IFrame Player](https://developers.google.com/youtube/iframe_api_reference) handles previews. YouTube controls, ads, restrictions, and availability remain intact. The app does not proxy/extract audio for preview or pretend to analyze iframe audio. Some videos disallow embeds; use Open in YouTube. Autoplay can be blocked by your browser.

## Audio and file organization

Use downloads only where you have permission and where source terms and applicable law permit. No DRM, authentication, or geographic restriction bypass is implemented. Providers can rate-limit, require authentication, or break upstream; errors remain visible and retryable. Keep yt-dlp current when upstream changes.

Default native files:

- Database: `./data/trackswipe.sqlite3`
- Music: `./data/Music/Artist/Album/01 - Title.ext`
- Singles without albums: `./data/Music/Artist/Singles/Title.ext`
- Staging: `./data/temporary`
- Optional retained source audio: temporary directory's `originals/`

`TRACKSWIPE_DATA` changes the state root before startup. Settings changes persist in SQLite. Music and staging paths and output templates are configurable. Collaborations use album/primary artist for folders, all artists for tags. Playlist membership is a database relation and supported custom tag, never a Genre tag or duplicated file.

The modular yt-dlp backend selects best audio, uses ffmpeg for extraction/conversion, and Mutagen for tags and JPEG artwork. The image includes Node and yt-dlp’s packaged JavaScript challenge support. Original/best preserves the available audio codec where possible; selecting AAC/Opus/MP3 may transcode. Transcoding cannot improve source fidelity. With conversion disabled, an unavailable requested source format fails instead of silently transcoding. ReplayGain is explicitly unavailable in the UI.

A single worker checks known file identifiers before downloading, stages work, and creates final paths exclusively. Existing paths are never overwritten. Missing/unreachable artwork is logged as a history warning without discarding successfully tagged audio. Pause stops new searches/downloads; an in-progress download finishes safely. On restart, interrupted work is requeued. Rescan refreshes metadata matches and returns missing existing files to review. Repair tags first writes a `.tags-backup` copy alongside the original.

## Backup and restore

Settings → Data exports a consistent SQLite backup or human-readable JSON containing tracks, playlist joins, candidates/rejections, decisions, file paths, and settings. JSON is for inspection/interchange; **restore accepts SQLite backups**. Pause first. Restore validates schema/integrity, saves `pre-restore-<timestamp>.sqlite3` in the data directory, restores rows transactionally, and remains paused. Back up your music separately; database exports do not contain audio. After moving a library, update paths and rescan.

## Verification and architecture

```bash
.venv/bin/python -m pytest -q
npm run build --prefix frontend
```

See [ARCHITECTURE.md](ARCHITECTURE.md). Migration version 1 initializes automatically using SQLite `user_version`; unsupported backup versions are rejected. Backend modules separate import, scoring/search, tagging/downloading, persistence, and API orchestration. Logs include provider/download failures; `/api/health` reports ffmpeg availability. Interactive API documentation is at `/docs`.

No Spotify credentials or paid API are required. Search terms are sent to YouTube; artwork requests go to the URL supplied by the export; unresolved links may contact Spotify. Fonts fall back to local system fonts if Google Fonts cannot load. All durable library state is stored locally.
