#!/usr/bin/env python3
"""纯 IPv4 地址表管线：上游 IP 源 → 本地快照 → 校验 → 手工层 → 排除层 → 产物。

与 domain-rules（纯域名管线）分工：

  domain-rules  只产出域名规则（OxiDNS domain_set / RouterOS FWD）
  ip-rules      只产出 IPv4 地址表（直连表 + CN/运营商表 + blacklist 表）

目录（IN/OUT，与 domain-rules 保持同一约定）：

  sources.json       上游源与输出表定义（单一入口）
  input/manual/      手工 IP 表：include-ipv4.txt（手工添加）/ exclude-ipv4.txt（手工排除）
  input/upstream/    上游原始快照（抓取失败按 sha256 + 72 小时时效回退）
  output/            IPv4 产物（直连表、CN/运营商表、blacklist 表、报告）
  service-evidence/  单项服务的实测证据；licenses/ 上游许可

组装顺序（报告 precedence 同名输出）：

  ① 上游源：CN 直连三源并集（gaoyifan/misaka/metowolf）；
  ② 手工层：input/manual/include-ipv4.txt + direct_asns（RIPE RIS 整 ASN）；
  ③ 排除层：input/manual/exclude-ipv4.txt + blacklist 表地址（强制代理优先）；
  ④ 派生：DIRECT_IP_NOCM / DIRECT_IP_NOCT（减 cn-mobile / cn-telecom 地址）。

tables 按 sources.json 生成独立地址表：cn / cn-telecom / cn-mobile /
cn-unicom / cn-cernet / blacklist（2026-11-26 从 domain-rules 迁入本管线）。

本管线不解析域名、不访问 DNS、不登录 RouterOS。标准库 + git。
"""
import argparse
import hashlib
import ipaddress as ip
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time

NONPUBLIC = [ip.ip_network(x) for x in (
    '0.0.0.0/8', '10.0.0.0/8', '100.64.0.0/10', '127.0.0.0/8',
    '169.254.0.0/16', '172.16.0.0/12', '192.0.0.0/24', '192.0.2.0/24',
    '192.168.0.0/16', '198.18.0.0/15', '198.51.100.0/24', '203.0.113.0/24',
    '224.0.0.0/3')]

INPUT_MANUAL = Path('input') / 'manual'
INPUT_UPSTREAM = Path('input') / 'upstream'
OUTPUT = Path('output')
LEGACY_INPUT_DIRS = (Path('input') / 'ip', Path('input') / 'domain', Path('raw'))
LEGACY_FLAT_FILES = ('include-ipv4.txt', 'exclude-ipv4.txt', 'direct-domains.json')
IP_TOKEN_RE = re.compile(r'\b\d{1,3}(?:\.\d{1,3}){3}(?:/\d{1,2})?\b')

# 表产物 -> 输出文件名；直连表在 main 里单独登记。
TABLE_OUTPUTS = ('cn', 'cn-telecom', 'cn-mobile', 'cn-unicom', 'cn-cernet', 'blacklist')


def canonical(n):
    n = ip.ip_network(n, strict=False)
    if n.version != 4 or n.prefixlen < 8 or any(n.overlaps(b) for b in NONPUBLIC):
        raise ValueError(f'not an allowed public IPv4 prefix: {n}')
    return n


def parse_cidrs(text):
    """严格解析手工表 / 直连源：一行一条 IPv4/CIDR，# 注释。

    只要有一行不是合法公网 IPv4 就报错，绝不从错误页面里"捞出"像 IP 的文本。
    """
    result = []
    for number, line in enumerate(text.splitlines(), 1):
        line = line.partition('#')[0].strip()
        if not line:
            continue
        try:
            result.append(canonical(line))
        except ValueError as e:
            raise ValueError(f'line {number}: {e}') from e
    return list(ip.collapse_addresses(result))


def parse_table_tokens(text):
    """宽松解析上游地址表源（YAML / Surge / 纯列表），只取 IPv4 地址 token。

    上游表可能是 Clash payload（- '1.0.1.0/24'）、Surge（IP-CIDR,x,y）或纯列表，
    因此按 token 提取；只作为地址表数据，不做可执行内容解释。
    """
    result = []
    for line in text.splitlines():
        line = line.split('#', 1)[0].strip()
        if not line:
            continue
        for token in IP_TOKEN_RE.findall(line):
            try:
                net = ip.ip_network(token, strict=False)
            except ValueError:
                continue
            if net.version == 4:
                result.append(net)
    return list(ip.collapse_addresses(result))


def minus(networks, excluded):
    """Subtract address sets without expanding to individual IPs."""
    left = [(int(n.network_address), int(n.broadcast_address))
            for n in ip.collapse_addresses(networks)]
    right = [(int(n.network_address), int(n.broadcast_address))
             for n in ip.collapse_addresses(excluded)]
    result, j = [], 0
    for lo, hi in left:
        while j < len(right) and right[j][1] < lo:
            j += 1
        k, cur = j, lo
        while k < len(right) and right[k][0] <= hi:
            a, b = right[k]
            if cur < a:
                result.extend(ip.summarize_address_range(ip.IPv4Address(cur), ip.IPv4Address(a - 1)))
            cur = max(cur, b + 1)
            if cur > hi:
                break
            k += 1
        if cur <= hi:
            result.extend(ip.summarize_address_range(ip.IPv4Address(cur), ip.IPv4Address(hi)))
    return list(ip.collapse_addresses(result))


def cidr_text(nets):
    return ''.join(f'{n}\n' for n in ip.collapse_addresses(nets))


def digest(data):
    return hashlib.sha256(data).hexdigest()


def atomic(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, str):
        data = data.encode()
    if path.is_file() and path.read_bytes() == data:
        return
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as f:
        temp = Path(f.name)
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.chmod(temp, 0o644)
    os.replace(temp, path)


def json_text(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n'


def input_layout(base):
    """IN/OUT 布局：input/manual（手工表）+ input/upstream（上游快照）+ output。

    发现 2026-11-26 之前的旧布局（input/ip、input/domain、raw/、根目录手动表）时
    明确报错，避免迁移不完整时静默读到空输入、发布空表。
    """
    base = Path(base)
    for name in LEGACY_FLAT_FILES:
        if (base / name).exists():
            raise RuntimeError(f'旧扁平布局文件仍在: {name}; 应为 input/manual/{name}')
    for rel in LEGACY_INPUT_DIRS:
        if (base / rel).exists():
            raise RuntimeError(f'旧输入布局目录仍在: {rel}/; 应为 input/manual/ 与 input/upstream/')
    manual = base / INPUT_MANUAL
    upstream = base / INPUT_UPSTREAM
    if not manual.is_dir() or not upstream.is_dir():
        raise RuntimeError(f'缺少必需目录: {manual} 与 {upstream}')
    return manual, upstream


def output_path(base, name):
    """产物都平铺在 output/（IP 管线只有 IP 产物）。"""
    if '/' in name or '\\' in name or name in ('.', '..'):
        raise KeyError(f'非法产物名: {name}')
    return Path(base) / OUTPUT / name


def assemble(upstream, manual, excluded):
    """权威顺序：上游源 与 手工层取并集，再由排除层做地址差集。

    返回 (direct, conflicts)；conflicts 是上游/手工里被排除层命中的那部分，
    用于报告"手写条目被强制代理/排除表吃掉"，避免静默失效。
    """
    merged = list(ip.collapse_addresses(list(upstream) + list(manual)))
    direct = minus(merged, excluded)
    return direct, minus(merged, direct)


def git(repo, *args):
    env = dict(os.environ, GIT_TERMINAL_PROMPT='0',
               GIT_SSH_COMMAND='ssh -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=15')
    r = subprocess.run(['git', '-C', str(repo), *args], capture_output=True, timeout=120, env=env)
    if r.returncode:
        raise RuntimeError(r.stderr.decode(errors='replace')[-1200:])
    return r.stdout


def source_validate(spec, data):
    """按源的 kind 解析并做规模校验；失败即视为不可用源。"""
    text = data.decode('utf-8-sig', errors='strict')
    kind = spec['kind']
    if kind == 'cidr':
        nets = parse_cidrs(text)
    elif kind == 'list':
        nets = parse_table_tokens(text)
    else:
        raise ValueError(f'unknown source kind: {kind}')
    count = len(nets)
    if not spec['min_prefixes'] <= count <= spec['max_prefixes']:
        raise ValueError(f'{spec.get("id", "?")}: unexpected prefix count {count}')
    if kind == 'cidr' and any(k in spec for k in ('min_addresses', 'max_addresses')):
        coverage = sum(n.num_addresses for n in nets)
        lo = spec.get('min_addresses', 0)
        hi = spec.get('max_addresses', 1 << 32)
        if not lo <= coverage <= hi:
            raise ValueError(f'{spec.get("id", "?")}: unexpected address coverage {coverage}')
    return nets


def fetch_source(spec, base, cache, refresh):
    """取上游文本：成功刷新快照与出处；失败回退 72 小时内的已验证快照。"""
    sid = spec['id']
    raw_dir = Path(base) / INPUT_UPSTREAM
    raw_path = raw_dir / f'{sid}.txt'
    meta_path = raw_dir / f'{sid}.json'
    previous = json.loads(meta_path.read_text()) if meta_path.exists() else None
    old_data = raw_path.read_bytes() if raw_path.exists() else None
    error = None
    if refresh:
        try:
            repo = cache / spec['repo'].replace('/', '__')
            repo.mkdir(parents=True, exist_ok=True)
            if not (repo / '.git').exists():
                git(repo, 'init', '--quiet')
                git(repo, 'remote', 'add', 'origin', 'git@github.com:' + spec['repo'] + '.git')
            git(repo, 'fetch', '--quiet', '--depth', '1', '--filter=blob:none', 'origin', spec['ref'])
            commit = git(repo, 'rev-parse', 'FETCH_HEAD').decode().strip()
            data = git(repo, 'show', f'{commit}:{spec["path"]}')
            source_validate(spec, data)
            stamp = int(git(repo, 'show', '-s', '--format=%ct', commit).strip())
            max_age = int(spec.get('max_age_days', 0))
            if max_age and time.time() - stamp > max_age * 86400:
                raise ValueError(f'{sid}: upstream branch has not updated for {max_age} days')
            # 直连底表规模大，做新旧覆盖率变化保护；小表源不做（列表本身会抖动）。
            if old_data and 'min_addresses' in spec:
                old = source_validate(spec, old_data)
                new = source_validate(spec, data)
                old_size = sum(n.num_addresses for n in old)
                new_size = sum(n.num_addresses for n in new)
                if old_size and abs(new_size / old_size - 1) > .15:
                    raise ValueError(f'{sid}: source coverage changed by more than 15%')
            meta = {'repo': spec['repo'], 'ref': spec['ref'], 'path': spec['path'],
                    'commit': commit, 'sha256': digest(data), 'fetched_at': int(time.time()),
                    'commit_time': stamp,
                    'url': f'https://github.com/{spec["repo"]}/blob/{commit}/{spec["path"]}'}
            return data, meta, None
        except Exception as e:
            error = f'{sid}: {type(e).__name__}: {e}'
    if previous and old_data and digest(old_data) == previous['sha256']:
        source_validate(spec, old_data)
        if time.time() - previous['fetched_at'] <= 72 * 3600:
            return old_data, previous, error
    raise RuntimeError(error or f'{sid}: no valid source snapshot newer than 72h')


def render_ros(nets, name='DIRECT_IP'):
    """直连表增量更新：先 add/update，最后清本管线拥有而本次缺失的旧记录。

    保留手工条目与其它管线条目；重复导入可复用既有地址。不得改动路由/BGP。
    """
    raw = cidr_text(nets)
    generation = 'ip-rules-auto:' + digest(raw.encode())[:16]
    rows = ['# IPv4 direct IP set; see scripts/ip-rules/README.md for source attribution.',
            '# Does not configure routes/BGP. Import must be serialized.', '{',
            f':local generation "{generation}";', ':local prefixes {']
    # RouterOS stores /32 address-list entries in host representation.
    rows += [f'"{n.network_address if n.prefixlen == 32 else n}";' for n in nets]
    rows += ['};', ':local wanted [:toarray ""];', ':local existing [:toarray ""];',
             ':local keep [:toarray ""];',
             ':foreach prefix in=$prefixes do={ :set ($wanted->$prefix) true; };',
             f':foreach entry in=[/ip firewall address-list print as-value where list="{name}"] do={{',
             '  :local key [:tostr ($entry->"address")];',
             '  :set ($existing->$key) true;',
             '  :if (($wanted->$key) = true && ($entry->"comment") ~ "^(ip-rules|direct-ip)-auto:" && ($entry->"dynamic") = false) do={',
             '    :set keep ($keep, ($entry->".id"));',
             '  };', '};',
             ':if ([:len $keep] > 0) do={ /ip firewall address-list set $keep comment=$generation; };',
             ':foreach prefix in=$prefixes do={',
             '  :if (($existing->$prefix) != true) do={',
             f'    /ip firewall address-list add list="{name}" address=$prefix comment=$generation;',
             '  };', '};',
             '# This line is reached only after every desired entry was processed.',
             f'/ip firewall address-list remove [find where list="{name}" and dynamic=no and comment~"^(ip-rules|direct-ip)-auto:" and comment!=$generation];',
             f':log info "DIRECT_IP synced: {len(nets)} IPv4 prefixes";', '}', '']
    return '\n'.join(rows)


def render_table_rsc(name, spec, v4, v6):
    """独立地址表（cn/运营商/blacklist）整表重建。

    与直连表的增量更新不同，这些表不含本管线之外的静态手工条目，
    因此按 2026-11-26 前的 domain-rules 语义整表重建：先清表（blacklist 保留动态、
    迁移旧列表名），再全量 add。语义等价，便于 ROS 侧重复 import。
    """
    list_name = spec['ros_list']
    marker = spec.get('marker')
    legacy = spec.get('legacy_lists', [])
    remove_mode = spec.get('remove_mode')
    if remove_mode == 'static':
        # 清全部静态、保留动态（与 OxiDNS 动态注入共存的黑名单表用此模式），
        # 重建内容必须是全量超集，否则会丢掉旧表独有网段。
        remove_lines = [f'remove [find where list="{list_name}" && dynamic=no]']
        remove_lines += [f'remove [find list={old}]' for old in legacy]
    elif marker:
        remove_lines = [f'remove [find where list="{list_name}" && comment="{marker}"]']
        remove_lines += [f'remove [find list={old}]' for old in legacy]
    elif legacy:
        remove_lines = [f'remove [find list={list_name}]']
        remove_lines += [f'remove [find list={old}]' for old in legacy]
    else:
        remove_lines = [f'remove [find list={list_name}]']
    ts = time.strftime('%F %T')
    rows = [f'#{name} — {len(v4) + len(v6)} 条, {ts} 由 ip-rules/gen_direct.py 生成\n',
            f'# ROS 拉取: /tool fetch url="http://192.168.40.1:18080/ros/{name}.rsc" mode=http\n',
            f'#         /import file-name={name}.rsc\n',
            '/ip firewall address-list\n']
    for line in remove_lines:
        rows.append(line + '\n')
    comment = f' comment="{marker}"' if marker else ''
    for n in v4:
        address = n.with_prefixlen
        if remove_mode == 'static':
            # RouterOS 地址表把 /32 存成主机形式，逐条 remove 用主机表示。
            key = str(n.network_address) if n.prefixlen == n.max_prefixlen else address
            rows.append(f'remove [find where list="{list_name}" and address="{key}"]\n')
        rows.append(f'add list={list_name} address={address}{comment}\n')
    if v6 and spec.get('ipv6'):
        rows.append('\n/ipv6 firewall address-list\n')
        for n in v6:
            rows.append(f'add list={list_name} address={n.with_prefixlen}{comment}\n')
    elif v6:
        rows.append(f'# （{len(v6)} 条 IPv6 网段未导入：内网未启用 IPv6，ipv6=true 可开启）\n')
    return ''.join(rows)


def operator_variants(all_direct, ct, cm, name='DIRECT_IP'):
    """Per-operator exclusion tables: NOCM drops CM (mobile) nets, NOCT drops CT (telecom) nets.

    Both are derived from the same daily DIRECT_IP set so a carrier line only
    carries prefixes that do not belong to the other carrier.
    """
    return {f'{name}_NOCM': minus(all_direct, cm),
            f'{name}_NOCT': minus(all_direct, ct)}


def publish(outputs, root, static):
    """Each complete release is selected by one atomic current-symlink switch."""
    release_id = digest(b''.join(k.encode() + v.encode() for k, v in sorted(outputs.items())))[:20]
    release = root / 'releases' / release_id
    release.mkdir(parents=True, exist_ok=True)
    for name, body in outputs.items():
        atomic(release / name, body)
    static.mkdir(parents=True, exist_ok=True)
    for name in outputs:
        target = root / 'current' / name
        link = static / name
        if os.path.lexists(link) and (not link.is_symlink() or os.readlink(link) != str(target)):
            raise RuntimeError(f'refusing to overwrite unrelated published file: {link}')
        if not os.path.lexists(link):
            link.symlink_to(target)
    temp = root / f'.current-{os.getpid()}'
    temp.symlink_to(release)
    os.replace(temp, root / 'current')


def build_table(name, spec, cfg, parsed, base, refresh, warnings):
    """按 tables 定义生成独立地址表（v4 + 未启用的 v6 计数）。"""
    from asn_sources import load_asn
    v4, v6, asns = [], [], {}
    for sid in spec['sources']:
        v4.extend(parsed[sid])
    for cidr in spec.get('extra_cidrs', []):
        net = ip.ip_network(cidr, strict=False)
        (v6 if net.version == 6 else v4).append(net)
    for asn in spec.get('asns', []):
        av4, av6, meta, warning = load_asn(
            asn, base, refresh, spec.get('asn_max_prefixes', 10000),
            spec.get('asn_max_addresses', 1 << 24))
        v4.extend(av4)
        v6.extend(av6)
        asns[str(asn)] = meta
        if warning:
            warnings.append(warning)
    m4 = list(ip.collapse_addresses(v4))
    m6 = list(ip.collapse_addresses(v6))
    if not spec['min_prefixes'] <= len(m4) <= spec['max_prefixes']:
        raise ValueError(f'table {name}: IPv4 prefix count {len(m4)} outside '
                         f'[{spec["min_prefixes"]}, {spec["max_prefixes"]}]')
    report = {'ros_list': spec['ros_list'], 'output': f'{name}.rsc',
              'prefixes': len(m4), 'addresses': sum(n.num_addresses for n in m4),
              'ipv6_prefixes_not_imported': len(m6), 'sources': list(spec['sources']),
              'asns': asns, 'legacy_lists': list(spec.get('legacy_lists', []))}
    return {'v4': m4, 'v6': m6, 'spec': spec, 'report': report}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', type=Path, default=Path(__file__).resolve().parent)
    ap.add_argument('--cache', type=Path, default=Path('/var/cache/ip-rules-upstreams'))
    ap.add_argument('--offline', action='store_true',
                    help='不拉上游，只用 input/upstream 里 72 小时内的已验证快照重新生成')
    ap.add_argument('--publish-root', type=Path)
    ap.add_argument('--static-dir', type=Path, default=Path('/srv/github-mirror/static/ros'))
    args = ap.parse_args()
    base, cache = args.base, args.cache
    refresh = not args.offline
    cfg = json.loads((base / 'sources.json').read_text())
    manual_dir, upstream_dir = input_layout(base)
    for sid, spec in cfg['sources'].items():
        spec['id'] = sid
    cache.mkdir(parents=True, exist_ok=True)

    warnings = []
    used = set(cfg.get('direct_sources', []))
    for spec in cfg['tables'].values():
        used.update(spec['sources'])
    raw, parsed = {}, {}
    for sid, spec in cfg['sources'].items():
        if sid not in used:
            continue
        data, meta, warning = fetch_source(spec, base, cache, refresh)
        raw[sid] = (data, meta)
        parsed[sid] = source_validate(spec, data)
        if warning:
            warnings.append(warning)

    # ① 独立地址表：cn / 运营商 / blacklist（语义同 2026-11-26 前的 domain-rules）
    tables, table_reports, outputs = {}, {}, {}
    for name, spec in cfg['tables'].items():
        tables[name] = build_table(name, spec, cfg, parsed, base, refresh, warnings)
        table_reports[name] = tables[name]['report']
        outputs[f'{name}.rsc'] = render_table_rsc(name, spec, tables[name]['v4'], tables[name]['v6'])
    for name in cfg['tables']:
        if name not in TABLE_OUTPUTS:
            warnings.append(f'table {name}: 未在 TABLE_OUTPUTS 登记（仅影响提示）')

    # ② 直连表：上游 CN 三源 ∪ 手工层，再减排除层
    from asn_sources import load_asn
    upstream = list(ip.collapse_addresses(
        [n for sid in cfg.get('direct_sources', []) for n in parsed[sid]]))
    manual_ipv4 = parse_cidrs((manual_dir / 'include-ipv4.txt').read_text())
    exclude_manual = parse_cidrs((manual_dir / 'exclude-ipv4.txt').read_text())
    exclude_tables = cfg.get('exclude', {}).get('tables', [])
    excluded = list(ip.collapse_addresses(
        exclude_manual + [n for t in exclude_tables for n in tables[t]['v4']]))
    asn_nets, asn_report = [], {}
    for asn in cfg.get('direct_asns', []):
        v4, _v6, meta, warning = load_asn(asn, base, refresh)
        asn_nets.extend(v4)
        asn_report[str(asn)] = dict(meta, aggregated_ipv4_prefixes=len(list(ip.collapse_addresses(v4))))
        outputs[f'direct-as{asn}-ipv4.txt'] = cidr_text(v4)
        if warning:
            warnings.append(warning)
    manual = list(ip.collapse_addresses(manual_ipv4 + asn_nets))
    all_direct, manual_conflicts = assemble(upstream, manual, excluded)
    extra = minus(manual, upstream + excluded)
    effective_cn = minus(upstream, excluded)
    size = sum(n.num_addresses for n in all_direct)
    if not 1000 <= len(all_direct) <= 30000 or not 100_000_000 <= size <= 650_000_000:
        raise ValueError('combined direct output outside expected bounds')
    old_path = output_path(base, 'direct-ipv4.txt')
    if old_path.exists():
        old = parse_cidrs(old_path.read_text())
        old_size = sum(n.num_addresses for n in old)
        if old_size and (abs(size / old_size - 1) > .15
                         or abs(len(all_direct) / len(old) - 1) > .5):
            raise ValueError('combined output changed too much; old release retained')

    ct_nets = tables['cn-telecom']['v4']
    cm_nets = tables['cn-mobile']['v4']
    operator = ct_nets + cm_nets
    nocm_name = cfg['ros_list'] + '_NOCM'
    noct_name = cfg['ros_list'] + '_NOCT'
    variants = operator_variants(all_direct, ct_nets, cm_nets, cfg['ros_list'])

    report = {'ipv4_only': True, 'list': cfg['ros_list'],
              'precedence': ['upstream-sources', 'manual-include+direct-asns',
                             'exclude-ipv4+blacklist-table', 'operator-variants(NOCM/NOCT)'],
              'upstream_prefixes': len(upstream),
              'upstream_addresses': sum(n.num_addresses for n in upstream),
              'manual_ipv4_prefixes': len(manual_ipv4),
              'manual_ipv4_addresses': sum(n.num_addresses for n in manual_ipv4),
              'manual_asn_prefixes': len(list(ip.collapse_addresses(asn_nets))),
              'manual_conflicts_prefixes': len(manual_conflicts),
              'manual_conflicts': [str(n) for n in manual_conflicts][:200],
              'cn_union_prefixes': len(upstream),
              'cn_effective_prefixes': len(effective_cn),
              'direct_prefixes': len(all_direct), 'direct_addresses': size,
              'extra_outside_cn_prefixes': len(extra), 'excluded_prefixes': len(excluded),
              'direct_nocm_prefixes': len(variants[nocm_name]),
              'direct_noct_prefixes': len(variants[noct_name]),
              'existing_ct_cm_unique_prefixes': len(list(ip.collapse_addresses(operator))),
              'direct_addresses_outside_ct_cm': sum(n.num_addresses for n in minus(all_direct, operator)),
              'warnings': warnings, 'sources': {}, 'direct_asns': asn_report,
              'tables': table_reports}
    for sid in cfg.get('direct_sources', []):
        nets = parsed[sid]
        others = [n for oid in cfg['direct_sources'] if oid != sid for n in parsed[oid]]
        report['sources'][sid] = {'prefixes': len(nets),
                                  'addresses': sum(n.num_addresses for n in nets),
                                  'unique_addresses': sum(n.num_addresses for n in minus(nets, others)),
                                  'sha256': raw[sid][1]['sha256']}

    outputs.update({
        'direct-ipv4.txt': cidr_text(all_direct),
        'direct-cn-ipv4.txt': cidr_text(effective_cn),
        'direct-extra-ipv4.txt': cidr_text(extra),
        'direct-excluded-ipv4.txt': cidr_text(excluded),
        'direct-manual-ipv4.txt': cidr_text(manual),
        'direct-ipv4.rsc': render_ros(all_direct, cfg['ros_list']),
        'direct-ipv4-nocm.rsc': render_ros(variants[nocm_name], nocm_name),
        'direct-ipv4-noct.rsc': render_ros(variants[noct_name], noct_name),
        'direct-ipv4-report.json': json_text(report),
    })
    # 所有校验完成后才动最后一份好产物。
    for sid, (data, meta) in raw.items():
        atomic(upstream_dir / f'{sid}.txt', data)
        atomic(upstream_dir / f'{sid}.json', json_text(meta))
    for name, body in outputs.items():
        atomic(output_path(base, name), body)
    if args.publish_root:
        publish(outputs, args.publish_root, args.static_dir)
    print(json_text(report), flush=True)


if __name__ == '__main__':
    main()
