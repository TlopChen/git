"""RIPE RIS ASN snapshots; only prefixes visible at the response endpoint."""
import datetime as dt
import ipaddress as ip
import json
import time
import urllib.request


def timestamp(value):
    return dt.datetime.fromisoformat(value.replace('Z', '+00:00')).replace(tzinfo=dt.timezone.utc).timestamp()


def parse_snapshot(body, asn, max_prefixes=10000, max_addresses=1 << 24):
    """解析 RIPE announced-prefixes；只保留 query_endtime 仍可见的起源前缀。

    返回 (v4 列表, v6 列表, query_endtime)。v4 已按公网前缀规范化，
    并做规模上下限校验，防止异常/错误响应被当成有效快照。
    """
    from gen_direct import canonical
    obj = json.loads(body)
    if obj.get('status') != 'ok':
        raise ValueError('RIPE response status is not ok')
    data = obj['data']
    if str(data['resource']).upper().removeprefix('AS') != str(asn):
        raise ValueError('RIPE resource mismatch')
    end = timestamp(data['query_endtime'])
    if time.time() - end > 48 * 3600:
        raise ValueError('RIPE snapshot older than 48h')
    v4, v6 = set(), set()
    for row in data['prefixes']:
        if not any(timestamp(t['starttime']) <= end <= timestamp(t['endtime']) for t in row['timelines']):
            continue
        net = ip.ip_network(row['prefix'], strict=False)
        if net.version == 4:
            v4.add(canonical(str(net)))
        else:
            v6.add(net)
    merged = list(ip.collapse_addresses(v4))
    if not 1 <= len(merged) <= max_prefixes or sum(n.num_addresses for n in merged) > max_addresses:
        raise ValueError('ASN IPv4 snapshot outside expected bounds')
    return sorted(v4), sorted(v6), data['query_endtime']


def load_asn(asn, base, refresh, max_prefixes=10000, max_addresses=1 << 24):
    """取 ASN 当前公告前缀；刷新失败时回退 72 小时内且哈希一致的快照。"""
    from gen_direct import atomic, digest, json_text
    asn = int(asn)
    snap_dir = base / 'input' / 'upstream'
    raw = snap_dir / f'as{asn}-response.json'
    meta_file = snap_dir / f'as{asn}-meta.json'
    warning = None
    if refresh:
        try:
            # 取最近 24 小时公告，再按响应 query_endtime 丢掉已撤销的条目。
            url = (f'https://stat.ripe.net/data/announced-prefixes/data.json?resource=AS{asn}'
                   f'&starttime={int(time.time()) - 86400}&min_peers_seeing=1')
            with urllib.request.urlopen(url, timeout=35) as r:
                body = r.read(8_000_001)
            if len(body) > 8_000_000:
                raise ValueError('ASN response too large')
            v4, v6, end = parse_snapshot(body, asn, max_prefixes, max_addresses)
            meta = {'asn': asn, 'url': url, 'fetched_at': int(time.time()),
                    'sha256': digest(body), 'snapshot_time': end,
                    'observed_ipv4_prefixes': len(v4), 'observed_ipv6_prefixes': len(v6)}
            atomic(raw, body)
            atomic(meta_file, json_text(meta))
            return v4, v6, meta, None
        except Exception as e:
            warning = f'AS{asn}: {type(e).__name__}: {e}'
    if raw.exists() and meta_file.exists():
        body = raw.read_bytes()
        meta = json.loads(meta_file.read_text())
        if digest(body) == meta['sha256'] and time.time() - meta['fetched_at'] <= 72 * 3600:
            v4, v6, end = parse_snapshot(body, asn, max_prefixes, max_addresses)
            return v4, v6, meta, warning
    raise RuntimeError(warning or f'AS{asn}: no usable snapshot')
