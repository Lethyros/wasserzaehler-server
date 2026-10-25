#!/bin/bash
# Vom PC aus: Projekt in den Container kopieren und installieren/aktualisieren.
#   ./system/deploy.sh root@<container>
set -euo pipefail
ZIEL="${1:?Aufruf: system/deploy.sh root@<container>}"
cd "$(dirname "$0")/.."
rsync -a --delete --exclude __pycache__ --exclude .pytest_cache --exclude .venv ./ "$ZIEL:/root/wasserzaehler-quelle/"
ssh "$ZIEL" 'bash /root/wasserzaehler-quelle/system/install.sh && systemctl restart wasserzaehler && sleep 2 && systemctl --no-pager status wasserzaehler | head -5'
