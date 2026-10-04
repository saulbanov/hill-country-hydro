"""Package per-station history partitions for the browser from the full-history reader. Offline.

One file per station under app/history/, loaded on demand; the map never downloads the archive or
the normalized database. Values are the preserved observations; ranks and summaries come from
tools/regional_history.py. No provider field is interpreted here.
"""
from collections import Counter
import datetime as dt
import json
from pathlib import Path
try:
    from .regional_analytics import Reader
    from . import regional_history as history
except ImportError:
    from regional_analytics import Reader
    import regional_history as history

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = 'regional-history-partition/v1'
POINT_LIMIT = 6000
LABELS = {('discharge', 'daily_mean'): 'Daily mean discharge', ('storage', 'daily_report'): 'Reported total storage',
          ('percent_full', 'daily_report'): 'Percent of conservation capacity', ('groundwater_depth', 'daily_high'): 'Daily high water level, depth below land surface',
          ('groundwater_depth', 'reported_point'): 'Reported water level, depth below land surface',
          ('rain', 'daily_total_boundary_unverified'): 'Daily rain total (day boundary unverified)'}
WANTED = {'river': [('discharge', 'daily_mean')], 'spring': [('discharge', 'daily_mean')],
          'reservoir': [('storage', 'daily_report'), ('percent_full', 'daily_report')],
          'well': [('groundwater_depth', 'daily_high'), ('groundwater_depth', 'reported_point')],
          'rain': [('rain', 'daily_total_boundary_unverified')]}


def slug(key):
    return ''.join(c if c.isalnum() else '-' for c in key).strip('-').lower()


def runs(days):
    """Collapse sorted ISO dates into inclusive [first,last] runs."""
    out = []
    for d in days:
        if out and (dt.date.fromisoformat(d)-dt.date.fromisoformat(out[-1][1])).days == 1:
            out[-1][1] = d
        else:
            out.append([d, d])
    return out


def encode(rows):
    """Dense daily array with nulls where coverage allows; otherwise dated pairs. Nothing interpolated."""
    good = [r for r in rows if r['state'] == 'measured']
    if not good:
        return {'encoding': 'empty'}
    stamped = {}
    if all(r['time']['statistic'] in history.DAILY and r['time']['instant'] for r in good):
        # A daily value the provider stamps with a clock time: keep one value per stamp date and report the clock times seen.
        labels = [r['time']['instant'][:10] for r in good]
        if len(set(labels)) == len(labels):
            stamped = {'date_basis': 'UTC date of the provider time stamp', 'stamp_clock_utc': dict(Counter(r['time']['instant'][11:16] for r in good))}
    if stamped or all(r['time']['date'] for r in good):
        by = {(r['time']['date'] or r['time']['instant'][:10]): r['value'] for r in good}
        first, last = min(by), max(by)
        span = (dt.date.fromisoformat(last)-dt.date.fromisoformat(first)).days+1
        if len(by) >= .5*span:
            start = dt.date.fromisoformat(first)
            values = [by.get(str(start+dt.timedelta(days=i))) for i in range(span)]
            if sum(v == 0 for v in values) >= .7*span:
                # Lossless: measured zeros are the default, missing days are listed as runs, everything else is explicit.
                missing = []
                for i, v in enumerate(values):
                    if v is None:
                        if missing and missing[-1][1] == i-1:
                            missing[-1][1] = i
                        else:
                            missing.append([i, i])
                return {'encoding': 'zero_default', 'start': first, 'length': span, 'nonzero': [[i, v] for i, v in enumerate(values) if v], 'missing_runs': missing, **stamped}
            return {'encoding': 'dense', 'start': first, 'values': values, **stamped}
        return {'encoding': 'sparse', 'points': sorted(by.items()), **stamped}
    points = sorted((r['time']['instant'], r['value']) for r in good if r['time']['instant'])
    if len(points) <= POINT_LIMIT:
        return {'encoding': 'sparse', 'points': points}
    last = {}
    for at, v in points:
        last[at[:10]] = (at, v)
    return {'encoding': 'sparse', 'points': [last[d] for d in sorted(last)], 'subsample': f'{len(points)} preserved point readings; the browser file keeps the last reading of each UTC date. Every reading stays in the offline history store; no daily statistic is computed from points.'}


def station(reader, key, meta, site, series_ids):
    cat = reader.catalog; out = []; sources = {}
    for sid in series_ids:
        s = cat['series'][sid]; rows = reader.rows(sid)
        if not any(r['state'] == 'measured' for r in rows):
            continue
        cont = history.continuity(rows)
        item = {'id': sid, 'label': LABELS.get((s['quantity'], s['statistic']), s['quantity']), 'quantity': s['quantity'], 'statistic': s['statistic'],
                'unit': s['unit'], 'vertical_datum': s['vertical_datum'], 'primary': s['primary'], **encode(rows)}
        other = sorted({history.day_of(r) for r in rows if r['state'] == 'measured' and r['approval'] not in ('Approved', 'unknown')})
        item['approval'] = cont['approval']; item['not_approved_runs'] = runs(other)
        if s['quantity'] == 'discharge' and s['statistic'] == 'daily_mean' and item['encoding'] == 'dense':
            base = history.FixedBaseline(rows); by = {r['time']['date']: r for r in rows if r['state'] == 'measured' and r['time']['date']}
            start = dt.date.fromisoformat(item['start']); ranks = []; reasons = Counter()
            for i in range(len(item['values'])):
                r = base.rank(by.get(str(start+dt.timedelta(days=i))))
                ranks.append(round(r['percentile'], 1) if r['available'] else None)
                if not r['available'] and item['values'][i] is not None:
                    reasons[r['reason']] += 1
            sample = base.reference_for(9, 30)
            item['percentile'] = ranks
            item['rank'] = {'ranked_days': sum(x is not None for x in ranks), 'unranked_days_with_values': dict(reasons),
                            'sept_30_reference': {k: sample.get(k) for k in ('available', 'accepted_years', 'days', 'expected_days', 'coverage', 'median', 'reason')}}
        agg = history.aggregate(rows, 'year')
        if agg['available']:
            item['years'] = {k: agg[k] for k in ('input_statistic', 'coverage_threshold', 'missingness', 'rain_note', 'periods')}
        item['continuity'] = {k: cont.get(k) for k in ('first', 'last', 'records', 'numeric', 'unavailable', 'days_with_values', 'day_coverage', 'by_year', 'missing_years',
                                                       'gap_count', 'missing_days_total', 'gaps', 'gap_meaning', 'capacity_eras', 'provenance', 'qualified_records', 'continuity')}
        item['continuity']['gaps'] = (cont.get('gaps') or [])[:8]
        for source_id in cont['source_ids']:
            src = cat['sources'][source_id]
            sources[source_id] = {k: src.get(k) for k in ('url', 'sha256', 'retrieved_at', 'provenance_status', 'bytes')}
        item['source_ids'] = cont['source_ids']
        out.append(item)
    return {'schema_version': SCHEMA, 'station': key, 'name': ' '.join(str(site.get('name') or key).replace('<br />', ' ').split()), 'kind': meta['kind'], 'basin': meta.get('basin'), 'aquifer': site.get('aquifer'),
            'cutoff': cat['cutoff'], 'series': out, 'sources': sources,
            'baseline': {'reference_years': list(history.REFERENCE), 'half_window_days': history.HALF_WINDOW, 'policy': history.FixedBaseline.__doc__.split('Policy. ')[1].strip(),
                         'applies_to': 'daily mean discharge only'},
            'trace': "python3 tools/regional_history.py show '<series id>' <YYYY-MM-DD> prints the stored record with its capture hash and body locator"}


def package(folder=history.OUT, out=ROOT/'app/history'):
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    chosen = json.loads(history.STATIONS.read_text())['stations']
    reader = Reader(folder); cat = reader.catalog; index = {}; network = {}
    captured = set(json.loads((ROOT/'data/captures/twdb-wells/manifest.json').read_text()))
    by_site = {}
    for sid, s in cat['series'].items():
        by_site.setdefault(s['site_key'], []).append(sid)
    keep = set()
    for key, meta in sorted(chosen.items()):
        ids = []
        for quantity, statistic in WANTED[meta['kind']]:
            match = [sid for sid in by_site.get(key, []) if (cat['series'][sid]['quantity'], cat['series'][sid]['statistic']) == (quantity, statistic)
                     and not cat['series'][sid]['original_series_id'].startswith('recent:') and ':current:' not in sid]
            primary = [sid for sid in match if cat['series'][sid]['primary']]
            ids += primary if len(primary) == 1 else match if len(match) == 1 or meta['kind'] == 'well' else []
        doc = station(reader, key, meta, cat['sites'].get(key, {}), ids)
        if not doc['series']:
            index[key] = {'name': doc['name'], 'kind': meta['kind'], 'basin': meta.get('basin'), 'file': None,
                          'reason': 'TWDB lists a full record for this well, but it was never captured, so no history is shown; it is recoverable with one request' if meta['kind'] == 'well' and key[5:] not in captured
                          else 'no usable numeric history in the preserved record, or no unique provider-designated series'}
            continue
        name = slug(key)+'.json'; keep.add(name)
        (out/name).write_text(json.dumps(doc, separators=(',', ':'), allow_nan=False)+'\n')
        index[key] = {'name': doc['name'], 'kind': meta['kind'], 'basin': meta.get('basin'), 'file': 'history/'+name, 'bytes': (out/name).stat().st_size,
                      'series': [{'id': s['id'], 'label': s['label'], 'first': s['continuity']['first'], 'last': s['continuity']['last'],
                                  'days_with_values': s['continuity']['days_with_values'], 'missing_years': len(s['continuity']['missing_years'])} for s in doc['series']]}
        years = set()
        for s in doc['series']:
            years |= set(s['continuity']['by_year'])
        for y in years:
            network.setdefault(meta['kind'], Counter())[y] += 1
    reader.close()
    for p in out.glob('*.json'):
        if p.name not in keep and p.name != 'index.json':
            p.unlink()
    doc = {'schema_version': SCHEMA, 'cutoff': cat['cutoff'], 'normalized_sha256': cat['observations']['sha256'], 'stations': index,
           'stations_reporting_by_year': {k: dict(sorted(v.items())) for k, v in network.items()},
           'network_note': 'Counts of named pilot stations with at least one preserved value in a year. A growing count is a growing network, not a regional trend.'}
    (out/'index.json').write_text(json.dumps(doc, separators=(',', ':'))+'\n')
    total = sum(v.get('bytes', 0) for v in index.values())
    print('History partitions', sum(bool(v['file']) for v in index.values()), 'of', len(index), 'stations;', total, 'bytes; largest', max((v.get('bytes', 0), k) for k, v in index.items()))
    return doc


if __name__ == '__main__':
    package()
