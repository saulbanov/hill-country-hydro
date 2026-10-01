import gzip, hashlib, json, tempfile, unittest
from pathlib import Path
from tools import cloud_capture_restore as cr
class RestoreTests(unittest.TestCase):
    def test_restore_verifies_checksums_and_never_overwrites_a_differing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); folder=root/'_cloud-captures'/'session_x'; folder.mkdir(parents=True)
            body=b'{"a":1}'; sha=hashlib.sha256(body).hexdigest(); (folder/'usgs').mkdir(); (folder/'usgs'/'f.json.gz').write_bytes(gzip.compress(body))
            bad=b'{"b":2}'; (folder/'usgs'/'g.json').write_bytes(bad)
            rows=[{'stored_as':'usgs/f.json.gz','restore_to':'data/raw/usgs/f.json','body_sha256':sha,'body_bytes':len(body),'meta':None},{'stored_as':'usgs/g.json','restore_to':'data/raw/usgs/g.json','body_sha256':'0'*64,'body_bytes':len(bad),'meta':None}]
            (folder/'manifest.jsonl').write_text('\n'.join(json.dumps(r) for r in rows)+'\n')
            c=cr.restore(folder,root); self.assertEqual((c['restored'],c['checksum_mismatch']),(1,1)); self.assertEqual((root/'data/raw/usgs/f.json').read_bytes(),body); self.assertFalse((root/'data/raw/usgs/g.json').exists())
            (root/'data/raw/usgs/f.json').write_bytes(b'{"a":"local differs"}'); c=cr.restore(folder,root); self.assertEqual(c['kept_both'],1); self.assertTrue((root/'data/raw/usgs/f.json.attempt-1').exists()); self.assertEqual((root/'data/raw/usgs/f.json').read_bytes(),b'{"a":"local differs"}')
            c=cr.restore(folder,root,check=True); self.assertEqual(c['kept_both'],1)
if __name__=='__main__': unittest.main()
