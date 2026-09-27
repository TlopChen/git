import datetime as dt
import json
import unittest
from asn_sources import parse_snapshot

class AsnTests(unittest.TestCase):
    def test_current_only_and_family_separation(self):
        now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
        start = (now - dt.timedelta(hours=24)).isoformat()
        end = now.isoformat()
        obj = {'status':'ok','data':{'resource':'53850','query_endtime':end,'prefixes':[
            {'prefix':'192.154.104.0/21','timelines':[{'starttime':start,'endtime':end}]},
            {'prefix':'8.8.8.0/24','timelines':[{'starttime':start,'endtime':start}]},
            {'prefix':'2606:c700::/32','timelines':[{'starttime':start,'endtime':end}]}
        ]}}
        v4,v6,_=parse_snapshot(json.dumps(obj),53850)
        self.assertEqual(list(map(str,v4)),['192.154.104.0/21'])
        self.assertEqual(list(map(str,v6)),['2606:c700::/32'])
        with self.assertRaises(ValueError): parse_snapshot(json.dumps(obj),123)
        obj['data']['query_endtime']=start[:4]+'-01-01T00:00:00'
        with self.assertRaises(ValueError): parse_snapshot(json.dumps(obj),53850)

if __name__=='__main__': unittest.main()
