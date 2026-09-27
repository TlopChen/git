#!/usr/bin/env python3
"""IPv4 direct-route artifacts. Fetch -> raw snapshots -> validate -> publish.

No RouterOS login/import or routing changes. Standard library + git + dig.
"""
import argparse
import concurrent.futures
import datetime as dt
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


def canonical(n):
    n = ip.ip_network(n, strict=False)
    if n.version != 4 or n.prefixlen < 8 or any(n.overlaps(b) for b in NONPUBLIC):
        raise ValueError(f'not an allowed public IPv4 prefix: {n}')
    return n


def parse_cidrs(text):
    result = []
    for number, line in enumerate(text.splitlines(), 1):
        line = line.partition('#')[0].strip()
        if not line:
            continue
        # Accept CIDR/IP only, never scrape IP-looking text from error pages.
        try:
            result.append(canonical(line))
        except ValueError as e:
            raise ValueError(f'line {number}: {e}') from e
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


def git(repo, *args):
    env = dict(os.environ, GIT_TERMINAL_PROMPT='0',
               GIT_SSH_COMMAND='ssh -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=15')
    r = subprocess.run(['git', '-C', str(repo), *args], capture_output=True, timeout=120, env=env)
    if r.returncode:
        raise RuntimeError(r.stderr.decode(errors='replace')[-1200:])
    return r.stdout


def steam_cn(text):
    rules = []
    for line in text.splitlines():
        parts = line.partition('#')[0].split()
        if len(parts) < 2 or '@cn' not in parts[1:]:
            continue
        token = parts[0]
        exact = token.startswith('full:')
        host = token.removeprefix('full:').lower()
        if not re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?', host) or '.' not in host:
            raise ValueError(f'unsupported Steam CN rule: {token}')
        rules.append({'domain': host, 'match': 'full' if exact else 'domain-suffix',
                      'source': 'steam-cn', 'required': False})
    if not 5 <= len(rules) <= 200:
        raise ValueError('Steam CN source count outside bounds')
    return rules


def source_validate(spec, data):
    text = data.decode('utf-8-sig', errors='strict')
    if spec['kind'] == 'cidr':
        nets = parse_cidrs(text)
        count = len(nets)
        coverage = sum(n.num_addresses for n in nets)
        if not spec['min_prefixes'] <= count <= spec['max_prefixes']:
            raise ValueError(f'{spec["id"]}: unexpected prefix count {count}')
        if not 100_000_000 <= coverage <= 650_000_000:
            raise ValueError(f'{spec["id"]}: unexpected address coverage {coverage}')
        return nets
    return steam_cn(text)


def fetch_source(spec, base, cache, refresh):
    sid = spec['id']
    raw_path = base / 'raw' / f'{sid}.txt'
    meta_path = base / 'raw' / f'{sid}.json'
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
            if spec['kind'] == 'cidr' and time.time() - stamp > 14 * 86400:
                raise ValueError(f'{sid}: upstream branch has not updated for 14 days')
            if old_data and spec['kind'] == 'cidr':
                old = source_validate(spec, old_data)
                new = source_validate(spec, data)
                old_size = sum(n.num_addresses for n in old)
                new_size = sum(n.num_addresses for n in new)
                if abs(new_size / old_size - 1) > .15:
                    raise ValueError(f'{sid}: source coverage changed by more than 15%')
            meta = {'repo': spec['repo'], 'ref': spec['ref'], 'path': spec['path'],
                    'commit': commit, 'sha256': digest(data), 'fetched_at': int(time.time()),
                    'commit_time': stamp, 'url': f'https://github.com/{spec["repo"]}/blob/{commit}/{spec["path"]}'}
            return data, meta, None
        except Exception as e:
            error = f'{sid}: {type(e).__name__}: {e}'
    if previous and old_data and digest(old_data) == previous['sha256']:
        source_validate(spec, old_data)
        if time.time() - previous['fetched_at'] <= 72 * 3600:
            return old_data, previous, error
    raise RuntimeError(error or f'{sid}: no valid source snapshot newer than 72h')


def resolve_one(rule, resolvers, prior, now):
    host = rule['domain']
    by_resolver, errors = {}, []
    for resolver in resolvers:
        try:
            p = subprocess.run(['dig', '@' + resolver, host, 'A', '+time=2', '+tries=1',
                                '+noall', '+answer', '+comments'], capture_output=True,
                               text=True, timeout=4)
            if p.returncode or 'status: NOERROR' not in p.stdout:
                raise ValueError('DNS query failed or non-NOERROR status')
            found = set()
            for line in p.stdout.splitlines():
                cols = line.split()
                if len(cols) >= 5 and cols[2:4] == ['IN', 'A']:
                    found.add(str(canonical(cols[4])))
            if not found:
                raise ValueError('no A records')
            by_resolver[resolver] = sorted(found)
        except Exception as e:
            errors.append(f'{resolver}: {e}')
    addresses = sorted(set(x for v in by_resolver.values() for x in v))
    if len(addresses) > 128:
        raise ValueError(f'{host}: unexpectedly many DNS answers')
    if addresses:
        state = {'last_success': now, 'addresses': addresses}
        status = 'resolved' if not errors else 'partial'
    elif prior and now - prior['last_success'] <= 86400:
        addresses, state, status = prior['addresses'], prior, 'cached-under-24h'
    elif rule.get('required'):
        raise RuntimeError(f'required direct domain has no usable A records: {host}')
    else:
        state, status = {}, 'unresolved'
    result = dict(rule, addresses=addresses, status=status, resolver_answers=by_resolver,
                  errors=errors, resolution_scope='exact-host-only')
    return result, state


def parse_ros(path):
    text = Path(path).read_text()
    values = re.findall(r'^add\s+.*?\baddress=([0-9./]+)(?:\s|$)', text, re.M)
    if not values:
        raise ValueError(f'no IPv4 addresses found in {path}')
    return list(ip.collapse_addresses(canonical(x) for x in values))


def render_ros(nets, name='DIRECT_IP'):
    """Add/update first, sweep old owned rows last; keep unrelated manual rows."""
    raw = cidr_text(nets)
    generation = 'direct-ip-auto:' + digest(raw.encode())[:16]
    rows = ['# IPv4 direct IP set; see ros/direct-ip/README.md for source attribution.',
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
             '  :if (($wanted->$key) = true && ($entry->"comment") ~ "^direct-ip-auto:" && ($entry->"dynamic") = false) do={',
             '    :set keep ($keep, ($entry->".id"));',
             '  };', '};',
             ':if ([:len $keep] > 0) do={ /ip firewall address-list set $keep comment=$generation; };',
             ':foreach prefix in=$prefixes do={',
             '  :if (($existing->$prefix) != true) do={',
             f'    /ip firewall address-list add list="{name}" address=$prefix comment=$generation;',
             '  };', '};',
             '# This line is reached only after every desired entry was processed.',
             f'/ip firewall address-list remove [find where list="{name}" and dynamic=no and comment~"^direct-ip-auto:" and comment!=$generation];',
             f':log info "DIRECT_IP synced: {len(nets)} IPv4 prefixes";', '}', '']
    return '\n'.join(rows)


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', type=Path, default=Path(__file__).resolve().parent)
    ap.add_argument('--cache', type=Path, default=Path('/var/cache/direct-ip-upstreams'))
    ap.add_argument('--dns-only', action='store_true')
    ap.add_argument('--publish-root', type=Path)
    ap.add_argument('--static-dir', type=Path, default=Path('/srv/github-mirror/static/ros'))
    args = ap.parse_args()
    base, cache = args.base, args.cache
    cfg = json.loads((base / 'sources.json').read_text())
    cache.mkdir(parents=True, exist_ok=True)
    sources, raw, source_meta, warnings, all_cn, domain_rules = {}, {}, {}, [], [], []
    for spec in cfg['sources']:
        data, meta, warning = fetch_source(spec, base, cache, not args.dns_only)
        parsed = source_validate(spec, data)
        raw[spec['id']] = data
        source_meta[spec['id']] = meta
        if warning:
            warnings.append(warning)
        if spec['kind'] == 'cidr':
            sources[spec['id']] = parsed
            all_cn.extend(parsed)
        else:
            domain_rules.extend(parsed)
    manual_rules = json.loads((base / 'direct-domains.json').read_text())
    for rule in manual_rules:
        if not re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?', rule['domain']) or '.' not in rule['domain']:
            raise ValueError('manual domains must be exact lowercase DNS host names')
    rules = {r['domain']: r for r in domain_rules}
    rules.update({r['domain']: dict(r, match='full', source='manual') for r in manual_rules})
    dns_cache = cache / 'dns-state.json'
    prior = json.loads(dns_cache.read_text()) if dns_cache.exists() else {}
    now = int(time.time())
    resolved, new_state = [], {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        futures = {host: pool.submit(resolve_one, rule, cfg['resolvers'], prior.get(host), now)
                   for host, rule in sorted(rules.items())}
        for host, future in futures.items():
            record, state = future.result()
            resolved.append(record)
            if state:
                new_state[host] = state
            if record['status'] != 'resolved':
                warnings.append(f'DNS {host}: {record["status"]}')
    cn = list(ip.collapse_addresses(all_cn))
    manual = parse_cidrs((base / 'include-ipv4.txt').read_text())
    from asn_sources import load_asn
    asn_report, asn_outputs = {}, {}
    for asn in cfg.get('direct_asns', []):
        v4, v6, meta, warning = load_asn(asn, base, not args.dns_only)
        manual.extend(v4)
        asn_report[str(asn)] = dict(meta, aggregated_ipv4_prefixes=len(list(ip.collapse_addresses(v4))))
        asn_outputs[f'direct-as{asn}-ipv4.txt'] = cidr_text(v4)
        if warning:
            warnings.append(warning)
    excluded = parse_cidrs((base / 'exclude-ipv4.txt').read_text())
    protected = parse_ros(cfg['proxy_exclude_file'])
    if len(protected) < 10:
        raise ValueError('existing proxy blacklist unexpectedly short')
    excluded = list(ip.collapse_addresses(excluded + protected))
    dns_nets = [canonical(v) for r in resolved for v in r['addresses']]
    all_direct = minus(cn + manual + dns_nets, excluded)
    extra = minus(manual + dns_nets, cn + excluded)
    effective_cn = minus(cn, excluded)
    size = sum(n.num_addresses for n in all_direct)
    if not 1000 <= len(all_direct) <= 30000 or not 100_000_000 <= size <= 650_000_000:
        raise ValueError('combined direct output outside expected bounds')
    old_path = base / 'output' / 'direct-ipv4.txt'
    if old_path.exists():
        old = parse_cidrs(old_path.read_text())
        old_size = sum(n.num_addresses for n in old)
        if abs(size / old_size - 1) > .15 or abs(len(all_direct) / len(old) - 1) > .5:
            raise ValueError('combined output changed too much; old release retained')
    operator = parse_ros(cfg['ct_file']) + parse_ros(cfg['cm_file'])
    for record in resolved:
        record['excluded_addresses'] = [v for v in record['addresses']
                                        if not minus([canonical(v)], excluded)]
    report = {'ipv4_only': True, 'list': cfg['ros_list'],
              'cn_union_prefixes': len(cn), 'cn_effective_prefixes': len(effective_cn),
              'direct_prefixes': len(all_direct), 'direct_addresses': size,
              'extra_outside_cn_prefixes': len(extra), 'excluded_prefixes': len(excluded),
              'existing_ct_cm_unique_prefixes': len(list(ip.collapse_addresses(operator))),
              'direct_addresses_outside_ct_cm': sum(n.num_addresses for n in minus(all_direct, operator)),
              'warnings': warnings, 'sources': {}, 'direct_asns': asn_report,
              'domain_hosts': len(resolved),
              'domain_hosts_with_addresses': sum(bool(r['addresses']) for r in resolved)}
    for sid, nets in sources.items():
        others = [n for oid, ns in sources.items() if oid != sid for n in ns]
        report['sources'][sid] = {'prefixes': len(nets), 'addresses': sum(n.num_addresses for n in nets),
                                 'unique_addresses': sum(n.num_addresses for n in minus(nets, others)),
                                 'sha256': source_meta[sid]['sha256']}
    outputs = {'direct-ipv4.txt': cidr_text(all_direct),
               'direct-cn-ipv4.txt': cidr_text(effective_cn),
               'direct-extra-ipv4.txt': cidr_text(extra),
               'direct-excluded-ipv4.txt': cidr_text(excluded),
               'direct-ipv4.rsc': render_ros(all_direct, cfg['ros_list']),
               'direct-domains-resolved.json': json_text(resolved),
               'direct-ipv4-report.json': json_text(report)}
    outputs.update(asn_outputs)
    # All validation is complete before changing the last-good artifacts.
    for sid, data in raw.items():
        atomic(base / 'raw' / f'{sid}.txt', data)
        atomic(base / 'raw' / f'{sid}.json', json_text(source_meta[sid]))
    for name, body in outputs.items():
        atomic(base / 'output' / name, body)
    atomic(dns_cache, json_text(new_state))
    if args.publish_root:
        publish(outputs, args.publish_root, args.static_dir)
    print(json_text(report), flush=True)


if __name__ == '__main__':
    main()
