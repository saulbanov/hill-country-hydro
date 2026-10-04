"""Earlier floods at the pilot river gauges, from the preserved full records. Offline.

Two separate records are kept apart: USGS published annual peaks (instantaneous) and the
largest daily means in the full-history store. An instantaneous reading is only ever placed
among instantaneous peaks, a daily mean among daily means. See docs/REGIONAL_HISTORY.md.
"""
import datetime as dt
import gzip
import hashlib
import json
from pathlib import Path
import re
try:
    from .regional_analytics import Reader
    from . import regional_history as history
except ImportError:
    from regional_analytics import Reader
    import regional_history as history

ROOT = Path(__file__).resolve().parents[1]
PAIRS = [('USGS:08150000', 'USGS:08151500'), ('USGS:08152900', 'USGS:08153500')]


def annual_peaks(site, root=ROOT):
    """Parse the preserved USGS peak-flow file; codes keep the meanings printed in its own header."""
    folder = Path(root)/'data/captures/usgs-peaks'/site
    meta = json.loads((folder/'annual.meta.json').read_text())
    body = gzip.decompress((folder/'annual.txt.gz').read_bytes())
    if meta['status'] != 200 or hashlib.sha256(body).hexdigest() != meta['sha256']:
        raise ValueError('unverified annual-peak capture '+site)
    lines = body.decode().splitlines()
    section = None; meanings = {'peak_cd': {}, 'gage_ht_cd': {}}; last = None
    for line in lines:
        if not line.startswith('#'):
            break
        if 'Qualification Codes(peak_cd)' in line:
            section = 'peak_cd'; continue
        if 'Qualification Codes(gage_ht_cd' in line or 'Gage height qualification codes' in line.lower() or '(gage_ht_cd' in line:
            section = 'gage_ht_cd'; continue
        m = re.match(r'#\s+([0-9A-Z]) \.\.\. (.+)', line)
        if section and m:
            last = (section, m.group(1)); meanings[section][m.group(1)] = m.group(2).strip()
        elif section and last and last[0] == section and re.match(r'#\s{6,}\S', line):
            meanings[section][last[1]] += ' '+line.lstrip('# ').strip()
    data = [l.split('\t') for l in lines if l and not l.startswith('#')]
    head = data[0]; rows = []
    for parts in data[2:]:
        r = dict(zip(head, parts+['']*(len(head)-len(parts))))
        if r['site_no'] != site:
            raise ValueError('peak file site mismatch')
        rows.append({'date': r['peak_dt'], 'time': r['peak_tm'] or None, 'peak_cfs': float(r['peak_va']) if r['peak_va'] else None,
                     'peak_codes': [c for c in r['peak_cd'].split(',') if c], 'gage_height_ft': float(r['gage_ht']) if r['gage_ht'] else None,
                     'gage_height_codes': [c for c in r['gage_ht_cd'].split(',') if c]})
    return {'site': site, 'rows': rows, 'code_meanings': meanings,
            'source': {k: meta[k] for k in ('url', 'retrieved_at', 'sha256', 'bytes')},
            'statistic': 'annual instantaneous peak discharge by water year, as published by USGS'}


def place_among_peaks(value, peaks):
    """Where one instantaneous reading falls among published annual peaks. No rank is invented for a missing value."""
    vals = [r['peak_cfs'] for r in peaks['rows'] if r['peak_cfs'] is not None]
    if value is None or not vals:
        return {'available': False, 'reason': 'no instantaneous reading or no published annual peaks'}
    years = [r['date'][:4] for r in peaks['rows'] if r['peak_cfs'] is not None]
    return {'available': True, 'value': value, 'published_peaks': len(vals), 'larger': sum(v > value for v in vals), 'equal': sum(v == value for v in vals),
            'first_year': min(years), 'last_year': max(years), 'largest_published': max(vals),
            'limits': ['the reading is the largest saved value in this storm; gaps in the saved record may hide a larger one',
                       'this storm’s own annual peak has not been published', 'annual peaks carry the provider codes shown; regulation and datum changes are coded, not corrected']}


def daily_events(rows, top=10, separation=7):
    """Largest daily means that are the maximum within +/- `separation` days. Daily values only; nothing is filled."""
    if len({r['series_id'] for r in rows}) != 1 or any(r['time']['statistic'] != 'daily_mean' or r['quantity'] != 'discharge' for r in rows):
        return {'available': False, 'reason': 'requires one daily mean discharge series'}
    by = {r['time']['date']: r for r in rows if r['state'] == 'measured' and r['time']['date']}
    day = lambda s, n: str(dt.date.fromisoformat(s)+dt.timedelta(days=n))
    peaks = []
    for d, r in by.items():
        near = [by[day(d, o)]['value'] for o in range(-separation, separation+1) if o and day(d, o) in by]
        earlier = [by[day(d, o)]['value'] for o in range(-separation, 0) if day(d, o) in by]
        if all(r['value'] >= v for v in near) and all(r['value'] > v for v in earlier):
            peaks.append(d)
    peaks.sort(key=lambda d: (-by[d]['value'], d))
    out = []
    for d in peaks[:top]:
        v = by[d]['value']; n = 0; status = 'counted to the first day below half the peak'
        while True:
            nxt = by.get(day(d, n+1))
            if nxt is None:
                status = 'unavailable: a missing day interrupts the recession'; n = None; break
            if nxt['value'] < v/2:
                break
            n += 1
        before = by.get(day(d, -3))
        out.append({'date': d, 'daily_mean_cfs': v, 'approval': by[d]['approval'], 'three_days_before_cfs': before['value'] if before else None,
                    'days_at_or_above_half_peak_after': n, 'recession_note': status, 'observation_id': by[d]['id']})
    return {'available': True, 'rule': f'a day whose daily mean is the largest within {separation} days either side; ties go to the first day', 'events': out,
            'first': min(by), 'last': max(by)}


def pair_lags(up, down, window=3):
    """Date difference between upstream and downstream daily-mean peaks. Daily values cannot resolve hours."""
    out = []
    ups = {e['date']: e for e in up.get('events', [])}
    for e in down.get('events', []):
        d = dt.date.fromisoformat(e['date'])
        match = [u for u in ups if abs((dt.date.fromisoformat(u)-d).days) <= window]
        if len(match) == 1:
            out.append({'downstream_date': e['date'], 'upstream_date': match[0], 'lag_days': (d-dt.date.fromisoformat(match[0])).days})
        else:
            out.append({'downstream_date': e['date'], 'upstream_date': None, 'lag_days': None,
                        'reason': 'no single upstream event among its largest within three days' if not match else 'more than one upstream event within three days'})
    return out


def build(folder=history.OUT, root=ROOT, top=10):
    reader = Reader(folder); cat = reader.catalog; gauges = {}
    for site in history.RIVERS+history.AUSTIN:
        key = 'USGS:'+site; sid, why = reader.choose(key, 'discharge', 'daily_mean', 'USGS')
        rows = reader.rows(sid) if sid else []
        peaks = annual_peaks(site, root)
        gauges[key] = {'name': cat['sites'][key]['name'], 'daily_series': sid, 'daily_selection': why, 'daily_events': daily_events(rows, top),
                       'annual_peaks': peaks, 'last_daily_mean': max((r['time']['date'] for r in rows if r['state'] == 'measured'), default=None)}
        if not sid:
            gauges[key]['daily_events'] = {'available': False, 'reason': why}
    reader.close()
    lags = {f'{a}>{b}': pair_lags(gauges[a]['daily_events'], gauges[b]['daily_events']) for a, b in PAIRS}
    doc = {'schema_version': 'regional-events/v1', 'cutoff': cat['cutoff'], 'history_sha256': cat['observations']['sha256'], 'gauges': gauges, 'pair_lags': lags,
           'meaning': 'earlier floods at the same gauge, from its own record; annual peaks are instantaneous and daily events are daily means, never mixed',
           'limits': ['An event list ranks saved daily means; it is not a return period or a forecast.', 'A lag is the difference between two dates; hours are not resolved.',
                      'Volume, rainfall and starting conditions are not compared here.']}
    (Path(root)/'data/model/regional-events.json').write_text(json.dumps(doc, indent=1)+'\n')
    print('Events:', {k: (len(g['annual_peaks']['rows']), g['daily_events'].get('events', [{}])[0].get('date')) for k, g in gauges.items()})
    return doc


if __name__ == '__main__':
    build()
