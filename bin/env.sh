# Source this to use the studio tools:  source "<studio folder>/bin/env.sh"
# Works from bash or zsh, wherever the repo is cloned.
if [ -n "${ZSH_VERSION:-}" ]; then _vs_here="${(%):-%x}"; else _vs_here="${BASH_SOURCE[0]:-$0}"; fi
export STUDIO="$(cd "$(dirname "$_vs_here")/.." && pwd)"
export PATH="$STUDIO/bin:$STUDIO/.venv/bin:$PATH"
export HF_HOME="$STUDIO/tools/models"
unset _vs_here
