"""Full preserved histories for the pilot stations: partition, continuity audit, fixed-baseline ranks.

Offline. Reuses the regional-measurements/v1 adapters and Reader with the retention gates opened
for a named station list; the compact recent store is left untouched. See docs/REGIONAL_HISTORY.md.
"""
import argparse
import bisect
from collections import Counter
import datetime as dt
import json
from pathlib import Path
import statistics
try:
    from . import regional_normalize as normalize
    from .regional_analytics import Reader
    from .regional_geography import basin_at
    from .station_lists import SWIM_MAP_GAUGES
except ImportError:
    import regional_normalize as normalize
    from regional_analytics import Reader
    from regional_geography import basin_at
    from station_lists import SWIM_MAP_GAUGES

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'data/normalized/regional-history'
STATIONS = ROOT/'data/model/regional-history-stations.json'
REFERENCE = (2006, 2025)
HALF_WINDOW = 15
DAILY = ('daily_mean', 'daily_sum', 'daily_max', 'daily_min', 'unknown_daily', 'daily_report', 'daily_high',
         'daily_total_boundary_unverified')
RIVERS = ['08150000', '08151500', '08152900', '08153500']
# Austin creek gauges of the creek prototype; USGS places all six in HUC8 12090205.
AUSTIN = ['08154700', '08155300', '08156800', '08158600', '08158970', '08159000']
LAKES = ['buchanan', 'inks', 'lyndon-b-johnson', 'marble-falls', 'travis', 'austin']


def day_of(r):
    return r['time']['date'] or r['time']['original'][:10]


def select(root=ROOT, analytics=None):
    """Name the pilot stations from the integrated catalog, WBD containment and saved manifests."""
    root = Path(root)
    catalog = json.loads((Path(analytics or root/'data/normalized/regional-analytics')/'catalog.json').read_text())
    basins = json.loads((root/'app/regional-basins.geojson').read_text())['features']
    rain_history = set()
    for p in sorted((root/'data/captures/hydromet').glob('*/*manifest.json')):
        for w in json.loads(p.read_text()).get('windows', {}).values():
            if w.get('param') == 'rainDaily' and w.get('records'):
                rain_history.add(f"{w['agency']}:{w['site']}")
    out = {}
    for site in RIVERS:
        out['USGS:'+site] = {'kind': 'river', 'basis': 'pilot river gauge; USGS daily history manifest'}
    for site in AUSTIN:
        out['USGS:'+site] = {'kind': 'river', 'basin': 'Austin creeks', 'basis': 'Austin creek gauge of the creek prototype; USGS daily history manifest'}
    for slug in LAKES:
        out['TWDB-lake:'+slug] = {'kind': 'reservoir', 'basis': 'Highland Lakes chain; TWDB reservoir history capture'}
    for key, site in sorted(catalog['sites'].items()):
        basin = basin_at(site.get('coordinates'), basins)
        if site.get('kind') == 'spring':
            out[key] = {'kind': 'spring', 'basis': 'separate regional context; not located in a pilot watershed'}
        elif key.startswith('TWDB:') and site.get('kind') == 'well' and basin['huc8']:
            out[key] = {'kind': 'well', 'basin': basin['name'], 'huc8': basin['huc8'],
                        'basis': 'coordinates inside one pilot WBD subbasin; surface location only'}
        elif key.startswith('LCRA:') and basin['huc8'] and key in rain_history:
            out[key] = {'kind': 'rain', 'basin': basin['name'], 'huc8': basin['huc8'],
                        'basis': 'coordinates inside one pilot WBD subbasin; saved daily-rain history with records'}
    for site in SWIM_MAP_GAUGES:  # the swim map's springs are already named above as springs
        out.setdefault('USGS:'+site, {'kind': 'river', 'basis': 'gauge the Austin Swim Map rates swimming places from (station_lists.SWIM_MAP_GAUGES); USGS daily history manifest'})
    doc = {'purpose': 'Stations whose full preserved record is adapted into data/normalized/regional-history/.',
           'selection': 'tools/regional_history.py select; inventory membership is not evidence of numeric coverage',
           'counts': dict(Counter(v['kind'] for v in out.values())), 'stations': out}
    STATIONS.write_text(json.dumps(doc, indent=2)+'\n')
    print('History stations', doc['counts'])
    return doc


def build(root=ROOT, out=OUT, through='2026-10-03T12:15:00Z'):
    keys = sorted(json.loads(STATIONS.read_text())['stations'])
    return normalize.build(root, out, since='0001-01-01', through=through, daily_start='0001-01-01', only=keys, audit_path=None,
                           hydromet_params={'rainDaily'})


def continuity(rows, declared=None):
    """Describe what the preserved record holds. Unknown stays unknown; nothing is stitched."""
    good = [r for r in rows if r['state'] == 'measured']
    out = {'records': len(rows), 'numeric': len(good), 'unavailable': len(rows)-len(good),
           'statistics': sorted({r['time']['statistic'] for r in rows}), 'units': sorted({str(r['unit']) for r in rows}),
           'vertical_datum': sorted({str(r['vertical_datum']) for r in rows}),
           'approval': dict(Counter(r['approval'] for r in rows)),
           'qualified_records': sum(bool(r['qualifiers']) and any(r['qualifiers']) for r in rows),
           'provenance': dict(Counter(r.get('provenance_status', 'unknown') for r in rows)),
           'source_ids': sorted({r['source_id'] for r in rows})}
    if not good:
        return dict(out, first=None, last=None, by_year={}, missing_years=[], gaps=[], daily=False)
    days = sorted({day_of(r) for r in good})
    first, last = days[0], days[-1]
    by_year = Counter(d[:4] for d in days)
    span = range(int(first[:4]), int(last[:4])+1)
    daily = all(s in DAILY for s in out['statistics'])
    gaps = []
    previous = dt.date.fromisoformat(first)
    for d in days[1:]:
        current = dt.date.fromisoformat(d)
        missing = (current-previous).days-1
        if missing > 0:
            gaps.append({'after': str(previous), 'before': d, 'missing_days': missing})
        previous = current
    out.update(first=first, last=last, daily=daily, days_with_values=len(days), by_year=dict(sorted(by_year.items())),
               missing_years=[y for y in span if str(y) not in by_year],
               gap_count=len(gaps), missing_days_total=sum(g['missing_days'] for g in gaps),
               gaps=sorted(gaps, key=lambda g: -g['missing_days'])[:25],
               gap_meaning='calendar days inside the span with no numeric value; for point series a day without a reading is listed the same way')
    if daily:
        expected = (dt.date.fromisoformat(last)-dt.date.fromisoformat(first)).days+1
        out['day_coverage'] = round(len(days)/expected, 4)
    eras = []
    for r in good:
        c = (r.get('capacity') or {}).get('conservation_capacity_af')
        if c is None:
            continue
        if not eras or eras[-1]['conservation_capacity_af'] != c:
            eras.append({'from': day_of(r), 'to': day_of(r), 'conservation_capacity_af': c})
        else:
            eras[-1]['to'] = day_of(r)
    known, unknown = [], ['sensor, gauge-location and method changes are not documented in the preserved bodies']
    if len({r['series_id'] for r in rows}) == 1:
        known.append('one provider series identifier across the whole preserved span')
    if eras:
        known.append(f'{len(eras)} stated conservation-capacity value(s); boundaries are the dates the provider value changes')
        unknown.append('capacity survey version and the cause of each capacity change are not supplied')
        out['capacity_eras'] = eras
    if rows[0]['quantity'].startswith('groundwater'):
        unknown += ['screen or open interval not in the measurement record', 'pumping influence on any reading is not recorded']
    if rows[0]['quantity'] in ('stage', 'groundwater_elevation', 'reservoir_elevation') and out['vertical_datum'] == ['None']:
        unknown.append('vertical datum not supplied')
    if declared:
        out['provider_declared_span'] = declared
        if declared.get('begin') and declared['begin'][:10] < first:
            unknown.append(f"provider metadata declares a start of {declared['begin'][:10]}, earlier than the first preserved value")
    out['continuity'] = {'known': known, 'unknown': unknown}
    return out


def aggregate(rows, period='year', threshold=.9):
    """Summaries of a daily series by month or year. A period below the coverage threshold has no value.

    Point readings are never turned into daily or longer means; rain totals are not summed because the
    provider's day boundary is unverified and a missing day is not zero rain.
    """
    stats = {r['time']['statistic'] for r in rows}
    if len({r['series_id'] for r in rows}) != 1 or len(stats) != 1 or not stats <= set(DAILY):
        return {'available': False, 'reason': 'requires one daily series; point observations are not aggregated'}
    statistic = stats.pop()
    size = 4 if period == 'year' else 7
    groups = {}
    for r in rows:
        if r['state'] == 'measured':
            groups.setdefault(day_of(r)[:size], {})[day_of(r)] = r['value']
    out = []
    for key, values in sorted(groups.items()):
        y = int(key[:4])
        if period == 'year':
            expected = 366 if y % 4 == 0 and (y % 100 or y % 400 == 0) else 365
        else:
            m = int(key[5:7])
            expected = (dt.date(y+(m == 12), m % 12+1, 1)-dt.date(y, m, 1)).days
        vals = list(values.values())
        ok = len(vals) >= threshold*expected
        row = {'period': key, 'days': len(vals), 'expected_days': expected, 'coverage': round(len(vals)/expected, 4), 'complete': ok}
        if ok:
            row.update(min=min(vals), max=max(vals))
            if statistic == 'daily_mean':
                row['mean_of_daily_means'] = statistics.fmean(vals)
            elif statistic != 'daily_total_boundary_unverified':
                row['median_of_daily_values'] = statistics.median(vals)
        out.append(row)
    return {'available': True, 'input_statistic': statistic, 'period': period, 'coverage_threshold': threshold,
            'missingness': 'periods below the threshold report days and coverage only; absent periods have no row',
            'rain_note': 'daily rain totals are not summed' if statistic == 'daily_total_boundary_unverified' else None, 'periods': out}


def _leap_index(month, day):
    return (dt.date(2000, month, day)-dt.date(2000, 1, 1)).days


class FixedBaseline:
    """Rank any date's daily mean against one fixed reference era; the display range never changes it.

    Policy. Reference: the same series' Approved daily means within +/-15 calendar days in 2006-2025
    (the gates of regional_analytics.seasonal_reference: 80% of a year's window dates, 80% of all
    expected dates, five qualifying years). A date inside the reference era is ranked against the
    other reference years; its whole year is left out, so an observation is never in its own
    reference. A date outside the era is ranked against the same fixed distribution and labelled.
    A date without a measured daily mean has no rank and no substituted reading.
    """
    def __init__(self, rows, reference=REFERENCE, half_window=HALF_WINDOW):
        self.reference = reference
        self.half = half_window
        self.rows = rows
        self.ok = len({r['series_id'] for r in rows}) == 1 and all(
            r['quantity'] == 'discharge' and r['unit'] == 'ft3/s' and r['time']['statistic'] == 'daily_mean' for r in rows)
        self.values = {y: {} for y in range(reference[0], reference[1]+1)}
        for r in rows if self.ok else []:
            if r['state'] != 'measured' or r['approval'] != 'Approved' or not r['time']['date']:
                continue
            d = dt.date.fromisoformat(r['time']['date'])
            if d.year in self.values:
                self.values[d.year][_leap_index(d.month, d.day)] = r['value']
        self.valid = {y: {_leap_index(d.month, d.day) for d in (dt.date(y, 1, 1)+dt.timedelta(days=i) for i in range(366)) if d.year == y}
                      for y in self.values}
        self.cache = {}

    def reference_for(self, month, day, exclude_year=None):
        key = (month, day, exclude_year if exclude_year in self.values else None)
        if key in self.cache:
            return self.cache[key]
        anchor = _leap_index(month, day)
        window = [(anchor+o) % 366 for o in range(-self.half, self.half+1)]
        expected = {}; have = {}
        for y, vals in self.values.items():
            if y == key[2]:
                continue
            expected[y] = sum(i in self.valid[y] for i in window)
            have[y] = [vals[i] for i in window if i in vals]
        accepted = [y for y in expected if len(have[y]) >= .8*expected[y]]
        pool = sorted(v for y in accepted for v in have[y])
        total = sum(expected.values())
        out = {'available': False, 'reference_years': list(self.reference), 'excluded_year': key[2], 'half_window_days': self.half,
               'accepted_years': accepted, 'days': len(pool), 'expected_days': total, 'coverage': len(pool)/total if total else 0}
        if not self.ok:
            out['reason'] = 'requires one daily mean discharge series'
        elif len(accepted) < 5 or out['coverage'] < .8:
            out['reason'] = 'requires 5 qualifying years and 80% of all expected days'
        else:
            out.update(available=True, median=statistics.median(pool), values=pool)
        self.cache[key] = out
        return out

    def rank(self, reading):
        if not reading or reading['state'] != 'measured' or not reading['time']['date']:
            return {'available': False, 'reason': 'no measured daily mean on this date; no other reading is substituted'}
        if reading['time']['statistic'] != 'daily_mean' or reading['quantity'] != 'discharge':
            return {'available': False, 'reason': 'only daily mean discharge can receive a daily rank'}
        d = dt.date.fromisoformat(reading['time']['date'])
        inside = self.reference[0] <= d.year <= self.reference[1]
        ref = self.reference_for(d.month, d.day, d.year if inside else None)
        if not ref['available']:
            return {'available': False, 'reason': ref['reason'], 'reference_years': ref['reference_years']}
        vals = ref['values']; x = reading['value']
        below = bisect.bisect_left(vals, x); ties = bisect.bisect_right(vals, x)-below
        era = 'inside_reference_year_left_out' if inside else 'before_reference' if d.year < self.reference[0] else 'after_reference'
        return {'available': True, 'percentile': 100*(below+.5*ties)/len(vals), 'median': ref['median'], 'days': len(vals),
                'ratio_to_daily_median': x/ref['median'] if ref['median'] else None, 'reference_years': ref['reference_years'],
                'excluded_year': ref['excluded_year'], 'era': era,
                'comparability': {'inside_reference_year_left_out': 'ranked against the other reference years; its own year is excluded',
                                  'before_reference': 'ranked against the fixed later reference; measurement and management continuity between the eras is not certified',
                                  'after_reference': 'ranked against the fixed prior reference'}[era]}


def exact(rows, day):
    """The reading for exactly this date, or nothing. Never the nearest or the latest."""
    found = [r for r in rows if day_of(r) == day and r['time']['date']]
    return found[0] if len(found) == 1 and found[0]['state'] == 'measured' else None


def hydromet_missing(root=ROOT):
    """Windows a Hydromet manifest names whose preserved body is absent; grouped, with pilot relevance."""
    root = Path(root); groups = {}
    for p in sorted((root/'data/captures/hydromet').glob('*/*manifest.json')):
        for path, w in json.loads(p.read_text()).get('windows', {}).items():
            raw = w.get('raw_path')
            if (root/'data/captures/hydromet'/path).exists() or (raw and (root/raw).exists()):
                continue
            g = groups.setdefault(f"{w.get('agency')}:{w.get('site')}:{w.get('param')}", {'site_name': w.get('site_name'), 'windows': [], 'manifest_records': 0, 'manifest_sha256_present': 0})
            g['windows'].append(path); g['manifest_records'] += w.get('records') or 0; g['manifest_sha256_present'] += bool(w.get('sha256'))
    for g in groups.values():
        g['count'] = len(g['windows']); g['first_window'] = min(g['windows']); g['last_window'] = max(g['windows'])
    return groups


def audit(folder=OUT, root=ROOT):
    root = Path(root)
    chosen = json.loads(STATIONS.read_text())['stations']
    reader = Reader(folder); c = reader.catalog; series = {}
    declared = {}
    for key in chosen:
        if not key.startswith('USGS:'):
            continue
        for p in sorted((root/'data/model').glob(key[5:]+'-daily-history-manifest.json')):
            for x in json.loads(p.read_text()).get('station_series_inventory_00060_00065', []):
                declared[x['id']] = {'begin': x.get('begin'), 'end': x.get('end'), 'primary': x.get('primary'), 'computation': x.get('computation_identifier')}
    for sid, s in sorted(c['series'].items()):
        rows = reader.rows(sid)
        series[sid] = dict(station=s['site_key'], kind=chosen.get(s['site_key'], {}).get('kind'), quantity=s['quantity'], feed=s['feed'],
                           primary=s['primary'], **continuity(rows, declared.get(s['original_series_id'])))
    reader.close()
    missing = hydromet_missing(root)
    words = ('Llano', 'Pedernales', 'Buchanan', 'Inks', 'LBJ', 'Wirtz', 'Starcke', 'Marble Falls', 'Mansfield', 'Travis', 'Lake Austin', 'Tom Miller', 'Sandy Creek')
    pilot = {k for k, g in missing.items() if k.rsplit(':', 1)[0] in chosen or any(w in (g['site_name'] or '') for w in words)}
    captured = set(json.loads((root/'data/captures/twdb-wells/manifest.json').read_text()))
    inventory = {w['id']: w for w in json.loads((root/'data/wells-regional.json').read_text())['wells']}
    unfetched = {k: {'provider_full_record_bytes': inventory[k[5:]].get('full_record_bytes'), 'latest_feed_date': inventory[k[5:]].get('latest_feed_date'),
                     'status': inventory[k[5:]].get('status'), 'url': inventory[k[5:]]['source']+'.json',
                     'state': 'recoverable: the provider lists a full record that was never captured; the collection rule kept wells with a daily-feed row at most 7 days old'}
                 for k, v in sorted(chosen.items()) if v['kind'] == 'well' and k[5:] not in captured}
    stations_without = sorted(k for k in chosen if not any(s['station'] == k and s['numeric'] for s in series.values()))
    report = {'schema_version': c['schema_version'], 'cutoff': c['cutoff'], 'scope': 'full preserved record for named pilot stations',
              'reference_policy': FixedBaseline.__doc__.split('Policy. ')[1].strip(), 'reference_years': list(REFERENCE),
              'observations': c['observations'], 'stations': chosen, 'stations_without_numeric_history': stations_without,
              'series': series, 'source_gaps': c['gaps'], 'unfetched_well_histories': unfetched,
              'hydromet_missing_windows': {'groups': missing, 'total': sum(g['count'] for g in missing.values()),
                                           'meaning': 'the manifest names a fetched window but neither the versioned gzip nor a raw body is on disk; these are gaps, not coverage',
                                           'recovery': 'each window is one bounded request to the provider history endpoint through tools/hydromet.py; none was re-requested here',
                                           'pilot_relevant': sorted(pilot),
                                           'pilot_basis': 'station is in the history list, or the provider site name contains a pilot river, lake or dam name'}}
    (root/'data/model/regional-history-continuity.json').write_text(json.dumps(report, indent=1)+'\n')
    lines = ['# Regional station histories', '', f"Generated offline by `tools/regional_history.py audit`. Saved-data cutoff {c['cutoff']}. "
             f"{c['observations']['rows']} original records in {len(series)} series for {len(chosen)} named stations.", '',
             '| Station | Kind | Quantity / statistic | First | Last | Days with values | Missing years | Largest gap (days) |', '|---|---|---|---|---|---:|---:|---:|']
    lines.insert(3, 'Series with fewer than 30 values and the current-snapshot feeds are in the JSON report only. First and last are the first and last preserved values, not the first measurement ever made.')
    lines.insert(4, '')
    for sid, s in sorted(series.items(), key=lambda kv: (kv[1]['kind'] or '', kv[1]['station'], kv[1]['quantity'])):
        if s['numeric'] < 30 or ':current:' in sid or ':recent:' in sid:
            continue  # short snapshot series stay in the JSON report
        lines.append(f"| {s['station']} | {s['kind']} | {s['quantity']} / {', '.join(s['statistics'])} | {s['first']} | {s['last']} | {s['days_with_values']} | {len(s['missing_years'])} | {s['gaps'][0]['missing_days'] if s['gaps'] else 0} |")
    lines += ['', f"Stations named but without numeric history in the preserved bodies: {', '.join(stations_without) or 'none'}.", '',
              f"Pilot wells whose full record exists at TWDB but was never captured ({len(unfetched)}): {', '.join(k[5:] for k in unfetched) or 'none'}. Their history is recoverable with one request each; it is not counted here.", '',
              f"Hydromet windows named by a manifest with no preserved body: {report['hydromet_missing_windows']['total']} in {len(missing)} site/parameter groups. "
              'They are listed in `data/model/regional-history-continuity.json` with their window names; none is counted as coverage.', '']
    (root/'docs/REGIONAL_HISTORY_TABLE.md').write_text('\n'.join(lines))
    print('History audit:', len(series), 'series;', sum(s['numeric'] for s in series.values()), 'numeric;', 'missing Hydromet windows', report['hydromet_missing_windows']['total'])
    return report


def show(series, day, folder=OUT):
    """Print the preserved record(s) for one series and date with their source locator."""
    reader = Reader(folder, verify=False)
    rows = [r for r in reader.rows(series, resolved=False) if day_of(r) == day]
    for r in rows:
        src = reader.catalog['sources'][r['source_id']]
        print(json.dumps({'observation': r, 'source': src}, indent=1))
    reader.close()
    if not rows:
        print('No preserved record for', series, 'on', day)
    return rows


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    sub.add_parser('select'); sub.add_parser('build'); sub.add_parser('audit')
    s = sub.add_parser('show'); s.add_argument('series'); s.add_argument('day')
    a = p.parse_args()
    if a.command == 'select': select()
    elif a.command == 'build': build()
    elif a.command == 'audit': audit()
    else: show(a.series, a.day)
