#!/usr/bin/env bash
# 放在广州节点：/root/git/scripts/_infra/oxidns-image-sync.sh
# 作用：把 GitHub oxidns-images 分支里的 OxiDNS 镜像 tar 同步到 HTTP 发布目录（/ros/），供 ROS 按需拉取。
# 只做“搬运 + 校验 + 原子替换”，不访问 Docker Hub；失败保留旧文件并非 0 退出。
set -euo pipefail

REPO=/root/git
BRANCH="${OXIDNS_IMG_BRANCH:-oxidns-images}"
STATIC=/srv/github-mirror/static/ros
LOG=/var/log/oxidns-image-sync.log

log() { printf '%s %s\n' "$(date '+%F %T')" "$*" | tee -a "$LOG"; }

cd "$REPO"
git fetch --depth 1 origin "$BRANCH" >>"$LOG" 2>&1

MANIFEST="$(git show FETCH_HEAD:oxidns/manifest.json)"
TAG="$(printf '%s' "$MANIFEST" | python3 -c 'import json,sys;print(json.load(sys.stdin)["latest"]["tag"])')"
FILE="$(printf '%s' "$MANIFEST" | python3 -c 'import json,sys;print(json.load(sys.stdin)["latest"]["file"])')"
SHA="$(printf '%s' "$MANIFEST" | python3 -c 'import json,sys;print(json.load(sys.stdin)["latest"]["sha256"])')"
SIZE="$(printf '%s' "$MANIFEST" | python3 -c 'import json,sys;print(json.load(sys.stdin)["latest"]["bytes"])')"

mkdir -p "$STATIC"
TMP="$STATIC/.$FILE.tmp"
git show "FETCH_HEAD:oxidns/$FILE" > "$TMP"
GOT="$(sha256sum "$TMP" | awk '{print $1}')"
if [ "$GOT" != "$SHA" ]; then log "FAIL sha256 $FILE got=$GOT want=$SHA"; rm -f "$TMP"; exit 1; fi
if [ "$(stat -c%s "$TMP")" != "$SIZE" ]; then log "FAIL size $FILE"; rm -f "$TMP"; exit 1; fi
mv -f "$TMP" "$STATIC/$FILE"
printf '%s' "$MANIFEST" > "$STATIC/oxidns-image.json.tmp"
mv -f "$STATIC/oxidns-image.json.tmp" "$STATIC/oxidns-image.json"
log "OK $TAG -> $FILE ($SIZE bytes, sha256 $(printf '%s' "$SHA" | cut -c1-12)...)"
