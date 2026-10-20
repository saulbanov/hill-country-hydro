"""USGS annual instantaneous peaks; raw acquisition and normalization are separate.

Legacy redirects/refusals are preserved without following them. If annual peaks are
unavailable, collect-window saves only the requested OGC continuous interval. Those
readings are NOT annual maxima and never receive an annual peak rank.
"""
import argparse, csv, datetime as dt, gzip, hashlib, io, json, math, sqlite3, time
import urllib.error, urllib.parse, urllib.request
from pathlib import Path
from station_lists import history_stations

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data/raw/usgs-peaks'
CAP = ROOT / 'data/captures/usgs-peaks'
DB = ROOT / 'data/normalized/water.sqlite'
LIMIT = 50000

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

def capture(station, kind, url, pause=1):
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'hill-country-hydro/0.1'})
        with urllib.request.build_opener(NoRedirect).open(req, timeout=60) as r:
            body, status, error, headers = r.read(), r.status, None, dict(r.headers)
    except urllib.error.HTTPError as e:
        body, status, error, headers = e.read(), e.code, str(e), dict(e.headers)
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        body, status, error, headers = b'', 0, str(e), {}
    at = dt.datetime.now(dt.timezone.utc)
    folder = RAW / station; folder.mkdir(parents=True, exist_ok=True)
    raw = folder / (at.strftime('%Y%m%dT%H%M%S%fZ') + '-' + kind + '.txt')
    raw.write_bytes(body)
    meta = dict(station=station, kind=kind, url=url, retrieved_at=at.isoformat(), status=status,
                error=error, headers=headers, bytes=len(body), sha256=hashlib.sha256(body).hexdigest(),
                raw_path=str(raw.relative_to(ROOT)), interpretation='none; verbatim provider response')
    raw.with_suffix('.meta.json').write_text(json.dumps(meta, indent=2)+'\n')
    dest = CAP / station; dest.mkdir(parents=True, exist_ok=True)
    gz = dest / (kind + '.txt.gz')
    gz.write_bytes(gzip.compress(body, mtime=0))
    meta['capture_path'] = str(gz.relative_to(ROOT))
    gz.with_name(kind+'.meta.json').write_text(json.dumps(meta, indent=2)+'\n')
    manpath = dest / 'manifest.json'
    man = json.loads(manpath.read_text()) if manpath.exists() else {}
    man[kind] = meta
    manpath.write_text(json.dumps(man, indent=2)+'\n')
    time.sleep(pause)
    return meta

def number(value):
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except (ValueError, TypeError): return None

def parse_rdb(body, station):
    if b'No sites/data found using the selection criteria specified' in body: return []
    lines = [line for line in body.decode('utf-8', 'replace').splitlines() if line and not line.startswith('#')]
    if not lines or 'peak_va' not in lines[0].split('\t'): return None
    out = []
    for r in csv.DictReader(lines, delimiter='\t'):
        if r.get('agency_cd') != 'USGS': continue  # RDB column-format row
        if r.get('site_no') != station: raise ValueError('peak response station mismatch')
        # USGS can return partial dates; retain them faithfully, never invent a day.
        if number(r.get('peak_va')) is None: continue
        out.append(dict(station=station, date=r.get('peak_dt'), peak_cfs=number(r.get('peak_va')),
                        gage_height_ft=number(r.get('gage_ht')),
                        qualifiers=json.dumps({k:v for k,v in r.items() if k.endswith('_cd') or k=='peak_tm'})))
    return out

def read(meta):
    body = gzip.decompress((ROOT / meta['capture_path']).read_bytes())
    if hashlib.sha256(body).hexdigest() != meta['sha256']: raise ValueError('capture checksum mismatch')
    return body

def collect(stations, pause=1):
    for station in stations:
        url = 'https://nwis.waterdata.usgs.gov/nwis/peak?' + urllib.parse.urlencode(dict(site_no=station, agency_cd='USGS', format='rdb'))
        m = capture(station, 'annual', url, pause)
        print(f"{station}: HTTP {m['status']}, {m['bytes']} bytes", flush=True)

def collect_window(stations, start, end, pause=1, parameter="00060"):
    # Date validation before network or writes. An explicit window is mandatory.
    a = dt.datetime.fromisoformat(start.replace('Z','+00:00')); b = dt.datetime.fromisoformat(end.replace('Z','+00:00'))
    if a.tzinfo is None or b.tzinfo is None or not 0 < (b-a).total_seconds() <= 10*86400:
        raise ValueError('window must be timezone-aware, increasing, at most ten days')
    for station in stations:
        url = 'https://api.waterdata.usgs.gov/ogcapi/v1/collections/continuous/items?' + urllib.parse.urlencode(dict(f='json', monitoring_location_id='USGS-'+station, parameter_code=parameter, datetime=start+'/'+end, limit=LIMIT))
        m = capture(station, ('stage-window-' if parameter=='00065' else 'window-')+a.strftime('%Y%m%dT%H%M')+'-'+b.strftime('%Y%m%dT%H%M'), url, pause)
        print(f"{station}: continuous window HTTP {m['status']}, {m['bytes']} bytes", flush=True)

def normalize():
    DB.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB)
    db.execute('create table if not exists usgs_peaks(station text, date text, peak_cfs real, gage_height_ft real, qualifiers text, primary key(station,date))')
    db.execute('create table if not exists usgs_peak_window(station text, observed_at text, value real, series_id text, qualifiers text, source_file text, primary key(station,observed_at,series_id))')
    db.execute('create table if not exists usgs_stage_window(station text, observed_at text, value real, series_id text, qualifiers text, source_file text, primary key(station,observed_at,series_id))')
    report = {}
    for mp in sorted(CAP.glob('*/manifest.json')):
        sid = mp.parent.name; man = json.loads(mp.read_text()); entry = dict(annual_available=False, window_readings=0)
        for kind, meta in man.items():
            if meta['status'] != 200:
                entry[kind] = f"HTTP {meta['status']}; refusal preserved"; continue
            body = read(meta)
            if kind == 'annual':
                rows = parse_rdb(body, sid)
                if rows is None:
                    entry[kind] = 'not an RDB peak response; body preserved; use collect-window'; continue
                dest = ROOT / 'data/history' / f'{sid}-peaks.csv'; dest.parent.mkdir(parents=True, exist_ok=True)
                with dest.open('w', newline='') as f:
                    w = csv.DictWriter(f, fieldnames=['station','date','peak_cfs','gage_height_ft','qualifiers'],lineterminator='\n'); w.writeheader(); w.writerows(rows)
                db.executemany('insert or replace into usgs_peaks values(?,?,?,?,?)', [tuple(r.values()) for r in rows])
                entry.update(annual_available=bool(rows), annual_rows=len(rows))
            else:
                try: data = json.loads(body)
                except (ValueError, UnicodeDecodeError): entry[kind]='not JSON'; continue
                features = data.get('features')
                if not isinstance(features,list) or len(features)>=LIMIT or any(x.get('rel')=='next' for x in data.get('links',[])):
                    entry[kind]='incomplete response; not normalized'; continue
                rows=[]
                for f in features:
                    p=f['properties']
                    if p.get('monitoring_location_id')!='USGS-'+sid or p.get('parameter_code')!=('00065' if kind.startswith('stage-') else '00060'): raise ValueError('continuous identity mismatch')
                    if number(p.get('value')) is None: continue
                    rows.append((sid,p['time'],number(p['value']),p['time_series_id'],json.dumps(p.get('qualifier')),meta['capture_path']))
                table='usgs_stage_window' if kind.startswith('stage-') else 'usgs_peak_window'
                db.executemany('insert or replace into '+table+' values(?,?,?,?,?,?)', rows)
                entry['window_readings'] += len(rows)
        report[sid]=entry
    db.commit(); db.close()
    path=ROOT/'data/model/usgs-peaks-manifest.json'; path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(report,indent=2)+'\n')
    print(f'{len(report)} stations; {sum(x["annual_available"] for x in report.values())} annual peak records')

if __name__ == '__main__':
    ap=argparse.ArgumentParser(description=__doc__); sub=ap.add_subparsers(dest='cmd',required=True)
    c=sub.add_parser('collect'); c.add_argument('--stations',nargs='+',default=history_stations()); c.add_argument('--pause-seconds',type=float,default=1)
    w=sub.add_parser('collect-window'); w.add_argument('--stations',nargs='+',default=history_stations()); w.add_argument('--parameter',choices=['00060','00065'],default='00060'); w.add_argument('--start',required=True); w.add_argument('--end',required=True); w.add_argument('--pause-seconds',type=float,default=1)
    sub.add_parser('normalize'); a=ap.parse_args()
    if a.cmd=='collect': collect(a.stations,a.pause_seconds)
    elif a.cmd=='collect-window': collect_window(a.stations,a.start,a.end,a.pause_seconds,a.parameter)
    else: normalize()
