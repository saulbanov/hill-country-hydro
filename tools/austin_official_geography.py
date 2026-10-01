#!/usr/bin/env python3
"""Acquire City of Austin GIS geometry (PARD park boundaries, creek centerlines), then normalize.

Two official City of Austin ArcGIS feature layers are preserved verbatim, one response
per layer, before anything is drawn:

- BOUNDARIES_city_of_austin_parks  -> PARD-owned parkland polygons
- INLANDWATERS_creeks_lines         -> Watershed Protection creek centerlines

A park polygon says where PARD parkland is. A creek line says where the City draws the
channel. Neither says that swimming is permitted, that water is present, or that a
reach is reachable. This layer is orientation only.
"""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT=Path(__file__).resolve().parents[1]
RAW=ROOT/'data/raw/austin-gis'
OUT_PARKS=ROOT/'app/austin-parks.geojson'
OUT_CREEKS=ROOT/'app/austin-creeks-city.geojson'
MANIFEST=ROOT/'data/model/austin-city-geography-manifest.json'
BASE='https://services.arcgis.com/0L95CJ0VTaxqcmED/arcgis/rest/services'
BBOX='-97.98,30.10,-97.64,30.48'
PARK_TERMS=['Barton Creek Greenbelt','Bull Creek','St. Edwards','Blunn Creek','Emma Long','Commons Ford','Stacy','Zilker',
            'Deep Eddy','Shoal Creek','Walnut Creek','Barton Springs']
CREEKS=['Barton Creek','Bull Creek','Shoal Creek','Blunn Creek','Walnut Creek','Onion Creek','Williamson Creek']
LAYERS={
    'parks':{
        'service':'BOUNDARIES_city_of_austin_parks',
        'params':{'where':' OR '.join(f"LOCATION_NAME LIKE '%{t}%'" for t in PARK_TERMS),
                  'outFields':'LOCATION_NAME,ADDRESS,ASSET_STATUS,PARK_TYPE,OWNER_NAME,MANAGING_NAME,MODIFIED_DATE,GLOBALID'},
        'license':'City of Austin open data; PARD-owned parkland boundaries built on the NRPA GIS data model. Boundaries are approximate and not a survey.'},
    'creeks':{
        'service':'INLANDWATERS_creeks_lines',
        'params':{'where':'STREAM_NAME IN ('+','.join(f"'{c}'" for c in CREEKS)+')',
                  'outFields':'STREAM_NAME,CREEK_TYPE,WATERSHED_NAME,GEOMORPHIC_REACH_ID,CREEK_ID,MODIFIED_DATE',
                  'geometry':BBOX,'geometryType':'esriGeometryEnvelope','inSR':'4326','spatialRel':'esriSpatialRelIntersects'},
        'license':'City of Austin open data; Watershed Protection creek centerlines assembled from orthophotography, LiDAR planimetrics, and construction plans.'},
}
COMMON={'returnGeometry':'true','outSR':'4326','geometryPrecision':'5','f':'geojson'}

def query_url(layer):
    spec=LAYERS[layer]
    return f"{BASE}/{spec['service']}/FeatureServer/0/query?"+urlencode({**spec['params'],**COMMON})

def collect(layers):
    RAW.mkdir(parents=True,exist_ok=True)
    failures=0
    for layer in layers:
        url=query_url(layer); at=dt.datetime.now(dt.timezone.utc); status=0; error=None; body=b''
        try:
            with urlopen(Request(url,headers={'User-Agent':'austin-swim-map/0.1 source-first local project'}),timeout=120) as response:
                body=response.read(); status=response.status
        except HTTPError as exc: body=exc.read() or b''; status=exc.code; error=str(exc)
        except URLError as exc: error=str(exc)
        stem=at.strftime('%Y%m%dT%H%M%S%fZ'); path=RAW/f'{stem}-{layer}.geojson'; path.write_bytes(body)
        path.with_suffix('.meta.json').write_text(json.dumps({'url':url,'layer':layer,'service':LAYERS[layer]['service'],'retrieved_at':at.isoformat(),
            'status':status,'sha256':hashlib.sha256(body).hexdigest(),'error':error,'license':LAYERS[layer]['license'],
            'interpretation':'none; verbatim City GIS response'},indent=2)+'\n')
        print(f'preserved City GIS {layer}: {path.relative_to(ROOT)} HTTP {status}, {len(body)} bytes')
        if status!=200: failures+=1
    if failures: raise SystemExit(2)

def latest_good(layer):
    metas=sorted(RAW.glob(f'*-{layer}.meta.json'),reverse=True)
    for meta_path in metas:
        meta=json.loads(meta_path.read_text())
        if meta.get('status')==200: return meta_path,meta
    raise FileNotFoundError(f'{RAW}: no successful City GIS capture for {layer}')

def load(layer):
    meta_path,meta=latest_good(layer)
    raw=meta_path.with_name(meta_path.name.removesuffix('.meta.json')+'.geojson'); body=raw.read_bytes()
    if hashlib.sha256(body).hexdigest()!=meta['sha256']: raise ValueError(f'{raw}: checksum mismatch')
    try: payload=json.loads(body)
    except json.JSONDecodeError as exc: raise ValueError(f'{raw}: invalid JSON: {exc}') from exc
    if 'error' in payload: raise ValueError(f'{raw}: ArcGIS error {payload["error"]}')
    if payload.get('properties',{}).get('exceededTransferLimit'): raise ValueError(f'{raw}: response truncated by transfer limit; page the query before drawing')
    if not isinstance(payload.get('features'),list): raise ValueError(f'{raw}: missing features list')
    return raw,meta,payload

def normalize():
    manifest={'license':'City of Austin open data via ArcGIS Online; see each layer note','layers':{},
              'interpretation':'Display geometry only. A park polygon is PARD parkland, not swimming permission; a creek centerline is the City channel line, not a wet or reachable reach.'}
    raw,meta,payload=load('parks'); parks=[]
    for f in payload['features']:
        g=f.get('geometry') or {}; p=f.get('properties',{})
        if g.get('type') not in ('Polygon','MultiPolygon'): raise ValueError(f'{raw}: park {p.get("LOCATION_NAME")} is not a polygon')
        parks.append({'type':'Feature','id':f'coa-park/{p.get("GLOBALID")}','geometry':g,
            'properties':{'name':p.get('LOCATION_NAME'),'address':p.get('ADDRESS'),'park_type':p.get('PARK_TYPE'),'asset_status':p.get('ASSET_STATUS'),
                          'feature_kind':'park','source':'City of Austin PARD park boundaries','retrieved_at':meta['retrieved_at'],'access_claim':'none'}})
    if len(parks)<10: raise ValueError(f'{raw}: only {len(parks)} park polygons; source may be incomplete')
    OUT_PARKS.write_text(json.dumps({'type':'FeatureCollection','features':parks},separators=(',',':'))+'\n')
    manifest['layers']['parks']={'raw_path':str(raw.relative_to(ROOT)),'url':meta['url'],'retrieved_at':meta['retrieved_at'],'sha256':meta['sha256'],
                                 'feature_count':len(parks),'names':sorted({p['properties']['name'] for p in parks}),'license':meta['license']}
    raw,meta,payload=load('creeks'); creeks=[]
    for f in payload['features']:
        g=f.get('geometry') or {}; p=f.get('properties',{})
        if g.get('type') not in ('LineString','MultiLineString'): raise ValueError(f'{raw}: creek {p.get("STREAM_NAME")} is not a line')
        creeks.append({'type':'Feature','id':f'coa-creek/{p.get("CREEK_ID")}','geometry':g,
            'properties':{'name':(p.get('STREAM_NAME') or '').title(),'creek_type':p.get('CREEK_TYPE'),'reach_id':p.get('GEOMORPHIC_REACH_ID'),
                          'watershed':p.get('WATERSHED_NAME'),'feature_kind':'waterway','source':'City of Austin Watershed Protection creek centerlines',
                          'retrieved_at':meta['retrieved_at'],'access_claim':'none'}})
    if len(creeks)<50: raise ValueError(f'{raw}: only {len(creeks)} creek segments; source may be incomplete')
    OUT_CREEKS.write_text(json.dumps({'type':'FeatureCollection','features':creeks},separators=(',',':'))+'\n')
    manifest['layers']['creeks']={'raw_path':str(raw.relative_to(ROOT)),'url':meta['url'],'retrieved_at':meta['retrieved_at'],'sha256':meta['sha256'],
                                  'feature_count':len(creeks),'names':sorted({c['properties']['name'] for c in creeks}),'license':meta['license']}
    MANIFEST.write_text(json.dumps(manifest,indent=2)+'\n')
    print(f'normalized City geometry: {len(parks)} park polygons, {len(creeks)} creek segments')

if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('stage',choices=['collect','normalize'])
    parser.add_argument('--layers',nargs='+',default=list(LAYERS),choices=list(LAYERS))
    args=parser.parse_args()
    {'collect':lambda:collect(args.layers),'normalize':normalize}[args.stage]()
