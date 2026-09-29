# TrackSwipe

**Tinder, but for matching songs before downloading them.**

TrackSwipe turns a Spotify export into a persistent music library. Listen to a YouTube candidate, reject the wrong version, and approve the right one. Downloads use your imported song metadata—not whatever happens to be in the video title.

- Swipe review with keyboard shortcuts and visible YouTube previews
- Ranked Topic / YouTube Music candidates with explanations
- Optional high-confidence auto-pick, disabled by default
- Imports that merge tracks and playlist memberships without losing decisions
- Audio downloads, clean tags, artwork, and duplicate protection
- Automatic M3U playlist export for Navidrome and compatible music servers
- Local SQLite storage, backups, restore, and human-readable JSON export

File imports need no Spotify account connection or paid API. Optional playlist URL imports use your own Spotify developer app and account. Searches, previews, and downloads need internet access. Your library database stays on your machine.

## Quick start: Docker

Install Docker with Compose support. Docker Desktop is a convenient option on Windows and macOS; Docker Engine with the Compose plugin works on Linux.

```sh
git clone https://github.com/adriankralovsky/track-swipe.git
cd track-swipe
docker compose up --build -d
```

Open **http://localhost:8765**.

State persists in the project's `data` directory. By default, music is stored in `data/Music`. To stop the app without deleting your library:

```sh
docker compose down
```

To update, back up your state in **Settings → Data**, then run:

```sh
git pull
docker compose up --build -d
```

### Use an existing music directory

Add a bind mount to the `volumes` section of `compose.yaml`:

```yaml
volumes:
  - ./data:/data
  - /path/to/your/Music:/music
```

On Windows, the host path can look like `C:/Users/YourName/Music`. Then recreate the container and select **`/music`** in **Settings → Library → Music Library Directory**.

The directory browser shows the filesystem of the machine/container running the backend. Docker cannot access a host directory unless you mount it. On Linux systems with SELinux, add an appropriate volume label: `:Z` for private application data, or `:z` for a music folder shared with another container. Do not relabel system directories.

Keep the application bound to localhost. This is a personal filesystem tool without remote-user authentication.

## First import

1. Set your Music Library Directory first, especially if you already have downloaded music.
2. Click **Import library** and choose your export.
3. TrackSwipe scans existing files and excludes matching recordings from review by default.
4. Open **Review** and listen before deciding.

Supported inputs:

| Format | What is imported |
| --- | --- |
| Exportify / playlist CSV | Spotify IDs, title, artists, album, duration, release date, ISRC, and other supplied fields |
| Spotify account ZIP / JSON | Recognized playlist, saved-library, and track-history records; unrelated account data is ignored |
| Spotify track links / URIs in `.txt` | Track IDs, with best-effort public metadata enrichment |
| Spotify API-shaped playlist JSON | Track objects, album metadata, artist credits, and playlist names |

A complete CSV export is recommended for large libraries. Link-only exports often lack artist, album, or duration; use **Edit metadata** to fill missing fields. Public Spotify oEmbed and optional MusicBrainz ISRC lookups can fill some gaps. Unavailable metadata is not invented.

CSV filenames become playlist names, with underscores restored to spaces (for example, `Liked_Songs.csv` → `Liked Songs`), unless the export supplies a Playlist / Playlist Name column. Explicit playlist names are preserved exactly, including intentional underscores. Spotify account playlist names are preserved. An optional Import Directory lets you choose exports already present on the backend machine.

Re-importing merges matching Spotify IDs and adds playlist memberships. Existing skips, candidate rejections, and approvals remain intact. Different releases are not blindly merged by similar titles.

## Review controls

| Action | Keyboard | Result |
| --- | --- | --- |
| Wrong candidate | Left arrow | Reject this result and keep reviewing the **same song** |
| Approve match | Right arrow | Lock the candidate and queue the track |
| Skip song | Down arrow | Permanently skip the song until restored from Skipped |
| Next candidate | Up arrow | Browse another candidate without rejecting it |
| Preview | Space | Open or control the YouTube player |

Horizontal swipes work on touch devices. If automatic results run out, edit the search query, search again, paste a manual YouTube URL, or skip the song. Rejected candidate IDs remain rejected across searches.

Previews use the visible [official YouTube iframe player](https://developers.google.com/youtube/iframe_api_reference). Browser autoplay rules and YouTube embed restrictions apply. Use **Open in YouTube** if a video cannot play in the embedded player.

### Automatic confidence mode

Enable **Settings → Matching → Automatic confidence mode** and choose a threshold, such as 98%. Saving matching settings re-evaluates **already saved candidates**, including after changing the threshold. New searches also apply the rules. The download worker rechecks saved candidates after startup/resume.

A candidate must meet the threshold **and** these safety checks:

- Topic channel **or** a structured YouTube Music song result
- Exact normalized title and primary artist
- Known duration difference strictly below 2 seconds
- Featured artists accounted for
- No unexpected version keywords, music-video classification, or known ISRC conflict

The threshold is inclusive: 98% qualifies at a 98% setting. An eligible YouTube Music result does not need a literal `- Topic` suffix. Each card explains any additional reason it still needs manual review. Skipped tracks, rejected candidates, existing audio, and failed downloads are not silently approved again.

Scores are ranking heuristics, not statistical probabilities. Most search results do not expose a reliable ISRC; the app does not claim to have verified one when it is unavailable. Searches use `ytmusicapi` and `yt-dlp`, so provider changes and rate limits can affect availability. Auto-pick handles cached candidates and searches performed by Review; it is not an unattended search of every unreviewed song.

## Downloads and YouTube sign-in

Use downloads where you have permission and where applicable law and source terms allow. TrackSwipe does not bypass DRM or access restrictions.

Approved tracks download automatically unless paused. Pause stops new work; an active download finishes safely. Queue shows a red **needs attention** banner and highlighted rows for failed downloads, plus **Retry failed downloads** and individual Retry controls. A red badge on Queue makes failures visible from other pages.

Temporary network failures, rate limits, and temporary HTTP errors receive **up to three automatic retries after the initial attempt**, with waits of **30 seconds, 2 minutes, and 5 minutes**. A rate limit cools down the whole download worker to avoid hammering the provider. Waiting retries display their attempt number and scheduled time. Pause holds retries; restart preserves their remaining budget and schedule. After all three retries fail, the track stays red for manual attention. Authentication, unavailable-video, and local filesystem errors require manual action immediately. A manual retry starts a fresh retry budget.

### “Please sign in” / authentication errors

Some videos require an authenticated YouTube session. Configure **Settings → Audio → YouTube authentication**:

**Native application:** choose **Signed-in local browser**, select your browser, and optionally supply its profile. Run TrackSwipe as the same operating-system user as the browser. Cookie extraction may require an unlocked keyring or a closed browser, depending on the platform.

**Docker or another backend machine:** choose **Netscape cookies file**. Export your YouTube session using the [yt-dlp cookie instructions](https://github.com/yt-dlp/yt-dlp/wiki/Extractors#exporting-youtube-cookies). For example, store the file at `data/private/youtube-cookies.txt` on the host and configure `/data/private/youtube-cookies.txt` in the app. The backend needs a readable, writable cookie file because yt-dlp can update it.

Use **Save & retry sign-in failures** after configuration. Only authentication-related failures are requeued; other failures remain unchanged. Expired cookies may need to be exported again. Cookies do not guarantee access to removed, private, region-restricted, or otherwise unavailable videos.

Cookie files grant access to your session: keep them private and do not commit or share them. TrackSwipe stores only the selected mode, browser/profile, and file path in settings—not cookie contents. Database backups do not include the cookie file. Git and Docker ignore rules exclude conventional cookie filenames and private directories.

The packaged downloader includes JavaScript challenge support and uses Node. If extraction breaks after an upstream change, update dependencies or rebuild the Docker image before retrying. See the [yt-dlp authentication FAQ](https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp).

## Import a Spotify playlist URL

Open **Import → Connect Spotify to import links**. Create an app in the [Spotify developer dashboard](https://developer.spotify.com/dashboard), select Web API, and register this redirect URI for the default local installation:

```text
http://127.0.0.1:8765/api/spotify/callback
```

Enter the app's **Client ID** and exact redirect URI in TrackSwipe, then choose **Continue to Spotify**. No client secret is required. Spotify asks for read access to private and collaborative playlists. After connecting, paste an `https://open.spotify.com/playlist/…` link or `spotify:playlist:…` URI and choose **Import playlist**. Full links with share parameters are accepted; shortened share links must first be opened in a browser and copied as full links.

The importer retrieves every page before saving, checks whether the playlist changed during the fetch, preserves the original name, and merges songs by Spotify ID. Re-importing adds memberships and retains approvals, rejections, skips, and downloaded files. It does not remove earlier memberships when a track disappears from Spotify. Local files, unavailable entries and podcast episodes are omitted, with a count shown after import.

**Spotify access limits:** current development-mode apps require the app owner to have Spotify Premium, and playlist contents are available only when the signed-in user owns or collaborates on the playlist. Other accounts may need to be added to the developer app's allowed users. A public link alone does not guarantee API access. Use a CSV export when Spotify denies access. See [Spotify's development-mode rules](https://developer.spotify.com/documentation/web-api/tutorials/february-2026-migration-guide).

For another port or remote deployment, register the matching callback address and enter it in TrackSwipe. Spotify permits HTTP on explicit loopback addresses such as `127.0.0.1`, but requires HTTPS elsewhere; `localhost` is not an accepted Spotify redirect hostname. Native development users should complete connection/import at the backend address (default port 8765).

Tokens are stored only in `spotify-connection.json` inside the local data directory, with owner-only permissions on Unix. They are excluded from JSON/SQLite library exports. Reconnect after restoring the library on another machine. **Connection settings → Disconnect** removes local tokens; you can also revoke access in your Spotify account. Never publish the data directory.

## Navidrome / Subsonic playlists

Playlist membership is stored separately from audio: a song in five playlists still has one physical file. Custom audio tags alone do **not** create server playlists.

TrackSwipe writes UTF-8 extended **`.m3u` files** inside your Music Library Directory, under `Playlists` by default:

```text
Music/
  Artist/Album/01 - Song.opus
  Playlists/Gym.m3u
  Playlists/Favorites.m3u
```

Entries use relative paths such as `../Artist/Album/01 - Song.opus`. This works when TrackSwipe and your music server mount the same library at different absolute paths. Only existing audio files within the configured library are included; skipped, missing, and unfinished tracks are omitted. Playlist files update after imports, successful downloads, decisions, and library rescans. Unchanged files keep their timestamps to avoid unnecessary server reimports. Managed files carry a stable playlist ID, so later display-name changes keep the same file path. Navidrome preserves names of playlists it has already imported; change an existing server playlist name there when needed.

Use **Playlists → Sync to music server** to export all existing memberships immediately. Automatic updates and the playlist subdirectory are configurable in **Settings → Library**. TrackSwipe only replaces files carrying its own management marker; unrelated playlist files are protected. Avoid manually editing generated files because a future sync replaces their content.

### Navidrome setup

Point Navidrome at the **same music library**, including its `Playlists` subdirectory. Ensure these settings permit import:

```yaml
environment:
  ND_AUTOIMPORTPLAYLISTS: "true"
  ND_PLAYLISTSPATH: "Playlists/**"
```

An empty `ND_PLAYLISTSPATH` also allows playlists throughout the library. If you choose another subdirectory in TrackSwipe, update this setting accordingly. Trigger a Navidrome library scan after the first sync. Navidrome needs an existing admin user before it imports playlists. See [Navidrome configuration](https://www.navidrome.org/docs/usage/configuration/options/) and [initial setup](https://www.navidrome.org/docs/getting-started/).

After Navidrome imports the files, its Subsonic/OpenSubsonic clients can browse those server playlists. Other Subsonic-compatible servers can use the same relative-path M3U files where they support playlist import; consult that server's import settings. TrackSwipe does not call a remote Subsonic API or manage server playlist permissions. Depending on the server, imported playlists may initially belong to an administrator or require sharing before other users can see them.

## File organization and audio quality

Default music layout:

```text
Music/Album Artist/Album/01 - Title.ext
Music/Artist/Singles/Title.ext
```

Collaborations use album/primary artist for folders while retaining all artists in tags. Set a custom output template in **Settings → Library**. Unicode names are preserved; unsafe filename characters are replaced.

Original/best audio preserves the source codec where possible. M4A/AAC, Opus, and MP3 are available when conversion is allowed. Transcoding cannot improve source fidelity. With conversion disabled, unavailable requested formats fail instead of silently converting. ReplayGain is currently unavailable and is marked accordingly in Settings.

Mutagen writes supported title, artists, album, album artist, track/disc, date, ISRC, Spotify ID, explicit status, playlist membership, and artwork fields. Artwork failures appear in history without discarding otherwise successful audio. Playlist membership never overwrites Genre.

Downloads are staged and published atomically without overwriting existing files. Duplicate checks prioritize ISRC and Spotify IDs, then metadata, duration, and conservative filename fallback. **Rescan library** picks up manually added/removed music. **Repair tags** updates an existing file after preserving a `.tags-backup` copy.

## Local data and backups

| Data | Default location |
| --- | --- |
| Database and settings | `data/trackswipe.sqlite3` |
| Music | `data/Music/` |
| Temporary downloads | `data/temporary/` |
| Optional retained source audio | Temporary directory's `originals/` subdirectory |
| Generated playlists | Music directory's `Playlists/` subdirectory |

`TRACKSWIPE_DATA` changes the state root before startup. Music and staging directories are configurable independently.

**Settings → Data** provides:

- A consistent SQLite backup containing tracks, playlists, candidates, decisions, settings, and history
- A human-readable JSON export for inspection and interchange
- SQLite restore with integrity/schema checks and an automatic pre-restore safety backup

Pause before restoring. The app remains paused afterward. JSON is an export format; restore accepts SQLite backups. Music and cookie files are not embedded in database backups—back up audio separately, and treat session cookies separately from ordinary library data. Update directory settings and rescan after moving a library.

## Native installation and development

Install **Python 3.11+**, **Node.js 22+ with npm**, and **ffmpeg**. They must be available on PATH. Install them using your operating system's package manager or their official installers.

### Linux / macOS

For development:

```sh
./dev.sh
```

The script prepares dependencies, starts the API on port 8765, and runs Vite at **http://localhost:5173**.

For a single production service:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
npm ci --prefix frontend
npm run build --prefix frontend
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8765
```

### Windows PowerShell

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
npm ci --prefix frontend
npm run build --prefix frontend
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8765
```

Open **http://localhost:8765**. Docker is the tested, consistent deployment path across host operating systems; native Windows/macOS behavior can depend on installed codecs, browser cookie access, and filesystem permissions.

### Tests and architecture

With the Python environment activated, run:

```sh
python -m pytest -q
npm run build --prefix frontend
```

Tests cover ranking, cached auto-pick, durable decisions, imports, real audio tag round-trips, duplicate protection, backup/restore, M3U paths, and authentication configuration without reading your browser cookies.

See [ARCHITECTURE.md](ARCHITECTURE.md). The backend separates persistence, imports, matching, automatic approval, playlist export, YouTube options, and audio/tagging. SQLite schema initialization/migration is automatic. Schema v2 adds persistent retry state; v1 and v2 SQLite backups can be restored. API documentation is at `/docs`; `/api/health` reports ffmpeg availability. Provider failures are logged and remain visible in the interface.
