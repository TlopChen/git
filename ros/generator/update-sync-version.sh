#!/bin/bash
# Publish a content hash of the six ROS-synced tables for the ROS-side watcher.
set -euo pipefail
cd /srv/github-mirror/static/ros
files=(cn-telecom.rsc cn-mobile.rsc blacklist.rsc direct-ipv4.rsc direct-ipv4-nocm.rsc direct-ipv4-noct.rsc)
for f in "${files[@]}"; do
    if [ ! -e "$f" ]; then
        echo "[sync-version] missing $f" >&2
        exit 1
    fi
done
tmp=".sync-version.$$"
sha256sum "${files[@]}" | sha256sum | awk '{print $1}' > "$tmp"
mv "$tmp" sync-version.txt
chmod 644 sync-version.txt
echo "[sync-version] $(cat sync-version.txt)"
