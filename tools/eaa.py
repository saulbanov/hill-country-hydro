"""Edwards Aquifer Authority monitoring data (raw first, context only).

Source: https://data.edwardsaquifer.org/ . There is no JSON API; each list page embeds its site table
as a script variable, and each site offers CSV downloads per sensor:
  /GroundWater         allWellsLocationsJSON        /GroundWater/DownloadGroundwaterCsv?siteId=..&sensorName=DHE|DTW|WLE
  /SpringsAndStreams   springsStreamsLocationsJSON  /SpringsAndStreams/DownloadSpringAndStreamCsv?siteId=..&sensorName=GAGHT
  /RainGauges          rainGaugesLocationsJSON      /RainGauges/DownloadRainGaugesCsv?siteId=..&sensorName=DLRAIN|HRRAIN
CSV rows: siteId, date, value, status flag (A approved, P provisional, Q questionable ...), last-modified.
Commands:
  collect [--streams]   the three list pages (raw, then parsed to data/eaa-sites.json) and the DHE and DTW
                        CSVs for every active well and the DLRAIN CSV for every active rain gauge; --streams
                        adds GAGHT for active streams (large hourly files; weekly is enough).
  normalize             captures -> sqlite tables eaa_well_levels (site, date, dhe_ft_amsl, dtw_ft_bls, status),
                        eaa_rain_daily (site, date, inches, status), eaa_stream_stage (site, datetime, ft, status).
  assess                app/eaa.json: wells (latest elevation, 7/30-day change, 13-month percentile), rain gauges
                        (last 1, 3, 7, 30 days in inches), both with data health. No color, no rule.
Every CSV is the full record, so each day's capture supersedes the last; the versioned copy under
data/captures/eaa/ keeps only the newest per site and sensor.
"""
import argparse, datetime as dt, gzip, hashlib, json, re, sqlite3, time, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data/raw/eaa'; CAP = ROOT / 'data/captures/eaa'; DB = ROOT / 'data/normalized/water.sqlite'; APP = ROOT / 'app'; SITES = ROOT / 'data/eaa-sites.json'
UA = 'austin-swim-map/0.1 (saul.elbein@gmail.com)'; BASE = 'https://data.edwardsaquifer.org'
PAGES = {'wells': ('/GroundWater', 'allWellsLocationsJSON'), 'streams': ('/SpringsAndStreams', 'springsStreamsLocationsJSON'), 'rain': ('/RainGauges', 'rainGaugesLocationsJSON')}
CSV = {'wells': '/GroundWater/DownloadGroundwaterCsv?siteId={sid}&sensorName={sensor}', 'streams': '/SpringsAndStreams/DownloadSpringAndStreamCsv?siteId={sid}&sensorName={sensor}', 'rain': '/RainGauges/DownloadRainGaugesCsv?siteId={sid}&sensorName={sensor}'}

def now_utc(): return dt.datetime.now(dt.timezone.utc)

def fetch(url, dest_dir, stem, ext):
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    try:
        with urllib.request.urlopen(req, timeout=180) as r: body, status = r.read(), r.status
    except urllib.error.HTTPError as e: body, status = e.read() or b'', e.code
    except Exception as e: body, status = b'', 0
    t = now_utc(); dest_dir.mkdir(parents=True, exist_ok=True); name = f"{t.strftime('%Y%m%dT%H%M%S%fZ')}-{stem}"
    (dest_dir / (name + ext)).write_bytes(body)
    meta = {'url': url, 'retrieved_at': t.isoformat(), 'status': status, 'sha256': hashlib.sha256(body).hexdigest(), 'bytes': len(body), 'source': 'Edwards Aquifer Authority, data.edwardsaquifer.org', 'interpretation': 'none; verbatim source capture; EAA marks data provisional unless stated'}
    (dest_dir / (name + '.meta.json')).write_text(json.dumps(meta, indent=2) + '\n')
    return dest_dir / (name + ext), meta

def parse_sites(html, var):
    m = re.search(var + r'\s*=\s*(\[.*?\]);', html, re.S)
    return json.loads(m.group(1)) if m else []

def version(p, group, sid, sensor):
    CAP.mkdir(parents=True, exist_ok=True); gz = CAP / f'{p.stem}-{group}-{sid}-{sensor}.csv.gz'
    with gzip.open(gz, 'wb', compresslevel=9) as z: z.write(p.read_bytes())
    for old in CAP.glob(f'*-{group}-{sid}-{sensor}.csv.gz'):
        if old != gz: old.unlink()
    return gz

def collect(streams=False, pause=3.0, only=None, skip_pages=False):
    sites = {}
    if skip_pages and SITES.exists(): sites = json.loads(SITES.read_text())['sites']
    else:
        for group, (path, var) in PAGES.items():
            p, m = fetch(BASE + path, RAW / 'pages', group, '.html')
            sites[group] = parse_sites(p.read_text(encoding='utf-8', errors='replace'), var) if m['status'] == 200 else []
            print(f"{group}: HTTP {m['status']}, {len(sites[group])} sites listed"); time.sleep(pause)
        SITES.write_text(json.dumps({'retrieved_at': now_utc().isoformat(), 'source': BASE, 'counts': {g: {'listed': len(v), 'active': sum(1 for s in v if s.get('siteStatus') == 'Active')} for g, v in sites.items()}, 'sites': sites}, indent=2) + '\n')
    plan = [('wells', s['siteId'], 'DHE') for s in sites['wells'] if s.get('siteStatus') == 'Active'] + [('wells', s['siteId'], 'DTW') for s in sites['wells'] if s.get('siteStatus') == 'Active'] + [('rain', s['siteId'], 'DLRAIN') for s in sites['rain'] if s.get('siteStatus') == 'Active']
    if streams: plan += [('streams', s['siteId'], 'GAGHT') for s in sites['streams'] if s.get('siteStatus') == 'Active']
    if only: plan = [x for x in plan if x[1] in only]
    ok = 0; failed = 0
    for group, sid, sensor in plan:
        p, m = fetch(BASE + CSV[group].format(sid=sid, sensor=sensor), RAW / group / sid, f'{sid}-{sensor}', '.csv')
        if m['status'] == 200 and m['bytes'] > 0: version(p, group, sid, sensor); ok += 1
        else:
            failed += 1; print(f'{group} {sid} {sensor}: HTTP {m["status"]}, {m["bytes"]} bytes')
            if failed >= 8 and ok == 0: print('stopping: the server is refusing every download; try again later at a gentler pace'); break
        time.sleep(pause)
    print(f'csv captures: {ok} of {len(plan)} succeeded')

def rows_of(text):
    for line in text.splitlines():
        if not line or line.startswith('#'): continue
        parts = [x.strip() for x in line.split(',')]
        if len(parts) < 3: continue
        try: v = float(parts[2])
        except ValueError: continue
        yield parts[0], parts[1], v, parts[3] if len(parts) > 3 else None

def newest_captures(group):
    best = {}
    for meta_path in sorted((RAW / group).rglob('*.meta.json')) if (RAW / group).exists() else []:
        meta = json.loads(meta_path.read_text()); body = meta_path.with_suffix('').with_suffix('.csv')
        if meta.get('status') != 200 or not body.exists(): continue
        key = body.name.split('-', 1)[1][:-4]  # <sid>-<sensor>
        best[key] = (body, meta)
    return best

def normalize():
    DB.parent.mkdir(parents=True, exist_ok=True); db = sqlite3.connect(DB)
    db.execute('create table if not exists eaa_well_levels(site text, date text, sensor text, value real, status text, source_file text, retrieved_at text, primary key(site, date, sensor))')
    db.execute('create table if not exists eaa_rain_daily(site text, date text, inches real, status text, source_file text, retrieved_at text, primary key(site, date))')
    db.execute('create table if not exists eaa_stream_stage(site text, datetime text, ft real, status text, source_file text, retrieved_at text, primary key(site, datetime))')
    n = 0
    for key, (body, meta) in newest_captures('wells').items():
        sid, sensor = key.rsplit('-', 1)
        for s, d, v, st in rows_of(body.read_text(errors='replace')): db.execute('insert or replace into eaa_well_levels values(?,?,?,?,?,?,?)', (s, d[:10], sensor, v, st, str(body.relative_to(ROOT)), meta['retrieved_at'])); n += 1
    for key, (body, meta) in newest_captures('rain').items():
        for s, d, v, st in rows_of(body.read_text(errors='replace')): db.execute('insert or replace into eaa_rain_daily values(?,?,?,?,?,?)', (s, d[:10], v, st, str(body.relative_to(ROOT)), meta['retrieved_at'])); n += 1
    for key, (body, meta) in newest_captures('streams').items():
        for s, d, v, st in rows_of(body.read_text(errors='replace')): db.execute('insert or replace into eaa_stream_stage values(?,?,?,?,?,?)', (s, d, v, st, str(body.relative_to(ROOT)), meta['retrieved_at'])); n += 1
    db.commit(); db.close(); print(f'eaa tables: {n} rows written')

def pct(values, x):
    b = sum(1 for v in values if v < x); t = sum(1 for v in values if v == x); return round(100.0 * (b + 0.5 * t) / len(values), 1) if values else None

def assess(at=None):
    at = at or now_utc(); sites = json.loads(SITES.read_text())['sites'] if SITES.exists() else {'wells': [], 'rain': [], 'streams': []}
    db = sqlite3.connect(DB) if DB.exists() else None; wells = {}; rain = {}
    for s in sites['wells']:
        sid = s['siteId']; rows = db.execute("select date, value from eaa_well_levels where site=? and sensor='DHE' order by date", (sid,)).fetchall() if db else []
        rec = {k: s.get(k) for k in ('siteName', 'siteStatus', 'county', 'aquiferZone', 'aquifer', 'entity', 'latitude', 'longitude', 'stateWellNumber', 'usgssiteNo')}
        rec.update({'unit': 'ft above mean sea level (daily high water elevation)', 'meaning': 'EAA well; higher elevation means a higher water table. Context for Edwards springs; not a swim verdict.', 'source': f"{BASE}/GroundWater/Details/{s.get('siteInfoId')}"})
        if not rows: rec.update({'latest': None, 'data_health': 'no level on file'}); wells[sid] = rec; continue
        series = dict(rows); dates = sorted(series); last = dates[-1]; v = series[last]; age = (at.date() - dt.date.fromisoformat(last)).days
        def back(days):
            tgt = (dt.date.fromisoformat(last) - dt.timedelta(days=days)).isoformat(); prior = [d for d in dates if d <= tgt]; return round(v - series[prior[-1]], 2) if prior else None
        yr = [series[d] for d in dates if d >= (dt.date.fromisoformat(last) - dt.timedelta(days=395)).isoformat()]
        rec.update({'latest': {'date': last, 'elevation_ft_amsl': v}, 'age_days': age, 'data_health': 'fresh' if age <= 2 else f'stale ({age} d)', 'change_7d_ft': back(7), 'change_30d_ft': back(30), 'percentile_13mo': pct(yr, v) if len(yr) >= 200 else None, 'record_days_on_file': len(dates), 'first_date_on_file': dates[0]})
        wells[sid] = rec
    for s in sites['rain']:
        sid = s['siteId']; rows = db.execute('select date, inches from eaa_rain_daily where site=? order by date', (sid,)).fetchall() if db else []
        rec = {k: s.get(k) for k in ('siteName', 'siteStatus', 'county', 'aquiferZone', 'latitude', 'longitude')}; rec.update({'unit': 'inches per day', 'meaning': 'EAA rain gauge daily accumulation; a missing day is unreported, never zero.', 'source': f"{BASE}/RainGauges/Details/{s.get('siteInfoId')}"})
        if not rows: rec.update({'latest': None, 'data_health': 'no reading on file'}); rain[sid] = rec; continue
        series = dict(rows); dates = sorted(series); last = dates[-1]; age = (at.date() - dt.date.fromisoformat(last)).days
        def total(days):
            tgt = (dt.date.fromisoformat(last) - dt.timedelta(days=days - 1)).isoformat(); got = [series[d] for d in dates if d >= tgt]; return {'inches': round(sum(got), 2), 'days_reported': len(got)}
        rec.update({'latest': {'date': last, 'inches': series[last]}, 'age_days': age, 'data_health': 'fresh' if age <= 2 else f'stale ({age} d)', 'last_1d': total(1), 'last_3d': total(3), 'last_7d': total(7), 'last_30d': total(30), 'record_days_on_file': len(dates)})
        rain[sid] = rec
    if db: db.close()
    payload = {'generated_at': at.isoformat(), 'source': BASE, 'meaning': 'Edwards Aquifer Authority wells and rain gauges, read verbatim and summarized deterministically; context only.', 'counts': {'wells': len(wells), 'wells_fresh': sum(1 for r in wells.values() if r.get('data_health') == 'fresh'), 'rain_gauges': len(rain), 'rain_fresh': sum(1 for r in rain.values() if r.get('data_health') == 'fresh')}, 'wells': wells, 'rain_gauges': rain}
    (APP / 'eaa.json').write_text(json.dumps(payload, indent=2) + '\n'); print('eaa:', payload['counts'])
    for sid in ('J17WL', 'J27WL'):
        r = wells.get(sid)
        if r and r.get('latest'): print(f"  {sid} {r['siteName']}: {r['latest']['elevation_ft_amsl']} ft amsl on {r['latest']['date']}, 7d {r['change_7d_ft']}, 30d {r['change_30d_ft']}, pct13mo {r['percentile_13mo']}")

if __name__ == '__main__':
    p = argparse.ArgumentParser(); sub = p.add_subparsers(dest='cmd', required=True)
    c = sub.add_parser('collect'); c.add_argument('--streams', action='store_true'); c.add_argument('--pause-seconds', type=float, default=3.0); c.add_argument('--sites', nargs='*'); c.add_argument('--skip-pages', action='store_true')
    sub.add_parser('normalize'); sub.add_parser('assess'); a = p.parse_args()
    if a.cmd == 'collect': collect(a.streams, a.pause_seconds, set(a.sites) if a.sites else None, a.skip_pages)
    elif a.cmd == 'normalize': normalize()
    else: assess()
