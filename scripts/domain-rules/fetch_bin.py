#!/usr/bin/env python3
"""拉二进制规则资产（geosite.dat 等）到内网 HTTP 分发目录。

二进制体积大，不进 Git；清单见 sources.json 的 binaries。
拉取失败时保留上一份可用文件。
"""
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import store

CFG = store.load()
DEST = os.environ.get("BIN_DEST", "/srv/github-mirror/static/ros")

for spec in CFG.get("binaries", []):
    name = spec["name"]
    dst = os.path.join(DEST, name)
    try:
        req = urllib.request.Request(spec["url"], headers={"User-Agent": "curl/8"})
        with urllib.request.urlopen(req, timeout=300) as r:
            data = r.read()
        if len(data) < int(spec.get("min_bytes", 100000)):
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