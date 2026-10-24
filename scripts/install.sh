#!/usr/bin/env bash
# Build the venv (uv, like ToolBox), link ~/.local/bin/webapp, and (re)generate one .desktop
# launcher per site in ~/.local/share/applications. Launchers of sites removed from sites.yaml
# are deleted. Re-run after editing sites.yaml.
#   scripts/install.sh               venv + launchers
#   scripts/install.sh --venv-only   just the venv
set -euo pipefail
APP_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"
cd "$APP_DIR"
unset VIRTUAL_ENV PYTHONHOME
if [[ ! -x .venv/bin/python ]] || ! .venv/bin/python -c 'import PySide6.QtWebEngineWidgets, yaml' 2>/dev/null; then
    echo "• building .venv"
    if command -v uv >/dev/null; then
        [[ -x .venv/bin/python ]] || uv venv -q --python 3.13 .venv 2>/dev/null || uv venv -q .venv
        uv pip install -q --python .venv/bin/python -r pyproject.toml --extra dev
    else
        python3 -m venv .venv && .venv/bin/pip install -q 'pyside6>=6.6.0' 'pyyaml>=6.0' pytest pytest-qt
    fi
fi
[[ "${1:-}" == "--venv-only" ]] && exit 0

if [[ -z "${SITEWRAP_SITES:-}" && ! -e sites.yaml ]]; then
    cp sites.example.yaml sites.yaml
    echo "• created sites.yaml from sites.example.yaml: edit it, then re-run scripts/install.sh"
fi

mkdir -p "$HOME/.local/bin"
ln -sfn "$APP_DIR/bin/webapp" "$HOME/.local/bin/webapp"
ln -sfn "$APP_DIR/bin/webapp" "$HOME/.local/bin/sitewrap"
echo "• ~/.local/bin/webapp, ~/.local/bin/sitewrap → $APP_DIR/bin/webapp"
echo "• launchers in ${SITEWRAP_APPS_DIR:-$HOME/.local/share/applications}:"
QT_QPA_PLATFORM=offscreen PYTHONPATH="$APP_DIR" .venv/bin/python -m sitewrap.desktop install "$@"
if command -v desktop-file-validate >/dev/null; then
    for f in "${SITEWRAP_APPS_DIR:-$HOME/.local/share/applications}"/sitewrap*.desktop; do
        [[ -e "$f" ]] && desktop-file-validate "$f" && echo "  ✓ valid: $(basename "$f")"
    done
fi
