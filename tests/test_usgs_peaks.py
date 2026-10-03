import sys, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import usgs_peaks as p
class PeaksTests(unittest.TestCase):
    def test_missing_partial_date_and_qualifiers(self):
        raw=b'# USGS\nagency_cd\tsite_no\tpeak_dt\tpeak_va\tgage_ht\tpeak_cd\n5s\t15s\t10d\t8n\t8n\t2s\nUSGS\t08155500\t1990-00-00\t123\t\t7\nUSGS\t08155500\t1991-01-02\t\t1.2\t\n'
        rows=p.parse_rdb(raw,'08155500')
        self.assertEqual(len(rows),1); self.assertEqual(rows[0]['date'],'1990-00-00'); self.assertIsNone(rows[0]['gage_height_ft'])
        self.assertIn('7',rows[0]['qualifiers'])
    def test_retirement_is_not_empty_history(self):
        self.assertIsNone(p.parse_rdb(b'<html>Retired</html>','08155500'))
    def test_identity(self):
        with self.assertRaises(ValueError): p.parse_rdb(b'agency_cd\tsite_no\tpeak_va\nUSGS\twrong\t4','08155500')
    def test_nonfinite_missing(self):
        for v in ['NaN','Infinity',None,'']: self.assertIsNone(p.number(v))
    def test_window_bounds_before_network(self):
        with self.assertRaises(ValueError): p.collect_window(['08155500'],'2026-01-01T00:00Z','2026-02-01T00:00Z')
