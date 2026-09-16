#!/usr/bin/env python3
"""Fetch binary rule assets (geosite.dat / geoip.dat) into static/ros/ so that
downstream consumers (oxidns) can pull them over the internal mirror.

Sources are GitHub release assets; falls back to the previous local copy on failure.
"""
import os, time, urllib.request

OUT_DIR = "/srv/github-mirror/static/ros"
ASSETS = [
    ("geosite.dat", "https://github.com/Loyalsoldier/v2ray-rules-dat/releases/latest/download/geosite.dat"),
]

for name, url in ASSETS:
    dst = os.path.join(OUT_DIR, name)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "curl/8"})
        with urllib.request.urlopen(req, timeout=300) as r:
            data = r.read()
        if len(data) < 100000:
            raise ValueError("suspiciously small: %d bytes" % len(data))
        tmp = dst + ".tmp"
        with open(tmp, "wb") as fh:
            fh.write(data)
        os.replace(tmp, dst)
        print("[ok] %s  %d bytes" % (name, len(data)))
    except Exception as e:
        if os.path.isfile(dst):
            print("[warn] %s fetch failed (%s), kept previous copy" % (name, e))
        else:
            print("[fail] %s: %s" % (name, e))
