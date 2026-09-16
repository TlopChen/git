#!/usr/bin/env python3
"""国内域名表 -> OxiDNS domain_set 文本（供 oxidns 的 cn 反转判据使用）。

源：felixonmars/dnsmasq-china-list 的 accelerated-domains.china.conf
    格式 server=/example.com/1.2.3.4  ->  输出 domain:example.com
"""
import os, re, time, urllib.request

MIRROR = "http://192.168.40.1:18080/"
SRC = "https://raw.githubusercontent.com/felixonmars/dnsmasq-china-list/master/accelerated-domains.china.conf"
OUT_DIR = "/srv/github-mirror/static/ros"
DST = os.path.join(OUT_DIR, "cn-domains.oxi.txt")


def fetch(url):
    err = None
    for _ in range(3):
        try:
            with urllib.request.urlopen(MIRROR + url, timeout=120) as r:
                data = r.read()
            if not data:
                raise ValueError("empty body")
            return data.decode("utf-8", "replace")
        except Exception as e:
            err = e
            time.sleep(3)
    raise SystemExit("[fail] %s: %s" % (url, err))


text = fetch(SRC)
doms = set()
for line in text.splitlines():
    m = re.match(r"^server=/([^/]+)/", line.strip())
    if m:
        doms.add(m.group(1))

if len(doms) < 1000:
    raise SystemExit("[abort] only %d domains, source looks broken" % len(doms))

out = sorted(doms)
tmp = DST + ".tmp"
with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
    fh.write("# cn-domains OxiDNS domain_set from dnsmasq-china-list, %d rules, %s\n"
             % (len(out), time.strftime("%F %T")))
    for d in out:
        fh.write("domain:" + d + "\n")
os.replace(tmp, DST)
print("[ok] %s  %d rules" % (DST, len(out)))
