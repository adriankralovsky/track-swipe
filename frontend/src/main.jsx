import React, { useState, useEffect, useRef, useCallback } from "react";
import { createRoot } from "react-dom/client";
import { motion, AnimatePresence } from "framer-motion";
import {
  AudioLines,
  Disc3,
  Heart,
  Layers3,
  Library,
  FolderHeart,
  SkipForward,
  History,
  Settings,
  Plus,
  ArrowUpRight,
  ArrowRight,
  ArrowLeft,
  ChevronDown,
  ChevronRight,
  ChevronLeft,
  Check,
  X,
  Play,
  Pause,
  Search,
  RefreshCw,
  Download,
  Upload,
  Music2,
  Headphones,
  ShieldCheck,
  SlidersHorizontal,
  Folder,
  Keyboard,
  Volume2,
  LoaderCircle,
  CheckCheck,
  MoreHorizontal,
  ExternalLink,
  Database,
  CloudDownload,
  FileMusic,
  Radio,
  Info,
} from "lucide-react";
import "./style.css";

const api = async (path, options = {}) => {
  const r = await fetch("/api" + path, {
    ...options,
    headers:
      options.body instanceof FormData
        ? {}
        : { "Content-Type": "application/json", ...options.headers },
  });
  if (!r.ok) {
    let d;
    try {
      d = await r.json();
    } catch {}
    throw Error(d?.detail || `Request failed (${r.status})`);
  }
  return r.json();
};
const post = (path, body = {}) =>
  api(path, { method: "POST", body: JSON.stringify(body) });
const duration = (n) =>
  n
    ? `${Math.floor(Math.round(n) / 60)}:${String(Math.round(n) % 60).padStart(2, "0")}`
    : "—";
const nav = [
  ["Review", Layers3],
  ["Queue", CloudDownload],
  ["Library", Library],
  ["Playlists", FolderHeart],
  ["Skipped", SkipForward],
  ["History", History],
];
const labels = {
  waiting: "Waiting for review",
  approved: "Approved",
  downloading: "Downloading",
  completed: "Downloaded",
  existing: "Already in library ✓",
  failed: "Needs attention",
  retrying: "Retry scheduled",
  skipped: "Skipped",
};

function Art({ src, className = "", small = false }) {
  const [failed, setFailed] = useState(false);
  useEffect(() => setFailed(false), [src]);
  return (
    <div className={`art ${className}`}>
      {src && !failed ? (
        <img src={src} onError={() => setFailed(true)} alt="Album artwork" />
      ) : (
        <div className="record-art">
          <div className="record">
            <span>
              <AudioLines size={small ? 16 : 36} />
            </span>
          </div>
          {!small && (
            <div className="art-caption">
              GOOD MUSIC.
              <br />
              RIGHT VERSION.
            </div>
          )}
        </div>
      )}
    </div>
  );
}
function App() {
  const [page, setPage] = useState("Review"),
    [status, setStatus] = useState({ total: 0, counts: {}, rejected: 0 }),
    [settings, setSettings] = useState(null),
    [revision, setRevision] = useState(0),
    [toast, setToast] = useState(null),
    [importOpen, setImportOpen] = useState(false),
    [busy, setBusy] = useState(false),
    [search, setSearch] = useState("");
  const notify = useCallback(
    (message, error = false) => setToast({ message, error, id: Date.now() }),
    [],
  );
  const refresh = useCallback(() => setRevision((v) => v + 1), []);
  useEffect(() => {
    api("/settings")
      .then(setSettings)
      .catch((e) => notify(e.message, true));
  }, []);
  useEffect(() => {
    let live = true;
    const fetchStatus = () =>
      api("/status")
        .then((s) => live && setStatus(s))
        .catch(() => {});
    fetchStatus();
    const id = setInterval(fetchStatus, 2500);
    return () => {
      live = false;
      clearInterval(id);
    };
  }, [revision]);
  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 6000);
    return () => clearTimeout(t);
  }, [toast]);
  const perform = async (fn, msg) => {
    try {
      const result = await fn();
      if (msg) notify(msg);
      refresh();
      return result;
    } catch (e) {
      notify(e.message, true);
      return null;
    }
  };
  const pause = () =>
    perform(
      async () => {
        const s = await api("/settings", {
          method: "PUT",
          body: JSON.stringify({ paused: !status.paused }),
        });
        setSettings(s);
      },
      status.paused
        ? "Process resumed"
        : "Paused. An active download will finish safely.",
    );
  const counts = status.counts,
    downloaded = (counts.completed || 0) + (counts.existing || 0),
    remaining =
      (counts.waiting || 0) +
      (counts.approved || 0) +
      (counts.downloading || 0) +
      (counts.failed || 0) +
      (counts.retrying || 0);
  return (
    <div
      className="app"
      data-reduced={settings?.reduced_motion}
      style={{ "--motion": settings?.animation_intensity ?? 1 }}
    >
      <aside className="sidebar">
        <a className="brand" onClick={() => setPage("Review")}>
          <span className="brand-icon">
            <AudioLines size={23} />
          </span>
          track<span>swipe</span>
          <i />
        </a>
        <div className="workspace">YOUR MUSIC, REIMAGINED</div>
        <nav>
          {nav.map(([name, Icon]) => (
            <button
              key={name}
              className={page === name ? "active" : ""}
              onClick={() => {
                setPage(name);
                setSearch("");
              }}
            >
              <Icon size={19} />
              <span>{name}</span>
              {name === "Review" && <b>{counts.waiting || 0}</b>}
              {name === "Queue" && !!counts.failed ? (
                <b
                  className="queue-error-badge"
                  title={`${counts.failed} downloads need attention`}
                >
                  {counts.failed} !
                </b>
              ) : (
                name === "Queue" &&
                !!((counts.approved || 0) + (counts.retrying || 0)) && (
                  <b>{(counts.approved || 0) + (counts.retrying || 0)}</b>
                )
              )}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="local-card">
            <span className="local-dot" />
            LOCAL-FIRST LIBRARY
            <p>
              Your music. Your machine.
              <br />
              Always in your control.
            </p>
            <div className="tiny-progress">
              <i
                style={{
                  width: status.total
                    ? `${(downloaded / status.total) * 100}%`
                    : "0%",
                }}
              />
            </div>
            <small>{downloaded.toLocaleString()} tracks in your library</small>
          </div>
          <button
            className={
              page === "Settings" ? "settings-link active" : "settings-link"
            }
            onClick={() => setPage("Settings")}
          >
            <Settings size={19} />
            Settings<span>⌘ ,</span>
          </button>
          <div className="profile">
            <div className="avatar">
              <Headphones size={18} />
            </div>
            <div>
              Your listening room<small>Personal workspace</small>
            </div>
            <span className="online" />
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header>
          <div className="breadcrumb">
            Workspace
            <ChevronRight size={13} />
            <strong>{page}</strong>
          </div>
          <div className="header-right">
            <span className="private">
              <span className="local-dot" />
              All systems local
            </span>
            <button
              className="icon-button"
              title="Settings"
              onClick={() => setPage("Settings")}
            >
              <Settings size={17} />
            </button>
            <button
              className="icon-button"
              title={status.paused ? "Resume process" : "Pause process"}
              onClick={pause}
            >
              {status.paused ? <Play size={17} /> : <Pause size={17} />}
            </button>
            <button
              className="primary small"
              onClick={() => setImportOpen(true)}
            >
              <Plus size={16} />
              Import library
            </button>
          </div>
        </header>
        <main>
          <div className="page-heading">
            <div className="eyebrow">
              {page === "Review"
                ? "A LITTLE PICKY. A BETTER LIBRARY."
                : "YOUR PERSONAL MUSIC SPACE"}
            </div>
            <div className="heading-row">
              <div>
                <h1>
                  {page === "Review" ? (
                    <>
                      Find your perfect <em>match.</em>
                    </>
                  ) : page === "Queue" ? (
                    "Good things are on the way."
                  ) : page === "Library" ? (
                    "A collection that’s yours."
                  ) : page === "Playlists" ? (
                    "Every mood. One library."
                  ) : page === "Skipped" ? (
                    "Maybe another time."
                  ) : page === "History" ? (
                    "Your listening trail."
                  ) : (
                    "Make yourself at home."
                  )}
                </h1>
                <p>
                  {page === "Review"
                    ? "Listen. Decide. Keep the version you love."
                    : page === "Settings"
                      ? "Fine-tune your library, your matches, and your flow."
                      : "Every track, every decision, right where you left it."}
                </p>
              </div>
              {page === "Review" && (
                <div className="manual-chip">
                  <span />
                  {settings?.auto_approve
                    ? "Strict auto approval"
                    : "Manual review"}
                </div>
              )}
            </div>
          </div>
          <div className="stat-strip">
            <span>
              <strong>{status.total.toLocaleString()}</strong> tracks imported
            </span>
            <span>
              <i className="dot green" />
              <strong>{downloaded.toLocaleString()}</strong> downloaded
            </span>
            <span>
              <i className="dot purple" />
              <strong>{counts.waiting || 0}</strong> to review
            </span>
            <span>
              <i className="dot amber" />
              <strong>{counts.skipped || 0}</strong> skipped
            </span>
            <span className="remaining">
              {remaining} remaining
              <ArrowUpRight size={14} />
            </span>
          </div>
          {status.paused && (
            <div className="notice">
              <Pause size={16} />
              Process paused. Your decisions are safe.
              <button onClick={pause}>Resume</button>
            </div>
          )}
          {settings &&
            (page === "Review" ? (
              <Review
                {...{ settings, status, revision, refresh, notify, perform }}
                onImport={() => setImportOpen(true)}
              />
            ) : page === "Settings" ? (
              <SettingsPage
                {...{ settings, setSettings, perform, notify, refresh }}
              />
            ) : page === "History" ? (
              <HistoryPage revision={revision} />
            ) : (
              <LibraryPage
                {...{ page, revision, perform, search, setSearch, status }}
              />
            ))}
          <footer>
            <span>
              <ShieldCheck size={13} />
              Made for your ears. Stored on your machine.
            </span>
            <span>
              TRACKSWIPE <b>v1.0</b>
            </span>
          </footer>
        </main>
      </div>
      <AnimatePresence>
        {toast && (
          <motion.div
            role="status"
            aria-live="polite"
            className={`toast ${toast.error ? "error" : ""}`}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 20 }}
          >
            {toast.error ? <Info size={19} /> : <Check size={19} />}
            <span>{toast.message}</span>
            <button onClick={() => setToast(null)}>
              <X size={15} />
            </button>
          </motion.div>
        )}
      </AnimatePresence>
      {importOpen && (
        <Modal
          title="Bring your music along."
          subtitle="Your playlists are the starting point. Your taste does the rest."
          close={() => !busy && setImportOpen(false)}
        >
          <label className="dropzone">
            <span className="upload-icon">
              {busy ? <LoaderCircle className="spin" /> : <Upload />}
            </span>
            <strong>
              {busy
                ? "Importing & checking your library…"
                : "Choose your Spotify export"}
            </strong>
            <p>
              Exportify CSV, playlist CSV, Spotify ZIP / JSON,
              <br />
              or a .txt file of Spotify track links
            </p>
            <input
              type="file"
              accept=".csv,.zip,.json,.txt"
              disabled={busy}
              onChange={async (e) => {
                const file = e.target.files[0];
                if (!file) return;
                setBusy(true);
                const f = new FormData();
                f.append("file", file);
                const result = await perform(() =>
                  api("/import", { method: "POST", body: f }),
                );
                setBusy(false);
                if (result) {
                  notify(
                    `${result.imported} tracks added · ${result.merged} merged · ${result.scan.matched} already in library${result.unresolved ? " · Some tracks need metadata" : ""}`,
                  );
                  setImportOpen(false);
                }
              }}
            />
            <span className="primary">
              Browse files
              <ArrowUpRight size={16} />
            </span>
          </label>
          {settings?.import_dir && (
            <LocalImports
              busy={busy}
              setBusy={setBusy}
              perform={perform}
              done={() => setImportOpen(false)}
              notify={notify}
            />
          )}
          <div className="import-note">
            <ShieldCheck size={18} />
            <p>
              Existing songs are detected before review. Re-imports preserve
              your decisions and merge playlist memberships.
            </p>
          </div>
        </Modal>
      )}
    </div>
  );
}

function LocalImports({ busy, setBusy, perform, done, notify }) {
  const [files, setFiles] = useState([]),
    [error, setError] = useState("");
  useEffect(() => {
    api("/import-files")
      .then(setFiles)
      .catch((e) => setError(e.message));
  }, []);
  return (
    <div className="local-imports">
      <h3>From your import directory</h3>
      {error && <p>{error}</p>}
      {!files.length && !error && (
        <p>No supported exports in this directory.</p>
      )}
      {files.map((name) => (
        <button
          disabled={busy}
          key={name}
          onClick={async () => {
            setBusy(true);
            const result = await perform(() => post("/import-local", { name }));
            setBusy(false);
            if (result) {
              notify(
                `${result.imported} added · ${result.merged} merged · ${result.scan.matched} already in library`,
              );
              done();
            }
          }}
        >
          <FileMusic size={16} />
          <span>{name}</span>
          <ArrowRight size={15} />
        </button>
      ))}
    </div>
  );
}

function Review({
  settings,
  status,
  revision,
  refresh,
  notify,
  perform,
  onImport,
}) {
  const [tracks, setTracks] = useState([]),
    [candidates, setCandidates] = useState([]),
    [index, setIndex] = useState(0),
    [loading, setLoading] = useState(false),
    [loadError, setLoadError] = useState(""),
    [direction, setDirection] = useState(0),
    [acting, setActing] = useState(false),
    [query, setQuery] = useState(""),
    [manual, setManual] = useState(""),
    [tools, setTools] = useState(false),
    [edit, setEdit] = useState(false),
    [playing, setPlaying] = useState(false),
    [preview, setPreview] = useState(false);
  const reviewed = useRef(new Set());
  const player = useRef(null),
    requestVersion = useRef(0),
    track = tracks[0],
    target = track?.metadata,
    candidate = candidates[index];
  const loadTracks = () =>
    api("/tracks?view=review")
      .then((rows) =>
        setTracks(rows.filter((t) => !reviewed.current.has(t.id))),
      )
      .catch((e) => notify(e.message, true));
  useEffect(() => {
    loadTracks();
  }, [revision]);
  useEffect(() => {
    if (!settings.auto_approve || status.paused) return;
    const timer = setInterval(loadTracks, 2000);
    return () => clearInterval(timer);
  }, [settings.auto_approve, status.paused]);
  const searchCandidates = async (tid, q) => {
    const token = ++requestVersion.current;
    setLoading(true);
    setLoadError("");
    try {
      const r = await post(`/tracks/${tid}/search`, { query: q });
      if (token !== requestVersion.current) return;
      setCandidates(r.candidates.filter((c) => !c.rejected));
      setIndex(0);
      if (r.warnings.length)
        notify(
          "Some search providers were unavailable. Available results are shown.",
        );
      refresh();
    } catch (e) {
      if (token === requestVersion.current) setLoadError(e.message);
    } finally {
      if (token === requestVersion.current) setLoading(false);
    }
  };
  useEffect(() => {
    setCandidates([]);
    setIndex(0);
    setPreview(false);
    setQuery(target ? `${target.artists.join(" ")} ${target.title}` : "");
    setLoadError("");
    if (!track) return;
    const token = ++requestVersion.current;
    setLoading(true);
    api(`/tracks/${track.id}/candidates`)
      .then((r) => {
        if (token !== requestVersion.current) return;
        const available = r.filter((c) => !c.rejected);
        setCandidates(available);
        setLoading(false);
        if (!r.length && !status.paused) searchCandidates(track.id);
      })
      .catch((e) => {
        setLoading(false);
        setLoadError(e.message);
      });
    return () => {
      requestVersion.current++;
    };
  }, [track?.id, status.paused]);
  useEffect(() => {
    if (!track || target.artwork) return;
    let active = true;
    post(`/tracks/${track.id}/enrich`)
      .then((r) => {
        if (active)
          setTracks((ts) =>
            ts.map((t) =>
              t.id === track.id ? { ...t, metadata: r.metadata } : t,
            ),
          );
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, [track?.id]);
  useEffect(() => {
    setPlaying(false);
    setPreview(settings.autoplay);
  }, [candidate?.video_id]);
  useEffect(() => {
    if (!preview || !candidate) return;
    let cancelled = false;
    const mount = () => {
      if (cancelled || !document.getElementById("youtube-player")) return;
      player.current?.destroy?.();
      player.current = new window.YT.Player("youtube-player", {
        videoId: candidate.video_id,
        playerVars: { autoplay: 1, origin: location.origin, playsinline: 1 },
        events: {
          onReady: (e) => e.target.setVolume(settings.volume),
          onStateChange: (e) => setPlaying(e.data === 1),
          onError: () =>
            notify(
              "YouTube cannot play this embed. Use “Open in YouTube” to listen.",
              true,
            ),
        },
      });
    };
    if (window.YT?.Player) mount();
    else {
      window.onYouTubeIframeAPIReady = mount;
      if (!document.querySelector("script[data-youtube]")) {
        const script = document.createElement("script");
        script.src = "https://www.youtube.com/iframe_api";
        script.dataset.youtube = "true";
        document.body.append(script);
      }
    }
    return () => {
      cancelled = true;
      player.current?.destroy?.();
      player.current = null;
    };
  }, [preview, candidate?.video_id]);
  const togglePlay = () => {
    if (!candidate) return;
    if (!preview) {
      setPreview(true);
      return;
    }
    if (player.current?.getPlayerState?.() === 1) player.current.pauseVideo();
    else player.current?.playVideo?.();
  };
  const decide = async (action) => {
    if (
      !track ||
      acting ||
      status.paused ||
      ((action === "accept" || action === "reject") && !candidate)
    )
      return;
    setActing(true);
    let ok;
    try {
      ok = await post(`/tracks/${track.id}/decision`, {
        action,
        video_id: candidate?.video_id,
      });
    } catch (e) {
      notify(e.message, true);
    }
    if (ok) {
      setDirection(action === "accept" ? 1 : action === "reject" ? -1 : 2);
      await new Promise((r) =>
        setTimeout(
          r,
          settings.reduced_motion ? 0 : 240 * settings.animation_intensity,
        ),
      );
      if (action === "reject") {
        setCandidates((cs) =>
          cs.filter((c) => c.video_id !== candidate.video_id),
        );
        setIndex(0);
      } else {
        reviewed.current.add(track.id);
        setTracks((ts) => ts.filter((t) => t.id !== track.id));
        notify(
          action === "accept"
            ? "Perfect match. Added to your download queue."
            : "Song skipped. You can restore it anytime.",
        );
      }
      setDirection(0);
      refresh();
    }
    setActing(false);
  };
  useEffect(() => {
    const handler = (e) => {
      if (
        !settings.keyboard ||
        /INPUT|TEXTAREA|SELECT/.test(e.target.tagName) ||
        document.querySelector("[role=dialog]")
      )
        return;
      if (
        ["ArrowLeft", "ArrowRight", "ArrowDown", "ArrowUp", " "].includes(e.key)
      )
        e.preventDefault();
      if (e.key === "ArrowLeft") decide("reject");
      if (e.key === "ArrowRight") decide("accept");
      if (e.key === "ArrowDown") decide("skip");
      if (e.key === "ArrowUp")
        setIndex((i) => (i + 1) % Math.max(candidates.length, 1));
      if (e.key === " ") togglePlay();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [
    candidate,
    track,
    acting,
    status.paused,
    preview,
    settings,
    edit,
    candidates,
  ]);
  if (!track)
    return (
      <div className="empty-review">
        <div className="empty-visual">
          <div className="orbit orbit-one" />
          <div className="orbit orbit-two" />
          <Art />
          <span className="float-badge">
            <Check size={19} />
            Only the right version.
          </span>
          <span className="float-note">
            <Music2 size={20} />
          </span>
        </div>
        <div className="empty-copy">
          <span className="section-kicker">
            {status.total
              ? "ALL CAUGHT UP"
              : "YOUR NEXT GREAT MATCH STARTS HERE"}
          </span>
          <h2>
            {status.total ? (
              <>
                Good taste.
                <br />
                Great work.
              </>
            ) : (
              <>
                Your library.
                <br />A little more <em>chemistry.</em>
              </>
            )}
          </h2>
          <p>
            {status.total
              ? "No songs are waiting for review. Your approved matches, downloaded music, and skipped songs are saved."
              : "Bring your Spotify collection. Preview the best audio matches, swipe away the wrong versions, and build a library that sounds like you."}
          </p>
          <button className="primary" onClick={onImport}>
            <Plus size={18} />
            Import your library
            <ArrowRight size={17} />
          </button>
          <small>No account needed. No decisions lost.</small>
        </div>
        <div className="how-it-works">
          <span>
            <b>01</b>Bring your tracks
          </span>
          <ChevronRight size={15} />
          <span>
            <b>02</b>Find the right version
          </span>
          <ChevronRight size={15} />
          <span>
            <b>03</b>Make it yours
          </span>
        </div>
      </div>
    );
  return (
    <>
      <div className="review-toolbar">
        <div>
          <span className="live-dot" />
          THE MATCH ROOM
          <span className="divider" />
          Track {track.id}{" "}
          <span className="muted">· {tracks.length} left to explore</span>
        </div>
        <button className="text-button" onClick={() => setTools(!tools)}>
          <SlidersHorizontal size={15} />
          Match controls
        </button>
      </div>
      <div className="match-grid">
        {target.artwork && (
          <div
            className="album-atmosphere"
            style={{
              backgroundImage: `url(${JSON.stringify(target.artwork).slice(1, -1)})`,
            }}
          />
        )}
        <section className="target-panel">
          <div className="panel-label">
            <span className="spotify-dot">
              <AudioLines size={13} />
            </span>
            YOUR SPOTIFY TRACK<span>SOURCE OF TRUTH</span>
          </div>
          <Art src={target.artwork} className="target-art" />
          <div className="target-info">
            <div className="source-pill">
              <span />
              From your library
            </div>
            <h2>{target.title || "Unresolved Spotify track"}</h2>
            <p>{target.artists.join(", ") || "Artist metadata needed"}</p>
            <div className="track-meta">
              <span>
                <Disc3 size={14} />
                {target.album || "Single"}
              </span>
              <span>
                {String(target.release_date || "").slice(0, 4) || "—"}
              </span>
              <span>{duration(target.duration)}</span>
            </div>
            <div className="target-bottom">
              <span>
                {target.isrc
                  ? `ISRC ${target.isrc}`
                  : target.spotify_id
                    ? "Spotify metadata"
                    : "Imported metadata"}
              </span>
              <button onClick={() => setEdit(true)}>
                Edit metadata
                <ArrowUpRight size={12} />
              </button>
            </div>
          </div>
        </section>
        <div className="connection">
          <span>
            <AudioLines size={18} />
          </span>
        </div>
        <motion.section
          className={`candidate-panel ${direction === 1 ? "accepted" : direction === -1 ? "rejected" : ""}`}
          animate={{
            x: direction === 1 ? 120 : direction === -1 ? -120 : 0,
            y: direction === 2 ? 100 : 0,
            opacity: direction ? 0 : 1,
            rotate: direction === 1 ? 6 : direction === -1 ? -6 : 0,
          }}
          transition={{
            duration: settings.reduced_motion
              ? 0
              : 0.23 * settings.animation_intensity,
          }}
          drag={candidate && !acting ? "x" : false}
          dragConstraints={{ left: 0, right: 0 }}
          onDragEnd={(_, info) => {
            if (info.offset.x > 90) decide("accept");
            else if (info.offset.x < -90) decide("reject");
          }}
        >
          <div className="panel-label">
            <span className="youtube-mark">▶</span>THE POTENTIAL MATCH
            <span>
              {loading ? "SEARCHING" : `${index + 1} / ${candidates.length}`}
            </span>
          </div>
          {loading ? (
            <div className="candidate-empty">
              <LoaderCircle size={34} className="spin" />
              <h3>Looking for the one…</h3>
              <p>Comparing titles, artists, and clean audio sources.</p>
            </div>
          ) : candidate ? (
            <>
              <div className="candidate-media">
                {preview ? (
                  <div className="player-wrap">
                    <div id="youtube-player" />
                  </div>
                ) : (
                  <>
                    <Art src={candidate.thumbnail} />
                    <button
                      className="preview-play"
                      onClick={togglePlay}
                      aria-label="Play candidate preview"
                    >
                      <Play size={26} fill="currentColor" />
                    </button>
                    <span className="preview-label">
                      <Headphones size={13} />
                      Listen before you decide
                    </span>
                  </>
                )}
                <span className="duration-badge">
                  {duration(candidate.duration)}
                </span>
              </div>
              <div className="candidate-info">
                <div className="candidate-title-row">
                  <div>
                    <h2>{candidate.title}</h2>
                    <p>
                      {candidate.channel || candidate.artists?.join(", ")}
                      {(candidate.topic || candidate.music) && (
                        <ShieldCheck size={14} />
                      )}
                    </p>
                  </div>
                  <div
                    className={`confidence ${candidate.confidence < 80 ? "uncertain" : ""}`}
                  >
                    <strong>
                      {candidate.confidence}
                      <small>%</small>
                    </strong>
                    <span>MATCH</span>
                  </div>
                </div>
                <div className="candidate-badges">
                  {candidate.topic && (
                    <span>
                      <CheckCheck size={12} />
                      Topic channel
                    </span>
                  )}
                  {candidate.music && (
                    <span>
                      <Music2 size={12} />
                      YouTube Music
                    </span>
                  )}
                  <a
                    href={`https://www.youtube.com/watch?v=${candidate.video_id}`}
                    target="_blank"
                    rel="noreferrer"
                  >
                    Open in YouTube
                    <ExternalLink size={11} />
                  </a>
                </div>
                <div className="reasons">
                  {candidate.reasons.map((r, i) => (
                    <div key={i} className={r.ok ? "good" : "caution"}>
                      {r.ok ? <Check size={13} /> : <Info size={13} />}
                      <span>{r.label}</span>
                    </div>
                  ))}
                </div>
                {settings.auto_approve && (
                  <p className="help auto-explanation">
                    {candidate.auto_blockers?.length
                      ? `Manual review: ${candidate.auto_blockers.join("; ")}.`
                      : candidate.confidence < settings.auto_threshold
                        ? `Below your ${settings.auto_threshold}% auto-pick threshold.`
                        : "Meets your auto-pick rules. Queuing automatically…"}
                  </p>
                )}
                <div className="candidate-bottom">
                  <span>
                    <ShieldCheck size={13} />
                    {playing ? "Playing on YouTube" : "You have the final say."}
                  </span>
                  <div>
                    <button
                      aria-label="Previous candidate"
                      disabled={!index}
                      onClick={() => setIndex((i) => i - 1)}
                    >
                      <ChevronLeft size={16} />
                    </button>
                    <button
                      aria-label="Next candidate"
                      disabled={index >= candidates.length - 1}
                      onClick={() => setIndex((i) => i + 1)}
                    >
                      <ChevronRight size={16} />
                    </button>
                  </div>
                </div>
              </div>
            </>
          ) : (
            <div className="candidate-empty">
              <Search size={32} />
              <h3>
                {loadError
                  ? "Let’s try another way."
                  : "Not the one? Keep looking."}
              </h3>
              <p>
                {loadError ||
                  "You’ve reviewed all these candidates. Try a different search or add a YouTube link."}
              </p>
              <button className="secondary" onClick={() => setTools(true)}>
                Search & manual URL
                <ArrowUpRight size={15} />
              </button>
            </div>
          )}
        </motion.section>
      </div>
      <div className="decision-bar">
        <button
          className="decision wrong"
          disabled={!candidate || acting || status.paused}
          onClick={() => decide("reject")}
        >
          <span>
            <X size={26} />
          </span>
          <div>
            Wrong candidate<small>Same song, next match</small>
          </div>
          <kbd>←</kbd>
        </button>
        <button
          className="skip-button"
          disabled={acting || status.paused}
          onClick={() => decide("skip")}
        >
          <SkipForward size={18} />
          <span>Skip song</span>
          <kbd>↓</kbd>
        </button>
        <button
          className="decision correct"
          disabled={!candidate || acting || status.paused}
          onClick={() => decide("accept")}
        >
          <span>
            <Check size={26} />
          </span>
          <div>
            It’s a match<small>Approve & add to queue</small>
          </div>
          <kbd>→</kbd>
        </button>
      </div>
      <div className="keyboard-hints">
        <Keyboard size={14} />
        <span>
          <kbd>←</kbd> Reject
        </span>
        <span>
          <kbd>→</kbd> Approve
        </span>
        <span>
          <kbd>↓</kbd> Skip song
        </span>
        <span>
          <kbd>↑</kbd> Next candidate
        </span>
        <span>
          <kbd>space</kbd> Preview
        </span>
      </div>
      {tools && (
        <Modal
          title="Find your version."
          subtitle="Rejected results stay rejected, even when you search again."
          close={() => setTools(false)}
        >
          <label>
            Search query
            <input value={query} onChange={(e) => setQuery(e.target.value)} />
          </label>
          <button
            className="primary"
            disabled={loading}
            onClick={() => {
              searchCandidates(track.id, query);
              setTools(false);
            }}
          >
            <Search size={16} />
            Search again
          </button>
          <div className="modal-separator" />
          <label>
            Manual YouTube URL
            <input
              value={manual}
              onChange={(e) => setManual(e.target.value)}
              placeholder="https://www.youtube.com/watch?v=…"
            />
          </label>
          <button
            className="secondary"
            onClick={async () => {
              setLoading(true);
              const r = await perform(() =>
                post(`/tracks/${track.id}/manual`, { url: manual }),
              );
              setLoading(false);
              if (r) {
                setCandidates((cs) => [
                  r,
                  ...cs.filter((c) => c.video_id !== r.video_id),
                ]);
                setIndex(0);
                setTools(false);
              }
            }}
          >
            <Plus size={16} />
            Add candidate
          </button>
        </Modal>
      )}
      {edit && (
        <MetadataEditor
          track={track}
          close={() => setEdit(false)}
          perform={perform}
        />
      )}
    </>
  );
}

function Modal({ title, subtitle, close, children }) {
  const element = useRef(null),
    closeRef = useRef(close);
  closeRef.current = close;
  useEffect(() => {
    const previous = document.activeElement;
    element.current?.querySelector("button,input,select,a")?.focus();
    const key = (e) => {
      if (e.key === "Escape") closeRef.current();
      if (e.key === "Tab") {
        const items = [
          ...element.current.querySelectorAll(
            "button:not(:disabled),input:not(:disabled),select,a[href]",
          ),
        ];
        const first = items[0],
          last = items[items.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last?.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first?.focus();
        }
      }
    };
    window.addEventListener("keydown", key);
    return () => {
      window.removeEventListener("keydown", key);
      previous?.focus();
    };
  }, []);
  return (
    <div
      className="modal-backdrop"
      onMouseDown={(e) => e.target === e.currentTarget && close()}
    >
      <section
        className="modal"
        ref={element}
        role="dialog"
        aria-modal="true"
        aria-label={title}
      >
        <button
          className="modal-close icon-button"
          onClick={close}
          aria-label="Close"
        >
          <X size={20} />
        </button>
        <h2>{title}</h2>
        {subtitle && <p className="modal-subtitle">{subtitle}</p>}
        {children}
      </section>
    </div>
  );
}
function MetadataEditor({ track, close, perform }) {
  const [m, setM] = useState({
    ...track.metadata,
    artists: track.metadata.artists.join("; "),
  });
  return (
    <Modal
      title="The right details."
      subtitle="These tags are the source of truth for your audio files."
      close={close}
    >
      <div className="form-grid">
        {[
          "title",
          "artists",
          "album",
          "album_artist",
          "track_number",
          "disc_number",
          "release_date",
          "duration",
          "isrc",
          "artwork",
        ].map((k) => (
          <label key={k}>
            {k.replaceAll("_", " ")}
            <input
              value={m[k] || ""}
              onChange={(e) => setM({ ...m, [k]: e.target.value })}
            />
          </label>
        ))}
      </div>
      <label>
        Explicit status
        <select
          value={
            m.explicit === null || m.explicit === undefined
              ? "unknown"
              : String(m.explicit)
          }
          onChange={(e) =>
            setM({
              ...m,
              explicit:
                e.target.value === "unknown" ? null : e.target.value === "true",
            })
          }
        >
          <option value="unknown">Not supplied</option>
          <option value="true">Explicit</option>
          <option value="false">Clean</option>
        </select>
      </label>
      <p className="help">
        Separate artists with semicolons. Duration is in seconds.
      </p>
      <button
        className="secondary"
        style={{ marginRight: 10 }}
        onClick={async () => {
          const r = await perform(() => post(`/tracks/${track.id}/enrich`));
          if (r) {
            setM({ ...r.metadata, artists: r.metadata.artists.join("; ") });
          }
        }}
      >
        <RefreshCw size={15} />
        Enrich missing fields
      </button>
      <button
        className="primary"
        onClick={async () => {
          const r = await perform(
            () =>
              api(`/tracks/${track.id}`, {
                method: "PATCH",
                body: JSON.stringify({
                  ...m,
                  artists: m.artists
                    .split(";")
                    .map((a) => a.trim())
                    .filter(Boolean),
                }),
              }),
            "Metadata saved",
          );
          if (r) close();
        }}
      >
        Save metadata
        <Check size={16} />
      </button>
    </Modal>
  );
}
function LibraryPage({ page, revision, perform, search, setSearch, status }) {
  const [tracks, setTracks] = useState([]),
    [playlists, setPlaylists] = useState([]),
    [filter, setFilter] = useState("all"),
    [group, setGroup] = useState("All tracks"),
    [selected, setSelected] = useState(""),
    [edit, setEdit] = useState(null),
    [error, setError] = useState(""),
    [retryBusy, setRetryBusy] = useState(false);
  useEffect(() => {
    setSelected("");
    setGroup("All tracks");
    setFilter("all");
  }, [page]);
  useEffect(() => {
    const view =
      page === "Queue" ? "queue" : page === "Skipped" ? "skipped" : filter;
    api(`/tracks?view=${view}&q=${encodeURIComponent(search)}`)
      .then(setTracks)
      .catch((e) => setError(e.message));
    api("/playlists")
      .then(setPlaylists)
      .catch((e) => setError(e.message));
  }, [page, revision, filter, search]);
  useEffect(() => {
    if (page !== "Queue") return;
    const id = setInterval(
      () =>
        api(`/tracks?view=queue&q=${encodeURIComponent(search)}`)
          .then(setTracks)
          .catch(() => {}),
      2500,
    );
    return () => clearInterval(id);
  }, [page, search]);
  let visible = tracks;
  if (selected)
    visible = tracks.filter((t) =>
      page === "Playlists"
        ? t.playlists.includes(selected)
        : group === "Artists"
          ? t.metadata.artists.includes(selected)
          : (t.metadata.album || "Singles") === selected,
    );
  const groups =
    group === "Artists"
      ? [...new Set(tracks.flatMap((t) => t.metadata.artists))]
      : [...new Set(tracks.map((t) => t.metadata.album || "Singles"))];
  return (
    <section className="collection">
      {page === "Queue" && !!status.counts.failed && (
        <div className="queue-error-banner" role="alert">
          <Info size={23} />
          <div>
            <strong>
              {status.counts.failed}{" "}
              {status.counts.failed === 1 ? "download needs" : "downloads need"}{" "}
              attention
            </strong>
            <p>
              These downloads stopped after an error. You can retry them now.
              Sign-in or file-access errors may need fixing first.
            </p>
          </div>
          <button
            className="secondary"
            disabled={retryBusy}
            onClick={async () => {
              setRetryBusy(true);
              try {
                const result = await perform(() =>
                  post("/downloads/retry-failed"),
                );
                if (result)
                  await perform(
                    async () => result,
                    `${result.queued} failed downloads queued for retry`,
                  );
              } finally {
                setRetryBusy(false);
              }
            }}
          >
            <RefreshCw size={16} className={retryBusy ? "spin" : ""} />
            {retryBusy ? "Queuing…" : "Retry failed downloads"}
          </button>
        </div>
      )}
      {page === "Queue" && !!status.counts.retrying && (
        <div className="queue-retry-banner" role="status">
          <RefreshCw size={16} />
          <span>
            {status.counts.retrying}{" "}
            {status.counts.retrying === 1 ? "download is" : "downloads are"}{" "}
            waiting for an automatic retry.{" "}
            {status.paused
              ? "Retries are paused."
              : "Up to 3 retries, after 30 seconds, 2 minutes, and 5 minutes. Rate limits pause new downloads during cooldown."}
          </span>
        </div>
      )}
      {page === "Queue" && (
        <div className="queue-summary">
          {[
            ["Approved", status.counts.approved || 0],
            ["Downloading", status.counts.downloading || 0],
            ["Completed", status.counts.completed || 0],
            ["Needs attention", status.counts.failed || 0],
            ["Retry scheduled", status.counts.retrying || 0],
            ["Candidates rejected", status.rejected],
          ].map(([label, value]) => (
            <div
              key={label}
              className={
                label === "Needs attention" && value ? "queue-stat-failed" : ""
              }
            >
              <strong>{value}</strong>
              <span>{label}</span>
            </div>
          ))}
        </div>
      )}
      <div className="collection-toolbar">
        <div className="tabs">
          {page === "Library" ? (
            ["All tracks", "Artists", "Albums"].map((x) => (
              <button
                key={x}
                className={group === x ? "selected" : ""}
                onClick={() => {
                  setGroup(x);
                  setSelected("");
                }}
              >
                {x}
              </button>
            ))
          ) : (
            <h3>
              {page === "Queue"
                ? "Download queue"
                : page === "Skipped"
                  ? "Saved for another day"
                  : selected || "Your playlists"}
              <span className="count-pill">
                {page === "Playlists" && !selected
                  ? playlists.length
                  : visible.length}
              </span>
            </h3>
          )}
        </div>
        <div className="collection-tools">
          {page === "Playlists" && (
            <button
              className="secondary"
              onClick={() =>
                perform(
                  () => post("/playlists/sync"),
                  "M3U playlists synced. Run a scan in your music server.",
                )
              }
            >
              <RefreshCw size={15} />
              Sync to music server
            </button>
          )}
          {page === "Queue" && (
            <button
              className="text-button"
              onClick={async () => {
                const r = await perform(() => post("/downloads/retry-auth"));
                if (r)
                  await perform(
                    async () => r,
                    `${r.queued} sign-in failures requeued`,
                  );
              }}
            >
              Retry sign-in failures
            </button>
          )}

          <div className="search-input">
            <Search size={15} />
            <input
              placeholder="Search your library"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          {page === "Library" && (
            <select value={filter} onChange={(e) => setFilter(e.target.value)}>
              <option value="all">All statuses</option>
              <option value="downloaded">Downloaded</option>
              <option value="not_downloaded">Not downloaded</option>
              <option value="failed">Failed</option>
              <option value="skipped">Skipped</option>
            </select>
          )}
          <button
            className="icon-button"
            title="Rescan library"
            onClick={() => perform(() => post("/rescan"), "Library rescanned")}
          >
            <RefreshCw size={16} />
          </button>
        </div>
      </div>
      {error && <div className="notice">{error}</div>}
      {selected && (
        <button className="text-button back" onClick={() => setSelected("")}>
          <ArrowLeft size={14} />
          Back to {page === "Playlists"
            ? "playlists"
            : group.toLowerCase()} · {selected}
        </button>
      )}
      {page === "Playlists" && !selected ? (
        <div className="group-grid">
          {playlists.map((p, i) => (
            <button
              className="group-card"
              key={p.id}
              onClick={() => setSelected(p.name)}
            >
              <div className={`playlist-art color-${i % 4}`}>
                <FolderHeart size={46} />
                <span>TRACKSWIPE MIX</span>
              </div>
              <h3>{p.name}</h3>
              <p>
                {p.total} tracks · {p.downloaded || 0} downloaded
              </p>
              <small>
                {p.waiting || 0} waiting · {p.skipped || 0} skipped
              </small>
            </button>
          ))}
        </div>
      ) : page === "Library" && group !== "All tracks" && !selected ? (
        <div className="group-grid">
          {groups.map((name) => {
            const items = tracks.filter((t) =>
              group === "Artists"
                ? t.metadata.artists.includes(name)
                : (t.metadata.album || "Singles") === name,
            );
            return (
              <button
                className="group-card"
                key={name}
                onClick={() => setSelected(name)}
              >
                <Art src={items[0]?.metadata.artwork} />
                <h3>{name}</h3>
                <p>
                  {items.length} tracks ·{" "}
                  {new Set(items.map((t) => t.metadata.album)).size} albums
                </p>
                <small>
                  {new Set(items.flatMap((t) => t.playlists)).size} playlists
                </small>
              </button>
            );
          })}
        </div>
      ) : (
        <div className="track-list">
          {visible.map((t) => (
            <div
              className={`track-row ${t.status === "failed" ? "track-row-failed" : ""}`}
              key={t.id}
            >
              <Art src={t.metadata.artwork} small />
              <div className="row-title">
                <strong>{t.metadata.title || "Metadata needed"}</strong>
                <span>
                  {t.metadata.artists.join(", ") || t.metadata.spotify_id}
                </span>
                {t.error && <small className="error-text">{t.error}</small>}
                {t.status === "retrying" && (
                  <small className="retry-detail">
                    Automatic retry {t.retry_count}/3 ·{" "}
                    {status.paused
                      ? "Paused"
                      : `Scheduled for ${new Date(t.next_retry_at * 1000).toLocaleTimeString()}`}
                  </small>
                )}
                {t.status === "failed" && t.retry_count >= 3 && (
                  <small className="error-text">
                    All 3 automatic retries were used. Retry manually when
                    ready.
                  </small>
                )}
              </div>
              <span className="row-album">{t.metadata.album || "Single"}</span>
              <span className={`status-badge ${t.status}`}>
                {t.status === "downloading" && (
                  <LoaderCircle size={12} className="spin" />
                )}
                {labels[t.status]}
              </span>
              <span className="row-duration">
                {duration(t.metadata.duration)}
              </span>
              <div className="row-actions">
                {t.status === "skipped" ? (
                  <button
                    className="text-button"
                    onClick={() =>
                      perform(
                        () =>
                          post(`/tracks/${t.id}/decision`, {
                            action: "restore",
                          }),
                        "Restored to review",
                      )
                    }
                  >
                    Restore
                    <RefreshCw size={13} />
                  </button>
                ) : t.status === "failed" ? (
                  <button
                    className="text-button"
                    onClick={() =>
                      perform(
                        () =>
                          post(`/tracks/${t.id}/decision`, { action: "retry" }),
                        "Queued for retry",
                      )
                    }
                  >
                    Retry
                    <RefreshCw size={13} />
                  </button>
                ) : t.output_file ? (
                  <button
                    className="text-button"
                    title={t.output_file}
                    onClick={() =>
                      perform(
                        () => post(`/tracks/${t.id}/repair`),
                        "Metadata repaired. Original tags preserved in a backup.",
                      )
                    }
                  >
                    Repair tags
                  </button>
                ) : null}
                <button
                  className="icon-button"
                  title="Edit metadata"
                  onClick={() => setEdit(t)}
                >
                  <MoreHorizontal size={17} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
      {!tracks.length && page !== "Playlists" && (
        <Empty
          icon={page === "Queue" ? CloudDownload : Library}
          title={
            page === "Queue"
              ? "A good match is worth keeping."
              : "Nothing here. Yet."
          }
          text={
            page === "Queue"
              ? "Approve a match in Review and it will land here automatically."
              : "Import your collection or change your filters to find your tracks."
          }
        />
      )}
      {page === "Playlists" && !playlists.length && (
        <Empty
          icon={FolderHeart}
          title="A playlist for every side of you."
          text="Playlist names are preserved when you import. One track can live in many playlists without duplicating its audio."
        />
      )}
      {edit && (
        <MetadataEditor
          track={edit}
          close={() => setEdit(null)}
          perform={perform}
        />
      )}
    </section>
  );
}
function Empty({ icon: Icon, title, text }) {
  return (
    <div className="empty-standard">
      <div>
        <Icon size={30} />
      </div>
      <h2>{title}</h2>
      <p>{text}</p>
    </div>
  );
}
function HistoryPage({ revision }) {
  const [rows, setRows] = useState([]),
    [error, setError] = useState("");
  useEffect(() => {
    api("/history")
      .then(setRows)
      .catch((e) => setError(e.message));
  }, [revision]);
  return (
    <section className="collection">
      <div className="collection-toolbar">
        <h3>Every decision, remembered.</h3>
        <span className="muted">Most recent 1,000 events</span>
      </div>
      {error && <p>{error}</p>}
      {rows.map((r) => (
        <div className="history-row" key={r.id}>
          <span className={`history-icon ${r.action}`}>
            <History size={16} />
          </span>
          <div>
            <strong>{r.title || "Library activity"}</strong>
            <p>
              {r.action.replaceAll("-", " ")}
              {r.detail && <span> · {r.detail}</span>}
            </p>
          </div>
          <time>{new Date(r.created + "Z").toLocaleString()}</time>
        </div>
      ))}
      {!rows.length && (
        <Empty
          icon={History}
          title="A fresh start."
          text="Your imports, matches, skips, and downloads will leave a trail here."
        />
      )}
    </section>
  );
}
const toggleSections = {
  Matching: [
    [
      "prefer_topic",
      "Prefer Topic channels",
      "Prioritize clean, official audio releases.",
    ],
    [
      "prefer_music",
      "Prefer YouTube Music",
      "Use song and album metadata as ranking signals.",
    ],
    [
      "penalize_video",
      "Penalize music videos",
      "Avoid dialogue, cinematic intros, and outros.",
    ],
    ["ignore_live", "Penalize live versions"],
    ["ignore_covers", "Penalize covers & piano versions"],
    ["ignore_remixes", "Penalize unexpected remixes"],
    ["ignore_speed", "Penalize slowed / reverb / sped-up"],
    ["ignore_instrumental", "Penalize instrumental & karaoke"],
    [
      "auto_approve",
      "Automatic confidence mode",
      "Rechecks saved and new matches. Exact title/artist, duration within 2 seconds, and a Topic or YouTube Music source are required.",
    ],
  ],
  Audio: [
    [
      "allow_conversion",
      "Allow format conversion",
      "Conversion never improves the quality of the source.",
    ],
    [
      "embed_metadata",
      "Embed library metadata",
      "Your imported metadata is always the source of truth.",
    ],
    ["embed_artwork", "Embed album artwork"],
    [
      "normalize_filenames",
      "Replace spaces with underscores",
      "Unicode artist and song names remain intact.",
    ],
    [
      "keep_original",
      "Keep an original audio copy",
      "Stored in the temporary directory under originals/.",
    ],
  ],
  Review: [
    [
      "show_existing",
      "Show already downloaded tracks",
      "Use Repair tags for existing files. Duplicate downloads stay blocked.",
    ],
    ["show_skipped", "Show skipped tracks in review"],
    [
      "autoplay",
      "Automatically play previews",
      "Your browser may require a first click.",
    ],
    ["keyboard", "Keyboard shortcuts"],
    [
      "reduced_motion",
      "Reduced motion",
      "Minimize animations for a calmer experience.",
    ],
  ],
};
function SettingsPage({ settings, setSettings, perform, notify, refresh }) {
  const [tab, setTab] = useState("Library"),
    [draft, setDraft] = useState(settings),
    [browse, setBrowse] = useState(null),
    [dirs, setDirs] = useState(null),
    [restore, setRestore] = useState(null),
    [saving, setSaving] = useState(false);
  const update = (k, v) => setDraft((d) => ({ ...d, [k]: v }));
  const openDir = async (key, path) => {
    const r = await perform(() =>
      api("/directories?path=" + encodeURIComponent(path || draft[key])),
    );
    if (r) {
      setBrowse(key);
      setDirs(r);
    }
  };
  const save = async () => {
    setSaving(true);
    const r = await perform(
      () =>
        api("/settings", {
          method: "PUT",
          body: JSON.stringify(
            Object.fromEntries(
              Object.entries(draft).filter(([key]) => key !== "paused"),
            ),
          ),
        }),
      "Settings saved",
    );
    if (r) setSettings(r);
    setSaving(false);
    return r;
  };
  const example = () => {
    try {
      return draft.output_template.replace(
        /\{(\w+)\}/g,
        (_, k) =>
          ({
            artist: "Artist",
            album_artist: "Artist",
            album: "Album",
            title: "Your favorite song",
            track_number: "01",
            disc_number: "1",
            year: "2026",
            spotify_id: "spotify-id",
            ext: draft.audio_format === "best" ? "opus" : draft.audio_format,
          })[k] ?? `{${k}}`,
      );
    } catch {
      return "Check your template";
    }
  };
  return (
    <section className="settings-layout">
      <div className="settings-tabs">
        {[
          ["Library", Folder],
          ["Audio", AudioLines],
          ["Matching", Heart],
          ["Review", Layers3],
          ["Data", Database],
        ].map(([name, Icon]) => (
          <button
            className={name === tab ? "selected" : ""}
            key={name}
            onClick={() => setTab(name)}
          >
            <Icon size={17} />
            {name}
            <ChevronRight size={13} />
          </button>
        ))}
      </div>
      <div className="settings-content">
        <div className="settings-title">
          <div>
            <h2>
              {tab === "Data"
                ? "Your decisions are valuable."
                : `${tab} preferences`}
            </h2>
            <p>
              {tab === "Data"
                ? "Back them up. Take them with you."
                : "A few small choices. A library that feels like you."}
            </p>
          </div>
          {tab !== "Data" && (
            <button className="primary small" onClick={save} disabled={saving}>
              {saving ? (
                <LoaderCircle size={15} className="spin" />
              ) : (
                <Check size={15} />
              )}
              Save changes
            </button>
          )}
        </div>
        {tab === "Library" && (
          <>
            {[
              ["library_dir", "Music Library Directory"],
              ["temp_dir", "Temporary Download Directory"],
              ["import_dir", "Import Directory (optional)"],
            ].map(([key, label]) => (
              <label className="setting-field" key={key}>
                {label}
                <div className="input-action">
                  <input
                    value={draft[key]}
                    onChange={(e) => update(key, e.target.value)}
                  />
                  <button onClick={() => openDir(key)}>
                    <Folder size={17} />
                    Browse
                  </button>
                </div>
              </label>
            ))}
            <p className="help">
              Directories are on the machine running TrackSwipe. Docker paths
              refer to mounted container directories. Your browser file chooser
              remembers its own last import location.
            </p>
            <label className="setting-field">
              Output template
              <input
                value={draft.output_template}
                onChange={(e) => update("output_template", e.target.value)}
              />
            </label>
            <div className="template-preview">
              <Folder size={17} />
              {example()}
            </div>
            <p className="help">
              Variables: artist, album_artist, album, title, track_number,
              disc_number, year, spotify_id, ext. Wrap each in braces. Tracks
              without albums use Singles with the default template.
            </p>
            <div className="toggle-row">
              <div>
                <strong>Sync M3U playlists for Navidrome / Subsonic</strong>
                <p>
                  Automatically update portable playlists after imports,
                  downloads, skips, and rescans. Only existing audio files are
                  included.
                </p>
              </div>
              <button
                role="switch"
                aria-label="Automatic M3U playlist export"
                aria-checked={draft.playlist_auto_export}
                className={`toggle ${draft.playlist_auto_export ? "on" : ""}`}
                onClick={() =>
                  update("playlist_auto_export", !draft.playlist_auto_export)
                }
              >
                <i />
              </button>
            </div>
            <label className="setting-field">
              Playlist subdirectory
              <input
                value={draft.playlist_directory || "Playlists"}
                onChange={(e) => update("playlist_directory", e.target.value)}
              />
            </label>
            <p className="help">
              This directory is inside your music library. Relative audio paths
              work across Docker mounts. Enable playlist auto-import and scan
              this folder in Navidrome; Subsonic-compatible clients will see the
              server's imported playlists.
            </p>
            <button
              className="secondary"
              onClick={async () => {
                if (await save())
                  await perform(
                    () => post("/playlists/sync"),
                    "Playlists synced. Run a library scan in your music server.",
                  );
              }}
            >
              <FolderHeart size={15} />
              Sync playlists now
            </button>
            <button
              className="secondary"
              onClick={() =>
                perform(() => post("/rescan"), "Library scan complete")
              }
            >
              <RefreshCw size={16} />
              Rescan library
            </button>
          </>
        )}
        {tab === "Audio" && (
          <>
            <h3>YouTube authentication</h3>
            <p className="help">
              For videos that ask you to sign in. Credentials remain on this
              machine and are never included in database exports. Browser mode
              uses the selected local browser's session; Docker usually needs a
              cookies file.
            </p>
            <label className="setting-field">
              Authentication source
              <select
                value={draft.youtube_auth || "none"}
                onChange={(e) => update("youtube_auth", e.target.value)}
              >
                <option value="none">None (public videos)</option>
                <option value="file">Netscape cookies file</option>
                <option value="browser">Signed-in local browser</option>
              </select>
            </label>
            {draft.youtube_auth === "file" && (
              <label className="setting-field">
                Cookies file path
                <input
                  value={draft.youtube_cookies_file || ""}
                  placeholder="/data/private/youtube-cookies.txt"
                  onChange={(e) =>
                    update("youtube_cookies_file", e.target.value)
                  }
                />
                <span className="help">
                  Export YouTube cookies in Netscape format. The path must be
                  accessible to the backend. Do not commit or share this file.
                </span>
              </label>
            )}
            {draft.youtube_auth === "browser" && (
              <>
                <label className="setting-field">
                  Browser
                  <select
                    value={draft.youtube_browser || "firefox"}
                    onChange={(e) => update("youtube_browser", e.target.value)}
                  >
                    {[
                      "firefox",
                      "chrome",
                      "chromium",
                      "brave",
                      "edge",
                      "vivaldi",
                      "opera",
                      "safari",
                    ].map((name) => (
                      <option key={name}>{name}</option>
                    ))}
                  </select>
                </label>
                <label className="setting-field">
                  Browser profile (optional)
                  <input
                    value={draft.youtube_browser_profile || ""}
                    onChange={(e) =>
                      update("youtube_browser_profile", e.target.value)
                    }
                  />
                </label>
                <p className="help">
                  Run TrackSwipe as the same operating-system user as your
                  browser. Cookie extraction may need an unlocked keyring. No
                  cookies are read until a YouTube request runs.
                </p>
              </>
            )}
            <button
              className="secondary"
              onClick={async () => {
                const saved = await save();
                if (saved) {
                  const result = await perform(() =>
                    post("/downloads/retry-auth"),
                  );
                  if (result)
                    notify(
                      `${result.queued} authentication failures queued for retry`,
                    );
                }
              }}
            >
              <RefreshCw size={15} />
              Save & retry sign-in failures
            </button>

            <label className="setting-field">
              Preferred audio format
              <select
                value={draft.audio_format}
                onChange={(e) => update("audio_format", e.target.value)}
              >
                <option value="best">
                  Original / best audio (recommended)
                </option>
                <option value="m4a">M4A / AAC</option>
                <option value="opus">Opus</option>
                <option value="mp3">MP3 — convert only when needed</option>
              </select>
            </label>
            <div className="notice">
              <Info size={17} />
              Best available source audio. No artificial “320 kbps upgrades.”
            </div>
          </>
        )}
        {toggleSections[tab]?.map(([key, label, description]) => (
          <div className="toggle-row" key={key}>
            <div>
              <strong>{label}</strong>
              {description && <p>{description}</p>}
            </div>
            <button
              role="switch"
              aria-checked={draft[key]}
              aria-label={label}
              className={`toggle ${draft[key] ? "on" : ""}`}
              onClick={() => update(key, !draft[key])}
            >
              <i />
            </button>
          </div>
        ))}
        {tab === "Audio" && (
          <div className="toggle-row disabled">
            <div>
              <strong>ReplayGain analysis</strong>
              <p>
                Unavailable in this installation. Audio levels are preserved.
              </p>
            </div>
            <span className="count-pill">Not installed</span>
          </div>
        )}
        {tab === "Matching" && (
          <div className="notice">
            <Info size={17} />
            <span>
              Saving matching settings rechecks your saved candidates. The
              threshold is inclusive; additional safety rules are shown on each
              card.
            </span>
            <button
              onClick={async () => {
                const saved = await save();
                if (saved) {
                  const r = await perform(() => post("/auto-approve"));
                  if (r)
                    notify(
                      "Saved matches rechecked. Eligible matches are in the queue.",
                    );
                }
              }}
            >
              Apply now
            </button>
          </div>
        )}
        {tab === "Matching" && (
          <div className="form-grid">
            {[
              [
                "max_duration_difference",
                "Maximum duration difference (seconds)",
                1,
                120,
              ],
              ["candidate_count", "Candidates per provider", 1, 50],
              ["auto_threshold", "Auto-approval threshold (%)", 90, 100],
            ].map(([key, label, min, max]) => (
              <label className="setting-field" key={key}>
                {label}
                <input
                  type="number"
                  min={min}
                  max={max}
                  value={draft[key]}
                  onChange={(e) => update(key, Number(e.target.value))}
                />
              </label>
            ))}
          </div>
        )}
        {tab === "Review" && (
          <>
            <label className="setting-field">
              Preview volume · {draft.volume}%
              <input
                type="range"
                min="0"
                max="100"
                value={draft.volume}
                onChange={(e) => update("volume", Number(e.target.value))}
              />
            </label>
            <label className="setting-field">
              Animation intensity
              <select
                value={draft.animation_intensity}
                onChange={(e) =>
                  update("animation_intensity", Number(e.target.value))
                }
              >
                <option value={0}>Off</option>
                <option value={0.5}>Subtle</option>
                <option value={1}>Balanced</option>
                <option value={2}>Expressive</option>
              </select>
            </label>
          </>
        )}
        {tab === "Data" && (
          <>
            <div className="data-card">
              <span className="data-icon">
                <Database />
              </span>
              <div>
                <h3>Full library backup</h3>
                <p>
                  Tracks, playlists, decisions, candidates, settings, and
                  download history in a restorable SQLite database.
                </p>
              </div>
              <a className="secondary" href="/api/export/database" download>
                <Download size={16} />
                Back up
              </a>
            </div>
            <div className="data-card">
              <span className="data-icon">
                <FileMusic />
              </span>
              <div>
                <h3>Human-readable export</h3>
                <p>
                  All application records in JSON. Audio files are not included
                  in either export.
                </p>
              </div>
              <a className="secondary" href="/api/export/json" download>
                <Download size={16} />
                Export JSON
              </a>
            </div>
            <div className="data-card">
              <span className="data-icon">
                <History />
              </span>
              <div>
                <h3>Restore a backup</h3>
                <p>
                  Replace current state from a TrackSwipe SQLite backup. A
                  safety snapshot is saved first. Pause the process before
                  restoring.
                </p>
              </div>
              <label className="secondary file-button">
                <Upload size={16} />
                Choose backup
                <input
                  type="file"
                  accept=".sqlite3,.db,.sqlite"
                  onChange={(e) => setRestore(e.target.files[0])}
                />
              </label>
            </div>
            <p className="help">
              Back up your Music directory separately. Restored paths must exist
              on this machine; use Rescan Library after moving your audio.
            </p>
          </>
        )}
      </div>
      {browse && dirs && (
        <Modal title="Choose a directory" close={() => setBrowse(null)}>
          <div className="directory-path">{dirs.path}</div>
          <button
            className="text-button"
            onClick={() => openDir(browse, dirs.parent)}
          >
            <ArrowLeft size={15} />
            Parent directory
          </button>
          <div className="directory-list">
            {dirs.children.map((p) => (
              <button key={p} onClick={() => openDir(browse, p)}>
                <Folder size={17} />
                {p.split("/").pop()}
                <ChevronRight size={15} />
              </button>
            ))}
          </div>
          <button
            className="primary"
            onClick={() => {
              update(browse, dirs.path);
              setBrowse(null);
            }}
          >
            Use this directory
            <Check size={16} />
          </button>
        </Modal>
      )}
      {restore && (
        <Modal
          title="Restore this library?"
          subtitle="This replaces current decisions and settings. A safety backup will be saved on disk first."
          close={() => setRestore(null)}
        >
          <p>{restore.name}</p>
          <button
            className="primary"
            onClick={async () => {
              const f = new FormData();
              f.append("file", restore);
              const r = await perform(
                () => api("/restore", { method: "POST", body: f }),
                "Backup restored. Process remains paused.",
              );
              if (r) {
                const s = await api("/settings");
                setSettings(s);
                setDraft(s);
                setRestore(null);
                refresh();
              }
            }}
          >
            Restore backup
          </button>
        </Modal>
      )}
    </section>
  );
}
createRoot(document.getElementById("root")).render(<App />);
