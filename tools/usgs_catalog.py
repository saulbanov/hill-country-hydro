#!/usr/bin/env python3
"""Preserve the regional USGS location catalog and build a non-map master registry.

The selection is deliberately broad and does not establish current telemetry,
swimming-place linkage, or groundwater/spring causation.
"""
import argparse, datetime as dt, hashlib, json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT=Path(__file__).resolve().parents[1]
RAW=ROOT/'data/raw/usgs-catalog'; MASTER=ROOT/'data/master'
BBOX=(-100.0,29.45,-97.5,30.85)
BASE='https://api.waterdata.usgs.gov/ogcapi/v1/collections/monitoring-locations/items'

def collect():
    RAW.mkdir(parents=True,exist_ok=True)
    at=dt.datetime.now(dt.timezone.utc); query=urlencode({'f':'json','bbox':','.join(map(str,BBOX)),'limit':'10000'})
    url=f'{BASE}?{query}'; body=urlopen(Request(url,headers={'User-Agent':'swimming-hole-alerts/0.1'}),timeout=90).read()
    stamp=at.strftime('%Y%m%dT%H%M%SZ'); raw=RAW/f'{stamp}-central-texas.geojson'
    raw.write_bytes(body)
    raw.with_suffix('.meta.json').write_text(json.dumps({'url':url,'retrieved_at':at.isoformat(),'sha256':hashlib.sha256(body).hexdigest(),'bbox':BBOX,'purpose':'catalog discovery only; no map inclusion'},indent=2))
    print(f'preserved {raw.relative_to(ROOT)}')

def classify(site_type):
    if site_type.startswith('ST'): return 'surface_stream'
    if site_type=='SP': return 'surface_spring'
    if site_type=='LK': return 'surface_lake'
    if site_type.startswith('GW'): return 'groundwater_surface_relevance_unreviewed'
    return None

def normalize():
    raws=sorted(RAW.glob('*-central-texas.geojson'))
    if not raws: raise SystemExit('No preserved catalog. Run collect first.')
    raw=raws[-1]; meta=json.loads(raw.with_suffix('.meta.json').read_text()); payload=json.loads(raw.read_text())
    rows=[]
    for feature in payload['features']:
        p=feature.get('properties',{}); site_type=p.get('site_type_code','')
        category=classify(site_type)
        if not category: continue
        coords=feature.get('geometry',{}).get('coordinates',[None,None])
        rows.append({'station_id':p.get('monitoring_location_number'),'catalog_id':feature.get('id'),'name':p.get('monitoring_location_name'),'agency':p.get('agency_code'),'site_type_code':site_type,'site_type':p.get('site_type'),'category':category,'longitude':coords[0],'latitude':coords[1],'catalog_retrieved_at':meta['retrieved_at'],'raw_path':str(raw.relative_to(ROOT))})
    MASTER.mkdir(parents=True,exist_ok=True)
    with (MASTER/'usgs-central-texas-stations.jsonl').open('w') as out:
        for row in rows: out.write(json.dumps(row)+'\n')
    counts={}
    for row in rows: counts[row['category']]=counts.get(row['category'],0)+1
    (MASTER/'usgs-central-texas-stations-summary.json').write_text(json.dumps({'extent':{'west':BBOX[0],'south':BBOX[1],'east':BBOX[2],'north':BBOX[3]},'catalog_retrieved_at':meta['retrieved_at'],'source':meta['url'],'counts':counts,'limits':['Catalog presence does not establish active telemetry.','No station is added to the map by this process.','Groundwater rows are broad candidates: their relationship to a spring or surface reach is unreviewed.']},indent=2))
    print(f'normalized {len(rows)} regional USGS candidates: {counts}')

if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('stage',choices=('collect','normalize')); a=p.parse_args()
    {'collect':collect,'normalize':normalize}[a.stage]()
