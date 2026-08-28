#!/usr/bin/env python3
"""把上游规则源（经本机镜像服务取文件）转成 ROS 可 import 的 .rsc 地址列表。

用法: python3 gen_rules.py
配置: sources.json   （每条规则: type=cidr|domain, list=ROS地址表名, sources=[上游URL]）
输出: static/ros/<名>.rsc          CIDR 源 → /ip firewall address-list 脚本
      static/ros/<名>.domains.txt  域名源 → 纯域名表（给 OxiDNS 等 DNS 层用）
"""
import ipaddress
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
MIRROR = "http://127.0.0.1:18080/"
OUT = os.path.join(BASE, "static", "ros")
CFG = json.load(open(os.path.join(BASE, "sources.json")))
IP_RE = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}(?:/\d{1,2})?\b")
MIN_ENTRIES = 1  # 0 条视为拉取失败，拒绝生成空文件（telegram 这类源本身只有十几条，属正常）


def fetch(url):
    err = None
    for _ in range(3):
        try:
            with urllib.request.urlopen(MIRROR + url, timeout=120) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:
            err = e
            time.sleep(3)
    raise SystemExit(f"[fail] {url}: {err}")


def parse_cidrs(text):
    nets = []
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        for tok in IP_RE.findall(line):
            try:
                nets.append(ipaddress.ip_network(tok, strict=False))
            except ValueError:
                pass
    return nets


def parse_domains(text):
    doms = set()
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip().rstrip(".")
        if not line:
            continue
        if "," in line:  # Surge 类格式: DOMAIN-SUFFIX,example.com
            typ, _, val = line.partition(",")
            val = val.strip().split("/")[0].strip()
            if typ.strip().upper() in ("DOMAIN-SUFFIX", "DOMAIN") and val and " " not in val:
                doms.add(val.lower())
            continue
        if IP_RE.search(line):
            continue  # 跳过混入的 IP 行（CIDR 归地址表，不归域名表）
        if "." not in line or not re.fullmatch(r"[A-Za-z0-9._*-]+", line):
            continue
        doms.add(line.lower().lstrip("."))  # 点前缀=后缀语义，输出为裸域名
    return sorted(doms)


def rsc_header(name, list_name, count):
    ts = time.strftime("%F %T")
    return (f"#{name} — {count} 条, {ts} 由 gen_rules.py 生成\n"
            f"# ROS 拉取: /tool fetch url=\"http://192.168.40.1:18080/ros/{name}.rsc\" mode=http\n"
            f"#         /import file-name={name}.rsc\n"
            "/ip firewall address-list\n"
            f"remove [find list={list_name}]\n")


def main():
    os.makedirs(OUT, exist_ok=True)
    for name, cfg in CFG.items():
        texts = [fetch(u) for u in cfg["sources"]]
        if cfg["type"] == "cidr":
            v4 = [n for t in texts for n in parse_cidrs(t) if n.version == 4]
            v6 = [n for t in texts for n in parse_cidrs(t) if n.version == 6]
            m4 = list(ipaddress.collapse_addresses(v4))
            m6 = list(ipaddress.collapse_addresses(v6))
            merged = sorted(m4 + m6, key=lambda n: (n.version, int(n.network_address)))
            if len(merged) < MIN_ENTRIES:
                raise SystemExit(f"[abort] {name}: 仅 {len(merged)} 条, 疑似拉取失败, 不生成")
            with open(os.path.join(OUT, f"{name}.rsc"), "w") as fh:
                fh.write(rsc_header(name, cfg["list"], len(merged)))
                for n in merged:
                    fh.write(f"add list={cfg['list']} address={n.with_prefixlen}\n")
            print(f"[ok] {name}.rsc  共 {len(merged)} 条 (v4 {len(m4)} + v6 {len(m6)})")
        elif cfg["type"] == "domain":
            doms = sorted(set().union(*(parse_domains(t) for t in texts)))
            if len(doms) < MIN_ENTRIES:
                raise SystemExit(f"[abort] {name}: 仅 {len(doms)} 条, 疑似拉取失败, 不生成")
            with open(os.path.join(OUT, f"{name}.domains.txt"), "w") as fh:
                fh.write(f"# {name} — {len(doms)} 个域名, {time.strftime('%F %T')} 生成 (DNS 层用, 如 OxiDNS)\n")
                for d in doms:
                    fh.write(d + "\n")
            print(f"[ok] {name}.domains.txt  {len(doms)} 条")
        else:
            raise SystemExit(f"[abort] {name}: 未知 type {cfg['type']}")


if __name__ == "__main__":
    main()
