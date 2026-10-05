"""Geometry, snapshot, history-partition, geology and packaging checks for the regional pilot consumer."""
import datetime as dt
import gzip
import json
from pathlib import Path
import tempfile
import unittest
from tools import regional_geography as geo, regional_geology as geology, regional_pilot as pilot, package_regional_site as site

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT/'app'


def piece(ident, a, b, name='River', waterbody=None, flowdir=1):
    return {'type': 'Feature', 'geometry': {'type': 'LineString', 'coordinates': [a, b]}, 'properties': {'id': ident, 'name': name, 'flowdir': flowdir, 'waterbody_id': waterbody, 'reachcode': '12090204000001'}}


class RouteTests(unittest.TestCase):
    lakes = [{'properties': {'id': 'L1', 'name': 'Lake One'}}, {'properties': {'id': 'L2', 'name': 'Lake Two'}}]

    def test_route_follows_endpoints_and_names_first_lake(self):
        features = [piece('a', [0, 0], [1, 0]), piece('b', [1, 0], [2, 0], 'Reservoir channel', 'L1'), piece('c', [2, 0], [3, 0], 'Reservoir channel', 'L2')]
        r = geo.downstream_route('a', features, self.lakes)
        self.assertEqual((r['first_receiving_reservoir'], r['reference_waterbodies_in_order'], r['pieces']), ('Lake One', ['Lake One', 'Lake Two'], 3))
        self.assertEqual(r['stopped'], 'end of saved network')

    def test_route_never_bridges_a_gap_or_guesses_at_a_divergence(self):
        gap = [piece('a', [0, 0], [1, 0]), piece('b', [1.001, 0], [2, 0], 'Reservoir channel', 'L1')]
        self.assertIsNone(geo.downstream_route('a', gap, self.lakes)['first_receiving_reservoir'])
        fork = [piece('a', [0, 0], [1, 0]), piece('b', [1, 0], [2, 0], waterbody='L1'), piece('c', [1, 0], [2, 1], waterbody='L2')]
        r = geo.downstream_route('a', fork, self.lakes)
        self.assertIn('divergence', r['stopped']); self.assertIsNone(r['first_receiving_reservoir'])

    def test_route_refuses_reversed_flow_direction(self):
        r = geo.downstream_route('a', [piece('a', [0, 0], [1, 0], flowdir=0)], self.lakes)
        self.assertEqual(r['pieces'], 0); self.assertIn('direction', r['stopped'])

    def length(self, line):
        import math
        return sum(math.hypot((b[0]-a[0])*math.cos(math.radians(a[1])), b[1]-a[1])*111195 for a, b in zip(line, line[1:]))

    def test_gauge_stroke_is_at_most_a_kilometre_on_one_line(self):
        line = [[0, 30], [0.02, 30], [0.04, 30]]
        stroke = geo.gauge_stroke([0.02, 30.0001], line, 500)
        self.assertAlmostEqual(self.length(stroke), 1000, delta=2)
        self.assertEqual(stroke[len(stroke)//2], [0.02, 30])

    def test_gauge_stroke_stops_at_the_end_of_its_line(self):
        line = [[0, 30], [0.02, 30], [0.04, 30]]
        stroke = geo.gauge_stroke([0.0395, 30], line, 500)
        self.assertEqual(stroke[-1], [0.04, 30])
        self.assertLess(self.length(stroke), 600)

    def test_position_association_stays_inside_the_watershed(self):
        basin = {'type': 'Feature', 'properties': {'huc8': '12090204', 'name': 'Llano'}, 'geometry': {'type': 'Polygon', 'coordinates': [[[0, 0], [2, 0], [2, 2], [0, 2], [0, 0]]]}}
        near = dict(piece('x', [0.5, 1.0001], [1.5, 1.0001], 'Llano River'))
        across = dict(piece('y', [0.5, 1.00001], [1.5, 1.00001], 'Llano River')); across['properties']['reachcode'] = '12090206000001'
        result = geo.association({'coordinates': [1, 1], 'name': 'Llano Rv at Llano, TX'}, [near, across], [basin])
        self.assertEqual(result['channel_id'], 'x'); self.assertIsNone(result['reach_estimate'])
        self.assertFalse(geo.association({'coordinates': [5, 5], 'name': 'Llano Rv'}, [near], [basin])['available'])


class SavedGeographyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.snapshot = json.loads((APP/'regional-snapshot.json').read_text())
        cls.manifest = json.loads((ROOT/'data/model/regional-geography.json').read_text())

    def test_saved_network_components_are_recorded(self):
        self.assertEqual(self.manifest['topology']['component_sizes'], [2656, 28, 25, 2, 1])
        self.assertEqual([c['pieces'] for c in self.manifest['component_summary']], [2656, 28, 25, 2, 1])
        self.assertEqual(set(self.manifest['component_summary'][1]['names']), {'Sandy Creek'})

    def test_receiving_reservoirs_come_from_the_route_walk(self):
        lake = {x['id']: x['name'] for x in self.snapshot['items'] if x['kind'] == 'reservoir'}
        rivers = [x for x in self.snapshot['items'] if x['kind'] == 'river' and x['basin'] != 'Austin creeks']
        self.assertEqual(len(rivers), 4)
        for x in rivers:
            route = x['association']['downstream_route']
            self.assertEqual(route['stopped'], 'end of saved network')
            self.assertEqual(route['first_receiving_reservoir'], lake[self.snapshot['basins'][x['basin']]['receiving_reservoir']])
        self.assertIsNone(self.snapshot['basins']['Highland Lakes']['receiving_reservoir'])

    def test_reservoir_labels_sit_at_the_dam_the_provider_names_for_that_lake(self):
        expected = {'Lake Buchanan': 'Lake Buchanan', 'Inks Lake': 'Inks Lake', 'Lake Lyndon B Johnson': 'Lake LBJ', 'Lake Marble Falls': 'Lake Marble Falls', 'Lake Travis': 'Lake Travis', 'Lake Austin': 'Lake Austin'}
        for x in self.snapshot['items']:
            if x['kind'] == 'reservoir':
                self.assertIn('Dam', x['location_note']); self.assertIn('('+expected[x['name']]+')', x['location_note'])
                self.assertIsNotNone(x['coordinates'])

    def test_snapshot_keeps_missing_selections_missing(self):
        counts = {v: {k: sum(x['kind'] == k and bool(x['views'][v]['observation']) for x in self.snapshot['items']) for k in ('river', 'rain', 'well', 'reservoir')} for v in ('storm', 'seasonal')}
        self.assertEqual(counts['storm']['river'], 10); self.assertEqual(counts['seasonal']['river'], 9); self.assertEqual(counts['seasonal']['rain'], 0); self.assertEqual(counts['storm']['well'], 0)
        self.assertEqual(self.snapshot['coverage']['local_springs'], 0)
        self.assertNotIn('<br', json.dumps([x['name'] for x in self.snapshot['items']]))

    def test_rain_statistics_stay_separate_and_unsummed(self):
        rain = [x for x in self.snapshot['items'] if x['kind'] == 'rain']
        self.assertTrue(any(x['aligned']['increments']['available'] for x in rain))
        for x in rain:
            self.assertIsNone(x['views']['storm']['event_total'])
            for part in x['aligned'].values():
                self.assertNotIn('total', {k for k in part if k != 'note'})
            inc = x['aligned']['increments']
            if inc['available']:
                self.assertTrue(all(p[1] > 0 for p in inc['points'])); self.assertGreaterEqual(inc['reports'], len(inc['points']))

    def test_austin_creeks_are_a_named_group_not_a_watershed(self):
        creeks = [x for x in self.snapshot['items'] if x['kind'] == 'river' and x['basin'] == 'Austin creeks']
        self.assertEqual(len(creeks), 6)
        group = self.snapshot['basins']['Austin creeks']
        self.assertIsNone(group['receiving_reservoir']); self.assertIn('not a watershed outline', group['grouping'])
        for x in creeks:
            self.assertNotIn('downstream_route', x['association']); self.assertIsNone(x['association']['reach_estimate'])
        city = [x for x in self.snapshot['items'] if x['kind'] == 'rain' and x['id'].startswith('COA:')]
        self.assertTrue(city and all(x['basin'] == 'Austin creeks' and 'not by a watershed outline' in x['basin_basis'] for x in city))
        shoal = next(x for x in creeks if x['id'] == 'USGS:08156800')
        self.assertIsNone(shoal['views']['seasonal']['observation'])  # its daily record stops September 2; no later value is borrowed

    def test_strokes_follow_the_display_policy(self):
        import math
        policy = self.snapshot['display_policy']
        for x in self.snapshot['items']:
            if x['kind'] != 'river':
                continue
            line = x['stroke']['coordinates']
            metres = sum(math.hypot((b[0]-a[0])*math.cos(math.radians(a[1])), b[1]-a[1])*111195 for a, b in zip(line, line[1:]))
            self.assertLessEqual(metres, 2*policy['stroke']['half_length_m']+2, x['id'])
            excess = x['stroke']['excess_cfs']
            expected = max(b['id'] for b in policy['bands'] if b['min_excess_cfs'] is None or excess >= b['min_excess_cfs'])
            self.assertEqual(x['stroke']['band'], expected)
        bands = {x['id']: x['stroke']['band'] for x in self.snapshot['items'] if x['kind'] == 'river'}
        self.assertEqual((bands['USGS:08150000'], bands['USGS:08156800'], bands['USGS:08155300']), (5, 3, 0))

    def test_clean_strips_only_markup(self):
        self.assertEqual(pilot.clean('Mansfield Dam <br />(Lake Travis)'), 'Mansfield Dam (Lake Travis)')


class HistoryPartitionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index = json.loads((APP/'history/index.json').read_text())
        cls.junction = json.loads((APP/'history/usgs-08150000.json').read_text())['series'][0]

    def day(self, series, iso):
        i = (dt.date.fromisoformat(iso)-dt.date.fromisoformat(series['start'])).days
        return (series['values'][i], series['percentile'][i]) if 0 <= i < len(series['values']) else (None, None)

    def test_old_value_matches_the_preserved_capture(self):
        """A 1915 daily mean in the browser file equals the row in the raw USGS capture it cites."""
        manifest = json.loads((ROOT/'data/model/08150000-daily-history-manifest.json').read_text())['daily_request']
        self.assertIn(manifest['sha256'], {s['sha256'] for s in json.loads((APP/'history/usgs-08150000.json').read_text())['sources'].values()})
        capture = ROOT/manifest['capture_path']
        if not capture.exists():
            self.skipTest('versioned USGS capture not restored')
        rows = {f['properties']['time'][:10]: f['properties']['value'] for f in json.loads(gzip.decompress(capture.read_bytes()))['features']}
        for iso in ('1915-10-01', '1952-09-11', '2026-09-30'):
            self.assertEqual(self.day(self.junction, iso)[0], float(rows[iso]), iso)

    def test_record_reaches_far_before_the_recent_store(self):
        self.assertEqual(self.junction['start'], '1915-10-01')
        self.assertEqual(self.junction['continuity']['missing_years'], [1994, 1995, 1996])

    def test_gap_is_null_and_unranked_not_carried_forward(self):
        for iso in ('1993-05-11', '1995-06-01', '1997-09-30'):
            self.assertEqual(self.day(self.junction, iso), (None, None))
        self.assertIsNotNone(self.day(self.junction, '1993-05-10')[0]); self.assertIsNotNone(self.day(self.junction, '1997-10-01')[0])

    def test_every_value_has_a_rank_slot_and_baseline_is_fixed(self):
        self.assertEqual(len(self.junction['values']), len(self.junction['percentile']))
        doc = json.loads((APP/'history/usgs-08150000.json').read_text())
        self.assertEqual(doc['baseline']['reference_years'], [2006, 2025])
        self.assertTrue(all(p is None for v, p in zip(self.junction['values'], self.junction['percentile']) if v is None))

    def test_non_discharge_records_have_no_percentile(self):
        lake = json.loads((APP/'history/twdb-lake-buchanan.json').read_text())
        self.assertTrue(all('percentile' not in s for s in lake['series']))
        self.assertGreater(len(lake['series'][0]['continuity']['capacity_eras']), 1)
        comal = json.loads((APP/'history/eaa-08168710.json').read_text())['series'][0]
        self.assertTrue(all(p is None for p in comal['percentile']))  # approval unknown: nothing qualifies for the baseline

    def test_unfetched_wells_are_named_as_gaps(self):
        missing = [k for k, v in self.index['stations'].items() if not v['file']]
        self.assertEqual(len(missing), 11); self.assertTrue(all(k.startswith('TWDB:') and 'never captured' in self.index['stations'][k]['reason'] for k in missing))
        self.assertEqual(len(self.index['stations']), 179)

    def test_stations_can_be_placed_on_a_map(self):
        snapshot = {x['id']: x for x in json.loads((APP/'regional-snapshot.json').read_text())['items']}
        unplaced = [k for k, v in self.index['stations'].items() if v['file'] and not (v.get('coordinates') and v['coordinates'][0] is not None)
                    and not (snapshot.get(k, {}).get('coordinates'))]
        self.assertEqual(sorted(unplaced), ['EAA:08168710', 'EAA:08170000'])  # the two EAA springs have no verified coordinates

    def test_growing_network_is_reported_as_network(self):
        rain = self.index['stations_reporting_by_year']['rain']
        self.assertLess(rain['1990'], rain['2026']); self.assertIn('not a regional trend', self.index['network_note'])

    def test_rain_packing_keeps_zero_and_missing_apart(self):
        from tools import regional_history_package as package
        from tools import regional_normalize as n
        rows = [n.measurement(operator='LCRA', feed='Hydromet', site='1', series='s', parameter='p', quantity='rain', unit='in', value=v, when=f'2020-01-{i+1:02d}',
                              statistic='daily_total_boundary_unverified', source='c', locator=str(i)) for i, v in enumerate([0, 0, 0, .5, 0, 0, 0, 0, None, 0, 0, 0]) if i != 6]
        packed = package.encode(rows)
        self.assertEqual(packed['encoding'], 'zero_default')
        self.assertEqual((packed['nonzero'], packed['missing_runs'], packed['length']), ([[3, .5]], [[6, 6], [8, 8]], 12))

    def test_point_wells_are_not_made_into_daily_statistics(self):
        for key, entry in self.index['stations'].items():
            if entry['kind'] == 'well' and entry['file']:
                for s in json.loads((APP/entry['file']).read_text())['series']:
                    if s['statistic'] == 'reported_point':
                        self.assertNotIn('years', s)


class EarlierFloodTests(unittest.TestCase):
    def test_public_artifact_keeps_statistics_apart(self):
        doc = json.loads((APP/'regional-events.json').read_text())
        self.assertEqual(len(doc['gauges']), 10)
        junction = doc['gauges']['USGS:08150000']
        self.assertEqual(junction['storm_reading']['statistic'], 'instantaneous')
        self.assertEqual((junction['placement']['larger'], junction['placement']['published_peaks']), (31, 105))
        self.assertIn('not in the saved record yet', junction['storm_daily_means'])
        self.assertTrue(all(g['daily_events']['events'][0]['date'] <= g['last_daily_mean'] for g in doc['gauges'].values()))



class GeologyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = json.loads((ROOT/'data/model/regional-geology.json').read_text())

    REPORT = ('Disclaimer\n"x"\n\nStateWellNumber,County,AquiferCode,Aquifer,AquiferPickMethod,LandSurfaceElevation,LandSurfaceElevationMethod,WellDepth,WellDepthSource,DrillingEndDate,BoreholeCompletion\n'
              '1234567,Llano,371HCKR - Hickory,Hickory,,1000,Topo,300,Driller,1/1/1970,{completion}\n\nWellType,Owner,Driller\nObservation,A Private Person,Some Driller\n\n{casing}')

    def test_well_without_completion_rows_gets_no_interval(self):
        r = geology.well_record(self.REPORT.format(completion='', casing='CASING,CasDiameter,CasingType,CasingMaterial,Schedule,Gauge,CasTopDepth,CasBottomDepth\n'))
        self.assertEqual((r['screen_or_open_intervals'], r['interval_status']), ([], 'not documented in the Groundwater Database'))
        self.assertNotIn('A Private Person', json.dumps(r)); self.assertNotIn('Some Driller', json.dumps(r))

    def test_blank_casing_is_not_a_screen(self):
        casing = 'CASING,CasDiameter,CasingType,CasingMaterial,Schedule,Gauge,CasTopDepth,CasBottomDepth\nCasing,7,Blank,Steel,,,0,112\n'
        self.assertEqual(geology.well_record(self.REPORT.format(completion='', casing=casing))['interval_status'], 'casing recorded without a screen or open interval')
        r = geology.well_record(self.REPORT.format(completion='Open Hole', casing=casing+'Casing,,Open Hole,,,,112,300\n'))
        self.assertEqual(r['screen_or_open_intervals'], [{'type': 'Open Hole', 'top_ft': 112.0, 'bottom_ft': 300.0}])

    def test_surface_rock_never_assigns_an_aquifer(self):
        self.assertEqual(len(self.doc['wells']), 37)
        for w in self.doc['wells'].values():
            self.assertTrue(w['aquifer_assignment']['source'].startswith('TWDB provider assignment'))
            self.assertEqual(w['feed_aquifer'], w['gwdb_aquifer'])
            if w['surface_unit'] and w['surface_unit']['available']:
                self.assertIn('not the unit a well draws from', w['surface_unit']['meaning'])
            if w['interval_status'] != 'documented':
                self.assertEqual(w['screen_or_open_intervals'], [])
        differing = self.doc['wells']['TWDB:5750108']
        self.assertEqual((differing['feed_aquifer'], differing['surface_unit']['unit']), ('Ellenburger-San Saba', 'Hensell Sand'))

    def test_every_mapped_station_gets_its_own_geology_lookup(self):
        at = self.doc['stations']
        self.assertGreater(len(at), 400)
        well = at['TWDB:5750108']
        self.assertEqual(well['surface_unit']['unit'], 'Hensell Sand')
        self.assertIn({'aquifer': 'Ellenburger-San Saba', 'extent': 'subsurface'}, well['aquifer_extents'])
        llano = at['USGS:08151500']
        self.assertEqual((llano['surface_unit']['period'], llano['aquifer_extents']), ('Precambrian', []))
        self.assertNotEqual(at['USGS:08156800']['surface_unit']['unit'], llano['surface_unit']['unit'])
        self.assertIn('does not connect a station', self.doc['station_basis'])

    def test_well_log_rows_are_recorded_values_without_names(self):
        w = self.doc['wells']['TWDB:5750108']
        self.assertEqual(w['lithology'][0], {'top_ft': 0.0, 'bottom_ft': 18.0, 'description': 'Black Top Soil and Clay'})
        self.assertEqual(len(w['lithology']), w['lithology_rows'])
        self.assertNotIn('City of Fredericksburg', json.dumps(w))

    def test_sections_say_which_watershed_they_cross(self):
        by = {s['figure']: s['applies_to_basins'] for s in self.doc['sections']}
        self.assertEqual(by, {'Figure 112': ['Pedernales'], 'Figure 79': []})

    def test_outside_mapped_units_is_unavailable(self):
        square = {'type': 'Feature', 'properties': {'RockUnitName': 'u', 'RockUnitCode': 'c', 'Period': 'p', 'SheetName': 's'}, 'geometry': {'type': 'Polygon', 'coordinates': [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]}}
        units = geology.Units([square])
        self.assertTrue(units.at([.5, .5])['available']); self.assertFalse(units.at([5, 5])['available']); self.assertIsNone(units.at(None))

    def test_clip_and_simplify_keep_shape_inside_the_box(self):
        ring = [[-101, 30.2], [-99, 30.2], [-99, 30.6], [-101, 30.6], [-101, 30.2]]
        clipped = geology.clip_ring(ring)
        self.assertEqual(min(p[0] for p in clipped), geology.BOX[0]); self.assertEqual(clipped[0], clipped[-1])
        self.assertEqual(geology.clip_ring([[-110, 10], [-109, 10], [-109, 11], [-110, 10]]), [])
        line = [[0, 0], [1, .00001], [2, 0], [3, 1]]
        self.assertEqual(geology.simplify(line, .001), [[0, 0], [2, 0], [3, 1]])

    def test_outcrop_code_check_is_reported_with_its_counts(self):
        check = self.doc['aquifer_extents']['code_meaning']['check']
        self.assertEqual(sum(v['2'].get('matching surface unit', 0) for v in check.values()), 0)
        self.assertGreater(sum(v['1'].get('matching surface unit', 0) for v in check.values()), 100)

    def test_quoted_relationships_are_verbatim_in_their_captures(self):
        if not (geology.CAP/'usgs-ha730e-text10-minor-aquifers.gz').exists():
            self.skipTest('geology captures not restored')
        for name, _, sentence in geology.RELATIONSHIPS:
            self.assertIn(sentence, geology.plain(geology.capture(name)[0]))

    def test_sections_are_published_figures_with_credit_and_limits(self):
        for s in self.doc['sections']:
            self.assertTrue((APP/s['file']).is_file()); self.assertIn('U.S. Geological Survey', s['credit']); self.assertTrue(s['limits'])
        self.assertTrue(any('Llano River watershed' in g for g in self.doc['evidence_gaps']))


class SwimMapLinkTests(unittest.TestCase):
    def test_links_only_where_both_maps_have_the_gauge(self):
        links = json.loads((APP/'swim-map-links.json').read_text())
        index = json.loads((APP/'history/index.json').read_text())['stations']
        self.assertTrue(links['stations'])
        for key, entry in links['stations'].items():
            self.assertTrue(index[key]['file'], key)
            self.assertEqual(entry['anchor'], 'gauge.'+key.split(':')[1])
        self.assertNotIn('USGS:08150000', links['stations'])  # Llano near Junction is not a swim-map gauge
        self.assertIn('USGS:08156800', links['stations'])

    def test_address_anchor_round_trips_every_station_key(self):
        import re
        for key in json.loads((APP/'history/index.json').read_text())['stations']:
            anchor = key.replace(':', '.', 1)
            self.assertRegex(anchor, r'^[A-Za-z0-9._~-]+$')  # only characters an artifact link passes through
            m = re.match(r'^([A-Za-z-]+)\.([0-9A-Za-z-]+)$', anchor)
            self.assertEqual(m.group(1)+':'+m.group(2), key)


class PackagingTests(unittest.TestCase):
    def site(self, project=site.SITE):
        d = Path(tempfile.mkdtemp()); (d/'.openai').mkdir()
        (d/'.openai/hosting.json').write_text(json.dumps({'project_id': project, 'static': {'directory': 'out', 'not_found_handling': 'none'}}))
        return d

    def test_package_is_public_complete_and_linked(self):
        d = self.site(); files = site.package(d); out = d/'out'
        for page in ('index.html', 'austin.html', 'ledger.html', 'regional-snapshot.json', 'history/index.json', 'history/usgs-08150000.json', 'regional-geology.json',
                     'geology/usgs-ha730e-fig112.gif', 'swim-map-links.json', 'docs/REGIONAL_GEOGRAPHY.md', 'docs/REGIONAL_HISTORY.md', 'docs/REGIONAL_GEOLOGY.md', 'dist/water-state.json'):
            self.assertTrue((out/page).is_file(), page)
        names = [str(p.relative_to(out)) for p in out.rglob('*') if p.is_file()]
        self.assertFalse([n for n in names if n.endswith(('.sqlite', '.gz', '.py', '.meta.json')) or n.startswith('.git')])
        self.assertEqual(len(names), len(files))

    def test_wrong_site_identity_is_refused(self):
        with self.assertRaises(ValueError):
            site.package(self.site('appgprj_someone_else'))

    def test_private_strings_are_detected(self):
        p = Path(tempfile.mkdtemp())/'x.json'; p.write_text('{"path":"/Users/someone/file"}')
        self.assertTrue(site.private_hits(p))
        p.write_text('{"Owner":"A Person"}'); self.assertTrue(site.private_hits(p))
        p.write_text('{"well_depth_source":"Driller\'s Log"}'); self.assertFalse(site.private_hits(p))


if __name__ == '__main__':
    unittest.main()
