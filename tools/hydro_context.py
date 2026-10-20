#!/usr/bin/env python3
"""Deterministic hydrologic-context features for each Austin USGS station. Not a swim verdict.

Inputs (all local; no network):
* ``data/parsed/latest-by-station.json`` — latest typed value per station/parameter.
* ``data/normalized/water.sqlite`` — the trailing window of typed observations preserved by monitor.py.
* ``data/history/<station>-00060-daily-mean.csv`` — the station's own daily-mean record (usgs_history.py).

Output: ``app/hydro-context.json`` with, per station and parameter: the latest value and its
freshness, direction and rate over the trailing trend window, the window maximum and hours
since it, data health, and (discharge only) where the latest daily mean sits within the
station's own daily means for the same time of year. Every statement describes the station.
Nothing here maps a station onto a swimming place; that lives in place-relationships.json.
"""
import argparse, csv, datetime as dt, json, math, sqlite3, statistics
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
PARSED=ROOT/'data/parsed/latest-by-station.json'; DB=ROOT/'data/normalized/water.sqlite'
HISTORY=ROOT/'data/history'; OUT=ROOT/'app/hydro-context.json'
import sys as _sys; _sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from station_lists import history_stations
STATIONS=history_stations()
WINDOW_HOURS=48; TREND_HOURS=6; TREND_MATCH_MINUTES=30; FRESH_SECONDS=7200
ABS_TOL={'00060':0.05,'00065':0.02}; REL_TOL=0.05; SEASON_HALF_WINDOW_DAYS=15
LABEL={'00060':'discharge','00065':'gage height'}

def parse_time(s):
    t=dt.datetime.fromisoformat(str(s).replace('Z','+00:00'))
    if t.tzinfo is None: raise ValueError(f'observation time lacks timezone: {s}')
    return t

def dedupe(rows):
    """One observation per timestamp; the most recently retrieved copy wins. Rows: dicts with observed_at, retrieved_at, value, qualifiers."""
    by={}
    for r in rows:
        key=parse_time(r['observed_at'])
        if key not in by or str(r.get('retrieved_at',''))>str(by[key].get('retrieved_at','')): by[key]={**r,'_t':key}
    return [by[k] for k in sorted(by)]

def window_rows(db,station,parameter,since):
    cur=db.execute('select observed_at,retrieved_at,value,qualifiers,unit from observations where station_id=? and parameter=? and observed_at>=? order by observed_at',(station,parameter,since.isoformat()))
    return dedupe([{'observed_at':a,'retrieved_at':b,'value':c,'qualifiers':json.loads(d or '[]'),'unit':e} for a,b,c,d,e in cur.fetchall()])

def trend(rows,parameter,hours=TREND_HOURS,match_minutes=TREND_MATCH_MINUTES):
    """Compare the latest value with the observation nearest to `hours` earlier. Unknown when no such observation exists."""
    if not rows: return {'direction':'unknown','reason':'no observations in window'}
    latest=rows[-1]; target=latest['_t']-dt.timedelta(hours=hours)
    candidates=[r for r in rows[:-1] if abs((r['_t']-target).total_seconds())<=match_minutes*60]
    if not candidates: return {'direction':'unknown','reason':f'no observation within ±{match_minutes} min of {hours} h before the latest reading'}
    earlier=min(candidates,key=lambda r:abs((r['_t']-target).total_seconds()))
    delta=latest['value']-earlier['value']; span_h=(latest['_t']-earlier['_t']).total_seconds()/3600
    tol=max(ABS_TOL.get(parameter,0.05),REL_TOL*max(abs(earlier['value']),abs(latest['value'])))
    direction='steady' if abs(delta)<=tol else 'rising' if delta>0 else 'falling'
    return {'direction':direction,'change':round(delta,3),'change_per_hour':round(delta/span_h,4) if span_h else None,'hours':round(span_h,2),
            'compared_to_observed_at':earlier['_t'].isoformat(),'compared_to_value':earlier['value'],'tolerance':round(tol,3),
            'method':f'latest minus the observation nearest {hours} h earlier; steady when |change| <= max({ABS_TOL.get(parameter,0.05)}, {REL_TOL} × larger value)'}

def window_peak(rows):
    if not rows: return None
    peak=max(rows,key=lambda r:(r['value'],r['_t'])); latest=rows[-1]
    return {'value':peak['value'],'observed_at':peak['_t'].isoformat(),'hours_before_latest':round((latest['_t']-peak['_t']).total_seconds()/3600,2),
            'window_hours':WINDOW_HOURS,'is_latest':peak['_t']==latest['_t'],'window_minimum':min(r['value'] for r in rows)}

def data_health(rows,at):
    if not rows: return {'observation_count':0,'fresh':False,'reason':'no observations in window'}
    spacing=[(b['_t']-a['_t']).total_seconds()/60 for a,b in zip(rows,rows[1:])]
    latest=rows[-1]; age=(at-latest['_t']).total_seconds()
    return {'observation_count':len(rows),'first_observed_at':rows[0]['_t'].isoformat(),'latest_observed_at':latest['_t'].isoformat(),
            'median_spacing_minutes':round(statistics.median(spacing),1) if spacing else None,'gaps_over_60_minutes':sum(1 for s in spacing if s>60),
            'largest_gap_minutes':round(max(spacing),1) if spacing else None,'qualifier_rows':sum(1 for r in rows if r.get('qualifiers')),
            'age_minutes':round(age/60,1),'fresh':-300<=age<=FRESH_SECONDS,'freshness_rule':f'fresh within {FRESH_SECONDS//3600} h of generation'}

def load_daily(station):
    path=HISTORY/f'{station}-00060-daily-mean.csv'
    if not path.exists(): return None
    out=[]
    with path.open() as fh:
        for r in csv.DictReader(fh):
            if r['value']=='': continue
            out.append({'date':dt.date.fromisoformat(r['date']),'value':float(r['value']),'approval':r['approval_status']})
    return out

def doy_distance(a,b):
    d=abs(a.timetuple().tm_yday-b.timetuple().tm_yday); return min(d,365-d)

def percentile_rank(values,x):
    n=len(values); below=sum(1 for v in values if v<x); ties=sum(1 for v in values if v==x)
    return 100.0*(below+0.5*ties)/n

def seasonal_context(daily,day,value,half_window=SEASON_HALF_WINDOW_DAYS,exclude_date=None):
    """Where `value` sits among this station's own daily means within ±half_window days of `day`'s date, across all years."""
    pool=[r for r in daily if doy_distance(r['date'],day)<=half_window and r['date']!=exclude_date]
    if len(pool)<30: return {'available':False,'reason':f'only {len(pool)} comparable daily means'}
    vals=[r['value'] for r in pool]; years=sorted({r['date'].year for r in pool})
    return {'available':True,'percentile':round(percentile_rank(vals,value),1),'seasonal_median':statistics.median(vals),'seasonal_p10':percentile_nearest(vals,10),'seasonal_p90':percentile_nearest(vals,90),
            'comparable_days':len(vals),'years':len(years),'first_year':years[0],'last_year':years[-1],'zero_share':round(sum(1 for v in vals if v==0)/len(vals),3),
            'provisional_share':round(sum(1 for r in pool if r['approval']!='Approved')/len(pool),3),
            'window':f'±{half_window} days of {day.strftime("%b %d")} by day of year','method':'percentile rank = (values below + half of ties) / n'}

def percentile_nearest(values,p):
    s=sorted(values); k=max(1,math.ceil(p/100*len(s))); return s[k-1]

def describe_time(t): return t.astimezone(ZoneInfo('America/Chicago')).strftime('%b %d %-I:%M %p CT')

def ordinal(n):
    n=int(round(n)); suffix='th' if 10<=n%100<=20 else {1:'st',2:'nd',3:'rd'}.get(n%10,'th'); return f'{n}{suffix}'

def station_context(station,name,latest,rows_by_param,daily,at):
    params={}
    for parameter in [q for q in ('00060','00065') if q in rows_by_param or q in latest]:
        rows=rows_by_param.get(parameter,[]); lat=latest.get(parameter)
        entry={'label':LABEL.get(parameter,'parameter '+parameter),'unit':(lat or {}).get('unit') or (rows[-1]['unit'] if rows else None),
               'latest':{'value':lat['value'],'observed_at':lat['observed_at'],'qualifiers':lat.get('qualifiers',[])} if lat else None,
               'trend':trend(rows,parameter),'window_peak':window_peak(rows),'health':data_health(rows,at),
               'series':[[r['_t'].isoformat(),r['value']] for r in rows[::max(1,len(rows)//96)]]}
        if parameter=='00060':
            if daily:
                last=daily[-1]
                entry['latest_daily_mean']={'date':last['date'].isoformat(),'value':last['value'],'approval':last['approval'],'record_first_day':daily[0]['date'].isoformat(),'record_days':len(daily)}
                entry['seasonal_daily_mean']=seasonal_context(daily,last['date'],last['value'],exclude_date=last['date'])
                if lat: entry['seasonal_instantaneous']={**seasonal_context(daily,at.date(),lat['value']),'caveat':'an instantaneous reading compared with daily means; indicative only'}
            else: entry['seasonal_daily_mean']={'available':False,'reason':'no daily-history archive for this station'}
        params[parameter]=entry
    return {'name':name,'parameters':params,'narrative':narrative(name,params),'evidence_strength':'Measured · direct USGS station record','meaning':'Describes this station only. Not a swimming, safety, access, or water-quality statement.'}

def fmt(v): return f'{v:g}'

def narrative(name,params):
    q=params.get('00060'); parts=[]
    if q and q['latest']:
        lat=q['latest']; h=q['health']; t=q['trend']
        parts.append(f"{name} measured {fmt(lat['value'])} {q['unit']} at {describe_time(parse_time(lat['observed_at']))}"+(f" ({'fresh' if h.get('fresh') else 'stale'}, {h.get('age_minutes')} min old at generation)" if 'age_minutes' in h else ''))
        if t['direction']=='unknown': parts.append('trend unknown: '+t['reason'])
        else: parts.append(f"{t['direction']} over {t['hours']} h ({fmt(t['compared_to_value'])} → {fmt(lat['value'])})")
        pk=q.get('window_peak')
        if pk and not pk['is_latest'] and pk['value']>lat['value']: parts.append(f"{WINDOW_HOURS}-hour maximum {fmt(pk['value'])} {q['unit']} was {pk['hours_before_latest']} h earlier")
        elif pk: parts.append(f"{WINDOW_HOURS}-hour range {fmt(pk['window_minimum'])}–{fmt(pk['value'])} {q['unit']}")
    elif q: parts.append(f'{name}: no discharge reading in the saved window')
    else: parts.append(f'{name}: no discharge series saved')
    s=q.get('seasonal_daily_mean') if q else None; d=q.get('latest_daily_mean') if q else None
    if s and s.get('available') and d:
        band='below' if s['percentile']<50 else 'above' if s['percentile']>50 else 'at'
        parts.append(f"the latest daily mean, {fmt(d['value'])} {q['unit']} on {d['date']}, sits at the {ordinal(s['percentile'])} percentile of this station's own same-time-of-year daily means ({s['window']}, {s['years']} years {s['first_year']}–{s['last_year']}; median {fmt(s['seasonal_median'])}, {s['zero_share']*100:.0f}% of those days were zero) — {band} its seasonal median")
    elif s and not s.get('available'): parts.append('seasonal comparison unavailable: '+s['reason'])
    g=params.get('00065')
    if g and g['latest']: parts.append(f"gage height {fmt(g['latest']['value'])} {g['unit']} (stage at this gauge's own datum; not pool depth)")
    return '; '.join(parts)+'. This describes the station, not a swimming place.'

def build(at=None,stations=STATIONS):
    at=at or dt.datetime.now(dt.timezone.utc)
    if not PARSED.exists(): raise FileNotFoundError(f'{PARSED}: run signal_pipeline.py parse first')
    latest={}
    for r in json.loads(PARSED.read_text()):
        latest.setdefault(r['station_id'].replace('USGS-',''),{})[r['parameter']]=r
    gauges={g['id']:g for g in json.loads((ROOT/'data/gauges.json').read_text())}
    db=sqlite3.connect(DB) if DB.exists() else None
    since=at-dt.timedelta(hours=WINDOW_HOURS); out={}
    for station in stations:
        rows_by_param={}
        if db:
            for parameter in ('00060','00065'):
                rows=window_rows(db,'USGS-'+station,parameter,since)
                if rows: rows_by_param[parameter]=rows
        out[station]=station_context(station,gauges.get(station,{}).get('name','USGS-'+station),latest.get(station,{}),rows_by_param,load_daily(station),at)
    if db: db.close()
    payload={'generated_at':at.isoformat(),'window_hours':WINDOW_HOURS,'trend_hours':TREND_HOURS,'meaning':'Deterministic station features: measurement, freshness, direction, window peak, and seasonal position within the station\'s own record. Not a swim verdict; place relationships are separate.',
             'stations':out}
    return payload

def main(at=None):
    payload=build(at); OUT.write_text(json.dumps(payload,indent=2)+'\n')
    for s,v in payload['stations'].items(): print(s,'·',v['narrative'])

if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--at',help='ISO time for deterministic replay'); a=p.parse_args()
    main(dt.datetime.fromisoformat(a.at.replace('Z','+00:00')) if a.at else None)
