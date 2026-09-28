#!/usr/bin/env bash
set -euo pipefail
cd /root/autodl-tmp/chemical_kb
PYTHON=/root/miniconda3/envs/kb/bin/python
DB=data/kg/batch_extraction/corpus.sqlite
INITIAL_PID=9797
count_status() {
  "$PYTHON" -c 'import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); print(c.execute("SELECT COUNT(*) FROM chunks WHERE status=?", (sys.argv[2],)).fetchone()[0])' "$DB" "$1"
}
while ps -ww -p "$INITIAL_PID" -o args= 2>/dev/null | grep -q 'scripts/kg/extract_corpus.py --batch-size 4'; do
  sleep 60
done
while [[ "$(count_status queued)" -gt 0 ]]; do
  "$PYTHON" -u scripts/kg/extract_corpus.py --batch-size 4 >> /tmp/alpha_corpus_full.log 2>&1
done
"$PYTHON" -u scripts/kg/extract_corpus.py --batch-size 2 --retry-failed >> /tmp/alpha_corpus_retry.log 2>&1
"$PYTHON" -u scripts/kg/audit_corpus_candidates.py --static-only >> /tmp/alpha_corpus_audit.log 2>&1
"$PYTHON" -u scripts/kg/audit_corpus_candidates.py --batch-size 4 >> /tmp/alpha_corpus_audit.log 2>&1
date -Is