import datetime as dt
from pathlib import Path
import unittest
from tools import regional_normalize as n, regional_events as e

ROOT = Path(__file__).resolve().parents[1]


def row(value, when, **kw):
    args = dict(operator='USGS', feed='USGS', site='1', series='s', parameter='p', quantity='discharge', unit='cfs', value=value, when=when,
                statistic='daily_mean', source='capture', locator=when, approval='Approved')
    args.update(kw)
    return n.measurement(**args)


def series(start, values, **kw):
    d = dt.date.fromisoformat(start)
    return [row(v, str(d+dt.timedelta(days=i)), **kw) for i, v in enumerate(values) if v is not None]


class EventTests(unittest.TestCase):
    def test_events_are_separated_local_maxima(self):
        rows = series('2000-01-01', [1, 2, 50, 30, 20, 5, 1, 1, 1, 1, 1, 1, 40, 2, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 90, 60, 10])
        out = e.daily_events(rows, top=5, separation=7)
        self.assertEqual([x['date'] for x in out['events'][:3]], ['2000-01-25', '2000-01-03', '2000-01-13'])
        first = out['events'][0]
        self.assertEqual((first['daily_mean_cfs'], first['three_days_before_cfs'], first['days_at_or_above_half_peak_after']), (90, 1, 1))

    def test_plateau_counts_once(self):
        rows = series('2000-01-01', [1, 9, 9, 9, 1, 1, 1, 1, 1, 1])
        self.assertEqual([x['date'] for x in e.daily_events(rows, top=5, separation=3)['events']][:1], ['2000-01-02'])
        self.assertEqual(sum(x['daily_mean_cfs'] == 9 for x in e.daily_events(rows, top=5, separation=3)['events']), 1)

    def test_gap_after_peak_withholds_recession(self):
        rows = series('2000-01-01', [1, 1, 1, 80, 60, None, 5, 1])
        ev = e.daily_events(rows, top=1)['events'][0]
        self.assertIsNone(ev['days_at_or_above_half_peak_after']); self.assertIn('missing day', ev['recession_note'])

    def test_instantaneous_or_mixed_series_refused(self):
        self.assertFalse(e.daily_events([row(5, '2000-01-01T00:00:00Z', statistic='instantaneous')])['available'])
        self.assertFalse(e.daily_events(series('2000-01-01', [1, 2]) + series('2000-02-01', [1, 2], series='other'))['available'])

    def test_placement_counts_only_published_peaks(self):
        peaks = {'rows': [{'date': '1990-05-01', 'peak_cfs': 100.0}, {'date': '1991-05-01', 'peak_cfs': 50.0}, {'date': '1992-05-01', 'peak_cfs': None}, {'date': '1993-05-01', 'peak_cfs': 75.0}]}
        p = e.place_among_peaks(75.0, peaks)
        self.assertEqual((p['larger'], p['equal'], p['published_peaks'], p['largest_published']), (1, 1, 3, 100.0))
        self.assertFalse(e.place_among_peaks(None, peaks)['available'])
        self.assertFalse(e.place_among_peaks(5, {'rows': []})['available'])

    def test_lag_needs_one_matching_upstream_event(self):
        up = {'events': [{'date': '2000-11-03'}, {'date': '1990-01-01'}, {'date': '1990-01-03'}]}
        down = {'events': [{'date': '2000-11-04'}, {'date': '1990-01-02'}, {'date': '1975-06-01'}]}
        lags = e.pair_lags(up, down)
        self.assertEqual(lags[0]['lag_days'], 1); self.assertIsNone(lags[1]['lag_days']); self.assertIsNone(lags[2]['lag_days'])

    def test_peak_file_codes_come_from_its_own_header(self):
        if not (ROOT/'data/captures/usgs-peaks/08150000/annual.txt.gz').exists():
            self.skipTest('annual-peak capture not restored')
        peaks = e.annual_peaks('08150000')
        self.assertEqual(peaks['code_meanings']['peak_cd']['6'], 'Discharge affected by Regulation or Diversion')
        self.assertEqual(peaks['code_meanings']['gage_ht_cd']['6'], 'Gage datum changed during this year')
        self.assertEqual((peaks['rows'][0]['date'], peaks['rows'][0]['peak_cfs']), ('1916-05-22', 11100.0))


if __name__ == '__main__':
    unittest.main()
