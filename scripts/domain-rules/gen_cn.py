#!/usr/bin/env python3
"""国内域名表 -> OxiDNS domain_set 文本（供 oxidns 的 cn 反转判据使用）。

多源合并，来源见 sources.json 的 cn-domains（加减源只改那一处）:
  1) felixonmars/dnsmasq-china-list  accelerated-domains.china.conf
  2) blackmatrix7/ios_rule_script    Clash/ChinaMax
  3) blackmatrix7/ios_rule_script    Clash/China
  4) ACL4SSR/ACL4SSR                 Clash/ChinaDomain.list
  5) input/manual/manual-cn-domains.txt 手工补充（domain:/full: 前缀，仓库为权威）

语义（勿破坏）:
  后缀 -> domain:example.com   匹配该域及其子域
  精确 -> full:example.com     绝不放大成整域

输出: output/cn-domains.oxi.txt（可用 CN_DST 覆盖，便于试跑）
"""
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import store

CFG = store.load()
CN = CFG["cn-domains"]
DST = os.environ.get("CN_DST", str(store.OUT_DIR / "cn-domains.oxi.txt"))
OFFLINE = os.environ.get("GEN_CN_OFFLINE") == "1"
MANUAL = store.abs_path(CFG, CN["manual"])
MIN_RULES = int(CN.get("min_rules", 5000))
DOMAIN_RE = re.compile(r"^(?:[a-z0-9_](?:[a-z0-9_\-]*[a-z0-9_])?\.)+[a-z]{2,}$", re.I)
SKIP_PREFIX = ("IP-CIDR", "IP6-CIDR", "GEOIP", "DOMAIN-KEYWORD", "PROCESS",
               "RULE-SET", "URL-REGEX", "USER-AGENT", "SRC-IP", "DEST-PORT")


def fetch(spec):
    return store.fetch(CFG, spec, offline=OFFLINE)


def norm(raw):
    """规范化成裸域名；不合法返回 None。"""
    d = raw.strip().strip("'\"").strip().lower()
    d = d.lstrip("*").lstrip("+").lstrip(".")
    if not d or ":" in d or "/" in d:
        return None
    return d if DOMAIN_RE.match(d) else None


suffix, exact = set(), set()

for line in fetch(CN["dnsmasq_source"]).splitlines():
    m = re.match(r"^server=/([^/]+)/", line.strip())
    if m:
        d = norm(m.group(1))
        if d:
            suffix.add(d)

for spec in CN["sources"]:
    for line in fetch(spec).splitlines():
        s = line.strip()
        if not s or s.startswith("#") or s in ("payload:", "rules:"):
            continue
        s = s.lstrip("-").strip().strip("'\"")
        if not s:
            continue
        up = s.upper()
        if up.startswith("DOMAIN-SUFFIX,"):
            d = norm(s.split(",", 1)[1])
            if d:
                suffix.add(d)
        elif up.startswith("DOMAIN,"):
            d = norm(s.split(",", 1)[1])
            if d:
                exact.add(d)
        elif up.startswith(SKIP_PREFIX):
            continue
        else:
            d = norm(s)
            if d:
                suffix.add(d)

if os.path.isfile(MANUAL):
    added = 0
    with open(MANUAL, encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            s = line.split("#", 1)[0].strip()
            if not s:
                continue
            if s.startswith("domain:"):
                d = norm(s[7:])
                if d:
                    suffix.add(d)
            elif s.startswith("full:"):
                d = norm(s[5:])
                if d:
                    exact.add(d)
            else:
                raise SystemExit("[fail] %s:%d 需要 domain:/full: 前缀: %s"
                                 % (MANUAL, lineno, s))
            if not d:
                raise SystemExit("[fail] %s:%d 非法域名: %s" % (MANUAL, lineno, s))
            added += 1
    print("[info] manual-cn-domains.txt: %d rules" % added)
else:
    print("[warn] manual-cn-domains.txt not found: " + str(MANUAL))

full_only = exact - suffix
total = len(suffix) + len(full_only)
if total < MIN_RULES:
    raise SystemExit("[abort] only %d domains, source looks broken" % total)

tmp = str(DST) + ".tmp"
with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
    fh.write("# cn-domains OxiDNS domain_set from 4 sources "
             "(dnsmasq-china-list + ChinaMax + China + ChinaDomain), %d rules, %s\n"
             % (total, time.strftime("%F %T")))
    for d in sorted(suffix):
        fh.write("domain:" + d + "\n")
    for d in sorted(full_only):
        fh.write("full:" + d + "\n")
os.replace(tmp, DST)
print("[ok] %s  %d rules (%d suffix + %d full)" % (DST, total, len(suffix), len(full_only)))