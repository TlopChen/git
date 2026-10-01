#!/bin/bash
# 发布：把管线 output/ 与 ROS 侧脚本送进内网 HTTP 目录（/ros/<文件>）。
# 只做拷贝 + 原子替换，不生成任何内容；HTTP 路径与文件名保持不变。
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