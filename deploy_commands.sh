#!/usr/bin/env bash
set -euo pipefail
python -m py_compile app/*.py
git add .
git commit -m "feat: merge media downloader into NotebookLM bot" || true
git push
# Railway variables, run after railway login/link if needed:
railway variable set DOWNLOAD_MAX_FILE_MB=45
railway variable set DOWNLOAD_TIMEOUT_SECONDS=900
railway variable set EXTRACT_TIMEOUT_SECONDS=120
railway variable set KEEPALIVE_ENABLED=true
railway variable set KEEPALIVE_INTERVAL_SECONDS=240
