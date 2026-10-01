#!/usr/bin/env python3
"""Preserve bounded historical USGS continuous-value windows before normalization.

This is acquisition only.  It makes no swim assessment, silently drops no gaps,
and will refuse a window that reaches the provider's response limit.
"""
import argparse, datetime as dt, hashlib, json, time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

ROOT=Path(__file__).resolve().parents[1]
BASE='https://api.waterdata.usgs.gov/ogcapi/v1/collections/continuous/items'

def parse_day(value):
    return dt.datetime.fromisoformat(value).replace(tzinfo=dt.timezone.utc)

def stamp(value):
    return value.strftime('%Y%m%dT%H%M%SZ')

def file_stem(start,end):
    return f'{stamp(start)}--{stamp(end)}-continuous'

def metadata_paths(station,start,end):
    directory=ROOT/'data/raw/usgs-history'/station
    return sorted(directory.glob(file_stem(start,end)+'*.meta.json'))

def read_metadata(station,start,end):
    values=[]
    for path in metadata_paths(station,start,end):
        try: values.append((path,json.loads(path.read_text())))
        except (ValueError,OSError): pass
    return values

def complete(meta,limit):
    return meta.get('status')==200 and meta.get('feature_count') is not None and meta['feature_count']<limit and not meta.get('next_link')

def paginated(meta,limit):
    return meta.get('status')==200 and (meta.get('feature_count',0)>=limit or bool(meta.get('next_link')))

def save(station,start,end,url,status,body,error=None):
    directory=ROOT/'data/raw/usgs-history'/station
    directory.mkdir(parents=True,exist_ok=True)
    stem=file_stem(start,end); path=directory/f'{stem}.json'
    # A changed retry response is a distinct raw source record. Never overwrite a
    # 429, a paginated page, or an earlier response merely because its request
    # window has the same timestamps.
    if path.exists() and path.read_bytes()!=body:
        attempt=2
        while (directory/f'{stem}.attempt-{attempt}.json').exists(): attempt+=1
        path=directory/f'{stem}.attempt-{attempt}.json'
    path.write_bytes(body)
    try:
        payload=json.loads(body)
        returned=len(payload.get('features',[]))
        links=payload.get('links',[])
        next_link=next((x.get('href') for x in links if x.get('rel')=='next'),None)
    except (json.JSONDecodeError, UnicodeDecodeError):
        returned=None; next_link=None
    meta={
        'source':'USGS OGC API continuous collection', 'url':url,
        'station_id':'USGS-'+station, 'start':start.isoformat(), 'end_exclusive':end.isoformat(),
        'retrieved_at':dt.datetime.now(dt.timezone.utc).isoformat(), 'status':status,
        'sha256':hashlib.sha256(body).hexdigest(), 'feature_count':returned,
        'next_link':next_link, 'error':error,
        'completeness':'complete only when status is 200, feature_count is below the requested limit, and next_link is null'
    }
    path.with_suffix('.meta.json').write_text(json.dumps(meta,indent=2))
    return path,meta

def existing_ok(station,start,end):
    return any(complete(value,10000) for _,value in read_metadata(station,start,end))

def get_window(station,start,end,limit):
    query=urlencode({'f':'json','monitoring_location_id':'USGS-'+station,
                     'datetime':start.strftime('%Y-%m-%dT%H:%M:%SZ')+'/'+end.strftime('%Y-%m-%dT%H:%M:%SZ'),
                     'limit':str(limit)})
    url=BASE+'?'+query
    try:
        with urlopen(Request(url,headers={'User-Agent':'swimming-hole-alerts/0.1 historical-backfill'}),timeout=60) as response:
            body=response.read(); return save(station,start,end,url,response.status,body)
    except HTTPError as err: return save(station,start,end,url,err.code,err.read() or b'',str(err))
    except URLError as err: return save(station,start,end,url,0,b'',str(err))

def acquire_or_split(station,start,end,limit,pause,minimum_window_hours,stats):
    if any(complete(value,limit) for _,value in read_metadata(station,start,end)):
        stats['skipped']+=1; print(f'skip complete {start.date()} to {end.date()}'); return True
    saved=read_metadata(station,start,end)
    existing_page=next((value for _,value in saved if paginated(value,limit)),None)
    if existing_page:
        path=next(path for path,value in saved if value is existing_page); meta=existing_page
        print(f'{start.date()} to {end.date()}: preserved paginated response; splitting without re-fetching')
    else:
        path,meta=get_window(station,start,end,limit); stats['fetched']+=1
        print(f"{start.date()} to {end.date()}: status {meta['status']}, {meta.get('feature_count')} features, {'complete' if complete(meta,limit) else 'INCOMPLETE'}")
    if complete(meta,limit): return True
    duration_hours=(end-start).total_seconds()/3600
    if paginated(meta,limit) and duration_hours>minimum_window_hours:
        midpoint=start+(end-start)/2
        print(f'pagination at {path.name}; splitting into {midpoint-start} windows')
        return acquire_or_split(station,start,midpoint,limit,pause,minimum_window_hours,stats) and acquire_or_split(station,midpoint,end,limit,pause,minimum_window_hours,stats)
    stats['failed']+=1
    if meta.get('status')==429:
        print(f'preserved HTTP 429 at {path}; stop so the caller can resume later with a slower request cadence.')
    else:
        print(f'preserved incomplete response at {path}; stop before treating any later history as complete.')
    return False

def run(station,start,end,window_days,limit,pause,minimum_window_hours):
    if end <= start: raise SystemExit('--end must be after --start')
    cursor=start; stats={'fetched':0,'skipped':0,'failed':0}
    while cursor < end:
        window_end=min(cursor+dt.timedelta(days=window_days),end)
        if not acquire_or_split(station,cursor,window_end,limit,pause,minimum_window_hours,stats): break
        cursor=window_end
        if cursor < end: time.sleep(pause)
    print(f"historical acquisition: fetched={stats['fetched']} skipped_complete={stats['skipped']} incomplete_or_failed={stats['failed']}")
    if stats['failed']: raise SystemExit(2)

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--station',required=True,help='eight-digit USGS station number, without USGS-')
    parser.add_argument('--start',required=True,help='UTC day, e.g. 2021-01-01')
    parser.add_argument('--end',required=True,help='exclusive UTC day, e.g. 2026-01-01')
    parser.add_argument('--window-days',type=int,default=28)
    parser.add_argument('--limit',type=int,default=10000)
    parser.add_argument('--pause-seconds',type=float,default=.2)
    parser.add_argument('--minimum-window-hours',type=float,default=24,help='smallest interval eligible for pagination splitting')
    args=parser.parse_args()
    if args.window_days < 1 or args.limit < 1: raise SystemExit('window-days and limit must be positive')
    run(args.station,parse_day(args.start),parse_day(args.end),args.window_days,args.limit,args.pause_seconds,args.minimum_window_hours)
