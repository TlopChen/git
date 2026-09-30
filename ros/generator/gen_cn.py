#!/usr/bin/env python3
"""国内域名表 -> OxiDNS domain_set 文本（供 oxidns 的 cn 反转判据使用）。

多源合并（2026-09-23 起；此前只有 felixonmars 单源）：
  1) felixonmars/dnsmasq-china-list  accelerated-domains.china.conf   server=/example.com/1.2.3.4
  2) blackmatrix7/ios_rule_script    Clash/ChinaMax                   YAML payload
  3) blackmatrix7/ios_rule_script    Clash/China                      YAML payload
  4) ACL4SSR/ACL4SSR                 Clash/ChinaDomain                YAML payload
  5) generator/manual-cn-domains.txt 手工补充（domain:/full: 前缀，仓库为权威）

语义（见 pitfalls「两条重要语义（勿破坏）」）：
  后缀  -> domain:example.com    匹配该域及其子域
  精确  -> full:example.com      DOMAIN, 形式，绝不放大成整域

输出：static/ros/cn-domains.oxi.txt（可用环境变量 CN_DST 覆盖，便于试跑）
"""
import os
import re
import time
import urllib.request

MIRROR = "http://192.168.40.1:18080/"
SRC_DIR = "/srv/github-mirror/static/src"
OUT_DIR = "/srv/github-mirror/static/ros"
DST = os.environ.get("CN_DST", os.path.join(OUT_DIR, "cn-domains.oxi.txt"))
OFFLINE = os.environ.get("GEN_CN_OFFLINE") == "1"

DMSQ = "https://raw.githubusercontent.com/felixonmars/dnsmasq-china-list/master/accelerated-domains.china.conf"
CLASH_SOURCES = [
    "https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Clash/ChinaMax/ChinaMax_Classical.yaml",
    "https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Clash/China/China_Classical.yaml",
    "https://raw.githubusercontent.com/ACL4SSR/ACL4SSR/master/Clash/ChinaDomain.list",
]
MANUAL = "/root/git/ros/generator/manual-cn-domains.txt"
DOMAIN_RE = re.compile(r"^(?:[a-z0-9_](?:[a-z0-9_\-]*[a-z0-9_])?\.)+[a-z]{2,}$", re.I)
SKIP_PREFIX = ("IP-CIDR", "IP6-CIDR", "GEOIP", "DOMAIN-KEYWORD", "PROCESS",
               "RULE-SET", "URL-REGEX", "USER-AGENT", "SRC-IP", "DEST-PORT")


def fetch(url):
    """Download via mirror; archive the raw source under static/src/;
    fall back to the archived copy when the upstream is unreachable."""
    os.makedirs(SRC_DIR, exist_ok=True)
    cache = os.path.join(SRC_DIR, url.rsplit("/", 1)[-1])
    if OFFLINE:
        if os.path.isfile(cache):
            with open(cache, encoding="utf-8") as fh:
                return fh.read()
        raise SystemExit("[fail] offline source not cached: " + url)
    err = None
    for _ in range(3):
        try:
            with urllib.request.urlopen(MIRROR + url, timeout=120) as r:
                data = r.read()
            if not data:
                raise ValueError("empty body")
            text = data.decode("utf-8", "replace")
            tmp = cache + ".tmp"
            with open(tmp, "w", encoding="utf-8", newline="") as fh:
                fh.write(text)
            os.replace(tmp, cache)
            return text
        except Exception as e:
            err = e
            time.sleep(3)
    if os.path.isfile(cache):
        print("[warn] fetch failed, fallback to archived source: "
              + os.path.basename(cache) + " (" + str(err) + ")")
        with open(cache, encoding="utf-8") as fh:
            return fh.read()
    raise SystemExit("[fail] " + url + ": " + str(err))


def norm(raw):
    """规范化成裸域名；不合法返回 None。"""
    d = raw.strip().strip("'\"").strip().lower()
    d = d.lstrip("*").lstrip("+").lstrip(".")
    if not d or ":" in d or "/" in d:
        return None
    return d if DOMAIN_RE.match(d) else None


suffix, exact = set(), set()

for line in fetch(DMSQ).splitlines():
    m = re.match(r"^server=/([^/]+)/", line.strip())
    if m:
        d = norm(m.group(1))
        if d:
            suffix.add(d)

for url in CLASH_SOURCES:
    for line in fetch(url).splitlines():
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
    print("[warn] manual-cn-domains.txt not found: " + MANUAL)

full_only = exact - suffix
total = len(suffix) + len(full_only)
if total < 5000:
    raise SystemExit("[abort] only %d domains, source looks broken" % total)

tmp = DST + ".tmp"
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