#!/usr/bin/env python3
"""把域名中间产物合成 OxiDNS domain_set 文本。

输入: output/proxy-domain.domains.txt  后缀域（裸域名，覆盖子域）
      output/proxy-domain.exact.txt    精确 FQDN（只匹配该主机）
输出: output/proxy-domain.oxi.txt      OxiDNS domain_set（domain: / full:）
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import store

OUT = store.OUT_DIR
DST = os.environ.get("OXI_DST", str(OUT / "proxy-domain.oxi.txt"))


def load(path):
    if not os.path.isfile(path):
        return []
    out = []
    for line in open(path, encoding="utf-8"):
        d = line.strip()
        if d and not d.startswith("#"):
            out.append(d)
    return out


rules = ["full:" + d for d in load(OUT / "proxy-domain.exact.txt")] \
    + ["domain:" + d for d in load(OUT / "proxy-domain.domains.txt")]
rules = sorted(set(rules))
with open(DST, "w", encoding="utf-8", newline="\n") as fh:
    fh.write("# proxy-domain OxiDNS domain_set, %d rules, generated %s\n"
             % (len(rules), time.strftime("%F %T")))
    for r in rules:
        fh.write(r + "\n")
print("[ok] %s  %d rules" % (DST, len(rules)))