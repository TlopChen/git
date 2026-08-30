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
                data = r.read()
            if not data:
                raise ValueError("empty body")
            return data.decode("utf-8", "replace")
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


PSL_URL = "https://raw.githubusercontent.com/publicsuffix/list/main/public_suffix_list.dat"
PSL_CACHE = os.path.join(BASE, "psl.dat")
PSL_TTL = 30 * 86400  # PSL 变化很慢，30 天刷新一次


def load_psl():
    """加载 Public Suffix List，返回 (exact, wild, exc) 三个规则集，全部小写 punycode。"""
    if (not os.path.isfile(PSL_CACHE) or os.path.getsize(PSL_CACHE) == 0
            or time.time() - os.path.getmtime(PSL_CACHE) > PSL_TTL):
        with open(PSL_CACHE, "w", encoding="utf-8") as fh:
            fh.write(fetch(PSL_URL))
    exact, wild, exc = set(), set(), set()
    for line in open(PSL_CACHE, encoding="utf-8"):
        line = line.split("//", 1)[0].strip().lower()
        if not line or line.startswith("="):
            continue
        key, rule = "exact", line
        if rule.startswith("!"):
            key, rule = "exc", rule[1:]
        elif rule.startswith("*."):
            key, rule = "wild", rule[2:]
        try:
            rule = rule.encode("idna").decode()
        except Exception:
            pass
        {"exact": exact, "wild": wild, "exc": exc}[key].add(rule)
    return exact, wild, exc


def registrable(dom, psl):
    """按 PSL 求注册域（如 a.b.example.com → example.com）。

    求不出（域本身就是公共后缀，如 'ai'）或命中例外规则时原样返回，绝不放大。
    """
    exact, wild, exc = psl
    labels = dom.split(".")
    for i in range(len(labels)):
        if ".".join(labels[i:]) in exc:
            return dom
    best = 0  # 命中的公共后缀长度（标签数）
    for i in range(len(labels)):
        cand = ".".join(labels[i:])
        if cand in exact and len(labels) - i > best:
            best = len(labels) - i
        if cand in wild and i > 0 and len(labels) - i + 1 > best:
            best = len(labels) - i + 1
    if best == 0 or len(labels) <= best:
        return dom
    return ".".join(labels[-(best + 1):])


def dedup_suffix(doms):
    """后缀去重：父域已在集合中时丢弃子域（match-subdomain 已覆盖）。"""
    final = set()
    for d in sorted(doms, key=lambda x: x.count(".")):
        labels = d.split(".")
        if not any(".".join(labels[i:]) in final for i in range(1, len(labels))):
            final.add(d)
    return sorted(final)


def parse_surge_domains(text):
    """提取可静态化的域名，支持三种行格式。

    Surge 规则行（DOMAIN-SUFFIX,x / DOMAIN,x）、Clash payload YAML（- '+.x'）、
    裸域名行（.x / +.x / x）。正则(/…/)、通配符(*)、DOMAIN-KEYWORD 表达不了
    static FWD 的语义，跳过。

    返回 (suffix, exact)：
    - suffix：DOMAIN-SUFFIX 及其等价写法（+.x / .x / 裸域），语义是「整域及其
      所有子域」，收敛成注册域后 match-subdomain=yes 输出。
    - exact：DOMAIN,x 精确主机条目，语义是「只此一个主机名」。绝不收敛成注册域、
      绝不加 match-subdomain，否则会把精确子域放大成整域（如
      DOMAIN,apm-misaka.biliapi.net 被放大成 biliapi.net 整域走代理，直接卡
      B 站国内 API，2026-08-30 事故）。
    """
    suffix = set()
    exact = set()
    for line in text.splitlines():
        line = re.sub(r"//.*$", "", line).split("#", 1)[0].strip()
        if line.startswith("payload:") or line.startswith("- "):
            line = line[2:].strip().strip("'\"")
            line = re.sub(r"//.*$", "", line).split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("+."):
            val = line[2:]
            if re.fullmatch(r"[A-Za-z0-9._-]+", val):
                suffix.add(val.lower().lstrip(".").rstrip("."))
            continue
        if line.startswith("/") or "*" in line:
            continue
        if "," in line:
            typ, _, val = line.partition(",")
            val = val.strip().split("/")[0].strip()
            t = typ.strip().upper()
            if t == "DOMAIN-SUFFIX" and val and re.fullmatch(r"[A-Za-z0-9._-]+", val):
                suffix.add(val.lower().rstrip("."))
            elif t == "DOMAIN" and val and re.fullmatch(r"[A-Za-z0-9._-]+", val):
                exact.add(val.lower().rstrip("."))
            continue
        if IP_RE.search(line):
            continue
        if "." in line and re.fullmatch(r"[A-Za-z0-9._-]+", line):
            suffix.add(line.lower().lstrip(".").rstrip("."))
    return sorted(suffix), sorted(exact)


def rsc_header(name, list_name, count, remove_lines=None):
    """CIDR 类 .rsc 的头：注释 + 整表重建的 remove 行。

    remove_lines 缺省按列表名整清；对与 DNS 动态条目共用的列表
    （如 blacklist）必须传限定注释的 remove，避免误杀动态条目。
    """
    ts = time.strftime("%F %T")
    lines = [f"#{name} — {count} 条, {ts} 由 gen_rules.py 生成\n",
             f"# ROS 拉取: /tool fetch url=\"http://192.168.40.1:18080/ros/{name}.rsc\" mode=http\n",
             f"#         /import file-name={name}.rsc\n",
             "/ip firewall address-list\n"]
    for rl in (remove_lines or [f"remove [find list={list_name}]"]):
        lines.append(rl + "\n")
    return "".join(lines)


def main():
    os.makedirs(OUT, exist_ok=True)
    for name, cfg in CFG.items():
        texts = [fetch(u) for u in cfg["sources"]]
        if cfg["type"] == "cidr":
            extra = [ipaddress.ip_network(p) for p in
                     (q for asn in cfg.get("asn", []) for q in fetch_asn_prefixes(asn))]
            extra += [ipaddress.ip_network(c) for c in cfg.get("extra_cidrs", [])]
            v4 = [n for t in texts for n in parse_cidrs(t) if n.version == 4] \
                + [n for n in extra if n.version == 4]
            v6 = [n for t in texts for n in parse_cidrs(t) if n.version == 6] \
                + [n for n in extra if n.version == 6]
            m4 = list(ipaddress.collapse_addresses(v4))
            m6 = list(ipaddress.collapse_addresses(v6))
            merged = sorted(m4 + m6, key=lambda n: (n.version, int(n.network_address)))
            if len(merged) < MIN_ENTRIES:
                raise SystemExit(f"[abort] {name}: 仅 {len(merged)} 条, 疑似拉取失败, 不生成")
            marker = cfg.get("marker")
            legacy = cfg.get("legacy_lists", [])
            remove_lines = None
            if cfg.get("remove_mode") == "static":
                # 清全部静态、保留动态（与 DNS 动态注入共存的列表用此模式），
                # 重建内容必须是全量超集，否则会丢掉旧表独有网段
                remove_lines = [f'remove [find where list="{cfg["list"]}" && dynamic=no]']
                remove_lines += [f"remove [find list={old}]" for old in legacy]
            elif marker:
                # 带 marker 的列表与 DNS 动态条目共存：只清自己 + 迁移旧列表名
                remove_lines = [f'remove [find where list="{cfg["list"]}" && comment="{marker}"]']
                remove_lines += [f"remove [find list={old}]" for old in legacy]
            elif legacy:
                # 无 marker 的整表重建：清新名 + 迁移旧名
                remove_lines = [f"remove [find list={cfg['list']}]"]
                remove_lines += [f"remove [find list={old}]" for old in legacy]
            with open(os.path.join(OUT, f"{name}.rsc"), "w") as fh:
                fh.write(rsc_header(name, cfg["list"], len(merged), remove_lines))
                cmt = f' comment="{marker}"' if marker else ""
                for n in m4:
                    fh.write(f"add list={cfg['list']} address={n.with_prefixlen}{cmt}\n")
                # /ip 表不收 IPv6；确有 v6 需求时在 sources.json 开 ipv6 开关
                if m6 and cfg.get("ipv6"):
                    fh.write("\n/ipv6 firewall address-list\n")
                    for n in m6:
                        fh.write(f"add list={cfg['list']} address={n.with_prefixlen}{cmt}\n")
                if m6 and not cfg.get("ipv6"):
                    fh.write(f"# （{len(m6)} 条 IPv6 网段未导入：内网未启用 IPv6，ipv6=true 可开启）\n")
            print(f"[ok] {name}.rsc  共 {len(merged)} 条 (v4 {len(m4)} + v6 {len(m6)})")
        elif cfg["type"] == "rosdns":
            suffix_raw, exact_raw = set(), set()
            for t in texts:
                s, e = parse_surge_domains(t)
                suffix_raw |= set(s)
                exact_raw |= set(e)
            psl = load_psl()
            # 后缀域：收敛成注册域 + 后缀去重（match-subdomain 覆盖子域）
            auto_suffix = dedup_suffix(registrable(d, psl) for d in suffix_raw)
            # 精确域：完全限定 FQDN，不收敛、不去重（单个主机名语义），
            # 输出时 match-subdomain=no，避免把精确子域放大成整域
            auto_exact = sorted(exact_raw)
            # 排除名单：命中项及其所有子域从自动层剔除（如 bing.com 未被墙，不该走代理）
            excluded = set()
            if cfg.get("exclude"):
                ep = cfg["exclude"]
                excluded = {l.strip().lower() for l in open(ep, encoding="utf-8")
                            if l.strip() and not l.startswith("#")}
                auto_suffix = [d for d in auto_suffix
                               if not any(d == e or d.endswith("." + e) for e in excluded)]
                auto_exact = [d for d in auto_exact
                              if not any(d == e or d.endswith("." + e) for e in excluded)]
            manual = []
            if cfg.get("manual"):
                mp = cfg["manual"]
                if os.path.isfile(mp):
                    manual = [l.strip().lower() for l in open(mp, encoding="utf-8")
                              if l.strip() and not l.startswith("#")]
                else:
                    raise SystemExit(f"[abort] {name}: 手工域名文件不存在: {mp}")
            manual = sorted({d for d in manual
                             if "." in d and re.fullmatch(r"[A-Za-z0-9._-]+", d)})
            auto = [d for d in auto_suffix if d not in set(manual)]
            if len(auto) + len(auto_exact) + len(manual) < MIN_ENTRIES:
                raise SystemExit(f"[abort] {name}: 仅 {len(auto) + len(auto_exact) + len(manual)} 条, 疑似拉取失败, 不生成")
            marker = cfg.get("marker", "ros-rules-auto")
            with open(os.path.join(OUT, f"{name}.rsc"), "w") as fh:
                fh.write(f"#{name} — 手工 {len(manual)} 条 + 上游 {len(auto) + len(auto_exact)} 条, "
                         f"{time.strftime('%F %T')} 由 gen_rules.py 生成\n")
                fh.write(f"# 后缀域为注册域裸域名，零正则；子域由 match-subdomain=yes 覆盖\n")
                fh.write(f"# 精确域(DOMAIN,x)为完全限定 FQDN，match-subdomain=no，仅匹配单个主机名\n")
                fh.write(f"# 本脚本整表重建 {cfg['list']}，手工域名见 manual-blacklist.txt（comment=ros-rules-manual）\n")
                fh.write(f"/ip dns static remove [find address-list={cfg['list']}]\n")
                fh.write(f"/ip dns static\n")
                for d in manual:
                    fh.write(f"add address-list={cfg['list']} forward-to={cfg['forward-to']} "
                             f"match-subdomain=yes type=FWD name={d} comment=\"ros-rules-manual\"\n")
                for d in auto:
                    fh.write(f"add address-list={cfg['list']} forward-to={cfg['forward-to']} "
                             f"match-subdomain=yes type=FWD name={d} comment=\"{marker}\"\n")
                for d in auto_exact:
                    fh.write(f"add address-list={cfg['list']} forward-to={cfg['forward-to']} "
                             f"match-subdomain=no type=FWD name={d} comment=\"{marker}\"\n")
            print(f"[ok] {name}.rsc  手工 {len(manual)} + 上游 {len(auto) + len(auto_exact)} (后缀 {len(suffix_raw)} + 精确 {len(exact_raw)}, PSL 收纳)")
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
