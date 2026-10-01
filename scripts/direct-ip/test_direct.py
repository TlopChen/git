import json
import ipaddress as ip
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch
import gen_direct as g


class DirectTests(unittest.TestCase):
    def test_strict_cidr_normalization(self):
        self.assertEqual(g.cidr_text(g.parse_cidrs('8.8.8.9/24 # x\n8.8.9.0/24\n')), '8.8.8.0/23\n')
        for value in ['<html>8.8.8.8</html>', '0.0.0.0/0', '10.1.1.1',
                      '100.64.0.1', '224.0.0.1', '2001:4860::/32', '8.8.8.8 garbage']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                g.parse_cidrs(value)

    def test_subtraction_preserves_holes(self):
        whole = g.parse_cidrs('8.8.8.0/24\n8.8.9.0/24')
        denied = g.parse_cidrs('8.8.8.8/32\n8.8.9.0/25')
        result = g.minus(whole, denied)
        self.assertEqual(sum(n.num_addresses for n in result), 512-1-128)
        self.assertFalse(any(n.overlaps(d) for n in result for d in denied))
        self.assertEqual(g.minus(whole, whole), [])
        self.assertEqual(g.minus(whole, []), whole)

    def test_steam_cn_scope(self):
        data = '\n'.join(f'full:h{i}.example.com @cn' for i in range(5))
        rules = g.steam_cn(data + '\nsteamcommunity.com\nsteamcontent.com\nx.example.com @cn')
        self.assertEqual(len(rules), 6)
        self.assertEqual(rules[-1]['match'], 'domain-suffix')
        self.assertNotIn('steamcontent.com', [r['domain'] for r in rules])

    def test_steam_cn_exclude_hosts(self):
        data = '\n'.join(f'full:h{i}.example.com @cn' for i in range(5)) + '\ndead.example.com @cn\n'
        rules = g.steam_cn(data, ['dead.example.com'])
        self.assertEqual(len(rules), 5)
        self.assertNotIn('dead.example.com', [r['domain'] for r in rules])
        spec = {'id': 'steam-cn', 'kind': 'steam', 'repo': 'test/repo', 'ref': 'master',
                'path': 'data/steam', 'exclude_hosts': ['dead.example.com']}
        self.assertEqual(len(g.source_validate(spec, data.encode())), 5)

    def test_operator_variants_exclude_ct_or_cm(self):
        direct = g.parse_cidrs('8.8.8.0/24\n9.9.9.0/24\n80.80.80.0/24')
        ct = g.parse_cidrs('80.80.80.0/24')
        cm = g.parse_cidrs('9.9.9.0/24')
        variants = g.operator_variants(direct, ct, cm, 'DIRECT_IP')
        nocm, noct = variants['DIRECT_IP_NOCM'], variants['DIRECT_IP_NOCT']
        self.assertEqual(sorted(str(n) for n in nocm), ['8.8.8.0/24', '80.80.80.0/24'])
        self.assertEqual(sorted(str(n) for n in noct), ['8.8.8.0/24', '9.9.9.0/24'])
        rsc = g.render_ros(nocm, 'DIRECT_IP_NOCM')
        self.assertIn('list="DIRECT_IP_NOCM"', rsc)
        self.assertNotIn('list="DIRECT_IP"', rsc)

    def test_dns_stale_limit_and_required_domain(self):
        rule = {'domain': 'test.example.com', 'required': True}
        with patch.object(g.subprocess, 'run', side_effect=subprocess.TimeoutExpired('dig', 4)):
            result, _ = g.resolve_one(rule, ['223.5.5.5'],
                                      {'last_success': 100, 'addresses':['8.8.8.8/32']}, 200)
            self.assertEqual(result['status'], 'cached-under-24h')
            with self.assertRaises(RuntimeError):
                g.resolve_one(rule, ['223.5.5.5'],
                              {'last_success':100, 'addresses':['8.8.8.8/32']}, 90000)

    def test_dns_rejects_private_and_partial_keeps_public(self):
        good = subprocess.CompletedProcess([], 0, ';; status: NOERROR\nx. 60 IN A 8.8.8.8\n', '')
        bad = subprocess.CompletedProcess([], 0, ';; status: NOERROR\nx. 60 IN A 10.0.0.1\n', '')
        with patch.object(g.subprocess, 'run', side_effect=[good, bad]):
            record, _ = g.resolve_one({'domain':'x.example','required':True}, ['a','b'], None, 100)
            self.assertEqual(record['addresses'], ['8.8.8.8/32'])
            self.assertEqual(record['status'], 'partial')

    def test_failed_source_cache_checks_age_and_hash(self):
        spec = {'id':'steam-cn','kind':'steam','repo':'test/repo','ref':'master','path':'data/steam'}
        raw = '\n'.join(f'full:h{i}.example.com @cn' for i in range(5)).encode()
        with tempfile.TemporaryDirectory() as d:
            base=Path(d)
            g.atomic(base/'raw/steam-cn.txt',raw)
            meta={'sha256':g.digest(raw),'fetched_at':int(time.time())}
            g.atomic(base/'raw/steam-cn.json',g.json_text(meta))
            with patch.object(g, 'git', side_effect=RuntimeError('network down')):
                data, _, warning = g.fetch_source(spec,base,base/'cache',True)
                self.assertEqual(data,raw)
                self.assertIn('network down', warning)
            meta['fetched_at']=0
            g.atomic(base/'raw/steam-cn.json',g.json_text(meta))
            with self.assertRaises(RuntimeError):
                g.fetch_source(spec,base,base/'cache',False)

    def test_publish_rejects_collision_and_keeps_current(self):
        with tempfile.TemporaryDirectory() as d:
            root, static=Path(d)/'releases-root',Path(d)/'static'
            g.publish({'a.txt':'old'},root,static)
            previous=(root/'current').resolve()
            (static/'b.txt').write_text('unrelated')
            with self.assertRaises(RuntimeError):
                g.publish({'a.txt':'new','b.txt':'new'},root,static)
            self.assertEqual((root/'current').resolve(),previous)
            self.assertEqual((static/'a.txt').read_text(),'old')
            self.assertEqual((static/'b.txt').read_text(),'unrelated')

    def test_rsc_sweep_after_add_and_only_managed(self):
        rsc=g.render_ros(g.parse_cidrs('8.8.8.8/32\n9.9.9.0/24'))
        self.assertLess(rsc.index('address-list add'),rsc.index('address-list remove'))
        self.assertIn('comment~"^direct-ip-auto:"',rsc)
        self.assertIn('"8.8.8.8";',rsc)
        self.assertNotIn('list="blacklist"',rsc)


if __name__=='__main__':
    unittest.main()
