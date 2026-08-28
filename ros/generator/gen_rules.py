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


def fetch_asn_prefixes(asn):
    """RIPEstat 实时查询某 ASN 当前公告的全部网段（v4+v6）。"""
    url = f"https://stat.ripe.net/data/announced-prefixes/data.json?resource={asn}"
    err = None
    for _ in range(3):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                data = json.load(r)
            return [p["prefix"] for p in data.get("data", {}).get("prefixes", [])]
        except Exception as e:
            err = e
            time.sleep(3)
    raise SystemExit(f"[fail] RIPEstat {asn}: {err}")


def parse_surge_domains(text):
    """从 Surge 规则行（DOMAIN-SUFFIX,x / DOMAIN,x）和裸域名行提取可静态化的域名。

    正则(/…/)、通配符(*)、DOMAIN-KEYWORD 表达不了 static FWD 的语义，跳过；
    DOMAIN-SUFFIX 与 DOMAIN 在 match-subdomain=yes 下语义相同，都按裸域名输出。
    """
    doms = set()
    for line in text.splitlines():
        line = re.sub(r"//.*$", "", line).split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("/") or "*" in line:
            continue
        if "," in line:
            typ, _, val = line.partition(",")
            val = val.strip().split("/")[0].strip()
            if typ.strip().upper() in ("DOMAIN-SUFFIX", "DOMAIN") and val:
                doms.add(val.lower().rstrip("."))
            continue
        if IP_RE.search(line):
            continue
        if "." in line and re.fullmatch(r"[A-Za-z0-9._-]+", line):
            doms.add(line.lower().lstrip(".").rstrip("."))
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
            extra = [ipaddress.ip_network(p) for p in
                     (q for asn in cfg.get("asn", []) for q in fetch_asn_prefixes(asn))]
            v4 = [n for t in texts for n in parse_cidrs(t) if n.version == 4] \
                + [n for n in extra if n.version == 4]
            v6 = [n for t in texts for n in parse_cidrs(t) if n.version == 6] \
                + [n for n in extra if n.version == 6]
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
        elif cfg["type"] == "rosdns":
            doms = sorted(set().union(*(parse_surge_domains(t) for t in texts)))
            if len(doms) < MIN_ENTRIES:
                raise SystemExit(f"[abort] {name}: 仅 {len(doms)} 条, 疑似拉取失败, 不生成")
            marker = cfg.get("marker", "ros-rules-auto")
            with open(os.path.join(OUT, f"{name}.rsc"), "w") as fh:
                fh.write(f"#{name} — {len(doms)} 条, {time.strftime('%F %T')} 由 gen_rules.py 生成\n")
                fh.write(f"# 导入顺序：在手工维护的同类脚本之后导入（本脚本只清理 comment={marker} 的条目）\n")
                fh.write(f"/ip dns static remove [find where comment=\"{marker}\"]\n")
                fh.write("/ip dns static\n")
                for d in doms:
                    fh.write(f"add address-list={cfg['list']} forward-to={cfg['forward-to']} "
                             f"match-subdomain=yes type=FWD name={d} comment=\"{marker}\"\n")
            print(f"[ok] {name}.rsc  {len(doms)} 条")
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
