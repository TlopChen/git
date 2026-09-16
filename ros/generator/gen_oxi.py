#!/usr/bin/env python3
"""Extract domains from proxy-domain.rsc and emit an OxiDNS domain_set table.

proxy-domain.rsc      : RouterOS /ip dns static type=FWD 语句
proxy-domain.oxi.txt  : OxiDNS domain_set 文本（domain: 后缀域 / full: 精确域）
"""
import re, time, os

OUT_DIR = "/srv/github-mirror/static/ros"
SRC = os.path.join(OUT_DIR, "proxy-domain.rsc")
DST = os.path.join(OUT_DIR, "proxy-domain.oxi.txt")

rules = set()
for line in open(SRC, encoding="utf-8"):
    if not line.startswith("add ") or "type=FWD" not in line:
        continue
    m = re.search(r"name=(\S+)", line)
    s = re.search(r"match-subdomain=(\w+)", line)
    if not m:
        continue
    d = m.group(1).strip().strip('"')
    rules.add(("full:" if (s and s.group(1) == "no") else "domain:") + d)

out = sorted(rules)
with open(DST, "w", encoding="utf-8", newline="\n") as fh:
    fh.write("# proxy-domain OxiDNS domain_set, %d rules, generated %s\n"
             % (len(out), time.strftime("%F %T")))
    for r in out:
        fh.write(r + "\n")
print("[ok] %s  %d rules" % (DST, len(out)))
