# Video Studio

Matt's local editing studio for several clients.

**Client names, folders and house rules are in `CLAUDE.local.md`** (on this Mac only, never committed; Claude Code loads it with this file). Read both. It's shared tooling, and **client media never crosses over**. Every agent that edits here reads this first. Set up 8 Nov 2026.

## The three rules
1. **Nothing goes out with a watermark.** Every file runs `release-check <file>` before it goes to a client's Ready to Post folder. It must PASS: at least 1080×1920, 9:16, metadata clean. A person must also look at the corner sheets it writes. Exports from Descript's free plan, CapCut's free plan or OpusClip are watermarked or 720p, so they never ship. Final renders come from this studio (ffmpeg / HyperFrames) or from Final Cut Pro.
2. **Clients stay separate.** Each client's media lives in `clients/<slug>/`. Never put one client's footage, music, captions or brand assets in another's folder, project or render (client agreements require this; see `CLAUDE.local.md`). Each project folder holds one client. Nothing that identifies a client goes in this repo.
3. **Agents never post, send or publish.** Agents make files. Matt approves. Matt or the client's poster posts. SupoClip's social publishing stays **off**. The ig-* skills only draft.

## Folders
- `clients/<client>/inbox`: raw clips land here, named `YYYY-MM-DD_<series>_<what>.<ext>`.
- `clients/<client>/projects`: one folder per video (HyperFrames projects, FCP libraries, SRTs).
- `clients/<client>/exports`: final files that passed `release-check`. Copy them to that client's Ready to Post folder.
- `clients/<client>/captions`: Whisper SRTs and caption text.
- `clients/<client>/voice.md`: that client's voice. The ig-* skills read this, **not** `~/.claude/instagram/voice.md`.
- `brand/<client>`: fonts, logos and colours for that client only.
- `templates/`: HyperFrames scaffolds and the IG voice template. They're client-neutral.
- `bin/`: `ffmpeg`, `ffprobe`, `whisper`, `yt-dlp`, `hyperframes`, `vertical`, `release-check`, `crowd_down` (default on live clips: Demucs crowd reduction). Run `source bin/env.sh` to put them on PATH.
- `tools/`: the HyperFrames install, SupoClip (running in Docker since 8 Nov 2026; never read or print `tools/supoclip/.env`), the IG skill source, and the Whisper models.

## Tools
| Need | Tool | Command |
|---|---|---|
| Transcribe (EN/PT, word-level SRT) | Whisper large-v3-turbo on Apple MLX | `whisper clip.mp4 --language pt --output-format srt --output-dir clients/<slug>/captions` |
| Download a reference or source video | yt-dlp | `yt-dlp -o 'clients/<slug>/inbox/%(title)s.%(ext)s' <url>`, only for content we own or are licensed to use |
| Cut to 9:16, normalise loudness, burn captions | ffmpeg via `vertical` | `vertical in.mov out.mp4 [captions.srt] [start] [end]` |
| Motion graphics, titles, lower thirds, stitched promos | HyperFrames (HTML → MP4, local, no watermark) | the `/hyperframes` skill, then `hyperframes render -o out.mp4` |
| Long-form → clips (**speech-led only**; music footage → studio pipeline or FCPXML) | SupoClip (Docker; local Whisper is very slow here; Claude Sonnet; publishing off) | `cd tools/supoclip && docker compose up -d`, then http://localhost:3107. Every SupoClip clip still passes `release-check` before it ships |
| Hooks, captions, plans | the ig-* skills (`/ig-reel`, `/ig-caption` …) | read `clients/<client>/voice.md` first |
| Finishing, multicam, colour | Final Cut Pro (if Matt subscribes to Apple Creator Studio) | |
| Find moments in music footage | loudness, movement and scene analysis → `scripts/contact_sheet.py` | method notes in `CLAUDE.local.md` |
| Reframe a landscape clip | `CROP_X=<px> FADE=0.3 vertical in out "" start end` | |
| Final Cut handoff | `scripts/make_fcpxml.py clips.json out.fcpxml` (vertical projects, markers; `"beat_markers": "bar"` adds bar markers) | File → Import → XML in Final Cut |
| Colour grade | `bin/grade` / `scripts/grade.py` (looks in `templates/looks.json`; client default = `grade_default` or Matt's last picked look) | `grade in.mp4 out.mp4 --client <slug>`; pick board: `grade.py board <slug> <srcs> --out <dir>` + `board_server.py` |
| Cut on the beat | `scripts/beat_snap.py` (uses `beats.py`) | `.venv/bin/python scripts/beat_snap.py edl.json --render out.mp4` |
| Industry interviews | `scripts/interview.py` (claude-watch vendored in `tools/vendor/claude-watch`, MIT) | `interview.py fetch <slug> <url> <slug-name>`; method in `templates/interview-summary.md` |
| Release gate | `release-check` | `release-check clients/<slug>/exports/x.mp4` |

## Content library and /video-studio (added 9 Nov 2026)
- **`/video-studio`** is a user-level skill. Its source is in `skill/video-studio/SKILL.md`, and `~/.claude/skills/video-studio` is a symlink to it, so it works from any project folder. It works out the project from the folder it's opened in, using `projects.json`, and only ever touches that project's sources.
- **`projects.json`** lists, for each project: its local folders, its Drive folder ids, its Dropbox paths, its posted logs, and its categories.
- **`scripts/library.py`**: `resolve` · `scan` · `add-remote` · `posted` · `list` · `tag` · `path` · `excluded` · `serve`. The index, tags, thumbnails and the posted ledger live in `clients/<slug>/library/`.
- **30-day rule:** anything posted in the last 30 days is left out of every list and the catalog. Log posts with `library.py posted`.
- **Catalog:** `python3 scripts/library.py serve <slug> --port 8780`, then open http://127.0.0.1:8780/. It has filters, sorting, categories, tags, 1–5 ratings and notes.
- **Editor (11 Nov 2026):** `library.py serve` opens `scripts/studio.html`, an editor laid out like Final Cut: Library sidebar, skimmable Browser, Viewer, Inspector, and a Timeline with a music lane, Snap to beat and Render. It uses Final Cut's keys (J/K/L, I/O, E, F). Run it with `.venv/bin/python` so beat snap works. The simple catalog is at `/catalog`. Since 11 Nov 2026 the editor also has these:
  - a collapsible Library and Inspector
  - a large search bar
  - mouse dragging to the timeline and the Music lane
  - Finder import into the inbox (clips, `references/`, `music/`)
  - song waveforms you can slip
  - **✦ Ask Claude**: answered live by the Claude Code CLI if it's signed in; otherwise queued for `/video-studio prompts`
- **Simple editor (13 Nov 2026):** `library.py serve` now opens `scripts/simple.html` at `/`. Matt asked for less: search-first (no library list), tag chips from AI auto-tags, voice search, clip and photo preview, six look swatches, a strip of shots, music from a link or file, cut to the beat, Make video. The Final-Cut-style editor moved to `/pro`. Helpers are in `scripts/studio_media.py` (proxies, look frames, music import, voice, auto-tags).
- **Music is a guide track:** songs imported from a link are muted in the finished file unless Matt ticks "I have the rights". Spotify and Apple Music audio is never downloaded; the title is matched on YouTube.
- **Clip selection (11 Nov 2026):** the catalog's left-hand folder tree is the clip-selection directory. Type a pick set name, then Pick and Set in/out on clips. Picks go to `clients/<slug>/library/picks.json`. Read them back with `library.py picks <slug> --set <name> --json`.

## One rating store (11 Nov 2026)
- **Every rating Matt gives** goes to `clients/<slug>/feedback/ratings.jsonl` through `scripts/ratings.py`, in one shape:
  - kind `clip` / `edit` / `look` / `pick`
  - overall 1–5, plus moment, look, sound and pacing
  - verdict, note, tags, timed notes, better_hook, and by `matt` / `claude`
- **Sources:** catalog stars, review pages, grade boards and pick sets all write there. Old 7-score lines are read as the 4 scores.
- **Backups:** `ratings.jsonl.bak-2026-11-11`, `picks-*.json` and `grade-pick-*.json` are kept.
- **New review pages** start from `templates/review-page.html`.

## Feedback loop (continuous improvement)
- **Matt reviews every batch** in a local review page. Each clip gets 1–5 scores for moment, framing, hook words, hook look, sound, length/pacing and overall, plus notes, issue tags, a Keep/Swap/Cut verdict, a rank, his own hook rewrite, and notes pinned to timestamps.
- **Run it:** `python3 scripts/review_server.py <batch folder with preview.html> clients/<client>/feedback/ratings.jsonl 8771`, then open http://localhost:8771/preview.html. Every save is appended; none are overwritten.
- **Before any edit for a client:** run `python3 scripts/feedback_summary.py <client>` and read `clients/<client>/feedback/learnings.md`. Apply what's there.
- **After Matt rates a batch:** add one learning line to `learnings.md`, following the rule at the top of that file.
- **Every new batch gets a review page.** Copy `templates/review-page.html` to `<batch>/preview.html` and set `BATCH` and `clips`.

## House rules from the clients (they win over any skill)
- **Each client's house rules are in `CLAUDE.local.md`.** Read them before any edit, caption or export for that client.
- **Released songs:** unless a client's rules say otherwise, add them with each platform's audio picker; never bake them into the file.
- Portuguese captions need a human read-through before export.
- HyperFrames telemetry is **off**. Don't run `hyperframes events`, even though its skill says to (it reports usage to HeyGen).

## Disk
This Mac had about 68 GB free on 8 Nov 2026. Keep raw footage on an external SSD. Clean `clients/*/projects` render caches after export (`hyperframes clean`).
