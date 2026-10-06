#!/usr/bin/env bash
# Resume only queued main-corpus chunks with CPU Schema/Case retrieval.
set -euo pipefail

cd /root/autodl-tmp/chemical_kb
PY=/root/miniconda3/envs/kb/bin/python
DB=data/kg/batch_extraction/corpus.sqlite
CHECKPOINTS=/autodl-fs/data/alpha-corpus-checkpoints
LOCK=data/kg/batch_extraction/edcr_case.lock

exec 9>"$LOCK"
if ! flock -n 9; then
  echo "Another EDC+R+Case runner owns the corpus lock" >&2
  exit 1
fi

queued() {
  "$PY" -c 'import sqlite3,sys; db=sqlite3.connect(sys.argv[1]); print(db.execute("SELECT COUNT(*) FROM chunks WHERE status = ?", ("queued",)).fetchone()[0])' "$DB"
}

while true; do
  before=$(queued)
  echo "queued_before=$before"
  if (( before == 0 )); then
    echo "Main queued corpus complete; failed chunks and audits are separate stages"
    exit 0
  fi

  set +e
  "$PY" scripts/kg/extract_corpus.py     --edc-r-case --case-success-k 1 --case-failure-k 1     --batch-size 4 --max-seconds 21600
  result=$?
  set -e

  "$PY" scripts/kg/checkpoint_corpus.py --db "$DB" --out-dir "$CHECKPOINTS"
  after=$(queued)
  echo "queued_after=$after exit_code=$result"
  if (( result != 0 )); then
    echo "Extraction stopped after an error; inspect the log before resuming" >&2
    exit "$result"
  fi
  if (( after >= before )); then
    echo "No queued progress in this interval; stopping instead of looping" >&2
    exit 2
  fi
done
