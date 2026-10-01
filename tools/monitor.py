#!/usr/bin/env python3
"""Free/local acquisition -> normalization -> deterministic assessment. No delivery."""
import argparse, datetime as dt, hashlib, json, math, sqlite3, sys, time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT=Path(__file__).resolve().parents[1]; RAW=ROOT/'data/raw/usgs'; NORM=ROOT/'data/normalized'; APP=ROOT/'app'
BASE='https://api.waterdata.usgs.gov/ogcapi/v1/collections'

def now(): return dt.datetime.now(dt.timezone.utc).isoformat()
def save(kind,url,status,body,error=None):
    RAW.mkdir(parents=True,exist_ok=True); stamp=dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    p=RAW/f'{stamp}-{kind}.json'; p.write_bytes(body)
    meta={'url':url,'retrieved_at':now(),'status':status,'sha256':hashlib.sha256(body).hexdigest(),'error':error,'pagination':'first response; inspect links before expanding'}
    p.with_suffix('.meta.json').write_text(json.dumps(meta,indent=2)); return p
def request(kind,url):
    try:
        with urlopen(Request(url,headers={'User-Agent':'swimming-hole-alerts/0.1'}),timeout=30) as r:
            body=r.read(); return save(kind,url,r.status,body)
    except HTTPError as e: return save(kind,url,e.code,e.read() or b'',str(e))
    except URLError as e: return save(kind,url,0,b'',str(e))
def collect(stations):
    # Monitoring-location calls are stable OGC API records. Continuous collection is attempted
    # separately because available collection names/filters are provider-controlled.
    start=(dt.datetime.now(dt.timezone.utc)-dt.timedelta(days=2)).strftime('%Y-%m-%dT%H:%M:%SZ')
    for s in stations:
        request('location-'+s, BASE+'/monitoring-locations/items?'+urlencode({'f':'json','id':'USGS-'+s,'limit':'1'}))
        request('continuous-'+s, BASE+'/continuous/items?'+urlencode({'f':'json','monitoring_location_id':'USGS-'+s,'datetime':start+'/..','limit':'10000'}))
        # The continuous collection can paginate before reaching the newest value.
        # Preserve a separate latest-series response for current assessments.
        request('latest-continuous-'+s, BASE+'/latest-continuous/items?'+urlencode({'f':'json','monitoring_location_id':'USGS-'+s,'limit':'100'}))
    print('USGS acquisition complete: two-day window and latest-series responses saved raw; inspect series and qualifiers before interpreting.')
def normalize():
    NORM.mkdir(parents=True,exist_ok=True); db=sqlite3.connect(NORM/'water.sqlite')
    db.execute('create table if not exists responses(path text primary key, url text, retrieved_at text, status integer, sha256 text)')
    db.execute('create table if not exists observations(provider text, station_id text, series_id text, parameter text, unit text, observed_at text, retrieved_at text, value real, qualifiers text, raw_path text, primary key(station_id,series_id,observed_at,raw_path))')
    count=0
    # Include historical acquisitions stored in their own raw namespace.  They enter
    # the same typed collection only after their preserved response is parsed.
    for meta_path in list(RAW.glob('*.meta.json')) + list((ROOT/'data/raw/usgs-history').rglob('*.meta.json')) if (ROOT/'data/raw/usgs-history').exists() else list(RAW.glob('*.meta.json')):
        meta=json.loads(meta_path.read_text()); raw=meta_path.with_suffix('').with_suffix('.json')
        db.execute('insert or replace into responses values(?,?,?,?,?)',(str(raw.relative_to(ROOT)),meta['url'],meta['retrieved_at'],meta['status'],meta['sha256']))
        # Keep schema parsing intentionally conservative. OGC feature fields vary by collection;
        # unknown payloads remain raw rather than becoming fictional observations.
        if meta['status']==200 and raw.exists():
            try: payload=json.loads(raw.read_text())
            except json.JSONDecodeError as exc: raise ValueError(f'{raw}: malformed USGS JSON: {exc}') from exc
            if not isinstance(payload.get('features'),list):
                raise ValueError(f'{raw}: USGS response lacks features list')
            for f in payload.get('features',[]):
                p=f.get('properties',{}); val=p.get('value') if p.get('value') is not None else p.get('result')
                when=p.get('time') or p.get('datetime') or p.get('observation_time')
                station=p.get('monitoring_location_id') or p.get('site_no')
                try: value=float(val)
                except (TypeError,ValueError): continue
                if not math.isfinite(value): raise ValueError(f'{raw}: non-finite USGS value for {station} at {when}')
                if station and when:
                    db.execute('insert or ignore into observations values(?,?,?,?,?,?,?,?,?,?)',('USGS',str(station),str(p.get('time_series_id','unknown')),str(p.get('parameter_code','unknown')),str(p.get('unit_of_measure',p.get('unit','unknown'))),str(when),meta['retrieved_at'],value,json.dumps(p.get('qualifier') or p.get('qualifiers') or []),str(raw.relative_to(ROOT)))); count+=1
    db.commit(); db.close(); print(f'Normalized {count} typed observations; unknown schemas retained only as raw.')
def load_park_notices():
    p=APP/'tpwd-alerts.json'
    return json.loads(p.read_text()) if p.exists() else None

def apply_park_notices(holes,notices,at):
    """Operator alerts never color a place; they can only hold a green back to yellow or say they were not checked."""
    for hole in holes:
        park=hole.get('park_alerts')
        if not park: continue
        rec=(notices or {}).get('parks',{}).get(park)
        if not rec or not rec.get('checked'):
            why=(rec or {}).get('reason','no TPWD alert check on file')
            hole['park_notice']={'checked':False,'reason':why,'source':(rec or {}).get('url')}
            if hole['status'] in ('green','yellow','red'): hole['evidence']=f"{hole['evidence']} · TPWD alerts not checked ({why})"
            continue
        flagged=rec.get('flagged',[])
        hole['park_notice']={'checked':True,'retrieved_at':rec.get('retrieved_at'),'items':len(rec.get('items',[])),'flagged':[{'title':i['title'],'watch_terms':i['watch_terms']} for i in flagged],'source':rec.get('url')}
        if flagged and hole['status']=='green':
            hole['status']='yellow'; hole['reason']=f"{hole['reason']}; TPWD alert '{flagged[0]['title']}' mentions {', '.join(flagged[0]['watch_terms'])} — read it first"
        elif flagged and hole['status'] in ('yellow','red'):
            hole['reason']=f"{hole['reason']}; TPWD alert '{flagged[0]['title']}' mentions {', '.join(flagged[0]['watch_terms'])}"

FLOW_COLOR_MAX_AGE=dt.timedelta(hours=6)

def evaluate_rule(rule, reading, at):
    """A scoped flow band applies only to a compatible, recent observation."""
    if not reading: return None, 'No compatible discharge reading'
    if reading['parameter'] != rule['parameter'] or reading['unit'] not in ('ft^3/s','ft3/s','cfs'):
        return None, 'Station reading has an incompatible parameter or unit'
    try:
        observed=dt.datetime.fromisoformat(reading['observed_at'].replace('Z','+00:00'))
    except (TypeError, ValueError):
        return None, 'Station observation time is invalid'
    age=(at-observed).total_seconds()
    if age < -300 or age >= FLOW_COLOR_MAX_AGE.total_seconds(): return None, 'Station reading is too old for a planning cue or future-dated'
    value=reading['value']
    if not isinstance(value,(int,float)) or not math.isfinite(value): return None,'Station value is non-finite or invalid'
    band=next((b for b in rule['bands'] if ('lt' not in b or value < b['lt']) and ('gte' not in b or value >= b['gte'])),None)
    return band, None if band else 'Reading falls outside the published rule bands'

def assess(at=None):
    if not (ROOT/'data/holes.json').exists() or not (ROOT/'data/rules.json').exists():
        raise SystemExit('assess is a lens-side step (places and rules); this repo publishes the water-state bundle instead: python3 tools/publish_bundle.py')
    at=at or dt.datetime.now(dt.timezone.utc)
    parsed=ROOT/'data/parsed/latest-by-station.json'
    if parsed.exists():
        rows=[(r['station_id'],r['parameter'],r['unit'],r['observed_at'],r['value'],r['qualifiers']) for r in json.loads(parsed.read_text())]
    else:
        # Compatibility fallback for a first local run; the documented path parses first.
        db=sqlite3.connect(NORM/'water.sqlite'); rows=db.execute("select station_id,parameter,unit,observed_at,value,qualifiers from observations where observed_at in (select max(observed_at) from observations o2 where o2.station_id=observations.station_id and o2.parameter=observations.parameter group by o2.station_id,o2.parameter)").fetchall(); db.close()
    # Keep 00060 and 00065 distinct. Newest per parameter is a measurement, not a swim verdict.
    readings={}
    for station,param,unit,when,value,qualifiers in rows:
        readings.setdefault(station,[]).append({'parameter':param,'unit':unit,'observed_at':when,'value':value,'qualifiers':json.loads(qualifiers)})
    (APP/'gauge-readings.json').write_text(json.dumps({'generated_at':now(),'readings':readings},indent=2))
    holes=json.loads((ROOT/'data/holes.json').read_text())
    latest={(station,param):{'parameter':param,'unit':unit,'observed_at':when,'value':value,'qualifiers':qualifiers} for station,param,unit,when,value,qualifiers in rows}
    # Inventory copy can carry historical example labels. They are never live assessments.
    for hole in holes:
        if hole['kind']=='managed pool': reason='City operator schedule is assessed separately from creek flow'
        elif hole.get('gauge_context'): reason='Mapped station is context only; no supported local condition rule'
        elif not hole.get('gauge'): reason='No defensible local predictor or gauge relationship linked'
        else: reason='Station linked, but no documented place-specific condition rule'
        hole.update(status='gray',reason=reason,evidence='Coverage gap · check source',observed_at=None,valid_until=None)
    for rule in json.loads((ROOT/'data/rules.json').read_text()):
        reading=latest.get(('USGS-'+rule['station_id'],rule['parameter'])) or latest.get((rule['station_id'],rule['parameter']))
        band,problem=evaluate_rule(rule,reading,at)
        for hole in holes:
            if hole['id'] not in rule['place_ids']: continue
            if hole.get('gauge') != rule['station_id']:
                raise ValueError(f"Rule {rule['id']} references {hole['id']} without matching gauge")
            if problem:
                hole.update(status='gray',reason=problem,evidence=rule.get('evidence_label','Rule available').replace('Estimate','Rule available; no fresh reading'))
            else:
                valid=(dt.datetime.fromisoformat(reading['observed_at'].replace('Z','+00:00'))+FLOW_COLOR_MAX_AGE).isoformat()
                hole.update(status=band['status'],reason=f"{rule['station_id']} measured {reading['value']:g} {rule['unit']}; {rule['id']} applies",evidence=rule.get('evidence_label') or f"Flow estimate · {rule['basis']}",observed_at=reading['observed_at'],valid_until=valid,rule_source=rule['source'])
    apply_park_notices(holes,load_park_notices(),at)
    output=[{k:h.get(k) for k in ('id','name','status','reason','evidence','gauge','access','source','observed_at','valid_until','rule_source','park_notice')} for h in holes]
    (APP/'status.json').write_text(json.dumps({'generated_at':at.isoformat(),'delivery':'disabled','places':output},indent=2))
    preview='Delivery disabled — preview only.\n'+''.join(f"{h['name']}: {h['status']} · {h['reason']}. Evidence: {h['evidence']}. Access: {h['access']}. Water quality: unknown.\n" for h in output if h['id'] in ('twin-falls','bull-creek-district','barton-springs','commons-ford','emma-long'))
    (ROOT/'outputs/notification-preview.txt').write_text(preview)
    print('Assessment written from parsed signals. Only documented scoped rules with fresh compatible readings may color a creek place.')
if __name__=='__main__':
    p=argparse.ArgumentParser(); sub=p.add_subparsers(dest='cmd',required=True)
    c=sub.add_parser('collect'); c.add_argument('--stations',nargs='*',default=[]); c.add_argument('--inventory',action='store_true',help='every station in data/stations-regional.json plus the Austin ten')
    sub.add_parser('normalize'); sub.add_parser('assess'); a=p.parse_args()
    if a.cmd=='collect' and a.inventory:
        import sys as _s; _s.path.insert(0,str(ROOT/'tools')); from station_lists import all_stations; a.stations=all_stations()
    if a.cmd=='collect' and not a.stations: p.error('collect needs --stations or --inventory')
    {'collect':lambda:collect(a.stations),'normalize':normalize,'assess':assess}[a.cmd]()
