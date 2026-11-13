# Video Studio

A local, Claude-native editing studio for short-form social video. It runs on a Mac, keeps every client's footage separate, and never posts anything on its own.

- **Editor:** a browser workspace laid out like Final Cut Pro. It has a Library, a skimmable Browser, a Viewer, an Inspector, and a Timeline with a music lane, beat snapping and rendering.
- **✦ Ask Claude:** describe the cut you want. Claude picks clips and builds the timeline, and Undo reverses it. Bigger jobs go to Claude Code.
- **Colour grading:** six looks, a board for picking one, and a default per client.
- **Beat matching:** every cut snaps to the music's beat, half-bar or bar.
- **One rating store:** stars, review scores, grade picks and clip picks all feed the improvement loop.
- **Industry interviews:** pull a transcript and write a summary with timestamped, verbatim quote candidates.
- **Captions and finishing:** Whisper on Apple Silicon, burned-in captions at 9:16, crowd-noise reduction, a Final Cut XML handoff, and a release check that blocks watermarks and low resolution.

## Install
You need a Mac with Apple Silicon, Python 3.11 or newer, and ffmpeg (`brew install ffmpeg`).

```bash
git clone <this repo> "Video Studio"
cd "Video Studio"
./install.sh            # add --light to skip Demucs/torch, --hyperframes for motion titles
```

The installer:
- makes `.venv` and installs the packages in `requirements*.txt`
- links ffmpeg into `bin/`
- creates `projects.json` from `projects.example.json`
- links the `/video-studio` skill into `~/.claude/skills/`

Whisper downloads its model (about 1.6 GB) the first time you use it.

For live **Ask Claude**, sign in to Claude Code once: run `claude`, then `/login`.

## Use
1. **Register a client project:** in Claude Code, inside that project's folder, run `/video-studio setup`. It records the project's local, Drive and Dropbox folders in `projects.json`.
2. **Open the editor:** run `/video-studio`, or start it yourself:
   ```bash
   .venv/bin/python scripts/library.py serve <project> --port 8780
   ```
   Then open http://127.0.0.1:8780/.
3. **Cut:** skim clips, mark I and O, then press E or drag clips onto the timeline. Drop a song on the Music lane, then use Snap to beat, then Render. Finished files land in `clients/<project>/exports/` and must pass `release-check`.

`skill/video-studio/SKILL.md` lists every command (sync, find, pick, grade, beatcut, edit, caption, score, review, improve, interview, prompts, posted, setup). `CLAUDE.md` holds the house rules agents follow.

## What's in the repo
| Path | What |
|---|---|
| `scripts/` | `library.py` (library, editor server, CLI), `studio.html` (editor), `studio_ai.py`, `beat_snap.py`, `beats.py`, `grade.py`, `ratings.py`, `interview.py`, `make_fcpxml.py`, `review_server.py`, `board_server.py`, plus the shell tools |
| `bin/` | wrappers: `vertical`, `grade`, `crowd_down`, `release-check`, `whisper`, `yt-dlp`, `hyperframes`, `env.sh` |
| `templates/` | looks, review page, grade board, interview method, IG voice template |
| `skill/video-studio/` | the Claude Code skill |
| `.claude/skills/` | HyperFrames and ig-* agent skills (third-party, with their licences) |
| `tools/vendor/claude-watch` | vendored, MIT |
| `docs/setup-log.md` | how the original studio was set up and tested (8–11 Nov 2026) |

**Not in the repo (git-ignored):**
- client media and brand files (`clients/`, `brand/`, `downloads/`)
- `projects.json`
- `.venv`, the models, ffmpeg binaries, HyperFrames and SupoClip installs
- any `.env`

Client material never goes into git.

## Rules it keeps
- Agents make files. A person approves and posts them. Nothing is uploaded or published automatically.
- Clients stay separate. Every command is scoped to one project.
- Nothing ships with a watermark or below 1080×1920.
- Anything posted in the last 30 days is hidden from the library.
