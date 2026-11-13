#!/bin/bash
# Video Studio installer (macOS, Apple Silicon).
#   ./install.sh                 Python env + all tools + link the /video-studio skill into Claude Code
#   ./install.sh --light         skip Demucs/torch (crowd-noise reduction), about 1 GB less
#   ./install.sh --no-skill      don't touch ~/.claude/skills
#   ./install.sh --hyperframes   also install HyperFrames (needs Node/npm) into tools/hyperframes
# Safe to run again. It never deletes media and never overwrites projects.json.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIGHT=0; SKILL=1; HF=0
for a in "$@"; do case "$a" in
  --light) LIGHT=1;; --no-skill) SKILL=0;; --hyperframes) HF=1;;
  -h|--help) sed -n '2,8p' "$0"; exit 0;; *) echo "Unknown option $a"; exit 2;; esac; done
say(){ printf '\033[1m%s\033[0m\n' "$*"; }
warn(){ printf '\033[33m! %s\033[0m\n' "$*"; }

[[ "$(uname -s)" == "Darwin" ]] || warn "Built for macOS. Whisper (MLX) needs Apple Silicon."
[[ "$(uname -m)" == "arm64" ]] || warn "Not Apple Silicon: mlx-whisper won't install; captions won't work."

# 1. Python 3.11+
PY=""
for c in python3.13 python3.12 python3.11 python3; do
  if command -v "$c" >/dev/null && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then PY="$(command -v "$c")"; break; fi
done
[[ -n "$PY" ]] || { echo "Python 3.11 or newer is needed (python.org installer or Homebrew)."; exit 1; }
say "1/5 Python: $PY ($("$PY" --version 2>&1))"
[[ -x "$HERE/.venv/bin/python" ]] || "$PY" -m venv "$HERE/.venv"
"$HERE/.venv/bin/python" -m pip install -q --upgrade pip
say "2/5 Installing Python packages (first time takes a few minutes)"
"$HERE/.venv/bin/pip" install -q -r "$HERE/requirements.txt"
if [[ $LIGHT == 0 ]]; then "$HERE/.venv/bin/pip" install -q -r "$HERE/requirements-audio.txt"; else warn "Skipped Demucs: bin/crowd_down won't work (--light)."; fi

# 2. ffmpeg / ffprobe (not in the repo: about 130 MB)
say "3/5 ffmpeg"
for t in ffmpeg ffprobe; do
  if [[ -x "$HERE/bin/$t" ]]; then echo "  $t: already in bin/";
  elif command -v "$t" >/dev/null; then ln -sf "$(command -v "$t")" "$HERE/bin/$t"; echo "  $t: linked to $(command -v "$t")";
  else warn "$t not found. Install it (brew install ffmpeg, or a notarised build from https://ffmpeg.martin-riedl.de), then run ./install.sh again."; fi
done

# 3. Folders and config
say "4/5 Folders and config"
mkdir -p "$HERE/clients" "$HERE/brand" "$HERE/downloads" "$HERE/tools/models"
if [[ ! -f "$HERE/projects.json" ]]; then cp "$HERE/projects.example.json" "$HERE/projects.json"; echo "  Made projects.json from the example. Register a project with /video-studio setup."; else echo "  projects.json kept."; fi
chmod +x "$HERE"/bin/* "$HERE"/scripts/*.py "$HERE"/scripts/{crowd_down,vertical,release-check} 2>/dev/null || true

if [[ $HF == 1 ]]; then
  if command -v npm >/dev/null; then mkdir -p "$HERE/tools/hyperframes"; (cd "$HERE/tools/hyperframes" && [[ -f package.json ]] || npm init -y >/dev/null; npm install -q hyperframes@^0.9.23); echo "  HyperFrames installed. Turn telemetry off as in docs/setup-log.md.";
  else warn "npm not found: skipped HyperFrames."; fi
fi

# 4. Claude Code skill
say "5/5 Claude Code skill"
if [[ $SKILL == 1 ]]; then
  mkdir -p "$HOME/.claude/skills"; L="$HOME/.claude/skills/video-studio"
  if [[ -e "$L" && ! -L "$L" ]]; then mv "$L" "$L.bak-$(date +%Y%m%d%H%M%S)"; echo "  Moved your old copy aside: $L.bak-*"; fi
  ln -sfn "$HERE/skill/video-studio" "$L"; echo "  /video-studio -> $HERE/skill/video-studio"
else echo "  Skipped (--no-skill)."; fi

# Check
"$HERE/.venv/bin/python" -c "import numpy, yt_dlp, certifi; print('  python packages OK')"
"$HERE/.venv/bin/python" -m py_compile "$HERE"/scripts/*.py && echo "  scripts compile OK"
say "Done. Open the editor for a registered project:"
echo "  cd \"$HERE\" && .venv/bin/python scripts/library.py serve <project> --port 8780   ->  http://127.0.0.1:8780/"
echo "For live ✦ Ask Claude, sign in to Claude Code once: run claude, then /login."
