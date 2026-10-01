#!/bin/bash
# 手工部分快速刷新：不拉上游，只用已验证快照重生成手工相关产物。
# Usage: manual-refresh rules | direct-ip
set -euo pipefail
MODE="${1:-rules}"
case "$MODE" in
  direct-ip) exec /usr/local/bin/direct-ip-update dns ;;
  rules) ;;
  *) echo "Usage: manual-refresh rules|direct-ip" >&2; exit 2 ;;
esac

REPO=/root/git
R="$REPO/scripts/domain-rules"
cd "$REPO"
exec 9>/tmp/ros-rules.lock
flock -w 60 9 || { echo '[manual-refresh] another rules job holds the lock'; exit 1; }

git pull --rebase --autostash --quiet origin main

/usr/bin/python3 "$R/gen_rules.py" --offline --only proxy-domain
/usr/bin/python3 "$R/gen_oxi.py"
GEN_CN_OFFLINE=1 /usr/bin/python3 "$R/gen_cn.py"
"$REPO/scripts/_infra/publish.sh"

git add -A
if ! git diff --cached --quiet; then
  git commit -m "手工域名快速刷新 $(date '+%F %T')" --quiet
fi
git push origin main
echo "[manual-refresh] rules success $(git rev-parse --short HEAD)"