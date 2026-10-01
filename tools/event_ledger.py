#!/usr/bin/env python3
"""Hydrograph event ledger per Austin station, from the preserved daily-mean record. Fits nothing.

An event is a hydrograph episode, not a pile of five-minute rows: a run of days that begins
when the daily mean reaches the station's own high threshold and ends when it drops below the
station's own low threshold (hysteresis). Both thresholds are percentiles of that station's
entire numeric daily record, so nothing is transferred between creeks. A calendar gap inside
an event ends the event and marks it ``ended_by_gap``.

Labels come from ``data/observations.jsonl`` (Saul's notes, verbatim) joined through
``data/model/place-relationships.json``: a note attaches to a station only when its place has a
recorded relationship to that station. A note with an unresolved year or a month-only date is
expanded into named scenarios; each scenario reports what the station recorded, never a
verdict. The holdout split is defined here, ahead of any fitting, by water year.
"""
import argparse, csv, datetime as dt, json, math, statistics
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
HISTORY=ROOT/'data/history'; MODEL=ROOT/'data/model'
import sys as _sys; _sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from station_lists import history_stations
STATIONS=history_stations()
P_HIGH=95; P_LOW=75; MIN_HIGH=1.0
CANDIDATE_YEARS=list(range(2019,2026))

def percentile_nearest(values,p):
    s=sorted(values); k=max(1,math.ceil(p/100*len(s))); return s[k-1]

def water_year(day): return day.year+1 if day.month>=10 else day.year

def load_daily(station):
    path=HISTORY/f'{station}-00060-daily-mean.csv'
    with path.open() as fh:
        return [{'date':dt.date.fromisoformat(r['date']),'value':float(r['value']) if r['value']!='' else None,'approval':r['approval_status']} for r in csv.DictReader(fh)]

def detect_events(daily,t_high,t_low):
    """Hysteresis runs over consecutive calendar days. Returns events with rise/recession bookkeeping."""
    events=[]; current=None; prev_date=None
    def close(ev,end_reason):
        ev['end']=ev['days'][-1]['date']; ev['end_reason']=end_reason; ev['duration_days']=len(ev['days'])
        peak=max(ev['days'],key=lambda d:(d['value'],-ev['days'].index(d)))
        ev['peak_date']=peak['date']; ev['peak_value']=peak['value']
        ev['rise_days']=ev['days'].index(peak)+1; ev['recession_days']=len(ev['days'])-ev['days'].index(peak)-1
        ev['mean_value']=round(statistics.mean(d['value'] for d in ev['days']),3); ev['has_provisional']=any(d['approval']!='Approved' for d in ev['days'])
        ev['water_year']=water_year(ev['peak_date']); ev['peak_month']=ev['peak_date'].month
        del ev['days']; events.append(ev)
    for r in daily:
        gap=prev_date is not None and (r['date']-prev_date).days>1
        if current and (gap or r['value'] is None): close(current,'ended_by_gap' if gap else 'ended_by_non_numeric_value'); current=None
        prev_date=r['date']
        if r['value'] is None: continue
        if current is None:
            if r['value']>=t_high: current={'start':r['date'],'days':[r]}
        else:
            if r['value']<t_low: close(current,'fell_below_low_threshold'); current=None
            else: current['days'].append(r)
    if current: close(current,'record_ends_inside_event')
    return events

def antecedent(daily_by_date,start,days=30):
    vals=[daily_by_date[start-dt.timedelta(days=i)] for i in range(1,days+1) if start-dt.timedelta(days=i) in daily_by_date and daily_by_date[start-dt.timedelta(days=i)] is not None]
    return {'days_available':len(vals),'mean':round(statistics.mean(vals),3) if vals else None}

def scenario_windows(obs):
    """Turn one note into dated windows. Unresolved years become one scenario per candidate year."""
    p=obs.get('date_precision'); d=obs.get('date')
    if p=='day' and d and not d.startswith('--'): x=dt.date.fromisoformat(d); return [{'scenario':'as recorded','start':x,'end':x}]
    if p=='day' and d and d.startswith('--'):
        m,dd=int(d[2:4]),int(d[5:7]); return [{'scenario':f'if the year was {y}','start':dt.date(y,m,dd),'end':dt.date(y,m,dd)} for y in CANDIDATE_YEARS]
    if p=='month' and d:
        y,m=int(d[:4]),int(d[5:7]); last=(dt.date(y+(m==12),(m%12)+1,1)-dt.timedelta(days=1)); return [{'scenario':'whole month as recorded','start':dt.date(y,m,1),'end':last}]
    if p=='date_range' and obs.get('date_start') and obs.get('date_end'):
        return [{'scenario':'whole recorded range','start':dt.date.fromisoformat(obs['date_start']),'end':dt.date.fromisoformat(obs['date_end']),'note':obs.get('date_basis')}]
    if p=='weekend_interval':
        return [{'scenario':f'if the year was {y}','start':dt.date(y,7,17),'end':dt.date(y,7,20),'note':'July 17–20 brackets a weekend containing July 18'} for y in CANDIDATE_YEARS]
    return []

def describe_window(daily_by_date,daily_numeric,events,start,end):
    vals=[(d,daily_by_date[d]) for d in (start+dt.timedelta(days=i) for i in range((end-start).days+1)) if d in daily_by_date and daily_by_date[d] is not None]
    if not vals: return {'days_with_data':0,'finding':'no daily mean recorded for this window'}
    values=[v for _,v in vals]; mean=statistics.mean(values)
    pool=[r['value'] for r in daily_numeric if min(abs(r['date'].timetuple().tm_yday-start.timetuple().tm_yday),365-abs(r['date'].timetuple().tm_yday-start.timetuple().tm_yday))<=15]
    pct=100.0*(sum(1 for v in pool if v<mean)+0.5*sum(1 for v in pool if v==mean))/len(pool) if pool else None
    overlapping=[e for e in events if e['start']<=end and e['end']>=start]
    prior=[e for e in events if e['end']<start]
    last=max(prior,key=lambda e:e['end']) if prior else None
    return {'days_with_data':len(values),'first':vals[0][0].isoformat(),'last':vals[-1][0].isoformat(),'min':min(values),'max':max(values),'mean':round(mean,3),
            'seasonal_percentile_of_mean':round(pct,1) if pct is not None else None,'inside_event':bool(overlapping),
            'overlapping_event_peaks':[{'peak_date':e['peak_date'].isoformat(),'peak_value':e['peak_value']} for e in overlapping],
            'days_since_previous_event_end':(start-last['end']).days if last else None,'previous_event_peak_value':last['peak_value'] if last else None}

def labels_for_station(station,relationships,observations):
    """Notes attach through recorded relationships only. A note whose reach was resolved attaches to that place alone."""
    aliases=relationships.get('observation_place_aliases',{}); places=relationships['places']
    out=[]
    for obs in observations:
        targets=[obs['reach']] if obs.get('reach') else aliases.get(obs['place_id'],[obs['place_id']])
        links=[]
        for pid in targets:
            for s in places.get(pid,{}).get('stations',[]):
                if s['station_id']==station: links.append({'place_id':pid,'relationship_class':s['relationship_class'],'confidence':s['confidence']})
        if links: out.append({'observation_id':obs['id'],'verbatim':obs['verbatim'],'reported_quality':obs.get('reported_quality'),'date_precision':obs.get('date_precision'),'date':obs.get('date'),'date_start':obs.get('date_start'),'date_end':obs.get('date_end'),'reach':obs.get('reach'),'reach_precision':obs.get('reach_precision'),'links':links})
    return out

def build_station(station,relationships,observations):
    daily=load_daily(station); numeric=[r for r in daily if r['value'] is not None]
    values=[r['value'] for r in numeric]
    if not values:
        return {'station_id':'USGS-'+station,'source_csv':f'data/history/{station}-00060-daily-mean.csv','record':{'first_day':daily[0]['date'].isoformat() if daily else None,'last_day':daily[-1]['date'].isoformat() if daily else None,'numeric_days':0,'zero_days':0,'median_daily_mean':None},
                'event_definition':None,'events':[],'summary':{'event_count':0,'events_per_water_year':{},'median_duration_days':None,'median_peak_value':None,'peak_month_counts':{},'events_ended_by_gap':0},'labels':[],
                'holdout_split':None,'rule_fit':{'attempted':False,'reason':'no numeric daily means on file for this station; nothing to evaluate'},'limits':['The daily-mean record has no numeric values (the station may report instantaneous flow only); no event or percentile can be computed.']}
    t_high=max(percentile_nearest(values,P_HIGH),MIN_HIGH); t_low=min(percentile_nearest(values,P_LOW),t_high)
    events=detect_events(daily,t_high,t_low); by_date={r['date']:r['value'] for r in daily}
    for e in events: e['antecedent_30_day']=antecedent(by_date,e['start'])
    labels=labels_for_station(station,relationships,observations)
    for lab in labels:
        lab['scenarios']=[{**w,'start':w['start'].isoformat(),'end':w['end'].isoformat(),'station_record':describe_window(by_date,numeric,events,w['start'],w['end'])} for w in scenario_windows(lab)]
    positives=[l for l in labels if l.get('reported_quality') and any(w in l['reported_quality'].lower() for w in ('good','nice','positive')) and l['date_precision'] in ('day','month','weekend_interval','date_range')]
    negatives=[l for l in labels if l.get('reported_quality') and any(w in l['reported_quality'] for w in ('bad','poor','dry','closed'))]
    exact_reach=[l for l in labels if l.get('reach')]
    fit={'attempted':False,'positive_personal_labels':len(positives),'negative_labels':len(negatives),'labels_with_resolved_reach':len(exact_reach),'independent_dated_labels':0,
         'reason':'No threshold can be evaluated: '+('no labels attach to this station' if not labels else f'{len(positives)} positive personal notes, {len(negatives)} negative notes, 0 independent dated labels, and {len(labels)-len(exact_reach)} note(s) with an unresolved reach; whole-event holdout evaluation needs both sides of the boundary and reach-resolved dates')+'. No fitted threshold exists; any color comes only from a hand-authored provisional rule recorded in data/rules.json.'}
    per_wy=Counter(e['water_year'] for e in events)
    return {'station_id':'USGS-'+station,'source_csv':f'data/history/{station}-00060-daily-mean.csv','record':{'first_day':daily[0]['date'].isoformat(),'last_day':daily[-1]['date'].isoformat(),'numeric_days':len(numeric),'zero_days':sum(1 for v in values if v==0),'median_daily_mean':statistics.median(values)},
            'event_definition':{'high_threshold':t_high,'low_threshold':t_low,'high_rule':f'P{P_HIGH} of all numeric daily means at this station, floored at {MIN_HIGH} ft^3/s','low_rule':f'P{P_LOW} of all numeric daily means at this station','unit':'ft^3/s daily mean',
                                'method':'event starts on the first day >= high threshold and ends on the last day before a day < low threshold, a calendar gap, or a non-numeric value','percentile_method':'nearest-rank'},
            'events':[{**e,'start':e['start'].isoformat(),'end':e['end'].isoformat(),'peak_date':e['peak_date'].isoformat()} for e in events],
            'summary':{'event_count':len(events),'events_per_water_year':dict(sorted(per_wy.items())),'median_duration_days':statistics.median(e['duration_days'] for e in events) if events else None,
                       'median_peak_value':statistics.median(e['peak_value'] for e in events) if events else None,'peak_month_counts':dict(sorted(Counter(e['peak_month'] for e in events).items())),'events_ended_by_gap':sum(1 for e in events if e['end_reason']=='ended_by_gap')},
            'labels':labels,'holdout_split':{'unit':'water_year (Oct 1–Sep 30)','fold':'water_year mod 5','protocol':'leave-one-fold-out over whole events; an event belongs to the water year of its peak; never a random split of adjacent readings','defined_before_any_fit':True},
            'rule_fit':fit,'limits':['Daily means hide within-day peaks and the timing of a visit inside a day.','Thresholds are descriptive event boundaries for this station, not swimming thresholds.','A note attached through a context relationship describes the station, not the place; the reach may be far from the gauge.']}

def main(stations):
    # Labels are a lens-side input (a swim map's visit notes joined through its place relationships).
    # In this repo they are usually absent; the ledger then describes the station record alone.
    rel_path=MODEL/'place-relationships.json'; obs_path=ROOT/'data/observations.jsonl'
    relationships=json.loads(rel_path.read_text()) if rel_path.exists() else {'observation_place_aliases':{},'places':{}}
    observations=[json.loads(l) for l in obs_path.read_text().splitlines() if l.strip()] if obs_path.exists() else []
    for station in stations:
        ledger=build_station(station,relationships,observations)
        (MODEL/f'{station}-event-ledger.json').write_text(json.dumps(ledger,indent=2)+'\n')
        print(f"{station}: {ledger['summary']['event_count']} events (high {(ledger['event_definition'] or {}).get('high_threshold')}, low {(ledger['event_definition'] or {}).get('low_threshold')}); {len(ledger['labels'])} attached notes; fit attempted={ledger['rule_fit']['attempted']}")

if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--stations',nargs='+',default=STATIONS); a=p.parse_args(); main(a.stations)
