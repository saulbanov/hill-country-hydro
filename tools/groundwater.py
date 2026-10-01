"""Regional aquifer wells from the Texas Water Development Board (raw first, context only).

Source: Water Data for Texas, https://waterdatafortexas.org/groundwater
  recent-conditions.json  one row per reporting well: state_well_number, date, daily high water level
                          (ft below land surface). One request covers the state; filtered to the
                          region by data/wells-regional.json.
  wells.geojson           the well index (aquifer, county, entity, status, coordinates).
  well/<id>.json          the full record of one well (up to 46 MB); kept only for index wells.
Commands:
  collect    fetch recent-conditions.json and wells.geojson, save raw under data/raw/twdb/daily/.
  history    fetch the full record for each index well (or --wells ...), raw under data/raw/twdb/history/,
             gzip copy under data/captures/twdb-wells/ with a checksum manifest.
  normalize  every daily feed capture and every history file -> sqlite table well_levels
             (well, date, level_ft_bls, source_file). Missing values are never zero.
  assess     app/groundwater.json: per region well the latest level, change over 7 and 30 days,
             the 13-month percentile where the record allows, and the data health. No color,
             no rule: a well level is context for springs and creeks, never a swim verdict.
Levels are feet below land surface: a larger number is a lower water table.
"""
import argparse
import datetime as dt
import gzip
import hashlib
import json
import sqlite3
import statistics
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data/raw/twdb'
CAP = ROOT / 'data/captures/twdb-wells'
NORM = ROOT / 'data/normalized'
DB = NORM / 'water.sqlite'
APP = ROOT / 'app'
WELLS = ROOT / 'data/wells-regional.json'
UA = 'austin-swim-map/0.1 (saul.elbein@gmail.com)'
RECENT = 'https://waterdatafortexas.org/groundwater/recent-conditions.json'
INDEX_URL = 'https://waterdatafortexas.org/groundwater/wells.geojson'
WELL_URL = 'https://waterdatafortexas.org/groundwater/well/{wid}.json'
LEVEL_KEYS = ('daily_high_water_level(ft below land surface)', 'water_level(ft below land surface)')

def now_utc(): return dt.datetime.now(dt.timezone.utc)

def fetch(url, dest_dir, stem):
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=300) as r: body, status = r.read(), r.status
    except urllib.error.HTTPError as e: body, status = e.read() or b'', e.code
    t = now_utc(); dest_dir.mkdir(parents=True, exist_ok=True); name = f"{t.strftime('%Y%m%dT%H%M%S%fZ')}-{stem}"
    ext = '.geojson' if url.endswith('.geojson') else '.json'
    (dest_dir / (name + ext)).write_bytes(body)
    meta = {'url': url, 'retrieved_at': t.isoformat(), 'status': status, 'sha256': hashlib.sha256(body).hexdigest(), 'bytes': len(body), 'source': 'Texas Water Development Board, Water Data for Texas', 'interpretation': 'none; this is a verbatim source capture'}
    (dest_dir / (name + '.meta.json')).write_text(json.dumps(meta, indent=2) + '\n')
    return dest_dir / (name + ext), meta

def collect():
    p, m = fetch(RECENT, RAW / 'daily', 'recent-conditions'); print(f"recent-conditions: HTTP {m['status']}, {m['bytes']} bytes -> {p.relative_to(ROOT)}")
    p, m = fetch(INDEX_URL, RAW / 'daily', 'wells'); print(f"wells.geojson: HTTP {m['status']}, {m['bytes']} bytes -> {p.relative_to(ROOT)}")

def history(wells, pause):
    CAP.mkdir(parents=True, exist_ok=True); manifest_path = CAP / 'manifest.json'
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    for wid in wells:
        p, m = fetch(WELL_URL.format(wid=wid), RAW / 'history' / wid, 'well')
        if m['status'] != 200: print(f'{wid}: HTTP {m["status"]}, kept raw, not versioned'); continue
        gz = CAP / f"{p.stem}-{wid}.json.gz"
        with gzip.open(gz, 'wb', compresslevel=9) as z: z.write(p.read_bytes())
        manifest[wid] = {'raw_path': str(p.relative_to(ROOT)), 'capture_path': str(gz.relative_to(ROOT)), 'sha256': m['sha256'], 'bytes': m['bytes'], 'retrieved_at': m['retrieved_at'], 'url': m['url']}
        print(f"{wid}: {m['bytes']} bytes raw, {gz.stat().st_size} gz"); time.sleep(pause)
    manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')

def level_of(row):
    for k in LEVEL_KEYS:
        if row.get(k) is not None: return float(row[k]), k
    return None, None

def normalize():
    NORM.mkdir(parents=True, exist_ok=True); db = sqlite3.connect(DB)
    db.execute('create table if not exists well_levels(well text, date text, level_ft_bls real, measure text, status text, source text, source_file text, retrieved_at text, primary key(well, date, source_file))')
    region = {w['id'] for w in json.loads(WELLS.read_text())['wells']} if WELLS.exists() else None
    n = 0
    for meta_path in sorted((RAW / 'daily').glob('*-recent-conditions.meta.json')) if (RAW / 'daily').exists() else []:
        meta = json.loads(meta_path.read_text()); body = meta_path.with_name(meta_path.name.replace('.meta.json', '.json'))
        if meta.get('status') != 200: continue
        for row in json.loads(body.read_text()).get('values', []):
            wid = row.get('state_well_number')
            if region is not None and wid not in region: continue
            level, key = level_of(row)
            if level is None: continue
            db.execute('insert or replace into well_levels values(?,?,?,?,?,?,?,?)', (wid, row['date'], level, key, None, 'recent-conditions', str(body.relative_to(ROOT)), meta['retrieved_at'])); n += 1
    for meta_path in sorted((RAW / 'history').rglob('*-well.meta.json')) if (RAW / 'history').exists() else []:
        meta = json.loads(meta_path.read_text()); body = meta_path.with_name(meta_path.name.replace('.meta.json', '.json')); wid = meta_path.parent.name
        if meta.get('status') != 200: continue
        daily = {}
        for row in json.loads(body.read_text()).get('values', []):
            level, key = level_of(row)
            if level is None: continue
            d = row['datetime'][:10]; daily.setdefault(d, []).append((level, key, row.get('status'), row.get('source')))
        for d, vals in daily.items():
            level = max(v[0] for v in vals) if 'daily_high' in (vals[0][1] or '') else round(statistics.mean(v[0] for v in vals), 3)
            db.execute('insert or replace into well_levels values(?,?,?,?,?,?,?,?)', (wid, d, level, vals[0][1], vals[0][2], vals[0][3] or 'history', str(body.relative_to(ROOT)), meta['retrieved_at'])); n += 1
    db.commit(); db.close(); print(f'well_levels: {n} rows written')

def percentile_rank(values, x):
    below = sum(1 for v in values if v < x); ties = sum(1 for v in values if v == x)
    return round(100.0 * (below + 0.5 * ties) / len(values), 1) if values else None

def assess(at=None):
    at = at or now_utc(); wells = json.loads(WELLS.read_text())['wells']; db = sqlite3.connect(DB) if DB.exists() else None
    out = {}
    for w in wells:
        rows = db.execute('select date, level_ft_bls from well_levels where well=? order by date', (w['id'],)).fetchall() if db else []
        series = {}
        for d, v in rows: series[d] = v  # history and feed overlap; the later insert wins per source_file, so keep last
        dates = sorted(series)
        rec = {'name': w['id'], 'aquifer': w['aquifer'], 'aquifer_type': w['aquifer_type'], 'county': w['county'], 'entity': w['entity'], 'lat': w['lat'], 'lon': w['lon'], 'index': w['index'], 'source': w['source'], 'unit': 'ft below land surface', 'meaning': 'A larger number is a lower water table. Context for springs and creeks; not a swim verdict.'}
        if not dates:
            rec.update({'data_health': 'no level on file', 'latest': None}); out[w['id']] = rec; continue
        last = dates[-1]; lv = series[last]; age = (at.date() - dt.date.fromisoformat(last)).days
        def back(days):
            target = (dt.date.fromisoformat(last) - dt.timedelta(days=days)).isoformat(); prior = [d for d in dates if d <= target]
            return round(lv - series[prior[-1]], 2) if prior else None
        yr = [series[d] for d in dates if d >= (dt.date.fromisoformat(last) - dt.timedelta(days=395)).isoformat()]
        rec.update({'latest': {'date': last, 'level_ft_bls': lv}, 'age_days': age, 'data_health': 'fresh' if age <= 2 else f'stale ({age} d)', 'change_7d_ft': back(7), 'change_30d_ft': back(30),
                    'direction': None, 'record_days_on_file': len(dates), 'first_date_on_file': dates[0],
                    'percentile_13mo': percentile_rank(yr, lv) if len(yr) >= 200 else None, 'percentile_note': None if len(yr) >= 200 else f'only {len(yr)} days on file in the last 13 months; percentile withheld'})
        c7 = rec['change_7d_ft']; rec['direction'] = None if c7 is None else ('falling (water table dropping)' if c7 > 0.05 else 'rising (water table coming up)' if c7 < -0.05 else 'steady')
        out[w['id']] = rec
    if db: db.close()
    payload = {'generated_at': at.isoformat(), 'source': RECENT, 'meaning': 'TWDB well levels for the region, read verbatim and summarized deterministically. Feet below land surface; falling means the number grew. Percentiles need at least 200 days on file, so most wells show one only after their full record is kept or the daily feed has run long enough.', 'counts': {'wells': len(out), 'fresh': sum(1 for r in out.values() if r.get('data_health') == 'fresh'), 'with_percentile': sum(1 for r in out.values() if r.get('percentile_13mo') is not None)}, 'wells': out}
    (APP / 'groundwater.json').write_text(json.dumps(payload, indent=2) + '\n')
    print(f"groundwater: {payload['counts']}")
    for wid in ('6837203', '5850301'):
        r = out.get(wid)
        if r and r.get('latest'): print(f"  {wid} {r['aquifer']} {r['county']}: {r['latest']['level_ft_bls']} ft bls on {r['latest']['date']}, 7d {r['change_7d_ft']}, 30d {r['change_30d_ft']}, pct13mo {r['percentile_13mo']}")

if __name__ == '__main__':
    p = argparse.ArgumentParser(); sub = p.add_subparsers(dest='cmd', required=True)
    sub.add_parser('collect'); h = sub.add_parser('history'); h.add_argument('--wells', nargs='*'); h.add_argument('--pause-seconds', type=float, default=1.0)
    sub.add_parser('normalize'); a2 = sub.add_parser('assess'); a2.add_argument('--at')
    a = p.parse_args()
    if a.cmd == 'collect': collect()
    elif a.cmd == 'history': history(a.wells or [w['id'] for w in json.loads(WELLS.read_text())['wells'] if w['index']], a.pause_seconds)
    elif a.cmd == 'normalize': normalize()
    else: assess(dt.datetime.fromisoformat(a.at.replace('Z', '+00:00')) if a.at else None)
