#!/usr/bin/env python3
"""Version checksums for ignored Austin current USGS captures; no acquisition."""
import argparse,datetime as dt,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
RAW=ROOT/'data/raw/usgs'
OUT=ROOT/'data/model/austin-current-usgs-capture-manifest.json'
STATIONS={'08154700','08155240','08155300','08155400','08155500','08156800','08158930','08158970','08159000'}

def main(day):
    records=[]
    for meta_path in sorted(RAW.glob(f'{day}T*-*.meta.json')):
        tail=meta_path.name.split('-')[-1].removesuffix('.meta.json')
        if tail not in STATIONS: continue
        meta=json.loads(meta_path.read_text())
        raw=meta_path.with_name(meta_path.name.removesuffix('.meta.json')+'.json')
        body=raw.read_bytes()
        if hashlib.sha256(body).hexdigest()!=meta['sha256']: raise ValueError(f'{raw}: checksum mismatch')
        records.append({'raw_path':str(raw.relative_to(ROOT)),'station_id':tail,'url':meta['url'],
                        'retrieved_at':meta['retrieved_at'],'http_status':meta['status'],'sha256':meta['sha256'],
                        'error':meta.get('error')})
    if not records: raise FileNotFoundError(f'{RAW}: no Austin captures from {day}')
    OUT.write_text(json.dumps({'scope':'Austin current station captures only; raw bytes remain local',
                              'capture_day_utc':day,'station_ids':sorted(STATIONS),'captures':records},indent=2)+'\n')
    print(f'versioned provenance for {len(records)} Austin USGS responses')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--date',default=dt.datetime.now(dt.timezone.utc).strftime('%Y%m%d'),help='UTC date YYYYMMDD');a=p.parse_args()
    main(a.date)
