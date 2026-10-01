"""Lake levels for the region from the Texas Water Development Board (raw first, context only).

Source: https://waterdatafortexas.org/reservoirs/individual/<slug>  (TWDB relays LCRA, USACE, GBRA and
BMA data). Each lake offers <slug>.csv (full record), <slug>-1year.csv, <slug>-30day.csv. Columns:
date, water_level (ft above msl), surface_area (acres), reservoir_storage (acre-ft),
conservation_storage, percent_full, conservation_capacity, dead_pool_capacity. Lines starting with #
are the provider's disclaimer and are kept verbatim in the raw file.
  collect    <slug>-30day.csv for every lake in LAKES -> data/raw/twdb-reservoirs/daily/
  history    <slug>.csv (full record) -> data/raw/twdb-reservoirs/history/, gzip under data/captures/twdb-reservoirs/
  normalize  all captures -> sqlite table reservoir_levels (lake, date, elevation_ft, percent_full, storage_af, ...)
  assess     app/reservoirs.json: latest elevation and percent full, 7- and 30-day change, 13-month percentile. No color.
A lake level is operator-managed storage, not a swimming condition; it is context for Lake Austin and
Lake Travis places and for the rivers below the dams.
"""
import argparse, csv, datetime as dt, gzip, hashlib, io, json, sqlite3, time, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data/raw/twdb-reservoirs'; CAP = ROOT / 'data/captures/twdb-reservoirs'; DB = ROOT / 'data/normalized/water.sqlite'; APP = ROOT / 'app'
UA = 'austin-swim-map/0.1 (saul.elbein@gmail.com)'
BASE = 'https://waterdatafortexas.org/reservoirs/individual/'
LAKES = {'austin': 'Lake Austin', 'travis': 'Lake Travis', 'buchanan': 'Lake Buchanan', 'inks': 'Inks Lake', 'lyndon-b-johnson': 'Lake LBJ', 'marble-falls': 'Lake Marble Falls',
         'canyon': 'Canyon Lake', 'medina': 'Medina Lake', 'georgetown': 'Lake Georgetown', 'granger': 'Granger Lake'}
COLS = ['date', 'water_level', 'surface_area', 'reservoir_storage', 'conservation_storage', 'percent_full', 'conservation_capacity', 'dead_pool_capacity']

def now_utc(): return dt.datetime.now(dt.timezone.utc)

def fetch(url, dest_dir, stem):
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    try:
        with urllib.request.urlopen(req, timeout=120) as r: body, status = r.read(), r.status
    except urllib.error.HTTPError as e: body, status = e.read() or b'', e.code
    t = now_utc(); dest_dir.mkdir(parents=True, exist_ok=True); name = f"{t.strftime('%Y%m%dT%H%M%S%fZ')}-{stem}"
    (dest_dir / (name + '.csv')).write_bytes(body)
    meta = {'url': url, 'retrieved_at': t.isoformat(), 'status': status, 'sha256': hashlib.sha256(body).hexdigest(), 'bytes': len(body), 'source': 'Texas Water Development Board, Water Data for Texas (relaying LCRA/USACE/GBRA/BMA)', 'interpretation': 'none; verbatim source capture'}
    (dest_dir / (name + '.meta.json')).write_text(json.dumps(meta, indent=2) + '\n')
    return dest_dir / (name + '.csv'), meta

def collect(pause=0.5):
    for slug in LAKES:
        p, m = fetch(BASE + f'{slug}-30day.csv', RAW / 'daily', slug); print(f"{slug}: HTTP {m['status']}, {m['bytes']} bytes"); time.sleep(pause)

def history(pause=1.0):
    CAP.mkdir(parents=True, exist_ok=True); man_path = CAP / 'manifest.json'; man = json.loads(man_path.read_text()) if man_path.exists() else {}
    for slug in LAKES:
        p, m = fetch(BASE + f'{slug}.csv', RAW / 'history', slug)
        if m['status'] != 200: print(f'{slug}: HTTP {m["status"]}, not versioned'); continue
        gz = CAP / f'{p.stem}.csv.gz'
        with gzip.open(gz, 'wb', compresslevel=9) as z: z.write(p.read_bytes())
        for old in CAP.glob(f'*-{slug}.csv.gz'):
            if old != gz: old.unlink()
        man[slug] = {'raw_path': str(p.relative_to(ROOT)), 'capture_path': str(gz.relative_to(ROOT)), 'sha256': m['sha256'], 'bytes': m['bytes'], 'retrieved_at': m['retrieved_at'], 'url': m['url']}
        print(f"{slug}: {m['bytes']} bytes, {gz.stat().st_size} gz"); time.sleep(pause)
    man_path.write_text(json.dumps(man, indent=2) + '\n')

def parse_rows(text):
    rows = []
    for line in text.splitlines():
        if not line or line.startswith('#'): continue
        parts = line.split(',')
        if parts[0] == 'date' or len(parts) < 2: continue
        rec = dict(zip(COLS, parts + [''] * (len(COLS) - len(parts))))
        def num(x):
            try: return float(x) if x not in ('', 'NA', 'nan') else None
            except ValueError: return None
        rows.append({'date': rec['date'], 'elevation_ft': num(rec['water_level']), 'percent_full': num(rec['percent_full']), 'storage_af': num(rec['reservoir_storage']), 'conservation_storage_af': num(rec['conservation_storage']), 'surface_area_ac': num(rec['surface_area'])})
    return rows

def normalize():
    DB.parent.mkdir(parents=True, exist_ok=True); db = sqlite3.connect(DB)
    db.execute('create table if not exists reservoir_levels(lake text, date text, elevation_ft real, percent_full real, storage_af real, conservation_storage_af real, surface_area_ac real, source_file text, retrieved_at text, primary key(lake, date, source_file))')
    n = 0
    for sub in ('history', 'daily'):
        for meta_path in sorted((RAW / sub).glob('*.meta.json')) if (RAW / sub).exists() else []:
            meta = json.loads(meta_path.read_text()); body = meta_path.with_suffix('').with_suffix('.csv')
            if meta.get('status') != 200: continue
            slug = body.name.split('-', 1)[1][:-4]
            for r in parse_rows(body.read_text(errors='replace')):
                if r['elevation_ft'] is None and r['percent_full'] is None: continue
                db.execute('insert or replace into reservoir_levels values(?,?,?,?,?,?,?,?,?)', (slug, r['date'], r['elevation_ft'], r['percent_full'], r['storage_af'], r['conservation_storage_af'], r['surface_area_ac'], str(body.relative_to(ROOT)), meta['retrieved_at'])); n += 1
    db.commit(); db.close(); print(f'reservoir_levels: {n} rows written')

def percentile_rank(values, x):
    below = sum(1 for v in values if v < x); ties = sum(1 for v in values if v == x)
    return round(100.0 * (below + 0.5 * ties) / len(values), 1) if values else None

def assess(at=None):
    at = at or now_utc(); db = sqlite3.connect(DB) if DB.exists() else None; out = {}
    for slug, name in LAKES.items():
        rows = db.execute('select date, elevation_ft, percent_full from reservoir_levels where lake=? order by date, retrieved_at', (slug,)).fetchall() if db else []
        series = {}
        for d, e, pf in rows: series[d] = (e, pf)
        dates = sorted(series); rec = {'name': name, 'slug': slug, 'source': BASE + slug, 'unit': 'ft above mean sea level; percent of conservation capacity', 'meaning': 'Managed reservoir storage relayed by TWDB. Context for lake places and the river below the dam; not a swimming verdict.'}
        if not dates: rec.update({'latest': None, 'data_health': 'no level on file'}); out[slug] = rec; continue
        last = dates[-1]; e, pf = series[last]; age = (at.date() - dt.date.fromisoformat(last)).days
        def back(days):
            target = (dt.date.fromisoformat(last) - dt.timedelta(days=days)).isoformat(); prior = [d for d in dates if d <= target]
            return round(e - series[prior[-1]][0], 2) if prior and e is not None and series[prior[-1]][0] is not None else None
        yr = [series[d][0] for d in dates if d >= (dt.date.fromisoformat(last) - dt.timedelta(days=395)).isoformat() and series[d][0] is not None]
        rec.update({'latest': {'date': last, 'elevation_ft': e, 'percent_full': pf}, 'age_days': age, 'data_health': 'fresh' if age <= 2 else f'stale ({age} d)', 'change_7d_ft': back(7), 'change_30d_ft': back(30), 'percentile_13mo': percentile_rank(yr, e) if len(yr) >= 200 and e is not None else None, 'record_days_on_file': len(dates), 'first_date_on_file': dates[0]})
        out[slug] = rec
    if db: db.close()
    (APP / 'reservoirs.json').write_text(json.dumps({'generated_at': at.isoformat(), 'source': 'https://waterdatafortexas.org/reservoirs/statewide', 'meaning': 'TWDB lake levels, read verbatim and summarized deterministically; context only.', 'lakes': out}, indent=2) + '\n')
    for slug, r in out.items():
        if r.get('latest'): print(f"{r['name']}: {r['latest']['elevation_ft']} ft, {r['latest']['percent_full']}% full on {r['latest']['date']}, 7d {r['change_7d_ft']}, 30d {r['change_30d_ft']}, pct13mo {r['percentile_13mo']}")

if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('cmd', choices=['collect', 'history', 'normalize', 'assess']); a = p.parse_args()
    {'collect': collect, 'history': history, 'normalize': normalize, 'assess': assess}[a.cmd]()
