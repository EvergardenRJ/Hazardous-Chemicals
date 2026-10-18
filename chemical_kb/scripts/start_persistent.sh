#!/bin/bash
set -eu
BASE=/root/autodl-tmp/chemical_kb
CONFIG="$BASE/deploy/autostart-supervisor.ini"
PIDFILE="$BASE/deploy/autostart-supervisor.pid"
mkdir -p "$BASE/logs" "$BASE/data/news/tmp"
exec 9>"$BASE/deploy/autostart-launch.lock"
flock -x 9
if [ -s "$PIDFILE" ]; then
    PID=$(cat "$PIDFILE")
    if [ -r "/proc/$PID/cmdline" ] && tr '\0' ' ' <"/proc/$PID/cmdline" | grep -Fq -- "$CONFIG"; then
        /bin/supervisord -c "$CONFIG" ctl start all >/dev/null 2>&1 || true
        echo "Chemical project supervisor already running ($PID)"
        exit 0
    fi
fi
/bin/supervisord -c "$CONFIG" -d 9>&-
echo "Chemical project supervisor started"
