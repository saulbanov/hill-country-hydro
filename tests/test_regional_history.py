import datetime as dt
import unittest
from tools import regional_normalize as n, regional_analytics as a, regional_history as h


def row(value=1, **kw):
    args = dict(operator='USGS', feed='USGS', site='1', series='s', parameter='p', quantity='discharge', unit='cfs', value=value,
                when='2026-09-30', statistic='daily_mean', source='capture', locator='row', approval='Approved')
    args.update(kw)
    return n.measurement(**args)


def daily(first, last, value=lambda d: d.timetuple().tm_yday, skip=lambda d: False, **kw):
    rows = []; d = dt.date.fromisoformat(first)
    while d <= dt.date.fromisoformat(last):
        if not skip(d):
            rows.append(row(value(d), when=str(d), locator=str(d), **kw))
        d += dt.timedelta(days=1)
    return rows


class HistoryTests(unittest.TestCase):
    def test_old_values_survive_outside_recent_cutoffs(self):
        rows = daily('1939-10-01', '1939-10-10') + daily('2026-09-25', '2026-09-30')
        c = h.continuity(rows)
        self.assertEqual((c['first'], c['last']), ('1939-10-01', '2026-09-30'))
        self.assertEqual(h.exact(rows, '1939-10-03')['value'], dt.date(1939, 10, 3).timetuple().tm_yday)

    def test_missing_years_and_gaps_are_reported_not_filled(self):
        rows = daily('1993-01-01', '1993-05-10') + daily('1997-10-01', '1997-12-31')
        c = h.continuity(rows)
        self.assertEqual(c['missing_years'], [1994, 1995, 1996])
        self.assertEqual(c['gaps'][0], {'after': '1993-05-10', 'before': '1997-10-01', 'missing_days': 1604})
        self.assertLess(c['day_coverage'], .25)

    def test_old_date_without_observation_is_unavailable_never_latest(self):
        rows = daily('2020-01-01', '2026-09-30')
        self.assertIsNone(h.exact(rows, '1950-06-01'))
        self.assertFalse(h.FixedBaseline(rows).rank(h.exact(rows, '1950-06-01'))['available'])
        self.assertIsNone(h.exact(rows + [row(None, when='2019-12-31', locator='x')], '2019-12-31'))

    def test_point_series_have_no_date_only_reading(self):
        point = row(5, when='2026-09-30T12:00:00Z', statistic='instantaneous')
        self.assertIsNone(h.exact([point], '2026-09-30'))
        self.assertFalse(h.aggregate([point])['available'])

    def test_display_range_never_changes_the_baseline(self):
        full = daily('1990-01-01', '2026-09-30')
        recent = [r for r in full if r['time']['date'] >= '2006-01-01']
        target = h.exact(full, '2026-09-30')
        self.assertEqual(h.FixedBaseline(full).rank(target), h.FixedBaseline(recent).rank(target))
        self.assertEqual(h.FixedBaseline(full).rank(target)['reference_years'], [2006, 2025])

    def test_fixed_baseline_matches_the_reference_function(self):
        skip = lambda d: d.year == 2011 or (d.year == 2014 and d.month == 3)
        rows = daily('2000-01-01', '2026-09-30', value=lambda d: (d.toordinal() * 7919) % 97, skip=skip)
        base = h.FixedBaseline(rows)
        for day, exclude in [('2026-09-30', None), ('2024-02-29', 2024), ('2016-01-05', 2016), ('1999-12-28', None), ('2014-03-10', 2014)]:
            d = dt.date.fromisoformat(day)
            slow = a.seasonal_reference(rows, day, reference_years=(2006, 2025), exclude_year=exclude)
            fast = base.reference_for(d.month, d.day, exclude)
            self.assertEqual(slow['available'], fast['available'], day)
            self.assertEqual((slow['days'], slow['expected_days']), (fast['days'], fast['expected_days']), day)
            if slow['available']:
                self.assertEqual(slow['values'], fast['values'], day)

    def test_date_inside_baseline_is_not_in_its_own_reference(self):
        rows = daily('2006-01-01', '2025-12-31', value=lambda d: 1000 if d.year == 2015 else 1)
        result = h.FixedBaseline(rows).rank(h.exact(rows, '2015-06-15'))
        self.assertEqual(result['era'], 'inside_reference_year_left_out')
        self.assertEqual(result['excluded_year'], 2015)
        self.assertEqual(result['percentile'], 100)
        self.assertEqual(result['days'], 19 * 31)

    def test_date_before_baseline_is_labelled_not_pooled(self):
        rows = daily('1950-01-01', '1950-12-31', value=lambda d: 5) + daily('2006-01-01', '2025-12-31', value=lambda d: 5)
        result = h.FixedBaseline(rows).rank(h.exact(rows, '1950-07-04'))
        self.assertEqual(result['era'], 'before_reference')
        self.assertIn('not certified', result['comparability'])
        self.assertEqual(result['days'], 20 * 31)
        self.assertEqual(result['percentile'], 50)

    def test_zero_flow_ties_keep_midrank_and_null_ratio(self):
        rows = daily('2006-01-01', '2026-09-30', value=lambda d: 0)
        result = h.FixedBaseline(rows).rank(h.exact(rows, '2026-09-30'))
        self.assertEqual(result['percentile'], 50)
        self.assertIsNone(result['ratio_to_daily_median'])

    def test_thin_baseline_withholds_rank(self):
        rows = daily('2022-01-01', '2026-09-30')
        self.assertFalse(h.FixedBaseline(rows).rank(h.exact(rows, '2026-09-30'))['available'])

    def test_instantaneous_and_mixed_sensors_get_no_daily_rank(self):
        rows = daily('2006-01-01', '2026-09-30')
        base = h.FixedBaseline(rows)
        self.assertFalse(base.rank(row(9, when='2026-09-30T12:00:00Z', statistic='instantaneous'))['available'])
        mixed = h.FixedBaseline(rows + daily('2006-01-01', '2006-12-31', series='other'))
        self.assertFalse(mixed.rank(h.exact(rows, '2026-09-30'))['available'])

    def test_aggregates_declare_statistic_threshold_and_missingness(self):
        rows = daily('2020-01-01', '2020-12-31', value=lambda d: 2) + daily('2021-01-01', '2021-03-01', value=lambda d: 4)
        out = h.aggregate(rows, 'year')
        self.assertEqual((out['input_statistic'], out['coverage_threshold']), ('daily_mean', .9))
        year = {p['period']: p for p in out['periods']}
        self.assertEqual(year['2020']['mean_of_daily_means'], 2)
        self.assertFalse(year['2021']['complete']); self.assertNotIn('mean_of_daily_means', year['2021'])
        month = {p['period']: p for p in h.aggregate(rows, 'month')['periods']}
        self.assertTrue(month['2021-02']['complete']); self.assertFalse(month['2021-03']['complete'])

    def test_rain_days_are_never_summed(self):
        rows = daily('2020-01-01', '2020-12-31', value=lambda d: .1, quantity='rain', unit='in', statistic='daily_total_boundary_unverified')
        period = h.aggregate(rows, 'year')['periods'][0]
        self.assertTrue(period['complete'])
        self.assertFalse(any('sum' in k or 'mean' in k for k in period))

    def test_capacity_eras_come_from_stated_values_only(self):
        rows = []
        for i, cap in enumerate([100, 100, 90, 90, 90]):
            rows.append(row(50, when=f'2020-01-0{i+1}', locator=str(i), quantity='conservation_storage', unit='acre-ft', statistic='daily_report',
                            extra={'capacity': {'conservation_capacity_af': cap}}))
        c = h.continuity(rows)
        self.assertEqual(c['capacity_eras'], [{'from': '2020-01-01', 'to': '2020-01-02', 'conservation_capacity_af': 100},
                                              {'from': '2020-01-03', 'to': '2020-01-05', 'conservation_capacity_af': 90}])
        self.assertTrue(any('survey version' in u for u in c['continuity']['unknown']))

    def test_well_continuity_keeps_screen_unknown(self):
        rows = [row(90, when='2020-01-01', quantity='groundwater_depth', unit='ft', statistic='daily_high', datum='land surface')]
        self.assertTrue(any('screen' in u for u in h.continuity(rows)['continuity']['unknown']))

    def test_provider_declared_start_earlier_than_preserved(self):
        c = h.continuity(daily('2000-01-01', '2000-01-05'), {'begin': '1915-10-01T05:00:00+00:00', 'end': None})
        self.assertTrue(any('1915-10-01' in u for u in c['continuity']['unknown']))

    def test_scoped_builder_keeps_default_gates(self):
        import inspect
        sig = inspect.signature(n.Builder.__init__).parameters
        self.assertEqual(sig['daily_start'].default, '2006-01-01')
        self.assertIsNone(sig['only'].default); self.assertIsNone(sig['hydromet_params'].default)


if __name__ == '__main__':
    unittest.main()
