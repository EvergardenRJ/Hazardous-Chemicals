#!/bin/sh
set -eu
cd /root/autodl-tmp/chemical_kb
export CHEMNEWS_DATA_DIR=/root/autodl-tmp/chemical_kb/data/news
mkdir -p "$CHEMNEWS_DATA_DIR/tmp"
export TMPDIR="$CHEMNEWS_DATA_DIR/tmp"
exec /root/miniconda3/envs/kb/bin/python -u -m app.explorer_api --host 127.0.0.1 --port 8503
