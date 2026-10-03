import hashlib, json, unittest
from pathlib import Path
from tools import eaa
ROOT = Path(__file__).resolve().parents[1]
SNIP = '<div>Index Wells Historic Daily High Levels</div><th>Today</th><td>Oct 01 2026</td><th>Yesterday</th><td>Sep 30 2026</td><th>Six Month</th><td>Apr 01 2026</td><th>One Year</th><td>Oct 01 2025</td><td>San Antonio Pool (J-17)</td><td>638.9</td><td>638.3</td><td>624.9</td><td>628.4</td><td>638.7</td><td>662.0</td><td>-23.1</td><td>Comal Springs</td><td>136</td><td>137</td><td>53</td><td>78</td><td>145</td><td>269</td><td>-133</td>'
class EaaConditionsTests(unittest.TestCase):
    def test_summary_table_and_reductions_parse_verbatim(self):
        table, dates = eaa.parse_summary_table(SNIP)
        self.assertEqual(table['San Antonio Pool (J-17)']['ten_day_average'], 638.7); self.assertEqual(table['Comal Springs']['difference_from_historical'], -133.0); self.assertNotIn('Uvalde Pool (J-27)', table)
        self.assertEqual(dates['today'], 'Oct 01 2026')
        self.assertEqual(eaa.parse_reductions('<p>San Antonio Pool</p><h2>35%</h2><p>CURRENT REDUCTION</p> Uvalde Pool 0% CURRENT REDUCTION'), {'San Antonio Pool': 35, 'Uvalde Pool': 0})
        self.assertEqual(eaa.parse_var('var xJSON = [{"a":1}]; var yJSON = [];', 'xJSON'), [{'a': 1}]); self.assertIsNone(eaa.parse_var('nothing', 'xJSON'))
    def test_stage_table_matches_its_captured_images_and_is_ordered(self):
        st = json.loads((ROOT / 'data/eaa-cpm-stages.json').read_text())
        for pool in ('san_antonio_pool', 'uvalde_pool'):
            img = ROOT / 'data/raw/eaa/cpm' / st[pool]['image']
            if img.exists(): self.assertEqual(hashlib.sha256(img.read_bytes()).hexdigest(), st[pool]['image_sha256'])
        sa = st['san_antonio_pool']['stages']; j17 = [s['j17_ft_amsl']['lt'] for s in sa[1:]]; self.assertEqual(j17, sorted(j17, reverse=True)); self.assertEqual(sa[3]['reduction_pct'], 35)
        self.assertIn('transcribed', st['how_obtained'])

class EaaDetailsTests(unittest.TestCase):
    def test_well_detail_page_yields_daily_highs_and_sensor_inventory_without_inventing_values(self):
        from tools import eaa
        h = (Path(__file__).resolve().parent / 'fixtures/eaa-well-details-sample.html').read_text()
        rows = eaa.parse_var(h, 'wellAllDailyHighElevationJSON'); stats = eaa.parse_var(h, 'wellSensorStatsJSON')
        self.assertEqual(len(rows), 3); self.assertEqual(rows[0]['siteId'], 'ENR806'); self.assertIsNone(rows[1]['waterLevelElevation'], 'a missing elevation stays missing')
        self.assertTrue(all(r['dailyHighDate'][:4].isdigit() for r in rows)); self.assertIn('DHE', {x['sensorName'] for x in stats})
        self.assertEqual(eaa.DETAIL_PAGES['wells'][0].format(id=211), '/GroundWater/Details/211')
        self.assertEqual(eaa.parse_var('<html>no data</html>', 'wellAllDailyHighElevationJSON'), None)

if __name__ == '__main__': unittest.main()
