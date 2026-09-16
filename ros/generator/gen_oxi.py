#!/usr/bin/env python3
"""Build the OxiDNS domain_set table from the pipeline's plain-domain intermediates.

Inputs (produced by gen_rules.py in the same directory):
  proxy-domain.domains.txt   suffix domains, one bare domain per line
  proxy-domain.exact.txt     exact FQDNs, one per line
Output:
  proxy-domain.oxi.txt       OxiDNS domain_set text (domain: / full:)
"""
import os, time

OUT_DIR = "/srv/github-mirror/static/ros"
SUFFIX_SRC = os.path.join(OUT_DIR, "proxy-domain.domains.txt")
EXACT_SRC = os.path.join(OUT_DIR, "proxy-domain.exact.txt")
DST = os.path.join(OUT_DIR, "proxy-domain.oxi.txt")


def load(path):
    if not os.path.isfile(path):
        return []
    out = []
    for line in open(path, encoding="utf-8"):
        d = line.strip()
        if d and not d.startswith("#"):
            out.append(d)
    return out


rules = ["full:" + d for d in load(EXACT_SRC)] + ["domain:" + d for d in load(SUFFIX_SRC)]
rules = sorted(set(rules))
with open(DST, "w", encoding="utf-8", newline="\n") as fh:
    fh.write("# proxy-domain OxiDNS domain_set, %d rules, generated %s\n"
             % (len(rules), time.strftime("%F %T")))
    for r in rules:
        fh.write(r + "\n")
print("[ok] %s  %d rules" % (DST, len(rules)))
