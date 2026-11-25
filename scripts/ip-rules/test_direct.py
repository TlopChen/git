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

    def test_parse_table_tokens_ignores_domains_and_comments(self):
        text = '\n'.join([
            '# IP-CIDR 注释 8.8.8.8 不应被当成数据',
            'DOMAIN-SUFFIX,example.com',
            'IP-CIDR,192.133.76.0/22,no-resolve',
            "- '1.0.1.0/24'",
            'DOMAIN,twitter.com',
        ])
        nets = g.parse_table_tokens(text)
        self.assertEqual([str(n) for n in nets], ['1.0.1.0/24', '192.133.76.0/22'])
        # 宽松解析也不"捞出"非公网/畸形 token
        self.assertEqual(g.parse_table_tokens('x 999.1.1.1/24 y'), [])

    def test_source_validate_kinds_and_bounds(self):
        cidr_spec = {'id': 'x', 'kind': 'cidr', 'min_prefixes': 1, 'max_prefixes': 10,
                     'min_addresses': 0, 'max_addresses': 1 << 24}
        self.assertEqual(len(g.source_validate(cidr_spec, b'8.8.8.0/24\n')), 1)
        with self.assertRaises(ValueError):
            g.source_validate(cidr_spec, b'1.0.0.0/8\n2.0.0.0/8\n204.0.0.0/8\n')
        surge_spec = {'id': 'y', 'kind': 'list', 'min_prefixes': 1, 'max_prefixes': 10}
        self.assertEqual(len(g.source_validate(surge_spec, b'IP-CIDR,8.8.8.0/24,no-resolve\n')), 1)
        with self.assertRaises(ValueError):
            g.source_validate({'id': 'z', 'kind': 'bogus'}, b'x')

    def test_failed_source_cache_checks_age_and_hash(self):
        spec = {'id': 'gaoyifan-cn', 'kind': 'cidr', 'repo': 'test/repo', 'ref': 'main',
                'path': 'china.txt', 'min_prefixes': 1, 'max_prefixes': 10,
                'min_addresses': 0, 'max_addresses': 1 << 24}
        raw = b'8.8.8.0/24\n'
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            (base / 'input/upstream').mkdir(parents=True)
            g.atomic(base/'input/upstream/gaoyifan-cn.txt', raw)
            meta = {'sha256': g.digest(raw), 'fetched_at': int(time.time())}
            g.atomic(base/'input/upstream/gaoyifan-cn.json', g.json_text(meta))
            with patch.object(g, 'git', side_effect=RuntimeError('network down')):
                data, _, warning = g.fetch_source(spec, base, base/'cache', True)
                self.assertEqual(data, raw)
                self.assertIn('network down', warning)
            meta['fetched_at'] = 0
            g.atomic(base/'input/upstream/gaoyifan-cn.json', g.json_text(meta))
            with self.assertRaises(RuntimeError):
                g.fetch_source(spec, base, base/'cache', False)

    def test_input_layout_requires_manual_and_upstream(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            (base/'input/manual').mkdir(parents=True)
            (base/'input/upstream').mkdir(parents=True)
            manual, upstream = g.input_layout(base)
            self.assertEqual(manual, base/'input/manual')
            self.assertEqual(upstream, base/'input/upstream')
            with self.assertRaises(RuntimeError):
                g.input_layout(base / 'input' / 'manual')

    def test_input_layout_rejects_legacy_layouts(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            (base/'input/ip').mkdir(parents=True)
            with self.assertRaises(RuntimeError):
                g.input_layout(base)
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            (base/'input/domain').mkdir(parents=True)
            with self.assertRaises(RuntimeError):
                g.input_layout(base)
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            (base/'include-ipv4.txt').write_text('8.8.8.0/24\n')
            with self.assertRaises(RuntimeError):
                g.input_layout(base)

    def test_output_flat_and_rejects_paths(self):
        base = Path('/repo')
        self.assertEqual(g.output_path(base, 'direct-ipv4.rsc'), base/'output/direct-ipv4.rsc')
        self.assertEqual(g.output_path(base, 'cn.rsc'), base/'output/cn.rsc')
        with self.assertRaises(KeyError):
            g.output_path(base, '../evil.txt')

    def test_assemble_precedence_upstream_manual_then_exclusion(self):
        upstream = g.parse_cidrs('8.8.8.0/24')
        manual = g.parse_cidrs('9.9.9.0/24\n80.80.80.0/24')
        excluded = g.parse_cidrs('9.9.9.128/25')
        direct, conflicts = g.assemble(upstream, manual, excluded)
        self.assertEqual(g.cidr_text(direct), '8.8.8.0/24\n9.9.9.0/25\n80.80.80.0/24\n')
        self.assertEqual(g.cidr_text(conflicts), '9.9.9.128/25\n')
        self.assertFalse(any(n.overlaps(ip.ip_network('9.9.9.128/25')) for n in direct))

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

    def test_render_table_rsc_blacklist_static_mode(self):
        spec = {'ros_list': 'blacklist', 'remove_mode': 'static',
                'marker': 'ros-rules-auto', 'legacy_lists': ['ROS_BLACKLIST']}
        text = g.render_table_rsc('blacklist', spec,
                                  g.parse_cidrs('8.8.8.8\n91.108.4.0/22'), [])
        self.assertIn('remove [find where list="blacklist" && dynamic=no]', text)
        self.assertIn('remove [find list=ROS_BLACKLIST]', text)
        # /32 用主机形式逐条清，再以带前缀形式重建
        self.assertIn('remove [find where list="blacklist" and address="8.8.8.8"]', text)
        self.assertIn('add list=blacklist address=8.8.8.8/32 comment="ros-rules-auto"', text)
        self.assertIn('add list=blacklist address=91.108.4.0/22 comment="ros-rules-auto"', text)

    def test_render_table_rsc_whole_table_and_v6_note(self):
        spec = {'ros_list': 'CN', 'legacy_lists': ['ROS_CN']}
        text = g.render_table_rsc('cn', spec, g.parse_cidrs('8.8.8.0/24'), [])
        self.assertIn('remove [find list=CN]', text)
        self.assertIn('remove [find list=ROS_CN]', text)
        self.assertIn('add list=CN address=8.8.8.0/24\n', text)
        self.assertNotIn('comment=', text)
        v6 = [ip.ip_network('2001:4860::/32')]
        text = g.render_table_rsc('cn', spec, g.parse_cidrs('8.8.8.0/24'), v6)
        self.assertIn('1 条 IPv6 网段未导入', text)

    def test_publish_rejects_collision_and_keeps_current(self):
        with tempfile.TemporaryDirectory() as d:
            root, static = Path(d)/'releases-root', Path(d)/'static'
            g.publish({'a.txt': 'old'}, root, static)
            previous = (root/'current').resolve()
            (static/'b.txt').write_text('unrelated')
            with self.assertRaises(RuntimeError):
                g.publish({'a.txt': 'new', 'b.txt': 'new'}, root, static)
            self.assertEqual((root/'current').resolve(), previous)
            self.assertEqual((static/'a.txt').read_text(), 'old')
            self.assertEqual((static/'b.txt').read_text(), 'unrelated')

    def test_render_ros_sweep_after_add_and_only_managed(self):
        rsc = g.render_ros(g.parse_cidrs('8.8.8.8/32\n9.9.9.0/24'))
        self.assertLess(rsc.index('address-list add'), rsc.index('address-list remove'))
        self.assertIn('comment~"^(ip-rules|direct-ip)-auto:"', rsc)
        self.assertIn(':local prefixes {', rsc)
        self.assertNotIn(':local prefixes [', rsc)
        self.assertIn('};', rsc)
        self.assertIn('"8.8.8.8";', rsc)
        self.assertNotIn('list="blacklist"', rsc)


if __name__ == '__main__':
    unittest.main()
