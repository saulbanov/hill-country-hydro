"""LCRA Hydromet: City of Austin and LCRA creek, river, lake and rain gauges (raw first, context only).

The Lower Colorado River Authority runs hydromet.lcra.org for its own gauges and the City of Austin's
flood-warning network. One public feed carries every current reading; two history endpoints return
15-minute (or hourly) records in windows of fewer than 180 days. Nothing needs a key.

  Current:   https://hydromet.lcra.org/api/GetDataForAllSites        (~407 sites: LCRA, COA and mirrored USGS)
  Lists:     https://hydromet.lcra.org/api/GetSitesBySensorType/<flow|rain|lakelevel|wtemp>
             https://hydromet.lcra.org/api/Coa/GetSitesBySensorType/<flow|rain>
  History:   https://hydromet.lcra.org/api/HistoricData/GetDataBySite/<site>/<param>/<m-d-yyyy>/<m-d-yyyy>[/hourly]   (LCRA)
             https://hydromet.lcra.org/api/CoaHistoricalData/GetDataBySite/<site>/<flow|rain>/<m-d-yyyy>/<m-d-yyyy>    (COA; no hourly)
  History params (LCRA): rain, rainDaily, flow (value1 stage ft, value2 flow cfs), lakelevel (value1 elevation ft msl,
  value2 tailwater), temp, tempstats, humidity, conductivity, wtemp. COA: flow, rain (value1 cumulative inches, value2 increment).
  Dates are inclusive calendar days in Central time; records come newest first with UTC timestamps. Both endpoints
  answer HTTP 400 "Start and End date must be within 180 days of each other" past the limit, so history is pulled in
  three fixed windows per calendar year (Jan 1-Apr 30, May 1-Aug 31, Sep 1-Dec 31) that never move, one gzip each.
  Record starts seen 2026-10-02: LCRA creek and river sites 1993 at 15 minutes (the hourly series is patchy: whole windows
  come back empty where the 15-minute series is complete, so an empty hourly window is asked again at 15 minutes), Lake
  Austin 2005, COA sites November 2015.

  collect    all-sites feed + the six site lists -> data/raw/hydromet/current/ (verbatim, with .meta.json)
  history    windows per site/param -> data/captures/hydromet/<agency>/<site>-<param>-<yyyy>-<n>.json.gz + manifest.json
             (closed windows are fetched once; the window holding today is refreshed every run; --refresh refetches all)
  normalize  captures -> sqlite tables hydromet_sites, hydromet_readings
  assess     app/hydromet.json: every site's latest readings and creek tag, history coverage per site/param. No color.
A gauge reading describes a point on a creek; it is context for the swim lens, never a verdict about a place.
"""
import argparse, datetime as dt, gzip, hashlib, json, re, sqlite3, time, urllib.error, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data/raw/hydromet'; CAP = ROOT / 'data/captures/hydromet'; DB = ROOT / 'data/normalized/water.sqlite'; APP = ROOT / 'app'
UA = 'hill-country-hydro/0.1 (saul.elbein@gmail.com)'
BASE = 'https://hydromet.lcra.org/api/'
ALL_SITES = BASE + 'GetDataForAllSites'
LISTS = {'lcra-flow': 'GetSitesBySensorType/flow', 'lcra-rain': 'GetSitesBySensorType/rain', 'lcra-lakelevel': 'GetSitesBySensorType/lakelevel',
         'lcra-wtemp': 'GetSitesBySensorType/wtemp', 'coa-flow': 'Coa/GetSitesBySensorType/flow', 'coa-rain': 'Coa/GetSitesBySensorType/rain'}
HISTORY = {'LCRA': 'HistoricData/GetDataBySite/', 'COA': 'CoaHistoricalData/GetDataBySite/'}
WINDOWS = ((1, 1, 4, 30), (5, 1, 8, 31), (9, 1, 12, 31))   # (start month, start day, end month, end day); each < 180 days
DEFAULT_SINCE = {'LCRA': 1988, 'COA': 2014}                  # a few years before the earliest record seen in probes (LCRA 1993, COA Nov 2015)
RECORD_WALKBACK_EMPTY_YEARS = 2                              # stop walking back after this many consecutive empty years once data has been seen
# The sites pulled in full by `history` without --sites. Chosen 2026-10-02 for the Austin creeks the swim lens cites,
# the Hill Country rivers, and the lake levels the region reads. Everything else is still captured daily by `collect`.
PRIORITY = {
    'COA': {'flow': ['950', '1130', '1100', '120', '2750', '122', '2060', '2070', '2080', '2400', '2510', '2520', '121', '248', '187', '800', '860', '3200', '3310', '3320'],
            'rain': ['3650', '2730', '1140', '1180', '1190', '124', '700', '3600', '3610', '810', '2100']},
    'LCRA': {'flow': ['3992', '4519', '4520', '4595', '4598', '4561', '4558', '3385', '3555', '3299', '2306', '2641', '3529', '3920'],
             'lakelevel': ['3965', '3967', '4543', '3963', '1972', '2096', '2958', '3999'],
             'rainDaily': ['3920', '3953', '3555', '3529', '3385', '4595']},
}
CREEKS = [('bull-creek', r'\bBull Ck|\bBull Creek'), ('barton-creek', r'\bBarton (Ck|Creek|Spgs)'), ('onion-creek', r'\bOnion (Ck|Creek)'),
          ('williamson-creek', r'\bWilliamson (Ck|Creek)|\bKincheon'), ('slaughter-creek', r'\bSlaughter (Ck|Creek)'), ('walnut-creek', r'\bWalnut (Ck|Creek)'),
          ('shoal-creek', r'\bShoal (Ck|Creek)'), ('waller-creek', r'\bWaller (Ck|Creek)'), ('boggy-creek', r'\bBoggy (Ck|Creek)|\bFort Branch|\bFt Br\b|\bTannehill'),
          ('blunn-creek', r'\bBlunn'), ('bouldin-creek', r'\bBouldin'), ('bear-creek', r'\bBear (Ck|Creek)'), ('pedernales-river', r'\bPedernales'),
          ('llano-river', r'\bLlano (Rv|River)'), ('san-saba-river', r'\bSan Saba (Rv|River)'), ('blanco-river', r'\bBlanco (Rv|River)'),
          ('lake-austin', r'\bLake Austin|\bTom Miller Dam'), ('lady-bird-lake', r'\bLady Bird'), ('lake-travis', r'\bLake Travis|\bMansfield Dam'),
          ('lake-lbj', r'\bLake LBJ|\bWirtz Dam'), ('lake-buchanan', r'\bLake Buchanan|\bBuchanan Dam'), ('inks-lake', r'\bInks (Lake|Dam)'),
          ('lake-marble-falls', r'\bMarble Falls|\bStarcke Dam'), ('colorado-river', r'\bColorado (Rv|River)'), ('gilleland-creek', r'\bGilleland')]
RAIN_FIELDS = ['rainfallRecent', 'rainfall1Hour', 'rainfall3Hours', 'rainfall6Hours', 'rainfall12Hours', 'rainfallToday', 'rainfall1Day', 'rainfall2Days', 'rainfall3Days', 'rainfall1Week', 'rainfall2Weeks', 'rainfall30Days', 'rainfallMonth', 'rainfallPrevMonth', 'rainfallYear', 'rainfallPrevYear']

def now_utc(): return dt.datetime.now(dt.timezone.utc)

def fetch(url, timeout=120):
    """One request. Returns (body bytes, status, error string or None). Never raises on HTTP or network errors."""
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r: return r.read(), r.status, None
    except urllib.error.HTTPError as e: return (e.read() or b''), e.code, str(e)
    except (urllib.error.URLError, TimeoutError, OSError) as e: return b'', 0, str(e)

def save_raw(dest_dir, stem, url, body, status, error, ext='json'):
    t = now_utc(); dest_dir.mkdir(parents=True, exist_ok=True); name = f"{t.strftime('%Y%m%dT%H%M%S%fZ')}-{stem}"
    (dest_dir / f'{name}.{ext}').write_bytes(body)
    meta = {'url': url, 'retrieved_at': t.isoformat(), 'status': status, 'error': error, 'sha256': hashlib.sha256(body).hexdigest(), 'bytes': len(body),
            'source': 'LCRA Hydromet (hydromet.lcra.org): LCRA and City of Austin flood-warning gauges', 'interpretation': 'none; verbatim source capture'}
    (dest_dir / f'{name}.meta.json').write_text(json.dumps(meta, indent=2) + '\n')
    return dest_dir / f'{name}.{ext}', meta

def collect(pause=1.0):
    body, status, err = fetch(ALL_SITES); p, m = save_raw(RAW / 'current', 'all-sites', ALL_SITES, body, status, err)
    print(f"all-sites: HTTP {status} {err or ''} {len(body)} bytes -> {p.relative_to(ROOT)}")
    for key, path in LISTS.items():
        time.sleep(pause); body, status, err = fetch(BASE + path); p, m = save_raw(RAW / 'lists', key, BASE + path, body, status, err)
        print(f"{key}: HTTP {status} {err or ''} {len(body)} bytes")

# ---------------------------------------------------------------- history
def windows_for_year(year):
    return [(dt.date(year, m1, d1), dt.date(year, m2, d2), n + 1) for n, (m1, d1, m2, d2) in enumerate(WINDOWS)]

def mdy(d): return f'{d.month}-{d.day}-{d.year}'

def history_url(agency, site, param, start, end, hourly=False):
    u = f'{BASE}{HISTORY[agency]}{site}/{param}/{mdy(start)}/{mdy(end)}'
    if hourly and agency == 'LCRA': u += '/hourly'
    return u

def parse_history(body):
    """Returns (records list newest-first as given, header dict) or ([], {}) when the body is not the expected shape."""
    try: d = json.loads(body.decode('utf-8'))
    except Exception: return [], {}
    if not isinstance(d, dict): return [], {}
    hdr = {k: d.get(k) for k in ('siteId', 'siteNumber', 'siteName', 'isHourly', 'isDaily', 'value1Type', 'value2Type')}
    return [r for r in d.get('records') or [] if isinstance(r, dict) and r.get('dateTime')], hdr

def attempt_plan(agency, hourly):
    """Resolutions to try, in order, until a window returns records. The LCRA hourly series came back empty for whole
    windows on 2026-10-02 while the 15-minute series had every reading (and one empty hourly window had data on a
    second ask), so an empty hourly window is asked again at 15 minutes; everything else is asked once more as is."""
    return [True, False] if (agency == 'LCRA' and hourly) else [hourly, hourly]

def capture_name(site, param, year, n, hourly): return f"{site}-{param}{'-hourly' if hourly else ''}-{year}-{n}.json.gz"

def manifest_path(agency, site): return CAP / agency.lower() / f'{site}-manifest.json'

def load_manifest(agency, site):
    """One manifest per (agency, site) so several pulls over disjoint site lists can run side by side. A legacy
    per-agency manifest.json, if present, seeds the site's entries the first time."""
    p = manifest_path(agency, site)
    man = json.loads(p.read_text()) if p.exists() else {'agency': agency, 'site': str(site), 'windows': {}}
    legacy = CAP / agency.lower() / 'manifest.json'
    if legacy.exists():
        for k, w in json.loads(legacy.read_text()).get('windows', {}).items():
            if str(w.get('site')) == str(site) and k not in man['windows']: man['windows'][k] = w
    return man

def load_manifests():
    """Every manifest merged: {window key: record}. Per-site manifests win over a legacy per-agency one."""
    out = {}
    for agency in HISTORY:
        legacy = CAP / agency.lower() / 'manifest.json'
        if legacy.exists(): out.update(json.loads(legacy.read_text()).get('windows', {}))
    for mp in sorted(CAP.glob('*/*-manifest.json')): out.update(json.loads(mp.read_text()).get('windows', {}))
    return out

def history(agency, sites, params, since=None, until_year=None, hourly=None, pause=1.0, refresh=False, max_failures=8, log=print):
    """Pull every window for each site/param from the current year back to `since`, stopping early once two whole years
    come back empty (the record start). Closed windows already in the manifest are skipped unless refresh=True."""
    hourly = (agency == 'LCRA') if hourly is None else hourly
    today = dt.date.today(); until_year = until_year or today.year; since = since or DEFAULT_SINCE[agency]
    out_dir = CAP / agency.lower(); out_dir.mkdir(parents=True, exist_ok=True)
    failures = 0; fetched = 0
    for site in sites:
        man = load_manifest(agency, site)
        for param in params:
            empty_years = 0; seen_data = False
            for year in range(until_year, since - 1, -1):
                year_records = 0
                for start, end, n in reversed(windows_for_year(year)):
                    if start > today: continue
                    name = capture_name(site, param, year, n, hourly); key = f'{agency.lower()}/{name}'; prev = man['windows'].get(key)
                    is_open = start <= today <= end
                    if prev and not refresh and not is_open and prev.get('status') == 200 and (prev.get('records', 0) > 0 or prev.get('attempts', 1) >= 2 or prev.get('param') in ('rainDaily', 'rain')):
                        year_records += prev.get('records', 0); continue
                    recs, hdr, body, status, err, used_hourly, attempts, url = [], {}, b'', 0, None, hourly, 0, None
                    for try_hourly in (attempt_plan(agency, hourly)[:1] if param in ('rainDaily', 'rain') else attempt_plan(agency, hourly)):   # rain is requested once; other params retain their existing empty-window resolution plan
                        url = history_url(agency, site, param, start, min(end, today), try_hourly); used_hourly = try_hourly; attempts += 1
                        body, status, err = fetch(url)
                        raw, meta = save_raw(RAW / 'history' / str(site), f'{param}-{year}-{n}', url, body, status, err)
                        time.sleep(pause)
                        recs, hdr = parse_history(body) if status == 200 else ([], {})
                        if status != 200 or recs or is_open: break
                    if status == 200:
                        failures = 0; fetched += 1; gz = out_dir / capture_name(site, param, year, n, used_hourly)
                        with gzip.open(gz, 'wb', compresslevel=9) as z: z.write(body)
                        gz.with_name(gz.name.replace('.json.gz', '.meta.json')).write_text(json.dumps(meta, indent=2) + '\n')
                        man['windows'][key] = {'agency': agency, 'site': str(site), 'param': param, 'year': year, 'window': n, 'start': start.isoformat(), 'end': min(end, today).isoformat(), 'hourly': used_hourly, 'file': f'{agency.lower()}/{gz.name}', 'attempts': attempts, 'url': url, 'status': 200,
                                               'retrieved_at': now_utc().isoformat(), 'sha256': hashlib.sha256(body).hexdigest(), 'bytes': len(body), 'gz_bytes': gz.stat().st_size, 'records': len(recs), 'raw_path': str(raw.relative_to(ROOT)),
                                               'first': recs[-1]['dateTime'] if recs else None, 'last': recs[0]['dateTime'] if recs else None, 'value1Type': hdr.get('value1Type'), 'value2Type': hdr.get('value2Type'), 'site_name': hdr.get('siteName'), 'open_window': is_open}
                        year_records += len(recs)
                    else:
                        failures += 1
                        man['windows'][key] = {**meta, 'raw_path': str(raw.relative_to(ROOT)), 'agency': agency, 'site': str(site), 'param': param, 'year': year, 'window': n, 'start': start.isoformat(), 'end': min(end, today).isoformat(), 'hourly': hourly, 'url': url, 'status': status, 'error': err or body[:200].decode('utf-8', 'replace'), 'retrieved_at': now_utc().isoformat(), 'records': 0}
                        log(f'{agency} {site} {param} {year}-{n}: HTTP {status} {err or body[:80]!r}')
                        if failures >= max_failures:
                            log(f'stopping after {failures} straight refusals; coverage recorded as partial'); _save_manifest(man); return fetched
                log(f'{agency} {site} {param} {year}: {year_records} records')
                if year_records == 0:   # the record start: two empty years after data was seen (a site whose record ended years ago walks the whole range)
                    empty_years += 1
                    if seen_data and empty_years >= RECORD_WALKBACK_EMPTY_YEARS: break
                else: empty_years = 0; seen_data = True
            _save_manifest(man)
    return fetched

def _save_manifest(man):
    p = manifest_path(man['agency'], man['site']); p.parent.mkdir(parents=True, exist_ok=True); man['updated_at'] = now_utc().isoformat()
    p.write_text(json.dumps(man, indent=1, sort_keys=True) + '\n')

# ---------------------------------------------------------------- normalize
def newest_current():
    metas = sorted((RAW / 'current').glob('*-all-sites.meta.json')) if (RAW / 'current').exists() else []
    for mp in reversed(metas):
        m = json.loads(mp.read_text())
        if m.get('status') == 200: return mp.with_name(mp.name.replace('.meta.json', '.json')), m
    return None, None

def hill_country_rain_sites(sites):
    """Frozen box from the storm handoff; only provider-identified LCRA rain sites."""
    return sorted({s['site'] for s in sites if s['agency'] == 'LCRA' and (s['site_type'] == 'rain' or bool(s.get('rain_in')))
                   and s['lat'] is not None and s['lon'] is not None
                   and 29.9 <= s['lat'] <= 30.9 and -100.2 <= s['lon'] <= -97.9})

def num(x):
    if x is None or x == '': return None
    try: return float(x)
    except (TypeError, ValueError): return None

def creek_tag(name):
    for tag, rx in CREEKS:
        if re.search(rx, name or '', re.I): return tag
    return None

def parse_sites(body):
    """The all-sites feed -> list of site dicts with typed numbers; siteName HTML (e.g. '<br />') is flattened to text."""
    d = json.loads(body.decode('utf-8') if isinstance(body, bytes) else body); out = []
    for s in d if isinstance(d, list) else []:
        name = re.sub(r'<[^>]+>', ' ', s.get('siteName') or '').strip(); name = re.sub(r'\s+', ' ', name)
        out.append({'site': str(s.get('siteNumber')), 'agency': s.get('agency'), 'name': name, 'site_type': (s.get('siteType') or '').strip(), 'lat': num(s.get('latitude')), 'lon': num(s.get('longitude')),
                    'observed_at': s.get('dateTime'), 'stage_ft': num(s.get('stage')), 'flow_cfs': num(s.get('flow')), 'head_ft': num(s.get('head')), 'tail_ft': num(s.get('tail')), 'water_temp_f': num(s.get('waterTemperature')),
                    'flood_stage_ft': num(s.get('floodStage')), 'bankfull_stage_ft': num(s.get('bankfullStage')), 'nwsid': s.get('nwsid') or None, 'stale': s.get('isStale'),
                    'rain_in': {k.replace('rainfall', ''): num(s.get(k)) for k in RAIN_FIELDS if num(s.get(k)) is not None}, 'creek': creek_tag(name)})
    return out

def normalize():
    DB.parent.mkdir(parents=True, exist_ok=True); db = sqlite3.connect(DB)
    db.execute('create table if not exists hydromet_sites(site text, agency text, name text, site_type text, lat real, lon real, creek text, observed_at text, stage_ft real, flow_cfs real, source_file text, retrieved_at text, primary key(site, agency))')
    db.execute('create table if not exists hydromet_readings(agency text, site text, param text, observed_at text, value1 real, value2 real, hourly integer, source_file text, primary key(agency, site, param, observed_at, hourly))')
    p, m = newest_current(); n_sites = 0
    if p:
        for s in parse_sites(p.read_bytes()):
            db.execute('insert or replace into hydromet_sites values(?,?,?,?,?,?,?,?,?,?,?,?)', (s['site'], s['agency'], s['name'], s['site_type'], s['lat'], s['lon'], s['creek'], s['observed_at'], s['stage_ft'], s['flow_cfs'], str(p.relative_to(ROOT)), m['retrieved_at'])); n_sites += 1
    windows = load_manifests(); n = 0
    for key, w in windows.items():
        if w.get('status') != 200: continue
        gz = CAP / w.get('file', key)
        if not gz.exists(): continue
        with gzip.open(gz, 'rb') as z: recs, hdr = parse_history(z.read())
        rows = [(w['agency'], w['site'], w['param'], r['dateTime'], num(r.get('value1')), num(r.get('value2')), 1 if w.get('hourly') else 0, key) for r in recs]
        db.executemany('insert or replace into hydromet_readings values(?,?,?,?,?,?,?,?)', rows); n += len(rows)
    db.commit(); db.close(); print(f'hydromet: {n_sites} sites, {n} readings from {sum(1 for w in windows.values() if w.get("status") == 200)} windows')

# ---------------------------------------------------------------- assess
def coverage(windows):
    cov = {}
    for key, w in windows.items():
        k = f"{w['agency']}:{w['site']}:{w['param']}"; c = cov.setdefault(k, {'agency': w['agency'], 'site': w['site'], 'param': w['param'], 'hourly': w.get('hourly'), 'windows_ok': 0, 'windows_failed': 0, 'records': 0, 'first': None, 'last': None, 'value1Type': None, 'value2Type': None})
        if w.get('status') == 200:
            c['windows_ok'] += 1; c['records'] += w.get('records', 0)
            if w.get('first') and (c['first'] is None or w['first'] < c['first']): c['first'] = w['first']
            if w.get('last') and (c['last'] is None or w['last'] > c['last']): c['last'] = w['last']
            c['value1Type'] = c['value1Type'] or w.get('value1Type'); c['value2Type'] = c['value2Type'] or w.get('value2Type')
        else: c['windows_failed'] += 1
    return cov

def assess(at=None):
    at = at or now_utc(); p, m = newest_current()
    out = {'generated_at': at.isoformat(), 'source': ALL_SITES, 'meaning': 'Latest reading at each LCRA Hydromet site (LCRA, City of Austin, and USGS sites the feed mirrors), with history coverage held in data/captures/hydromet/. Stage and flow are what the gauge reports; a 0.00 flow is a reading, not a verdict. Missing fields are absent, never zero.',
           'capture': None, 'sites': {}, 'history_coverage': coverage(load_manifests())}
    if not p:
        out['missing_inputs'] = ['no successful all-sites capture under data/raw/hydromet/current/']
    else:
        out['capture'] = {'path': str(p.relative_to(ROOT)), 'retrieved_at': m['retrieved_at'], 'sha256': m['sha256']}
        for s in parse_sites(p.read_bytes()):
            age = None
            try: age = round((at - dt.datetime.fromisoformat(s['observed_at'].replace('Z', '+00:00'))).total_seconds() / 3600, 2)
            except Exception: pass
            key = f"{s['agency']}:{s['site']}"
            out['sites'][key] = {**s, 'age_hours': age, 'fresh_within_1h': age is not None and 0 <= age <= 1,
                                 'history': [k.split(':', 2)[2] for k in out['history_coverage'] if k.startswith(key + ':')]}
    out['counts'] = {'sites': len(out['sites']), 'by_agency': {a: sum(1 for s in out['sites'].values() if s['agency'] == a) for a in ('LCRA', 'COA', 'USGS')},
                     'with_creek_tag': sum(1 for s in out['sites'].values() if s['creek']), 'history_series': len(out['history_coverage'])}
    APP.mkdir(exist_ok=True); (APP / 'hydromet.json').write_text(json.dumps(out, indent=1) + '\n'); print(f"hydromet.json: {out['counts']}"); return out

def expand_rain_priority():
    p, _ = newest_current()
    if p:
        PRIORITY['LCRA']['rainDaily'] = sorted(set(PRIORITY['LCRA']['rainDaily']) | set(hill_country_rain_sites(parse_sites(p.read_bytes()))))


def rain_window(sites, start, end, pause=0.5, refresh=False):
    """One bounded native rain request per site; preserve each refusal, never retry."""
    if not 0 <= (end-start).days < 180: raise ValueError('rain window must be 0..179 days')
    for site in sites:
        name = f'{site}-rain-window-{start}-{end}.json.gz'
        previous = load_manifest('LCRA', site)['windows'].get('lcra/'+name)
        if previous and previous.get('status') == 200 and not refresh:
            print(f'{site}: preserved existing rain window', flush=True); continue
        url = history_url('LCRA', site, 'rain', start, end, False)
        body, status, err = fetch(url)
        raw, meta = save_raw(RAW / 'history' / site, 'rain-window', url, body, status, err)
        time.sleep(pause)
        # Interpretation begins only after the raw body and sidecar are on disk.
        recs, hdr = parse_history(body) if status == 200 else ([], {})
        gz = CAP / 'lcra' / f'{site}-rain-window-{start}-{end}.json.gz'; gz.parent.mkdir(parents=True, exist_ok=True)
        gz.write_bytes(gzip.compress(body, mtime=0))
        gz.with_name(gz.name.replace('.json.gz','.meta.json')).write_text(json.dumps(meta, indent=2)+'\n')
        key = 'lcra/' + gz.name; man = load_manifest('LCRA', site)
        man['windows'][key] = {**meta, 'agency':'LCRA', 'site':site, 'param':'rain', 'file':key,
            'start':str(start), 'end':str(end), 'hourly':False, 'records':len(recs), 'value1Type':hdr.get('value1Type'),
            'value2Type':hdr.get('value2Type'), 'first':recs[-1]['dateTime'] if recs else None,
            'last':recs[0]['dateTime'] if recs else None, 'raw_path':str(raw.relative_to(ROOT))}
        _save_manifest(man)
        print(f"{site} rain window: HTTP {status}, {len(recs)} records", flush=True)


expand_rain_priority()

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter); sub = ap.add_subparsers(dest='cmd', required=True)
    sub.add_parser('collect').add_argument('--pause-seconds', type=float, default=1.0)
    h = sub.add_parser('history'); h.add_argument('--agency', choices=['COA', 'LCRA', 'both'], default='both'); h.add_argument('--sites', nargs='*', help='site numbers; default PRIORITY')
    h.add_argument('--params', nargs='*', help='history params; default PRIORITY per agency'); h.add_argument('--since', type=int); h.add_argument('--until-year', type=int, help='newest year to ask (a site whose record ended)'); h.add_argument('--hourly', action='store_true'); h.add_argument('--fifteen-minute', action='store_true', help='LCRA at native 15-minute (default hourly)')
    h.add_argument('--pause-seconds', type=float, default=1.0); h.add_argument('--refresh', action='store_true'); h.add_argument('--recent-only', action='store_true', help='only the window holding today (the daily routine)')
    w = sub.add_parser('rain-window'); w.add_argument('--start', type=dt.date.fromisoformat, required=True); w.add_argument('--end', type=dt.date.fromisoformat, required=True); w.add_argument('--pause-seconds', type=float, default=0.5); w.add_argument('--refresh', action='store_true')
    sub.add_parser('normalize'); sub.add_parser('assess')
    a = ap.parse_args()
    if a.cmd == 'collect': collect(a.pause_seconds)
    elif a.cmd == 'history':
        for agency in (['COA', 'LCRA'] if a.agency == 'both' else [a.agency]):
            plan = PRIORITY[agency]; params = a.params or list(plan)
            hourly = True if a.hourly else (False if a.fifteen_minute else None)
            for param in params:
                sites = a.sites or plan.get(param, [])
                since = dt.date.today().year if a.recent_only else a.since
                n = history(agency, sites, [param], since=since, until_year=a.until_year, hourly=hourly, pause=a.pause_seconds, refresh=a.refresh)
                print(f'{agency} {param}: {n} windows fetched for {len(sites)} sites')
    elif a.cmd == 'rain-window':
        p, _ = newest_current()
        if not p: raise SystemExit('no saved all-sites feed')
        rain_window(hill_country_rain_sites(parse_sites(p.read_bytes())), a.start, a.end, a.pause_seconds, a.refresh)
    elif a.cmd == 'normalize': normalize()
    elif a.cmd == 'assess': assess()

if __name__ == '__main__': main()
