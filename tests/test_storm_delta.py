import datetime as dt, sys, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import storm_delta as s
class StormTests(unittest.TestCase):
    def setUp(self):
        self.t0=s.instant('2026-01-02T00:00Z'); self.t1=s.instant('2026-01-05T00:00Z')
    def rows(self,vals): return [s.row(t,v,'fixture') for t,v in vals]
    def test_three_response_classes(self):
        for vals,expected in [([('2026-01-01T23:45Z',1),('2026-01-02T01:00Z',20),('2026-01-02T05:00Z',1),('2026-01-05T00:00Z',1)],'flash'),([('2026-01-01T23:45Z',1),('2026-01-02T01:00Z',20),('2026-01-05T00:00Z',8)],'sustained'),([('2026-01-01T23:45Z',0.2),('2026-01-02T01:00Z',0.3),('2026-01-05T00:00Z',0.2)],'no response')]:
            rows=self.rows(vals); summary=s.summarize(rows,self.t0,self.t1)
            self.assertEqual(s.response(summary,rows,self.t1,True)[0],expected)
    def test_missing_baseline_and_history(self):
        rows=self.rows([('2026-01-02T01:00Z',20)])
        summary=s.summarize(rows,self.t0,self.t1)
        self.assertIsNone(summary['start']); self.assertEqual(s.response(summary,rows,self.t1,True),(None,None)); self.assertEqual(s.ranks([],summary['peak']),(None,None))
    def test_well_depth_sign_and_dates(self):
        rows=self.rows([('2026-01-01',100),('2026-01-03',98)])
        pair=s.well_pair(rows,self.t0,self.t1,True)
        self.assertEqual(pair['change_ft'],2); self.assertEqual(pair['days_between'],2)
    def test_crossing_and_72_hour_recession(self):
        rows=self.rows([('2026-01-01T12:00Z',1),('2026-01-02T12:00Z',10),('2026-01-03T12:00Z',1)])
        w=s.detect_windows({'a':rows},{'a':5},[],s.instant('2026-01-07T00:00Z'))[0]
        self.assertEqual(w['t0'],'2026-01-01T12:00:00Z'); self.assertEqual(w['t1'],'2026-01-06T12:00:00Z'); self.assertEqual(w['triggered_by'][0]['reading']['value'],10)
    def test_first_high_is_not_crossing(self):
        self.assertEqual(s.detect_windows({'a':self.rows([('2026-01-02T12:00Z',10)])},{'a':5},[],self.t1),[])
    def test_open_never_invents_recession(self):
        w=s.detect_windows({'a':self.rows([('2026-01-01T12:00Z',1),('2026-01-02T12:00Z',10)])},{'a':5},[],self.t1)[0]
        self.assertIsNone(w['t1']); self.assertEqual(w['gauges_without_observed_recession'],['a'])
    def test_feed_fraction_uses_reporting_gauges(self):
        rows=[dict(site=str(i),agency='LCRA',site_type='rain',observed_at='2026-01-02T12:00Z',rain_in={'1Day':1 if i==0 else 0}) for i in range(5)]
        rows.append(dict(site='missing',agency='LCRA',site_type='rain',observed_at='2026-01-02T12:00Z',rain_in={}))
        trigger=s.rain_triggers({'fixture':rows})[0]
        self.assertEqual(trigger['reporting'],5); self.assertEqual(trigger['wet'],1)
    def test_trapezoid_and_gap(self):
        rows=self.rows([('2026-01-02T00:00Z',10),('2026-01-02T01:00Z',20),('2026-01-02T04:00Z',30)])
        v=s.volume(rows,self.t0,self.t1)
        self.assertEqual(v['acre_ft'],round(15*3600/43560,1)); self.assertEqual(len(v['gaps']),1)
        self.assertIsNone(s.volume([],self.t0,self.t1)['acre_ft'])
    def test_rate_requires_exact_time_pairs(self):
        rows=self.rows([('2026-01-02T00:00Z',1),('2026-01-02T00:15Z',3)])
        r=s.rate_of_rise(rows,self.t0,self.t1)
        self.assertEqual(r['15_minutes']['change_ft'],2); self.assertIsNone(r['60_minutes'])
    def test_no_zero_baseline_threshold_substitution(self):
        rows=self.rows([('2026-01-01T23:00Z',0),('2026-01-02T00:00Z',10),('2026-01-02T01:00Z',0)])
        summary=s.summarize(rows,self.t0,self.t1)
        self.assertNotEqual(s.response(summary,rows,self.t1,True)[0],'flash')
    def test_hourly_rain_sum_requires_complete_interval(self):
        rows=self.rows([('2026-01-02T00:00Z',9),('2026-01-02T00:15Z',.1),('2026-01-02T00:30Z',.2),('2026-01-02T00:45Z',.3),('2026-01-02T01:00Z',.4)])
        self.assertEqual(s.rain_intensity(rows)['inches_per_hour'],1)
        self.assertIsNone(s.rain_intensity([rows[0],rows[-1]]))
    def test_series_do_not_merge_different_sensors(self):
        import sqlite3
        db=sqlite3.connect(':memory:')
        db.execute('create table observations(station_id,parameter,observed_at,value,raw_path,series_id,retrieved_at)')
        db.executemany('insert into observations values(?,?,?,?,?,?,?)',[
            ('USGS-fixture','00060','2026-01-02T00:00Z',1,'raw-a','primary','2026-01-03'),
            ('USGS-fixture','00060','2026-01-02T00:15Z',2,'raw-a','primary','2026-01-03'),
            ('USGS-fixture','00060','2026-01-02T00:00Z',999,'raw-b','alternate','2026-01-03')])
        rows=s.series(db,focus=(self.t0,self.t1))[('fixture','00060')]
        self.assertEqual([r['value'] for r in rows],[1,2]); self.assertEqual(rows[0]['other_series_ids'],['alternate'])
    def test_daily_baseline_does_not_invent_a_clock_time(self):
        rows=self.rows([('2026-01-01',3),('2026-01-02',4),('2026-01-03',5)])
        summary=s.summarize(rows,s.instant('2026-01-02T12:00Z'),s.instant('2026-01-04T00:00Z'))
        self.assertEqual(summary['start']['at'],'2026-01-01')
    def test_cap_closes_a_persistently_high_gauge(self):
        rows=self.rows([('2026-01-01T12:00Z',1),('2026-01-02T12:00Z',10),('2026-01-15T12:00Z',10)])
        w=s.detect_windows({'a':rows},{'a':5},[],s.instant('2026-01-15T12:00Z'))[0]
        self.assertEqual(w['status'],'closed'); self.assertEqual(w['t1'],'2026-01-11T12:00:00Z')

    def test_detection_never_overwrites_original_evidence(self):
        import tempfile
        from unittest.mock import patch
        w=s.detect_windows({'a':self.rows([('2026-01-01T12:00Z',1),('2026-01-02T12:00Z',10)])},{'a':5},[],self.t1)[0]
        with tempfile.TemporaryDirectory() as tmp, patch.object(s,'STORMS',Path(tmp)):
            self.assertTrue(s.save_window(w)); original=(Path(tmp)/'2026-01-02.json').read_bytes()
            self.assertFalse(s.save_window({**w,'status':'closed'}))
            self.assertEqual((Path(tmp)/'2026-01-02.json').read_bytes(),original)

    def test_rain_clock_drift_uses_actual_duration_without_filling_gaps(self):
        rows=self.rows([('2026-01-02T00:10:20Z',9),('2026-01-02T00:25:22Z',.1),('2026-01-02T00:40:21Z',.2),('2026-01-02T00:55:23Z',.3),('2026-01-02T01:10:25Z',.4)])
        result=s.rain_intensity(rows)
        self.assertEqual(result['elapsed_seconds'],3605)
        self.assertEqual(result['inches_per_hour'],round(3600/3605,4))
        self.assertIsNone(s.rain_intensity(rows[:2]+rows[3:]))
