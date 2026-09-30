#!/bin/bash
# Fast manual-data-only refresh. No upstream source fetch.
# Usage: manual-refresh rules | direct-ip
set -euo pipefail

MODE="${1:-rules}"
case "$MODE" in
  direct-ip)
    exec /usr/local/bin/direct-ip-update dns
    ;;
  rules)
    ;;
  *)
    echo "Usage: manual-refresh rules|direct-ip" >&2
    exit 2
    ;;
esac

cd /root/git
exec 9>/tmp/ros-rules.lock
flock -w 60 9 || { echo '[manual-refresh] another rules job holds the lock'; exit 1; }

git pull --rebase --quiet origin main

# 1) proxy-domain: offline generator, only cached upstream source files.
/usr/bin/python3 /srv/github-mirror/gen_rules.py --offline --only proxy-domain
/usr/bin/python3 /srv/github-mirror/gen_oxi.py

# 2) cn-domains: offline generator from cached upstream files + manual-cn-domains.txt.
GEN_CN_OFFLINE=1 /usr/bin/python3 /srv/github-mirror/gen_cn.py

# 3) Copy only manual-affected outputs into Git archive.
cp /srv/github-mirror/static/ros/proxy-domain.rsc /root/git/ros/
cp /srv/github-mirror/static/ros/proxy-domain.domains.txt /root/git/ros/
cp /srv/github-mirror/static/ros/proxy-domain.exact.txt /root/git/ros/
cp /srv/github-mirror/static/ros/proxy-domain.oxi.txt /root/git/ros/
cp /srv/github-mirror/static/ros/cn-domains.oxi.txt /root/git/ros/

git add -- ros/proxy-domain.rsc ros/proxy-domain.domains.txt \
  ros/proxy-domain.exact.txt ros/proxy-domain.oxi.txt ros/cn-domains.oxi.txt

if ! git diff --cached --quiet; then
  git commit -m "手工域名快速刷新 $(date '+%F %T')" --quiet
fi

git push origin main
echo "[manual-refresh] rules success $(git rev-parse --short HEAD)"
