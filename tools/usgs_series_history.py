"""Daily history for non-discharge USGS series (stage, lake elevation, precipitation, well depth, water temperature).

Reads data/usgs-history-plan.json (written by regional_inventory.py --all-locations) and, for each
(location, parameter, statistic) listed there, fetches the whole daily record from the USGS OGC
``daily`` collection exactly as tools/usgs_history.py does for discharge: raw body first under
data/raw/usgs-daily/<station>/, gzip copy under data/captures/usgs-daily/<station>/, one versioned
copy kept per series. ``normalize`` writes data/history/<station>-<parameter>-<label>.csv and a
manifest under data/model/. Missing days are absent, never zero. Nothing here is interpreted.
"""
import argparse, csv, datetime as dt, json, sys, time
from pathlib import Path
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import usgs_history as uh  # preserve(), latest_capture(), read_body(), prune_versioned(), BASE, LIMIT, HISTORY, MODEL

PLAN = ROOT / 'data/usgs-history-plan.json'

def plan_items(only=None):
    plan = json.loads(PLAN.read_text())['plan']
    for loc in plan:
        if only and loc['id'] not in only: continue
        for s in loc['series']: yield loc['id'], s['parameter_code'], s['statistic_id'], s['label']

def kind_of(param, stat): return f'daily-{param}-{stat}'

def collect(pause, only=None):
    n = 0
    for sid, param, stat, label in plan_items(only):
        url = uh.BASE + '/daily/items?' + urlencode({'f': 'json', 'monitoring_location_id': 'USGS-' + sid, 'parameter_code': param, 'statistic_id': stat, 'skipGeometry': 'true', 'limit': str(uh.LIMIT)})
        meta_path, meta = uh.preserve(sid, kind_of(param, stat), url)
        complete = meta['status'] == 200 and meta['feature_count'] is not None and meta['feature_count'] < uh.LIMIT and not meta['next_link']
        print(f"{sid} {label}: status {meta['status']} features {meta['feature_count']} {'complete' if complete else 'INCOMPLETE'} {meta['bytes']} bytes"); n += 1; time.sleep(pause)
    print(f'{n} series fetched')

def normalize(only=None):
    uh.HISTORY.mkdir(parents=True, exist_ok=True); uh.MODEL.mkdir(parents=True, exist_ok=True); written = 0; skipped = []
    for sid, param, stat, label in plan_items(only):
        try: meta_path, meta = uh.latest_capture(sid, kind_of(param, stat))
        except FileNotFoundError as e: skipped.append({'station': sid, 'series': label, 'reason': str(e)}); continue
        payload = json.loads(uh.read_body(meta)); feats = payload.get('features')
        complete = meta['status'] == 200 and meta['feature_count'] is not None and meta['feature_count'] < uh.LIMIT and not meta['next_link']
        if not isinstance(feats, list) or not complete: skipped.append({'station': sid, 'series': label, 'reason': 'incomplete or malformed response; not normalized'}); continue
        # A location can carry more than one daily time series for the same parameter and statistic
        # (a second datum, sublocation, or a re-rated series). Keep the series with the most days;
        # record the others in the manifest. Never merge them into one column.
        by_ts = {}
        for f in feats:
            p = f['properties']
            if p.get('parameter_code') != param or p.get('statistic_id') != stat: raise ValueError(f'{sid} {label}: feature is not {param}/{stat}')
            by_ts.setdefault(p.get('time_series_id'), []).append(f)
        chosen = sorted(by_ts, key=lambda k: (-len(by_ts[k]), str(k)))[0]
        alternates = {str(k): {'days': len(v), 'first': min(x['properties']['time'] for x in v), 'last': max(x['properties']['time'] for x in v)} for k, v in by_ts.items() if k != chosen}
        rows = []; seen = set()
        for f in by_ts[chosen]:
            p = f['properties']; day = p.get('time')
            if not day or day in seen: raise ValueError(f'{sid} {label}: missing or duplicate day {day!r} inside one time series')
            seen.add(day); raw = p.get('value')
            try: value = float(raw) if raw not in (None, '') else ''
            except (TypeError, ValueError): value = ''
            rows.append({'date': day, 'value': value, 'raw_value': '' if value != '' else (raw if raw is not None else ''), 'unit': p.get('unit_of_measure'), 'approval_status': p.get('approval_status'), 'qualifiers': ';'.join(p.get('qualifier') or []) if isinstance(p.get('qualifier'), list) else (p.get('qualifier') or ''), 'last_modified': p.get('last_modified'), 'time_series_id': p.get('time_series_id')})
        rows.sort(key=lambda r: r['date'])
        uh.prune_versioned(sid, kind_of(param, stat), ROOT / meta['capture_path'])
        out = uh.HISTORY / f'{sid}-{param}-{label}.csv'
        with out.open('w', newline='') as fh:
            w = csv.DictWriter(fh, fieldnames=['date', 'value', 'raw_value', 'unit', 'approval_status', 'qualifiers', 'last_modified', 'time_series_id']); w.writeheader(); w.writerows(rows)
        numeric = [r for r in rows if r['value'] != '']
        (uh.MODEL / f'{sid}-{param}-{stat}-daily-history-manifest.json').write_text(json.dumps({'station_id': 'USGS-' + sid, 'series': {'parameter_code': param, 'statistic_id': stat, 'label': label}, 'daily_request': {k: meta[k] for k in ('url', 'retrieved_at', 'status', 'sha256', 'bytes', 'feature_count', 'next_link', 'raw_path', 'capture_path')},
            'csv': str(out.relative_to(ROOT)), 'time_series_id': str(chosen), 'other_time_series_for_same_statistic': alternates, 'days': len(rows), 'numeric_days': len(numeric), 'first_day': rows[0]['date'] if rows else None, 'last_day': rows[-1]['date'] if rows else None, 'limits': ['Daily statistics describe the station; missing days are absent, never zero.']}, indent=2) + '\n')
        written += 1
    (uh.MODEL / 'series-history-skipped.json').write_text(json.dumps({'skipped': skipped}, indent=2) + '\n')
    print(f'{written} series normalized, {len(skipped)} skipped')

if __name__ == '__main__':
    p = argparse.ArgumentParser(); sub = p.add_subparsers(dest='cmd', required=True)
    c = sub.add_parser('collect'); c.add_argument('--pause-seconds', type=float, default=0.8); c.add_argument('--stations', nargs='*')
    n = sub.add_parser('normalize'); n.add_argument('--stations', nargs='*'); a = p.parse_args()
    if a.cmd == 'collect': collect(a.pause_seconds, set(a.stations) if a.stations else None)
    else: normalize(set(a.stations) if a.stations else None)
