#!/usr/bin/env python3
"""Validate a forecast-based experiment label against what was actually observed. No interpretation of swimming.

Each run preserves, under the versioned ``data/captures/nws/`` folder:
* the NWS point forecast for Austin (the same product the storm-week protocol was written from);
* the last 24 h of NWS hourly observations at Camp Mabry (KATT) and Austin-Bergstrom (KAUS).

Then it normalizes daily observed precipitation per station into ``data/history/nws-observed-daily.csv``
(hours reported, hours with a precipitation value, summed inches; hours without a value are NOT zero)
and writes ``data/model/storm-week-validation.json``: for each calendar day, the forecast rain chance as
first captured, what the stations reported, and which USGS stations reached their own ledger high
threshold. A "storm week" is a forecast until this file shows rain and a gauge response.
"""
import argparse, csv, datetime as dt, gzip, hashlib, json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
CAP=ROOT/'data/captures/nws'; HISTORY=ROOT/'data/history'; MODEL=ROOT/'data/model'
TZ=ZoneInfo('America/Chicago'); UA='swimming-hole-alerts/0.1 (saul.elbein@gmail.com)'
FORECAST_URL='https://api.weather.gov/gridpoints/EWX/156,91/forecast'
STATIONS={'KATT':'Austin Camp Mabry','KAUS':'Austin-Bergstrom International Airport'}
USGS=['08154700','08155240','08155300','08155400','08155500','08156800','08158930','08158970','08159000']

def fetch(url):
    try:
        with urlopen(Request(url,headers={'User-Agent':UA,'Accept':'application/geo+json, application/json'}),timeout=90) as r: return r.status,r.read(),None
    except HTTPError as e: return e.code,(e.read() or b''),str(e)
    except URLError as e: return 0,b'',str(e)

def preserve(kind,url):
    CAP.mkdir(parents=True,exist_ok=True); status,body,error=fetch(url); at=dt.datetime.now(dt.timezone.utc)
    stem=f"{at.strftime('%Y%m%dT%H%M%SZ')}-{kind}"; path=CAP/f'{stem}.json.gz'
    with gzip.open(path,'wb',compresslevel=9) as z: z.write(body)
    meta={'url':url,'retrieved_at':at.isoformat(),'status':status,'error':error,'sha256':hashlib.sha256(body).hexdigest(),'bytes':len(body),'capture_path':str(path.relative_to(ROOT)),'interpretation':'none; verbatim NWS capture'}
    (CAP/f'{stem}.meta.json').write_text(json.dumps(meta,indent=2)); return meta,body

def collect(hours):
    end=dt.datetime.now(dt.timezone.utc); start=end-dt.timedelta(hours=hours)
    meta,_=preserve('austin-forecast',FORECAST_URL); print('forecast',meta['status'],meta['bytes'],'bytes')
    for sid in STATIONS:
        url=f"https://api.weather.gov/stations/{sid}/observations?start={start.strftime('%Y-%m-%dT%H:%M:%SZ')}&end={end.strftime('%Y-%m-%dT%H:%M:%SZ')}&limit=500"
        meta,_=preserve(f'obs-{sid}',url); print(sid,meta['status'],meta['bytes'],'bytes')

def captures(kind):
    """Successful captures of one kind, oldest first. Accepts the plain .json capture made before this tool existed."""
    out=[]
    for m in sorted(CAP.glob(f'*-{kind}.meta.json')):
        meta=json.loads(m.read_text())
        path=meta.get('capture_path')
        if not path:
            plain=m.with_name(m.name.replace('.meta.json','.json'))
            if plain.exists(): meta['capture_path']=str(plain.relative_to(ROOT))
        if meta.get('status')==200 and meta.get('capture_path') and (ROOT/meta['capture_path']).exists(): out.append(meta)
    return out

def load(meta):
    path=ROOT/meta['capture_path']
    body=gzip.open(path,'rb').read() if path.suffix=='.gz' else path.read_bytes()
    if hashlib.sha256(body).hexdigest()!=meta['sha256']: raise ValueError(f"{meta['capture_path']}: checksum mismatch")
    return json.loads(body)

def observed_daily():
    """Per local calendar day and station: hours reported, hours carrying a precipitation value, summed inches."""
    days={}
    for sid in STATIONS:
        seen=set()
        for meta in captures(f'obs-{sid}'):
            for f in load(meta).get('features',[]):
                p=f['properties']; ts=p.get('timestamp')
                if not ts or ts in seen: continue
                seen.add(ts); local=dt.datetime.fromisoformat(ts.replace('Z','+00:00')).astimezone(TZ)
                key=(local.date().isoformat(),sid); d=days.setdefault(key,{'date':key[0],'station':sid,'hours_reported':0,'hours_with_precip_value':0,'precip_in':0.0,'wet_descriptions':0})
                d['hours_reported']+=1
                mm=(p.get('precipitationLastHour') or {}).get('value')
                if mm is not None: d['hours_with_precip_value']+=1; d['precip_in']+=mm/25.4
                if any(w in (p.get('textDescription') or '').lower() for w in ('rain','thunder','drizzle','shower')): d['wet_descriptions']+=1
    rows=[days[k] for k in sorted(days)]
    for r in rows: r['precip_in']=round(r['precip_in'],3)
    HISTORY.mkdir(parents=True,exist_ok=True)
    with (HISTORY/'nws-observed-daily.csv').open('w',newline='') as fh:
        w=csv.DictWriter(fh,fieldnames=['date','station','hours_reported','hours_with_precip_value','precip_in','wet_descriptions']); w.writeheader(); w.writerows(rows)
    return rows

def forecast_by_day():
    """Rain chance for each day as FIRST captured (so later forecasts do not rewrite the prediction being tested)."""
    out={}
    for meta in captures('austin-forecast'):
        for p in load(meta).get('properties',{}).get('periods',[]):
            day=p['startTime'][:10]; pop=(p.get('probabilityOfPrecipitation') or {}).get('value')
            entry=out.setdefault(day,{'first_forecast_retrieved_at':meta['retrieved_at'],'max_rain_chance_pct':None,'short_forecasts':[]})
            if meta['retrieved_at']==entry['first_forecast_retrieved_at']:
                if pop is not None: entry['max_rain_chance_pct']=max(pop,entry['max_rain_chance_pct'] or 0)
                entry['short_forecasts'].append(p['shortForecast'])
    return out

def gauge_response():
    out={}
    for st in USGS:
        led=MODEL/f'{st}-event-ledger.json'; hist=HISTORY/f'{st}-00060-daily-mean.csv'
        if not led.exists() or not hist.exists(): continue
        high=json.loads(led.read_text())['event_definition']['high_threshold']
        with hist.open() as fh:
            for r in csv.DictReader(fh):
                if r['date']<'2026-09-20' or r['value']=='': continue
                v=float(r['value']); d=out.setdefault(r['date'],{'stations_at_or_above_high_threshold':[],'max_daily_mean_cfs':0.0})
                d['max_daily_mean_cfs']=max(d['max_daily_mean_cfs'],v)
                if v>=high: d['stations_at_or_above_high_threshold'].append(st)
    return out

def validate():
    obs=observed_daily(); fc=forecast_by_day(); gr=gauge_response()
    days=sorted(set(fc)|{r['date'] for r in obs}|set(gr))
    rows=[]
    for day in days:
        o={r['station']:r for r in obs if r['date']==day}
        rain=[r for r in o.values() if r['precip_in']>0]
        wet_only=[r for r in o.values() if r['precip_in']==0 and r['wet_descriptions']>0]
        if not o: observed='no station observations captured for this day'
        elif rain: observed='measured rain at '+', '.join(f"{s} ({r['precip_in']} in over {r['hours_with_precip_value']} h with values; {r['wet_descriptions']} wet hourly descriptions)" for s,r in o.items() if r in rain)
        elif wet_only: observed='wet hourly description(s) only, no measured amount, at '+', '.join(f"{s} ({r['wet_descriptions']} of {r['hours_reported']} reports)" for s,r in o.items() if r in wet_only)
        else: observed='no precipitation value or wet description in the captured hours (absence of a value is not zero)'
        g=gr.get(day,{})
        rows.append({'date':day,'forecast':fc.get(day),'observed':observed,'station_days':list(o.values()),'gauges':g,
                     'verdict':('storm day: rain reported and at least one gauge reached its event threshold' if rain and g.get('stations_at_or_above_high_threshold') else
                               'measured rain; no gauge reached its event threshold (yet)' if rain else
                               'wet descriptions only; no measured rain and no gauge event' if wet_only else
                               'gauge event without captured rain report' if g.get('stations_at_or_above_high_threshold') else 'no storm evidence in captured sources')})
    out={'purpose':'Checks the forecast-based "storm week" label against NWS station observations and USGS gauge response, day by day. A label is validated only by observed rain and a measured gauge event.',
         'sources':{'forecast':FORECAST_URL,'observations':{s:f'https://api.weather.gov/stations/{s}/observations' for s in STATIONS},'gauges':'data/history/<station>-00060-daily-mean.csv with thresholds from data/model/<station>-event-ledger.json'},
         'caveats':['NWS hourly observations carry precipitationLastHour only when the station reports a value; hours without one are counted as unreported, never as zero.','Daily means lag by a day; the gauge column fills in after the next weekly history refresh or a current-window collection.','A wet hourly description (rain, showers, thunder) is counted separately from measured inches.'],
         'generated_at':dt.datetime.now(dt.timezone.utc).isoformat(),'days':rows}
    (MODEL/'storm-week-validation.json').write_text(json.dumps(out,indent=2)+'\n')
    for r in rows[-8:]: print(r['date'],'| forecast max',(r['forecast'] or {}).get('max_rain_chance_pct'),'% |',r['verdict'])

if __name__=='__main__':
    p=argparse.ArgumentParser(); sub=p.add_subparsers(dest='cmd',required=True)
    c=sub.add_parser('collect'); c.add_argument('--hours',type=int,default=26)
    sub.add_parser('validate'); a=p.parse_args()
    collect(a.hours) if a.cmd=='collect' else validate()
