#!/usr/bin/env python3
"""把上游域名规则源转成 ROS 可 import 的 FWD .rsc 与 OxiDNS 域名中间产物。

本管线**只处理域名**；IPv4 地址表（cn/运营商/blacklist）在 scripts/ip-rules，
两边各自 IN/OUT、互不读取产物（2026-11-26 起）。

用法:
  python3 gen_rules.py                      # 全量（走本机 GitHub 镜像）
  python3 gen_rules.py --offline             # 只用 input/upstream 已验证快照
  python3 gen_rules.py --only proxy-domain   # 只重建一张表

配置: sources.json
  upstreams —— 上游仓库注册表 "owner/repo" -> {"branch": ...}
  tables    —— 域名表: type=rosdns, list=ROS 地址表名（FWD 打标）, sources=[...]

输入: input/upstream/<owner>__<repo>/<path>   （store.py 落盘并记出处）
输出: output/<名>.rsc / .domains.txt / .exact.txt
"""
import argparse
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import store

CFG = store.load()
TABLES = CFG["tables"]
OUT = str(store.OUT_DIR)
MIN_ENTRIES = 1  # 0 条视为拉取失败，拒绝生成空文件
OFFLINE = False
ONLY = []


def fetch(spec):
    """按 sources.json 的引用取上游文本，并留档到 input/upstream/。"""
    return store.fetch(CFG, spec, offline=OFFLINE)


PSL_SPEC = "publicsuffix/list:public_suffix_list.dat"
PSL_TTL = 30 * 86400  # PSL 变化很慢，30 天刷新一次


def load_psl():
    """加载 Public Suffix List，返回 (exact, wild, exc) 三个规则集，全部小写 punycode。"""
    psl = store.snapshot_path(CFG, PSL_SPEC)
    stale = (not psl.is_file() or psl.stat().st_size == 0
             or time.time() - psl.stat().st_mtime > PSL_TTL)
    if stale and not OFFLINE:
        fetch(PSL_SPEC)
    if not psl.is_file() or psl.stat().st_size == 0:
        raise SystemExit("[fail] PSL cache missing: " + str(psl))
    exact, wild, exc = set(), set(), set()
    for line in psl.read_text(encoding="utf-8").splitlines():
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
        if "." in line and re.fullmatch(r"[A-Za-z0-9._-]+", line):
            suffix.add(line.lower().lstrip(".").rstrip("."))
    return sorted(suffix), sorted(exact)


def main():
    os.makedirs(OUT, exist_ok=True)
    for name, cfg in TABLES.items():
        if ONLY and name not in ONLY:
            continue
        if cfg.get("type") != "rosdns":
            raise SystemExit(f"[abort] {name}: 本管线只处理域名（rosdns）表，收到 type={cfg.get('type')}")
        texts = [fetch(s) for s in cfg["sources"]]
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
        # 排除名单：命中项及其所有子域从自动层剔除（如 bing.com 未被墙，不该走代理；
        # 国内券商 .cn 站、CloudFront 公共 CDN 同理）。见 input/manual/exclude-blacklist.txt
        excluded = set()
        if cfg.get("exclude"):
            ep = store.abs_path(CFG, cfg["exclude"])
            excluded = {l.strip().lower() for l in open(ep, encoding="utf-8")
                        if l.strip() and not l.startswith("#")}
            auto_suffix = [d for d in auto_suffix
                           if not any(d == e or d.endswith("." + e) for e in excluded)]
            auto_exact = [d for d in auto_exact
                          if not any(d == e or d.endswith("." + e) for e in excluded)]
        manual = []
        if cfg.get("manual"):
            mp = store.abs_path(CFG, cfg["manual"])
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

        # 中间产物：纯域名一行，供各消费端（RouterOS / OxiDNS / 其它 DNS）分化处理
        with open(os.path.join(OUT, name + ".domains.txt"), "w") as fh:
            fh.write("# " + name + " suffix-domains (bare domain, covers subdomains) " +
                     str(len(manual) + len(auto)) + ", " + time.strftime("%F %T") + "\n")
            for d in sorted(set(manual) | set(auto)):
                fh.write(d + "\n")
        with open(os.path.join(OUT, name + ".exact.txt"), "w") as fh:
            fh.write("# " + name + " exact-domains (fully qualified host) " +
                     str(len(auto_exact)) + ", " + time.strftime("%F %T") + "\n")
            for d in auto_exact:
                fh.write(d + "\n")
        marker = cfg.get("marker", "ros-rules-auto")
        with open(os.path.join(OUT, f"{name}.rsc"), "w") as fh:
            fh.write(f"#{name} — 手工 {len(manual)} 条 + 上游 {len(auto) + len(auto_exact)} 条, "
                     f"{time.strftime('%F %T')} 由 gen_rules.py 生成\n")
            fh.write(f"# 后缀域为注册域裸域名，零正则；子域由 match-subdomain=yes 覆盖\n")
            fh.write(f"# 精确域(DOMAIN,x)为完全限定 FQDN，match-subdomain=no，仅匹配单个主机名\n")
            fh.write(f"# 本脚本整表重建 {cfg['list']}，手工域名见 input/manual/manual-blacklist.txt（comment=ros-rules-manual）\n")
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
        print(f"[ok] {name}.rsc  手工 {len(manual)} + 上游 {len(auto) + len(auto_exact)} "
              f"(后缀 {len(suffix_raw)} + 精确 {len(exact_raw)}, PSL 收纳)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--only", action="append", default=[])
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    OFFLINE = args.offline
    ONLY = args.only
    if args.out:
        OUT = args.out
    main()
