#!/usr/bin/env bash
# 广州侧：把 GitHub oxidns-images 分支里的 OxiDNS 镜像 tar 发布到 HTTP 目录（/ros/），供 ROS 按需拉取。
# 设计要点：用专用浅克隆（/srv/oxidns-images），不碰 /root/git（那里有日更管线，抢 .git 锁会互相打架）；
#           只做"搬运 + sha256 校验 + 原子替换"，不访问 Docker Hub；失败保留旧文件并非 0 退出。
set -euo pipefail

REPO_DIR=/srv/oxidns-images
REMOTE=git@github.com:TlopChen/git.git
BRANCH="${OXIDNS_IMG_BRANCH:-oxidns-images}"
STATIC=/srv/github-mirror/static/ros
LOG=/var/log/oxidns-image-sync.log

log() { printf '%s %s\n' "$(date '+%F %T')" "$*" | tee -a "$LOG"; }

if [ ! -d "$REPO_DIR/.git" ]; then
  log "首次克隆 $BRANCH → $REPO_DIR"
  git clone --quiet --depth 1 --branch "$BRANCH" "$REMOTE" "$REPO_DIR" >>"$LOG" 2>&1 \
    || { log "FAIL clone $BRANCH"; exit 1; }
else
  git -C "$REPO_DIR" fetch --quiet --depth 1 origin "$BRANCH" >>"$LOG" 2>&1 \
    || { log "FAIL fetch $BRANCH"; exit 1; }
  git -C "$REPO_DIR" reset --quiet --hard FETCH_HEAD
fi

MANIFEST_FILE="$REPO_DIR/oxidns/manifest.json"
[ -f "$MANIFEST_FILE" ] || { log "FAIL manifest.json 不存在"; exit 1; }
MANIFEST="$(cat "$MANIFEST_FILE")"
TAG="$(printf '%s' "$MANIFEST"  | python3 -c 'import json,sys;print(json.load(sys.stdin)["latest"]["tag"])')"
FILE="$(printf '%s' "$MANIFEST" | python3 -c 'import json,sys;print(json.load(sys.stdin)["latest"]["file"])')"
SHA="$(printf '%s' "$MANIFEST"  | python3 -c 'import json,sys;print(json.load(sys.stdin)["latest"]["sha256"])')"
SIZE="$(printf '%s' "$MANIFEST" | python3 -c 'import json,sys;print(json.load(sys.stdin)["latest"]["bytes"])')"
SRC="$REPO_DIR/oxidns/$FILE"
[ -f "$SRC" ] || { log "FAIL 分支里没有 $FILE"; exit 1; }

GOT="$(sha256sum "$SRC" | awk '{print $1}')"
[ "$GOT" = "$SHA" ] || { log "FAIL sha256 $FILE got=$GOT want=$SHA"; exit 1; }
[ "$(stat -c%s "$SRC")" = "$SIZE" ] || { log "FAIL size $FILE"; exit 1; }

mkdir -p "$STATIC"
install -m 0644 "$SRC" "$STATIC/.$FILE.tmp"
mv -f "$STATIC/.$FILE.tmp" "$STATIC/$FILE"
printf '%s' "$MANIFEST" > "$STATIC/oxidns-image.json.tmp"
mv -f "$STATIC/oxidns-image.json.tmp" "$STATIC/oxidns-image.json"
log "OK $TAG -> $FILE ($SIZE bytes, sha256 ${SHA:0:12}...)"
