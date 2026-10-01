#!/usr/bin/env python3
"""Preserve USGS daily-value history and station metadata for Austin stations. No assessment.

Acquisition (``collect``): one bounded request per station for daily mean discharge
(parameter 00060, statistic 00003) from the USGS OGC API ``daily`` collection, plus the
``monitoring-locations`` and ``time-series-metadata`` records that document the station.
Every response is written to disk before it is parsed:

* ``data/raw/usgs-daily/<station>/`` keeps the verbatim bytes (Git-ignored, like all raw).
* ``data/captures/usgs-daily/<station>/`` keeps a gzipped copy that IS versioned, because a
  cloud session's container is discarded and the daily record is small (well under 1 MB per
  station compressed). The manifest records both paths and one checksum of the raw bytes.

Normalization (``normalize``): ``data/history/<station>-00060-daily-mean.csv`` with one row per
returned day (date, value, unit, approval, qualifiers, last_modified, time_series_id). A day the
provider did not return is absent from the CSV and listed in the manifest gap report. It is
never filled with zero. A non-numeric provider value keeps its text in ``raw_value`` and leaves
``value`` empty.

The manifest ``data/model/<station>-daily-history-manifest.json`` records the request, the
checksum, completeness (HTTP 200, feature count below the requested limit, no next link),
series identity, begin/end, approval and qualifier counts, and calendar-day gaps.
"""
import argparse, csv, datetime as dt, gzip, hashlib, json, sys, time
from collections import Counter
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT=Path(__file__).resolve().parents[1]
RAW=ROOT/'data/raw/usgs-daily'; CAPTURES=ROOT/'data/captures/usgs-daily'
HISTORY=ROOT/'data/history'; MODEL=ROOT/'data/model'
BASE='https://api.waterdata.usgs.gov/ogcapi/v1/collections'
import sys as _sys; _sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from station_lists import history_stations
AUSTIN_STATIONS=history_stations()  # name kept for callers; now the Austin ten plus the inventory's history tiers
LIMIT=50000
UA='swimming-hole-alerts/0.1 usgs-daily-history'

def utcnow(): return dt.datetime.now(dt.timezone.utc)

def fetch(url):
    try:
        with urlopen(Request(url,headers={'User-Agent':UA}),timeout=180) as r: return r.status,r.read(),None
    except HTTPError as e: return e.code,(e.read() or b''),str(e)
    except URLError as e: return 0,b'',str(e)

def preserve(station,kind,url):
    """Write raw bytes and metadata before anything reads them. Returns (meta_path, meta)."""
    status,body,error=fetch(url)
    at=utcnow(); stem=f"{at.strftime('%Y%m%dT%H%M%S%fZ')}-{kind}"
    raw_dir=RAW/station; raw_dir.mkdir(parents=True,exist_ok=True)
    raw=raw_dir/f'{stem}.json'; raw.write_bytes(body)
    cap_dir=CAPTURES/station; cap_dir.mkdir(parents=True,exist_ok=True)
    cap=cap_dir/f'{stem}.json.gz'
    with gzip.open(cap,'wb',compresslevel=9) as z: z.write(body)
    feature_count=None; next_link=None; parse_error=None
    try:
        payload=json.loads(body); feature_count=len(payload.get('features',[]))
        next_link=next((l.get('href') for l in payload.get('links',[]) if l.get('rel')=='next'),None)
    except (json.JSONDecodeError,UnicodeDecodeError,AttributeError) as exc: parse_error=str(exc)
    meta={'source':'USGS OGC API','kind':kind,'url':url,'station_id':'USGS-'+station,
          'retrieved_at':at.isoformat(),'status':status,'error':error,'sha256':hashlib.sha256(body).hexdigest(),
          'bytes':len(body),'feature_count':feature_count,'next_link':next_link,'parse_error':parse_error,
          'raw_path':str(raw.relative_to(ROOT)),'capture_path':str(cap.relative_to(ROOT)),
          'completeness':'complete only when status is 200, feature_count is below the requested limit, and next_link is null'}
    meta_path=raw.with_suffix('.meta.json'); meta_path.write_text(json.dumps(meta,indent=2))
    (cap_dir/f'{stem}.meta.json').write_text(json.dumps(meta,indent=2))
    return meta_path,meta

def prune_versioned(station,kind,keep_path):
    """Keep one versioned gzip per station and kind. Raw bytes stay under data/raw; the versioned copy is the newest complete capture only, so weekly refreshes do not pile up in git."""
    folder=CAPTURES/station
    if not folder.exists(): return 0
    removed=0
    for p in folder.glob(f'*-{kind}.json.gz'):
        if p!=keep_path: p.unlink(); removed+=1
    for p in folder.glob(f'*-{kind}.meta.json'):
        if p.with_name(p.name.replace('.meta.json','.json.gz'))!=keep_path and not p.with_name(p.name.replace('.meta.json','.json.gz')).exists(): p.unlink()
    return removed

def collect(stations,pause):
    for station in stations:
        for kind,url in (
            ('location',BASE+'/monitoring-locations/items?'+urlencode({'f':'json','id':'USGS-'+station,'limit':'1'})),
            ('timeseries-metadata',BASE+'/time-series-metadata/items?'+urlencode({'f':'json','monitoring_location_id':'USGS-'+station,'limit':'1000','skipGeometry':'true'})),
            ('daily-00060-00003',BASE+'/daily/items?'+urlencode({'f':'json','monitoring_location_id':'USGS-'+station,'parameter_code':'00060','statistic_id':'00003','limit':str(LIMIT),'skipGeometry':'true'})),
        ):
            _,meta=preserve(station,kind,url)
            if kind=='location': state='ok' if meta['status']==200 and meta['feature_count']==1 else 'MISSING'
            else: state='complete' if meta['status']==200 and meta['feature_count'] is not None and meta['feature_count']<LIMIT and not meta['next_link'] else 'INCOMPLETE'
            print(f"{station} {kind}: status {meta['status']} features {meta['feature_count']} {state} {meta['bytes']} bytes")
            time.sleep(pause)
    print('USGS daily history preserved raw; run normalize before interpreting.')

def probe(stations,pause):
    """Identity and series inventory only: which parameters and statistics a candidate station actually carries, and their begin/end."""
    MODEL.mkdir(parents=True,exist_ok=True); report={}
    for station in stations:
        loc=preserve(station,'location',BASE+'/monitoring-locations/items?'+urlencode({'f':'json','id':'USGS-'+station,'limit':'1'}))[1]; time.sleep(pause)
        ts=preserve(station,'timeseries-metadata',BASE+'/time-series-metadata/items?'+urlencode({'f':'json','monitoring_location_id':'USGS-'+station,'limit':'1000','skipGeometry':'true'}))[1]; time.sleep(pause)
        entry={'location_request':{k:loc[k] for k in ('url','retrieved_at','status','sha256','feature_count','raw_path','capture_path')},
               'time_series_request':{k:ts[k] for k in ('url','retrieved_at','status','sha256','feature_count','raw_path','capture_path')},'station':None,'series':[]}
        if loc['status']==200 and loc['feature_count']:
            f=json.loads(read_body(loc))['features'][0]; p=f['properties']; g=f.get('geometry') or {}
            entry['station']={k:p.get(k) for k in ('monitoring_location_name','site_type','hydrologic_unit_code','drainage_area','county_name')}; entry['station']['coordinates_lon_lat']=g.get('coordinates')
        if ts['status']==200:
            for f in json.loads(read_body(ts)).get('features',[]):
                p=f['properties']; entry['series'].append({k:p.get(k) for k in ('parameter_code','parameter_name','statistic_id','computation_identifier','computation_period_identifier','begin','end','unit_of_measure')})
        entry['has_instantaneous_discharge']=any(x['parameter_code']=='00060' and x['computation_identifier']=='Instantaneous' for x in entry['series'])
        latest=[x['end'] for x in entry['series'] if x['parameter_code'] in ('00060','00065') and x['end']]
        entry['latest_00060_00065_end']=max(latest) if latest else None
        report[station]=entry
        print(f"{station}: {entry['station']['monitoring_location_name'] if entry['station'] else 'no location'}; series={len(entry['series'])}; inst discharge={entry['has_instantaneous_discharge']}; latest end={entry['latest_00060_00065_end']}")
    out=MODEL/'austin-candidate-station-probe.json'
    existing=json.loads(out.read_text()) if out.exists() else {'purpose':'Series availability for candidate stations; catalog presence is insufficient. Probing adds nothing to the map.','stations':{}}
    existing['stations'].update(report); existing['probed_at']=utcnow().isoformat()
    out.write_text(json.dumps(existing,indent=2)+'\n')

def latest_capture(station,kind):
    metas=[]
    for base in (RAW/station,CAPTURES/station):
        if base.exists(): metas+=list(base.glob(f'*-{kind}.meta.json'))
    best=None
    for path in sorted(metas):
        meta=json.loads(path.read_text())
        if meta.get('status')==200 and meta.get('kind')==kind and (best is None or meta['retrieved_at']>best[1]['retrieved_at']): best=(path,meta)
    if not best: raise FileNotFoundError(f'{station}: no successful {kind} capture under {RAW} or {CAPTURES}')
    return best

def read_body(meta):
    raw=ROOT/meta['raw_path']; cap=ROOT/meta['capture_path']
    if raw.exists(): body=raw.read_bytes()
    elif cap.exists():
        with gzip.open(cap,'rb') as z: body=z.read()
    else: raise FileNotFoundError(f"{meta['raw_path']}: neither raw nor gzipped capture is present")
    if hashlib.sha256(body).hexdigest()!=meta['sha256']: raise ValueError(f"{meta['raw_path']}: checksum mismatch against its metadata")
    return body

def normalize_daily(features,station,source):
    """Typed daily rows with named errors. Non-numeric values are kept as text, never coerced."""
    rows={}
    for n,f in enumerate(features):
        p=f.get('properties')
        if not isinstance(p,dict): raise ValueError(f'{source}: feature {n} lacks properties')
        if p.get('monitoring_location_id')!='USGS-'+station: raise ValueError(f"{source}: feature {n} belongs to {p.get('monitoring_location_id')}, not USGS-{station}")
        if p.get('parameter_code')!='00060' or p.get('statistic_id')!='00003': raise ValueError(f'{source}: feature {n} is not daily mean discharge')
        day=p.get('time')
        try: dt.date.fromisoformat(day)
        except (TypeError,ValueError) as exc: raise ValueError(f'{source}: feature {n} has an invalid day {day!r}') from exc
        raw_value=p.get('value'); value=''
        if raw_value is not None:
            try:
                value=float(raw_value)
                if value!=value or value in (float('inf'),float('-inf')): raise ValueError
            except ValueError: value=''
        if day in rows: raise ValueError(f'{source}: duplicate daily value for {day}')
        rows[day]={'date':day,'value':value,'raw_value':'' if raw_value is None else str(raw_value),'unit':p.get('unit_of_measure') or '',
                   'approval_status':p.get('approval_status') or '','qualifiers':json.dumps(p.get('qualifier') or []),
                   'last_modified':p.get('last_modified') or '','time_series_id':p.get('time_series_id') or ''}
    return [rows[k] for k in sorted(rows)]

def gap_report(rows):
    gaps=[]; days=[dt.date.fromisoformat(r['date']) for r in rows]
    for a,b in zip(days,days[1:]):
        if (b-a).days>1: gaps.append({'after':a.isoformat(),'before':b.isoformat(),'missing_days':(b-a).days-1})
    return gaps

def normalize(stations):
    HISTORY.mkdir(parents=True,exist_ok=True); MODEL.mkdir(parents=True,exist_ok=True)
    skipped=[]
    for station in stations:
        try: meta_path,meta=latest_capture(station,'daily-00060-00003')
        except FileNotFoundError as e:
            skipped.append({'station':station,'reason':str(e)}); print(f'{station}: skipped, {e}'); continue
        payload=json.loads(read_body(meta))
        if not isinstance(payload.get('features'),list): raise ValueError(f"{meta['raw_path']}: response lacks a features list")
        complete=meta['status']==200 and meta['feature_count'] is not None and meta['feature_count']<LIMIT and not meta['next_link']
        if not complete: raise ValueError(f"{meta['raw_path']}: daily response is incomplete (features={meta['feature_count']}, next={meta['next_link']}); refusing to normalize a truncated history")
        rows=normalize_daily(payload['features'],station,meta['raw_path'])
        pruned=prune_versioned(station,'daily-00060-00003',ROOT/meta['capture_path'])
        if pruned: print(f'{station}: pruned {pruned} older versioned daily capture(s); raw copies remain under data/raw')
        out=HISTORY/f'{station}-00060-daily-mean.csv'
        with out.open('w',newline='') as fh:
            w=csv.DictWriter(fh,fieldnames=['date','value','raw_value','unit','approval_status','qualifiers','last_modified','time_series_id']); w.writeheader(); w.writerows(rows)
        numeric=[r for r in rows if r['value']!='']
        loc_meta=ts_meta=None
        try: loc_meta=latest_capture(station,'location')[1]
        except FileNotFoundError: pass
        try: ts_meta=latest_capture(station,'timeseries-metadata')[1]
        except FileNotFoundError: pass
        station_facts={}
        if loc_meta:
            feats=json.loads(read_body(loc_meta)).get('features',[])
            if feats:
                p=feats[0]['properties']; g=feats[0].get('geometry') or {}
                station_facts={k:p.get(k) for k in ('monitoring_location_name','site_type','hydrologic_unit_code','drainage_area','contributing_drainage_area','altitude','vertical_datum','county_name')}
                station_facts['coordinates_lon_lat']=g.get('coordinates')
        series=[]
        if ts_meta:
            for f in json.loads(read_body(ts_meta)).get('features',[]):
                p=f['properties']
                if p.get('parameter_code') in ('00060','00065'):
                    series.append({k:p.get(k) for k in ('id','parameter_code','parameter_name','statistic_id','computation_identifier','computation_period_identifier','begin','end','unit_of_measure','primary','sublocation_identifier')})
        gaps=gap_report(rows)
        manifest={'version':'v1','purpose':'Versionable provenance, completeness, and gap report for the USGS daily-mean discharge history of one Austin station. Raw bytes are preserved before parsing; the CSV is a typed view, not a substitute source.',
            'station_id':'USGS-'+station,'station':station_facts,'daily_request':{k:meta[k] for k in ('url','retrieved_at','status','sha256','bytes','feature_count','next_link','raw_path','capture_path')},
            'metadata_requests':{'location':{k:loc_meta[k] for k in ('url','retrieved_at','status','sha256','raw_path','capture_path')} if loc_meta else None,
                                 'time_series_metadata':{k:ts_meta[k] for k in ('url','retrieved_at','status','sha256','raw_path','capture_path')} if ts_meta else None},
            'complete_response':complete,'normalized_csv':str(out.relative_to(ROOT)),
            'series':{'parameter_code':'00060','statistic_id':'00003','meaning':'daily mean discharge, ft^3/s; a daily mean is not an instantaneous reading and hides within-day peaks',
                      'time_series_ids':sorted({r['time_series_id'] for r in rows}),'first_day':rows[0]['date'] if rows else None,'last_day':rows[-1]['date'] if rows else None,
                      'returned_days':len(rows),'numeric_days':len(numeric),'non_numeric_days':len(rows)-len(numeric),
                      'approval_counts':dict(Counter(r['approval_status'] for r in rows)),'qualifier_counts':dict(Counter(r['qualifiers'] for r in rows)),
                      'zero_days':sum(1 for r in numeric if r['value']==0)},
            'station_series_inventory_00060_00065':series,
            'gaps':{'count':len(gaps),'missing_days_total':sum(g['missing_days'] for g in gaps),'calendar_gaps':gaps,
                    'meaning':'Days the provider did not return. They are absent from the CSV and are never treated as zero flow.'},
            'limits':['Daily means describe the station, not any swimming reach.','Provisional values may be revised by USGS.','This archive is context for percentiles and event detection; it fits no swimming rule.']}
        (MODEL/f'{station}-daily-history-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
        print(f"{station}: {len(rows)} days {rows[0]['date'] if rows else '-'}..{rows[-1]['date'] if rows else '-'}, {len(gaps)} calendar gaps ({sum(g['missing_days'] for g in gaps)} missing days)")
    (MODEL/'daily-history-skipped.json').write_text(json.dumps({'skipped':skipped,'note':'stations whose daily-mean capture is missing or failed; no CSV, no ledger, no context until a later collect succeeds'},indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(); sub=p.add_subparsers(dest='cmd',required=True)
    c=sub.add_parser('collect'); c.add_argument('--stations',nargs='+',default=AUSTIN_STATIONS); c.add_argument('--pause-seconds',type=float,default=1.0)
    n=sub.add_parser('normalize'); n.add_argument('--stations',nargs='+',default=AUSTIN_STATIONS)
    q=sub.add_parser('probe'); q.add_argument('--stations',nargs='+',required=True); q.add_argument('--pause-seconds',type=float,default=1.0)
    a=p.parse_args()
    if a.cmd=='collect': collect(a.stations,a.pause_seconds)
    elif a.cmd=='probe': probe(a.stations,a.pause_seconds)
    else: normalize(a.stations)

