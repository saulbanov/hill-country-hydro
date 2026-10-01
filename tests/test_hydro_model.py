"""Fixture tests for the measurement, context, relationship, and event layers. No network, no local raw archive needed."""
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from tools import hydro_context as hc
from tools import event_ledger as el
from tools import reach_geometry as rg
from tools import usgs_history as uh

ROOT=Path(__file__).resolve().parents[1]
UTC=dt.timezone.utc
AT=dt.datetime(2026,9,29,1,0,tzinfo=UTC)

def rows(values,start=AT-dt.timedelta(hours=8),step_minutes=15,retrieved='2026-09-29T01:05:00+00:00'):
    return hc.dedupe([{'observed_at':(start+dt.timedelta(minutes=i*step_minutes)).isoformat(),'retrieved_at':retrieved,'value':v,'qualifiers':[],'unit':'ft^3/s'} for i,v in enumerate(values)])

def daily(years,value_for_day,first=dt.date(1990,1,1)):
    out=[];d=first
    while d.year<first.year+years:
        out.append({'date':d,'value':value_for_day(d),'approval':'Approved'});d+=dt.timedelta(days=1)
    return out

class HydroContextTests(unittest.TestCase):
    def test_trend_direction_rate_and_tolerance(self):
        flat=rows([0.0]*33); self.assertEqual(hc.trend(flat,'00060')['direction'],'steady')
        rising=rows([float(i) for i in range(33)]); t=hc.trend(rising,'00060')
        self.assertEqual(t['direction'],'rising'); self.assertEqual(t['hours'],6.0); self.assertAlmostEqual(t['change'],24.0); self.assertAlmostEqual(t['change_per_hour'],4.0)
        falling=rows([float(40-i) for i in range(33)]); self.assertEqual(hc.trend(falling,'00060')['direction'],'falling')
        tiny=rows([10.0]*32+[10.3]); self.assertEqual(hc.trend(tiny,'00060')['direction'],'steady','a 3% wobble stays within the 5% tolerance')
    def test_trend_unknown_when_no_comparable_observation(self):
        short=rows([1.0,2.0,3.0]); t=hc.trend(short,'00060'); self.assertEqual(t['direction'],'unknown'); self.assertIn('no observation',t['reason'])
        self.assertEqual(hc.trend([],'00060')['direction'],'unknown')
    def test_dedupe_keeps_latest_retrieval_per_timestamp(self):
        a={'observed_at':'2026-09-29T00:00:00+00:00','retrieved_at':'2026-09-29T00:10:00+00:00','value':1.0,'qualifiers':[],'unit':'ft^3/s'}
        b={**a,'retrieved_at':'2026-09-29T00:20:00+00:00','value':2.0}
        out=hc.dedupe([a,b,a]); self.assertEqual(len(out),1); self.assertEqual(out[0]['value'],2.0)
        with self.assertRaises(ValueError): hc.dedupe([{**a,'observed_at':'2026-09-29T00:00:00'}])
    def test_window_peak_and_health(self):
        r=rows([0.0]*10+[6.5]+[0.2]*22); pk=hc.window_peak(r)
        self.assertEqual(pk['value'],6.5); self.assertFalse(pk['is_latest']); self.assertAlmostEqual(pk['hours_before_latest'],5.5); self.assertEqual(pk['window_minimum'],0.0)
        h=hc.data_health(r,AT); self.assertTrue(h['fresh']); self.assertEqual(h['gaps_over_60_minutes'],0); self.assertEqual(h['median_spacing_minutes'],15.0)
        stale=hc.data_health(r,AT+dt.timedelta(hours=3)); self.assertFalse(stale['fresh'])
        gappy=hc.dedupe([{'observed_at':(AT-dt.timedelta(hours=h)).isoformat(),'retrieved_at':'x','value':0.0,'qualifiers':[],'unit':'ft^3/s'} for h in (5,3,0)])
        self.assertEqual(hc.data_health(gappy,AT)['gaps_over_60_minutes'],2)
        self.assertFalse(hc.data_health([],AT)['fresh'])
    def test_seasonal_percentile_uses_station_own_record_and_day_of_year_window(self):
        # Every year: 10 cfs in September, 100 cfs otherwise. A late-September value of 10 is a tie with the whole window -> 50th.
        d=daily(20,lambda x:10.0 if x.month==9 else 100.0)
        s=hc.seasonal_context(d,dt.date(2009,9,16),10.0,half_window=14); self.assertTrue(s['available']); self.assertEqual(s['percentile'],50.0); self.assertEqual(s['years'],20); self.assertEqual(s['comparable_days'],20*29)
        s2=hc.seasonal_context(d,dt.date(2009,9,16),200.0,half_window=14); self.assertEqual(s2['percentile'],100.0)
        s3=hc.seasonal_context(d,dt.date(2009,9,16),0.0,half_window=14); self.assertEqual(s3['percentile'],0.0); self.assertEqual(s3['zero_share'],0.0)
        wide=hc.seasonal_context(d,dt.date(2009,9,15),10.0); self.assertLess(wide['percentile'],50.0,'a window reaching into August includes higher days')
        # Window straddling the year boundary still finds comparable days.
        s4=hc.seasonal_context(d,dt.date(2009,12,31),100.0); self.assertTrue(s4['available']); self.assertGreater(s4['comparable_days'],20*20)
        thin=hc.seasonal_context(d[:20],dt.date(1990,1,10),5.0); self.assertFalse(thin['available'])
        self.assertEqual(hc.percentile_rank([1,2,2,3],2),50.0)
    def test_missing_daily_history_is_reported_not_zero(self):
        entry=hc.station_context('00000000','Nowhere Creek',{'00060':{'parameter':'00060','unit':'ft^3/s','observed_at':AT.isoformat(),'value':0.0,'qualifiers':[]}},{'00060':rows([0.0]*33)},None,AT)
        self.assertFalse(entry['parameters']['00060']['seasonal_daily_mean']['available'])
        self.assertIn('not a swimming place',entry['narrative'])
        absent=hc.station_context('00000000','Nowhere Creek',{},{},None,AT)
        self.assertEqual(absent['parameters'],{}); self.assertIn('no discharge series saved',absent['narrative'])

class EventLedgerTests(unittest.TestCase):
    def series(self,values,start=dt.date(2020,1,1)):
        return [{'date':start+dt.timedelta(days=i),'value':v,'approval':'Approved'} for i,v in enumerate(values)]
    def test_hysteresis_events_rise_recession_and_water_year(self):
        d=self.series([0,0,5,60,80,30,12,4,0,0,70,20,9,0])
        ev=el.detect_events(d,t_high=50,t_low=10)
        self.assertEqual(len(ev),2)
        first=ev[0]; self.assertEqual(first['start'],dt.date(2020,1,4)); self.assertEqual(first['peak_value'],80); self.assertEqual(first['end'],dt.date(2020,1,7))
        self.assertEqual(first['rise_days'],2); self.assertEqual(first['recession_days'],2); self.assertEqual(first['end_reason'],'fell_below_low_threshold')
        self.assertEqual(first['water_year'],2020); self.assertEqual(el.water_year(dt.date(2020,10,1)),2021)
    def test_gap_and_non_numeric_end_an_event_instead_of_bridging_it(self):
        d=self.series([0,60,55,52]); d.append({'date':dt.date(2020,1,7),'value':58,'approval':'Provisional'}); d.append({'date':dt.date(2020,1,8),'value':None,'approval':'Provisional'}); d.append({'date':dt.date(2020,1,9),'value':57,'approval':'Provisional'})
        ev=el.detect_events(d,50,10)
        self.assertEqual([e['end_reason'] for e in ev],['ended_by_gap','ended_by_non_numeric_value','record_ends_inside_event'])
        self.assertTrue(ev[1]['has_provisional'])
    def test_scenarios_expand_unresolved_dates_without_inventing_one(self):
        day=el.scenario_windows({'date_precision':'day','date':'2025-05-18'}); self.assertEqual(day[0]['start'],dt.date(2025,5,18))
        month=el.scenario_windows({'date_precision':'month','date':'2025-06'}); self.assertEqual(month[0]['end'],dt.date(2025,6,30))
        unknown=el.scenario_windows({'date_precision':'day','date':'--06-21'}); self.assertEqual(len(unknown),len(el.CANDIDATE_YEARS)); self.assertTrue(all('if the year was' in s['scenario'] for s in unknown))
        weekend=el.scenario_windows({'date_precision':'weekend_interval','date':None}); self.assertEqual((weekend[0]['end']-weekend[0]['start']).days,3)
        self.assertEqual(el.scenario_windows({'date_precision':'none','date':None}),[])
        rng=el.scenario_windows({'date_precision':'date_range','date':None,'date_start':'2025-05-11','date_end':'2025-06-30'}); self.assertEqual((rng[0]['start'].isoformat(),rng[0]['end'].isoformat()),('2025-05-11','2025-06-30')); self.assertEqual(len(rng),1)
    def test_labels_attach_only_through_recorded_relationships(self):
        rel={'observation_place_aliases':{'bull-creek-unresolved':['st-edwards']},'places':{'st-edwards':{'stations':[{'station_id':'08154700','relationship_class':'context_station_downstream','confidence':'medium'}]},'twin-falls':{'stations':[{'station_id':'08155240','relationship_class':'rule_linked_product_baseline','confidence':'low'}]}}}
        obs=[{'id':'a','place_id':'bull-creek-unresolved','verbatim':'x','reported_quality':'good','date_precision':'day','date':'2025-05-18'},{'id':'b','place_id':'twin-falls','verbatim':'y','date_precision':'day','date':'--06-21'},{'id':'c','place_id':'nowhere','verbatim':'z','date_precision':'day','date':'2025-01-01'}]
        self.assertEqual([l['observation_id'] for l in el.labels_for_station('08154700',rel,obs)],['a'])
        self.assertEqual([l['observation_id'] for l in el.labels_for_station('08155240',rel,obs)],['b'])
        self.assertEqual(el.labels_for_station('08159000',rel,obs),[])
    def test_resolved_reach_attaches_to_that_place_only(self):
        rel={'observation_place_aliases':{'bull-creek-unresolved':['st-edwards','park']},'places':{'st-edwards':{'stations':[{'station_id':'08154700','relationship_class':'context_station_downstream','confidence':'medium'}]},'park':{'stations':[{'station_id':'08154700','relationship_class':'rule_linked_provisional_personal','confidence':'medium'}]}}}
        obs=[{'id':'a','place_id':'bull-creek-unresolved','verbatim':'x','reported_quality':'good','date_precision':'day','date':'2025-05-18','reach':'park','reach_precision':'approximate'}]
        labels=el.labels_for_station('08154700',rel,obs); self.assertEqual([k['place_id'] for k in labels[0]['links']],['park']); self.assertEqual(labels[0]['reach_precision'],'approximate')
        obs[0].pop('reach'); self.assertEqual([k['place_id'] for k in el.labels_for_station('08154700',rel,obs)[0]['links']],['st-edwards','park'])
    def test_window_description_reports_station_record_not_a_verdict(self):
        d=self.series([1,2,90,80,60,5,1,1,1,1]); ev=el.detect_events(d,50,10); by={r['date']:r['value'] for r in d}
        w=el.describe_window(by,d,ev,dt.date(2020,1,4),dt.date(2020,1,4)); self.assertTrue(w['inside_event']); self.assertEqual(w['overlapping_event_peaks'][0]['peak_value'],90)
        w2=el.describe_window(by,d,ev,dt.date(2020,1,9),dt.date(2020,1,10)); self.assertFalse(w2['inside_event']); self.assertEqual(w2['days_since_previous_event_end'],4)
        self.assertEqual(el.describe_window(by,d,ev,dt.date(2021,1,1),dt.date(2021,1,2))['days_with_data'],0)
        for key in ('verdict','status','safe'): self.assertNotIn(key,json.dumps(w))

class UsgsHistoryTests(unittest.TestCase):
    def feature(self,day,value,station='08154700',param='00060',stat='00003'):
        return {'properties':{'monitoring_location_id':'USGS-'+station,'parameter_code':param,'statistic_id':stat,'time':day,'value':value,'unit_of_measure':'ft^3/s','approval_status':'Approved','qualifier':None,'last_modified':'x','time_series_id':'t'}}
    def test_daily_normalization_is_strict_and_preserves_non_numeric(self):
        rows_=uh.normalize_daily([self.feature('2020-01-02','1.5'),self.feature('2020-01-01','Ice'),self.feature('2020-01-05',None)],'08154700','fixture')
        self.assertEqual([r['date'] for r in rows_],['2020-01-01','2020-01-02','2020-01-05'])
        self.assertEqual(rows_[0]['value'],''); self.assertEqual(rows_[0]['raw_value'],'Ice'); self.assertEqual(rows_[1]['value'],1.5); self.assertEqual(rows_[2]['raw_value'],'')
        gaps=uh.gap_report(rows_); self.assertEqual(gaps,[{'after':'2020-01-02','before':'2020-01-05','missing_days':2}])
        with self.assertRaisesRegex(ValueError,'belongs to'): uh.normalize_daily([self.feature('2020-01-01','1',station='08155240')],'08154700','fixture')
        with self.assertRaisesRegex(ValueError,'duplicate'): uh.normalize_daily([self.feature('2020-01-01','1'),self.feature('2020-01-01','2')],'08154700','fixture')
        with self.assertRaisesRegex(ValueError,'not daily mean'): uh.normalize_daily([self.feature('2020-01-01','1',stat='00001')],'08154700','fixture')
        with self.assertRaisesRegex(ValueError,'invalid day'): uh.normalize_daily([self.feature('yesterday','1')],'08154700','fixture')
    def test_versioned_daily_manifests_cover_every_context_station(self):
        for station in hc.STATIONS:
            manifest=ROOT/'data/model'/f'{station}-daily-history-manifest.json'; self.assertTrue(manifest.exists(),station)
            m=json.loads(manifest.read_text()); self.assertTrue(m['complete_response'],station); self.assertIsNone(m['daily_request']['next_link'])
            self.assertTrue((ROOT/m['normalized_csv']).exists(),station); self.assertTrue((ROOT/m['daily_request']['capture_path']).exists(),station)
            self.assertIn('never treated as zero',m['gaps']['meaning'])

class ReachGeometryTests(unittest.TestCase):
    def setUp(self):
        self.ways=[{'name':'Test Creek','osm_id':1,'coords':[(30.0,-97.0),(30.0,-97.01),(30.0,-97.02),(30.0,-97.03)],'cum':[0,963.0,1926.0,2889.0],'length_m':2889.0},
                   {'name':'Other Creek','osm_id':2,'coords':[(30.2,-97.0),(30.2,-97.01)],'cum':[0,963.0],'length_m':963.0}]
    def test_upstream_downstream_only_on_same_mapped_way(self):
        station=rg.project((30.0,-97.01),self.ways,'Test Creek'); place=rg.project((30.0001,-97.03),self.ways,'Test Creek')
        self.assertTrue(station['on_mapped_channel']); rel=rg.relate(place,station)
        self.assertEqual(rel['position'],'place_downstream_of_station'); self.assertAlmostEqual(rel['along_channel_m'],1926.0)
        self.assertEqual(rg.relate(station,place)['position'],'place_upstream_of_station')
        far=rg.project((30.01,-97.01),self.ways,'Test Creek'); self.assertFalse(far['on_mapped_channel']); self.assertEqual(rg.relate(far,station)['position'],'unresolved')
        other=rg.project((30.2,-97.0),self.ways,'Other Creek'); self.assertEqual(rg.relate(other,station)['position'],'different_mapped_ways')
        self.assertFalse(rg.project((30.0,-97.0),self.ways,'Missing Creek')['on_mapped_channel'])


if __name__=='__main__': unittest.main()
