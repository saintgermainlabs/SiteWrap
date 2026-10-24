#!/usr/bin/env bash
# Remove every SiteWrap launcher and the ~/.local/bin/webapp link.
# Site profiles (~/.local/share/webapps/<id>: logins, cookies) are kept unless --purge.
set -euo pipefail
APP_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"
cd "$APP_DIR"
echo "• removing launchers"
if [[ -x .venv/bin/python ]]; then
    PYTHONPATH="$APP_DIR" .venv/bin/python -m sitewrap.desktop uninstall
else
    A="${SITEWRAP_APPS_DIR:-$HOME/.local/share/applications}"
    grep -lE '^X-SiteWrap-(Id|Dashboard)=' "$A"/sitewrap*.desktop 2>/dev/null | xargs -r rm -v
    command -v update-desktop-database >/dev/null && update-desktop-database "$A" || true
fi
for b in webapp sitewrap; do
    if [[ "$(readlink -f "$HOME/.local/bin/$b" 2>/dev/null)" == "$APP_DIR/bin/webapp" ]]; then
        rm -f "$HOME/.local/bin/$b"; echo "• removed ~/.local/bin/$b"
    fi
done
if [[ "${1:-}" == "--purge" ]]; then
    rm -rf "${SITEWRAP_DATA:-$HOME/.local/share/webapps}"; echo "• removed site profiles"
else
    echo "• kept site profiles in ${SITEWRAP_DATA:-$HOME/.local/share/webapps} (use --purge to delete)"
fi
