"""Regional station and well inventory, built only from preserved source captures.

Inputs (verbatim captures under data/raw/documentary/usgs-regional-inventory-<date>/):
  USGS time-series-metadata for parameter 00060 (instantaneous discharge) in the region bbox,
  USGS monitoring-locations (site type Stream) in the same bbox,
  TWDB wells.geojson (well index) and recent-conditions.json (one daily row per reporting well).
Outputs:
  data/stations-regional.json  every USGS station with a discharge series still reporting, with its
                               tier: 'austin' (Travis, Williamson), 'regional-key' (hand-listed
                               rivers and springs the map's places sit on), or 'regional-other'.
  data/wells-regional.json     every TWDB well inside the bbox, with aquifer, county, entity, and
                               whether it has a row in the daily feed; 'index' marks wells whose full
                               record is kept (see tools/groundwater.py history).
Nothing here is a swim judgment. The bbox is -100.2,29.3 to -97.2,30.9 (Junction to Bastrop,
Uvalde to Georgetown); a station outside it is simply not listed.
"""
import argparse
import datetime as dt
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BBOX = (-100.2, 29.3, -97.2, 30.9)
AUSTIN_COUNTIES = {'Travis County', 'Williamson County'}
REGIONAL_KEY = {  # station -> why it is tier 1 (full daily history, ledger, context)
    '08153500': 'Pedernales near Johnson City (Pedernales Falls)', '08152900': 'Pedernales near Fredericksburg',
    '08171000': 'Blanco at Wimberley (Blue Hole Wimberley)', '08171300': 'Blanco near Kyle', '08171290': 'Blanco at Halifax Ranch',
    '08171350': 'Blanco at San Marcos', '08170950': 'Blanco at Fischer Store Rd', '08170890': 'Little Blanco at FM 32',
    '08170990': "Jacob's Well Spring", '08170500': 'San Marcos River at San Marcos', '08171400': 'San Marcos near Martindale',
    '08169000': 'Comal River at New Braunfels', '08168500': 'Guadalupe above Comal (New Braunfels)', '08167800': 'Guadalupe at Sattler',
    '08167500': 'Guadalupe near Spring Branch (Guadalupe River SP)', '08167000': 'Guadalupe at Comfort', '08166200': 'Guadalupe at Kerrville',
    '08165500': 'Guadalupe at Hunt', '08151500': 'Llano at Llano', '08150000': 'Llano near Junction', '08149900': 'South Llano at Junction (South Llano SP)',
    '08195000': 'Frio at Concan (Garner SP)', '08190000': 'Nueces at Laguna', '08198000': 'Sabinal near Sabinal', '08178880': 'Medina at Bandera',
    '08104900': 'South Fork San Gabriel at Georgetown (Blue Hole Georgetown)', '08158700': 'Onion Creek near Driftwood', '08183900': 'Cibolo near Boerne',
    '08152000': 'Sandy Creek near Kingsland (Inks Lake side)', '08155500': 'Barton Springs (already collected)', '08168000': 'Hueco Springs near New Braunfels (spring)',
}
INDEX_WELL_RULE = "Edwards (Balcones Fault Zone) wells in the bbox, plus Trinity wells in Hays, Travis, Blanco and Comal counties, when the full record is at most 20 MB; J-17 (6837203) and Lovelady (5850301) always"

def inb(c): return BBOX[0] <= c[0] <= BBOX[2] and BBOX[1] <= c[1] <= BBOX[3]

def newest(folder, stem):
    files = sorted(folder.glob(f'*-{stem}.*'))
    files = [f for f in files if not f.name.endswith('.meta.json')]
    if not files: raise SystemExit(f'no {stem} capture under {folder}')
    return files[-1]

def build(folder, active_since, sizes=None):
    tsm = json.loads(newest(folder, 'tsm-region-00060').read_text())['features']
    ml = {'USGS-' + f['properties']['monitoring_location_number']: f for f in json.loads(newest(folder, 'ml-region').read_text())['features']}
    stations = {}
    for f in tsm:
        p = f['properties']; end = p.get('end') or ''
        if end < active_since: continue
        sid = p['monitoring_location_id'][5:]; m = ml.get(p['monitoring_location_id'], {}).get('properties', {})
        lon, lat = f['geometry']['coordinates']
        tier = 'austin' if m.get('county_name') in AUSTIN_COUNTIES else 'regional-key' if sid in REGIONAL_KEY else 'regional-other'
        rec = stations.get(sid) or {'id': sid, 'name': m.get('monitoring_location_name'), 'county': m.get('county_name'), 'lat': lat, 'lon': lon,
                                    'drainage_area_sqmi': m.get('drainage_area'), 'tier': tier, 'why': REGIONAL_KEY.get(sid), 'discharge_series_end': end,
                                    'source': f'https://waterdata.usgs.gov/monitoring-location/USGS-{sid}/'}
        rec['discharge_series_end'] = max(rec['discharge_series_end'], end); stations[sid] = rec
    wells_raw = json.loads(newest(folder, 'twdb-wells').read_text())['features']
    recent = {r['state_well_number']: r for r in json.loads(newest(folder, 'twdb-recent').read_text())['values']}
    wells = []
    for f in wells_raw:
        if not inb(f['geometry']['coordinates']): continue
        p = f['properties']; wid = p['well_number']; lon, lat = f['geometry']['coordinates']
        size = (sizes or {}).get(wid)
        index = wid in ('6837203', '5850301') or ((p.get('aquifer') == 'Edwards (Balcones Fault Zone)' or (p.get('aquifer') == 'Trinity' and p.get('county') in ('Hays', 'Travis', 'Blanco', 'Comal'))) and (size is None or size <= 20_000_000))
        wells.append({'id': wid, 'aquifer': p.get('aquifer'), 'aquifer_type': p.get('aquifer_type'), 'county': p.get('county'), 'entity': p.get('entity'), 'status': p.get('status'),
                      'lat': lat, 'lon': lon, 'in_daily_feed': wid in recent, 'latest_feed_date': recent.get(wid, {}).get('date'), 'full_record_bytes': size, 'index': index,
                      'source': f'https://waterdatafortexas.org/groundwater/well/{wid}'})
    return stations, wells

def station_name(sid, fallback):
    """Prefer the USGS location capture saved by usgs_history.py (springs are not in the stream list)."""
    locs = sorted((ROOT / 'data/raw/usgs-daily' / sid).glob('*-location.json')) if (ROOT / 'data/raw/usgs-daily' / sid).exists() else []
    for loc in reversed(locs):
        try:
            feats = json.loads(loc.read_text()).get('features', [])
            if feats and feats[0]['properties'].get('monitoring_location_name'): return feats[0]['properties']['monitoring_location_name'], feats[0]['properties'].get('county_name')
        except Exception: continue
    return fallback, None

def sync_gauges():
    """Add every history-tier station to data/gauges.json as a context marker; never touch existing entries."""
    inv = json.loads((ROOT / 'data/stations-regional.json').read_text())['stations']
    gpath = ROOT / 'data/gauges.json'; gauges = json.loads(gpath.read_text()); have = {g['id'] for g in gauges}; added = 0
    for s in inv:
        if s['tier'] == 'regional-other' or s['id'] in have: continue
        name, county = station_name(s['id'], s['name'] or f"USGS {s['id']}")
        gauges.append({'id': s['id'], 'name': name, 'lat': s['lat'], 'lon': s['lon'], 'waterbody': None, 'parameter': 'discharge (00060)', 'unit': 'ft3/s', 'source': s['source'],
                       'county': county or s['county'], 'tier': s['tier'], 'link_status': f"regional context added 2026-10-01 ({s['tier']}{': ' + s['why'] if s.get('why') else ''}); no place rule"})
        added += 1
    gpath.write_text(json.dumps(gauges, indent=2, ensure_ascii=False) + '\n'); print(f'gauges.json: {added} added, {len(gauges)} total')

DAILY_WANTED = {  # (parameter, statistic) -> csv label; which non-discharge daily series to keep as history
    ('00065', '00003'): 'stage-daily-mean', ('62615', '00003'): 'lake-elevation-navd88-daily-mean', ('62614', '00003'): 'lake-elevation-ngvd29-daily-mean',
    ('00045', '00006'): 'precipitation-daily-total', ('72019', '00008'): 'well-depth-daily-median', ('72019', '00003'): 'well-depth-daily-mean', ('00010', '00003'): 'water-temperature-daily-mean',
}

def build_all_locations(folder, active_since):
    """Every USGS location in the bbox with any live instantaneous series, with its site type and live parameters, plus the daily series worth keeping."""
    tsm_all = json.loads(newest(folder, 'tsm-region-all').read_text())['features']
    tsm_daily = json.loads(newest(folder, 'tsm-region-daily').read_text())['features']
    names = {}
    for stem in ('ml-region', 'ml-region-gw', 'ml-region-sp', 'ml-region-lk'):
        try:
            for f in json.loads(newest(folder, stem).read_text())['features']:
                p = f['properties']; names['USGS-' + p['monitoring_location_number']] = {'name': p.get('monitoring_location_name'), 'county': p.get('county_name'), 'site_type': p.get('site_type')}
        except SystemExit: continue
    locs = {}
    for f in tsm_all:
        p = f['properties']
        if (p.get('end') or '') < active_since: continue
        lid = p['monitoring_location_id']; lon, lat = f['geometry']['coordinates']
        rec = locs.setdefault(lid, {'id': lid[5:], 'lat': lat, 'lon': lon, 'live_parameters': {}, 'daily_series': [], **names.get(lid, {'name': None, 'county': None, 'site_type': None})})
        rec['live_parameters'][p['parameter_code']] = {'name': p.get('parameter_name'), 'unit': p.get('unit_of_measure'), 'end': p.get('end')}
    for f in tsm_daily:
        p = f['properties']; lid = p['monitoring_location_id']
        if lid in locs and (p.get('parameter_code'), p.get('statistic_id')) in DAILY_WANTED and (p.get('end') or '') >= active_since:
            locs[lid]['daily_series'].append({'parameter_code': p['parameter_code'], 'statistic_id': p['statistic_id'], 'label': DAILY_WANTED[(p['parameter_code'], p['statistic_id'])], 'begin': p.get('begin'), 'end': p.get('end')})
    return locs

def write_all_locations(folder, since):
    locs = build_all_locations(folder, since)
    disch = json.loads((ROOT / 'data/stations-regional.json').read_text())['stations'] if (ROOT / 'data/stations-regional.json').exists() else []
    tiers = {s['id']: s['tier'] for s in disch}
    out = []
    for lid, r in locs.items():
        r['tier'] = tiers.get(r['id'], 'usgs-other'); r['has_discharge'] = '00060' in r['live_parameters']
        r['kind'] = 'stream' if r['site_type'] == 'Stream' else 'well' if r['site_type'] == 'Well' else 'lake' if r['site_type'] in ('Lake, Reservoir, Impoundment',) else 'spring' if r['site_type'] == 'Spring' else (r['site_type'] or 'unknown')
        out.append(r)
    counts = {}
    for r in out: counts[r['tier']] = counts.get(r['tier'], 0) + 1
    plan = [{'id': r['id'], 'name': r['name'], 'series': r['daily_series']} for r in out if r['daily_series'] and r['tier'] != 'regional-other']
    (ROOT / 'data/usgs-locations-regional.json').write_text(json.dumps({'generated_at': dt.datetime.now(dt.timezone.utc).isoformat(), 'built_from': str(folder.relative_to(ROOT)), 'bbox': BBOX, 'active_rule': f'any instantaneous series ending on or after {since}',
        'meaning': 'Every live USGS location in the region: streams with and without discharge, springs, wells, lakes. Tier usgs-other = current readings daily only. daily_series lists the non-discharge daily statistics worth keeping as history (tools/usgs_series_history.py).',
        'counts': counts, 'kinds': {k: sum(1 for r in out if r['kind'] == k) for k in sorted({r['kind'] for r in out})}, 'locations': sorted(out, key=lambda r: (r['tier'], r['kind'], r['id']))}, indent=2) + '\n')
    (ROOT / 'data/usgs-history-plan.json').write_text(json.dumps({'generated_at': dt.datetime.now(dt.timezone.utc).isoformat(), 'rule': 'non-discharge daily series for every location except tier regional-other; discharge daily means are handled by tools/usgs_history.py', 'count_locations': len(plan), 'count_series': sum(len(p['series']) for p in plan), 'plan': plan}, indent=2) + '\n')
    kinds = {k: sum(1 for r in out if r['kind'] == k) for k in sorted({r['kind'] for r in out})}
    print(f"locations: {counts}; kinds: {kinds}; history plan: {len(plan)} locations, {sum(len(p['series']) for p in plan)} series")

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--folder', default=None); ap.add_argument('--active-since', default=None); ap.add_argument('--sizes', default=None); ap.add_argument('--sync-gauges', action='store_true'); ap.add_argument('--all-locations', action='store_true')
    a = ap.parse_args()
    if a.sync_gauges: return sync_gauges()
    if a.all_locations:
        folder = Path(a.folder) if a.folder else sorted((ROOT / 'data/raw/documentary').glob('usgs-regional-inventory-*'))[-1]
        return write_all_locations(folder, a.active_since or (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=7)).strftime('%Y-%m-%d'))
    folder = Path(a.folder) if a.folder else sorted((ROOT / 'data/raw/documentary').glob('usgs-regional-inventory-*'))[-1]
    since = a.active_since or (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=7)).strftime('%Y-%m-%d')
    sizes = {k: int(v[1]) for k, v in json.loads(Path(a.sizes).read_text()).items() if v[0] == 200 and v[1]} if a.sizes else None
    stations, wells = build(folder, since, sizes)
    tiers = {}
    for s in stations.values(): tiers[s['tier']] = tiers.get(s['tier'], 0) + 1
    (ROOT / 'data/stations-regional.json').write_text(json.dumps({'generated_at': dt.datetime.now(dt.timezone.utc).isoformat(), 'built_from': str(folder.relative_to(ROOT)), 'bbox': BBOX,
        'active_rule': f'discharge series end on or after {since}', 'tiers': {'austin': 'Travis and Williamson counties: current readings daily, full daily history, ledger, context', 'regional-key': 'hand-listed rivers and springs under the map places: same treatment', 'regional-other': 'current readings daily only; no history, no ledger'},
        'counts': tiers, 'stations': sorted(stations.values(), key=lambda s: (s['tier'], s['county'] or '', s['id']))}, indent=2) + '\n')
    (ROOT / 'data/wells-regional.json').write_text(json.dumps({'generated_at': dt.datetime.now(dt.timezone.utc).isoformat(), 'built_from': str(folder.relative_to(ROOT)), 'bbox': BBOX,
        'index_rule': INDEX_WELL_RULE, 'counts': {'wells': len(wells), 'in_daily_feed': sum(w['in_daily_feed'] for w in wells), 'index': sum(w['index'] for w in wells)},
        'wells': sorted(wells, key=lambda w: (w['aquifer'] or '', w['county'] or '', w['id']))}, indent=2) + '\n')
    print(f"stations: {tiers}; wells: {len(wells)} ({sum(w['index'] for w in wells)} index)")

if __name__ == '__main__': main()
