"""Publish dist/water-state.json: the one file a lens reads from this repo.

Everything in the bundle is already on disk as a generated file; this only gathers it under one
schema with one timestamp, so a lens never has to know which tool wrote what. Shape (schema 1):
  schema_version, generated_at, source_repo,
  stations: {id: {name, lat, lon, county, tier, kind, latest: {parameter: {value, unit, observed_at, fresh}},
                  context: {trend, window_peak, seasonal, data_health, narrative}, thresholds: {high, low, unit},
                  source}},
  wells:    {state_well_number: app/groundwater.json record},
  lakes:    {slug: app/reservoirs.json record},
  eaa:      {wells: {...}, rain_gauges: {...}}  (absent when app/eaa.json is missing),
  hydromet: {sites: {'AGENCY:site': app/hydromet.json record}, history_coverage, counts}  (LCRA Hydromet: LCRA, City of Austin and mirrored USGS gauges; absent when app/hydromet.json is missing),
  alerts:   app/hazards-status.json 'alerts' and 'gauges' (NWS notices and flood-stage categories),
  captures: path and sha256 of the day's capture manifest when present.
Absent inputs are recorded under `missing_inputs`; they are never filled in.
"""
import datetime as dt
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'app'; DIST = ROOT / 'dist'; MODEL = ROOT / 'data/model'
SCHEMA_VERSION = 1

def load(path):
    return json.loads(path.read_text()) if path.exists() else None

def build(at=None):
    at = at or dt.datetime.now(dt.timezone.utc); missing = []
    readings = load(APP / 'gauge-readings.json') or {}; context = load(APP / 'hydro-context.json') or {}
    locs = load(ROOT / 'data/usgs-locations-regional.json') or {'locations': []}; gauges = {g['id']: g for g in (load(ROOT / 'data/gauges.json') or [])}
    stations = {}
    for r in locs['locations']:
        sid = r['id']; rd = readings.get('readings', {}).get('USGS-' + sid, [])
        latest = {}
        for x in rd:
            try: age_h = (at - dt.datetime.fromisoformat(x['observed_at'].replace('Z', '+00:00'))).total_seconds() / 3600
            except Exception: age_h = None
            latest[x['parameter']] = {'value': x['value'], 'unit': x['unit'], 'observed_at': x['observed_at'], 'fresh_within_1h': age_h is not None and 0 <= age_h <= 1, 'age_hours': round(age_h, 2) if age_h is not None else None}
        ctx = context.get('stations', {}).get(sid); led = load(MODEL / f'{sid}-event-ledger.json')
        stations[sid] = {'name': r.get('name') or gauges.get(sid, {}).get('name'), 'lat': r['lat'], 'lon': r['lon'], 'county': r.get('county'), 'tier': r.get('tier'), 'kind': r.get('kind'), 'live_parameters': sorted(r.get('live_parameters', {})),
                         'latest': latest, 'context': ctx, 'thresholds': ({'high': led['event_definition']['high_threshold'], 'low': led['event_definition']['low_threshold'], 'unit': led['event_definition']['unit']} if led and led.get('event_definition') else None),
                         'source': f'https://waterdata.usgs.gov/monitoring-location/USGS-{sid}/'}
    for sid, g in gauges.items():  # hand-placed gauges not in the inventory (e.g. the Austin ten before an inventory rebuild)
        if sid not in stations:
            stations[sid] = {'name': g['name'], 'lat': g['lat'], 'lon': g['lon'], 'county': g.get('county'), 'tier': g.get('tier', 'austin'), 'kind': 'stream', 'live_parameters': [], 'latest': {}, 'context': context.get('stations', {}).get(sid), 'thresholds': None, 'source': g.get('source')}
    gw = load(APP / 'groundwater.json'); rv = load(APP / 'reservoirs.json'); ea = load(APP / 'eaa.json'); hz = load(APP / 'hazards-status.json'); hm = load(APP / 'hydromet.json')
    for name, obj in (('groundwater.json', gw), ('reservoirs.json', rv), ('eaa.json', ea), ('hazards-status.json', hz), ('hydromet.json', hm), ('gauge-readings.json', readings or None), ('hydro-context.json', context or None)):
        if obj is None: missing.append(name)
    manifests = sorted(MODEL.glob('austin-current-usgs-capture-manifest*.json'))
    cap = {'path': str(manifests[-1].relative_to(ROOT)), 'sha256': hashlib.sha256(manifests[-1].read_bytes()).hexdigest()} if manifests else None
    bundle = {'schema_version': SCHEMA_VERSION, 'generated_at': at.isoformat(), 'source_repo': 'saulbanov/hill-country-hydro',
              'meaning': 'Measurements and deterministic station context for Central Texas water. A reading describes a station, a well or a lake. Nothing here is a verdict about a place, a person, or safety.',
              'counts': {'stations': len(stations), 'stations_with_fresh_reading': sum(1 for s in stations.values() if any(v['fresh_within_1h'] for v in s['latest'].values())), 'wells': len((gw or {}).get('wells', {})), 'lakes': len((rv or {}).get('lakes', {})), 'eaa_wells': len((ea or {}).get('wells', {})), 'eaa_rain_gauges': len((ea or {}).get('rain_gauges', {})), 'hydromet_sites': len((hm or {}).get('sites', {}))},
              'stations': stations, 'wells': (gw or {}).get('wells', {}), 'wells_meta': {k: v for k, v in (gw or {}).items() if k != 'wells'}, 'lakes': (rv or {}).get('lakes', {}), 'eaa': ({'wells': ea.get('wells', {}), 'rain_gauges': ea.get('rain_gauges', {}), 'critical_period': ea.get('critical_period'), 'generated_at': ea.get('generated_at')} if ea else None),
              'hydromet': ({'generated_at': hm.get('generated_at'), 'source': hm.get('source'), 'meaning': hm.get('meaning'), 'capture': hm.get('capture'), 'sites': hm.get('sites', {}), 'history_coverage': hm.get('history_coverage', {}), 'counts': hm.get('counts')} if hm else None),
              'alerts': ({'generated_at': hz.get('generated_at'), 'alerts': hz.get('alerts', []), 'gauges': hz.get('gauges', []), 'coverage': hz.get('coverage')} if hz else None), 'captures': cap, 'missing_inputs': missing}
    storm = load(APP / 'storm-delta.json')
    if storm is not None: bundle['storm_delta'] = storm
    return bundle

def main():
    DIST.mkdir(exist_ok=True); b = build(); (DIST / 'water-state.json').write_text(json.dumps(b, indent=1) + '\n')
    print(f"water-state.json: {b['counts']}; missing inputs: {b['missing_inputs']}")

if __name__ == '__main__': main()
