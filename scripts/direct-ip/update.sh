#!/bin/bash
# Called by /etc/cron.d/direct-ip. Shares the existing rules/Git lock.
set -euo pipefail
export GIT_TERMINAL_PROMPT=0
export GIT_SSH_COMMAND='ssh -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=15'
# Leave the existing 06:00 non-waiting cron enough room to acquire its lock.
if test "${1:-full}" = dns; then
    case "$(date +%H%M)" in 0555|0605) exit 0 ;; esac
fi
exec 9>/tmp/ros-rules.lock
flock -w 240 9 || { echo '[direct-ip] existing rules job still holds the lock'; exit 1; }
cd /root/git
test "$(git branch --show-current)" = main
if test -n "$(git status --porcelain)"; then
    echo '[direct-ip] working tree is dirty; refusing to mix unrelated changes'
    exit 1
fi
echo "[direct-ip] $(date -Is) start ${1:-full}"
# Retry a previously unpushed commit; stop on conflicts, never force-push.
timeout 120 git pull --rebase --quiet origin main
args=()
case "${1:-full}" in
  full) ;;
  dns) args+=(--dns-only) ;;
  *) echo 'Usage: direct-ip-update [full|dns]'; exit 2 ;;
esac
/usr/bin/python3 /root/git/scripts/direct-ip/gen_direct.py "${args[@]}" \
  --publish-root /var/lib/direct-ip --static-dir /srv/github-mirror/static/ros

git add -- scripts/direct-ip/raw scripts/direct-ip/output
if ! git diff --cached --quiet; then
    git commit -m "更新直连 IPv4 地址表 $(date '+%F %H:%M')" --quiet
fi
# Always retry push, including a clean rerun after a previous push failure.
timeout 120 git push origin main
echo "[direct-ip] $(date -Is) success $(git rev-parse --short HEAD)"
