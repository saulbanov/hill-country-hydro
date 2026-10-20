import json
from pathlib import Path
import unittest
from tools import creek_prototype as p
from tools import reach_geometry as g


def way(name='Bull Creek',ident=1,coords=None):
    coords=coords or [(30,-97),(30.001,-97),(30.002,-97),(30.003,-97),(30.004,-97)]
    cum=[0.0]
    for a,b in zip(coords,coords[1:]):cum.append(cum[-1]+g.haversine(a,b))
    return dict(name=name,osm_id=ident,coords=coords,cum=cum,length_m=cum[-1],retrieved_at='2026-10-03',source='OpenStreetMap')


class GeometryTests(unittest.TestCase):
    def test_proximity_without_named_channel_is_insufficient(self):
        ident=dict(creek='Little Walnut Creek',coordinates=[-97,30.002])
        self.assertFalse(p.association(ident,[way()], 'Bull Creek')['available'])
    def test_off_channel_and_absent_channel(self):
        ident=dict(creek='Bull Creek',coordinates=[-98,30.002])
        self.assertFalse(p.association(ident,[way()], 'Bull Creek')['available'])
        self.assertFalse(p.association(ident,[way('Onion Creek')], 'Bull Creek')['available'])
    def test_stroke_cap_and_provider_coordinate_strings(self):
        ident=dict(creek='Bull Creek',coordinates=['-97','30.002']);r=p.association(ident,[way()], 'Bull Creek',half_length=150)
        self.assertTrue(r['available']);self.assertLessEqual(r['stroke_length_m'],300);self.assertEqual(len(r['geometry']['coordinates']),3)
    def test_stop_at_saved_junction(self):
        w=way();branch=way('Tributary',2,[(30.001,-97),(30.001,-97.001)])
        r=p.association(dict(creek='Bull Creek',coordinates=[-97,30.002]),[w,branch], 'Bull Creek')
        self.assertEqual(r['first_node'],1);self.assertEqual(r['last_node'],4)
    def test_missing_coordinates(self):
        r=p.association(dict(creek='Bull Creek',coordinates=[None,30]),[way()],'Bull Creek');self.assertFalse(r['available'])


class PublicArtifactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root=Path(__file__).resolve().parents[1]
        cls.data=json.loads((cls.root/'app/creek-snapshot.json').read_text())
    def test_schema_and_integrated_layer(self):
        self.assertEqual(self.data['analytic_schema'],'creek-measurements/v1')
        self.assertEqual(self.data['normalization_commit'],json.loads((self.root/'data/model/creek-display-policy.json').read_text())['normalization_integration_commit'])
        self.assertEqual(len(self.data['normalization_commit']),40)
    def test_every_display_value_has_public_provenance(self):
        for c in self.data['creeks']:
            for v in c['views'].values():
                r=v['observation']
                if r:
                    source=self.data['sources'][r['source_id']]
                    self.assertTrue(source['url'].startswith('https://'));self.assertEqual(len(source['sha256']),64)
                    self.assertTrue(r['source_locator']);self.assertTrue(r['id'])
                    self.assertNotIn('raw_path',source)
    def test_comparisons_and_zero_references(self):
        for c in self.data['creeks']:
            for v in c['views'].values():
                comp=v['comparison']
                if comp['available']:
                    self.assertAlmostEqual(comp['difference_cfs'],v['observation']['value']-c['reference']['median'])
                    self.assertIsNone(comp['instantaneous_percentile'])
                    if c['reference']['median']==0:self.assertIsNone(comp['ratio_to_daily_median'])
        blunn=next(c for c in self.data['creeks'] if c['creek']=='Blunn Creek')
        self.assertFalse(blunn['views']['peak']['comparison']['available']);self.assertIsNotNone(blunn['views']['peak']['observation'])
    def test_snapshots_are_prior_and_within_age_bound(self):
        from tools.creek_normalize import stamp
        for view in self.data['policy']['views']:
            if view['at']:
                for c in self.data['creeks']:
                    r=c['views'][view['id']]['observation']
                    if r:self.assertTrue(0<=(stamp(view['at'])-stamp(r['time']['instant'])).total_seconds()<=1800)
    def test_geometry_and_history_limits(self):
        for c in self.data['creeks']:
            a=c['association'];self.assertTrue(a['available']);self.assertLessEqual(a['stroke_length_m'],1000)
            self.assertEqual(a['position']['waterbody'],c['creek']);self.assertLessEqual(a['position']['distance_to_channel_m'],100)
            if c['reference']['available']:self.assertGreaterEqual(c['reference']['calendar_coverage'],.8)

if __name__=='__main__':unittest.main()
