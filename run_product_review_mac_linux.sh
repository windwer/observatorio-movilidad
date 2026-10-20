#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
export OBS_DEMO=1
export OBS_DB="$PWD/data/demo/observatorio_demo.sqlite3"
export OBS_PORT=8866
bash run_mac_linux.sh
