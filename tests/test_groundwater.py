import datetime as dt, json, sqlite3, tempfile, unittest
from pathlib import Path
from tools import groundwater as gw
FEED={'values':[{'state_well_number':'1111111','date':'2026-09-30','daily_high_water_level(ft below land surface)':100.5},{'state_well_number':'1111111','date':'2026-09-29','daily_high_water_level(ft below land surface)':None},{'state_well_number':'9999999','date':'2026-09-30','daily_high_water_level(ft below land surface)':5.0}]}
HIST={'values':[{'datetime':f'2025-{m:02d}-{d:02d} 00:00:00','daily_high_water_level(ft below land surface)':90+0.01*(m*31+d),'status':'R','source':'x'} for m in range(1,13) for d in (1,8,15,22)]+[{'datetime':'2026-09-23 00:00:00','daily_high_water_level(ft below land surface)':100.0,'status':'R','source':'x'}]}
class GroundwaterTests(unittest.TestCase):
    def test_feed_and_history_normalize_without_inventing_zero_and_assess_stays_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); keep=(gw.ROOT,gw.RAW,gw.CAP,gw.NORM,gw.DB,gw.APP,gw.WELLS)
            gw.ROOT=root; gw.RAW=root/'raw'; gw.CAP=root/'cap'; gw.NORM=root/'norm'; gw.DB=gw.NORM/'water.sqlite'; gw.APP=root/'app'; gw.WELLS=root/'wells.json'; gw.APP.mkdir()
            try:
                gw.WELLS.write_text(json.dumps({'wells':[{'id':'1111111','aquifer':'Trinity','aquifer_type':'Confined','county':'Hays','entity':'TWDB','lat':30,'lon':-98,'index':True,'source':'u'}]}))
                d=gw.RAW/'daily'; d.mkdir(parents=True); (d/'20260930T000000000000Z-recent-conditions.json').write_text(json.dumps(FEED)); (d/'20260930T000000000000Z-recent-conditions.meta.json').write_text(json.dumps({'status':200,'retrieved_at':'2026-10-01T00:00:00+00:00'}))
                h=gw.RAW/'history'/'1111111'; h.mkdir(parents=True); (h/'20261001T000000000000Z-well.json').write_text(json.dumps(HIST)); (h/'20261001T000000000000Z-well.meta.json').write_text(json.dumps({'status':200,'retrieved_at':'2026-10-01T00:00:00+00:00'}))
                gw.normalize(); db=sqlite3.connect(gw.DB)
                self.assertEqual(db.execute("select count(*) from well_levels where well='9999999'").fetchone()[0],0,'wells outside the region are not stored')
                self.assertEqual(db.execute("select count(*) from well_levels where well='1111111' and date='2026-09-29'").fetchone()[0],0,'a null level is absent, never zero')
                self.assertEqual(db.execute("select level_ft_bls from well_levels where well='1111111' and date='2026-09-30'").fetchone()[0],100.5); db.close()
                gw.assess(dt.datetime(2026,10,1,tzinfo=dt.timezone.utc)); out=json.loads((gw.APP/'groundwater.json').read_text())['wells']['1111111']
                self.assertEqual(out['latest'],{'date':'2026-09-30','level_ft_bls':100.5}); self.assertEqual(out['change_7d_ft'],0.5); self.assertIn('falling',out['direction']); self.assertIsNone(out['percentile_13mo']); self.assertIn('withheld',out['percentile_note'])
                self.assertNotIn('status',out); self.assertIn('not a swim verdict',out['meaning'])
            finally: gw.ROOT,gw.RAW,gw.CAP,gw.NORM,gw.DB,gw.APP,gw.WELLS=keep
    def test_station_lists_always_keep_the_austin_ten(self):
        from tools import station_lists as sl
        self.assertTrue(set(sl.AUSTIN_TEN)<=set(sl.history_stations())<=set(sl.all_stations()))
        inv=json.loads((sl.INVENTORY).read_text()); self.assertTrue(all(s['tier'] in ('austin','regional-key','regional-other') for s in inv['stations']))
        self.assertEqual({s['id'] for s in inv['stations'] if s['tier']=='regional-other'}&set(sl.history_stations()),set())
if __name__=='__main__': unittest.main()
