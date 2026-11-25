#!/bin/bash
# /etc/cron.d/ip-rules 的日更入口（06:15 full）；manual-watch 手工改动触发 offline 重生成。
# 只做：拉仓库 → 生成并发布 IP 地址表 → 提交推送。不登录 ROS。
set -euo pipefail
export GIT_TERMINAL_PROMPT=0
export GIT_SSH_COMMAND='ssh -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=15'
# 06:00 的域名日更持锁时，手工触发的 offline 刷新避开整点窗口（full 会等待锁）。
if test "${1:-full}" = offline; then
    case "$(date +%H%M)" in 0555|0605) exit 0 ;; esac
fi
exec 9>/tmp/ros-rules.lock
flock -w 240 9 || { echo '[ip-rules] existing rules job still holds the lock'; exit 1; }
cd /root/git
test "$(git branch --show-current)" = main
if test -n "$(git status --porcelain)"; then
    echo '[ip-rules] working tree is dirty; refusing to mix unrelated changes'
    exit 1
fi
echo "[ip-rules] $(date -Is) start ${1:-full}"
# Retry a previously unpushed commit; stop on conflicts, never force-push.
timeout 120 git pull --rebase --quiet origin main
args=()
case "${1:-full}" in
  full) ;;
  offline) args+=(--offline) ;;
  *) echo 'Usage: ip-rules-update [full|offline]'; exit 2 ;;
esac
/usr/bin/python3 /root/git/scripts/ip-rules/gen_direct.py "${args[@]}" \
  --publish-root /var/lib/ip-rules --static-dir /srv/github-mirror/static/ros

git add -- scripts/ip-rules/input/upstream scripts/ip-rules/output
if ! git diff --cached --quiet; then
    git commit -m "更新 IP 地址表 $(date '+%F %H:%M')" --quiet
fi
# Always retry push, including a clean rerun after a previous push failure.
timeout 120 git push origin main
echo "[ip-rules] $(date -Is) success $(git rev-parse --short HEAD)"
