#!/bin/bash
# 发布域名管线产物与 ROS 侧脚本到内网 HTTP 目录（/ros/<文件>）。
# IP 地址表由 scripts/ip-rules 自己以 release + symlink 方式发布（/var/lib/ip-rules），
# 不经过本脚本。本脚本只做拷贝 + 原子替换，不生成内容；HTTP 路径与文件名保持不变。
set -euo pipefail
REPO="${REPO:-/root/git}"
DST="${DST:-/srv/github-mirror/static/ros}"
install -d "$DST"

pub() {
  local src="$1" name tmp
  name="$(basename "$src")"
  [ -f "$src" ] || return 0
  tmp="$DST/.tmp.$$.$name"
  cp -f "$src" "$tmp"
  mv -f "$tmp" "$DST/$name"
  echo "[publish] $name  $(stat -c%s "$DST/$name") bytes"
}

for f in "$REPO"/scripts/domain-rules/output/*.rsc \
         "$REPO"/scripts/domain-rules/output/*.txt \
         "$REPO"/scripts/ros-side/*.rsc ; do
  [ -e "$f" ] || continue
  pub "$f"
done
