"""Retrospective storm windows and deterministic changes at gauges. Stdlib; compute is offline.

Normalization materializes saved rain-feed snapshots and daily CSVs in SQLite.
Detection reads that store and frozen ledger thresholds. First crossings require a
previous below-threshold reading; an already-high first observation is not a crossing.
The storm record is immutable once created. Open records have t1=null until recession
is observed; the ten-day cap is an observation boundary, not a prediction.
"""
import argparse, bisect, csv, datetime as dt, gzip, json, math, sqlite3, statistics
from collections import defaultdict
from pathlib import Path
import hydro_context as hc
import hydromet as hm
import eaa

ROOT=Path(__file__).resolve().parents[1]; DB=ROOT/'data/normalized/water.sqlite'
STORMS=ROOT/'data/model/storms'; OUT=ROOT/'app/storm-delta.json'
UTC=dt.timezone.utc
RULE={'rain_fraction':0.2,'rainfall1Day_inches':1.0,'baseline_hours':24,'recession_hours':72,'cap_days':10,
      'trigger':'rainfall1Day >= 1 inch at >=20% of reporting rain gauges, or a flow crossing of its ledger high threshold',
      'end':'72 hours after all crossing gauges are observed below threshold, capped at t0 + 10 days',
      'daily_precision':'Daily means can identify a trigger day only; its UTC midnight is a window boundary, not an observed crossing time.'}
RESPONSE_RULES={'no response':'peak < 2 * start and peak < 1 cfs', 'flash':'peak / max(start, 0.1) >= 10 and observed below 2 * start within 24 hours after peak',
                'sustained':'peak / max(start, 0.1) >= 10 and observed above 2 * start at t1', 'modest':'all other fully observed cases',
                'missing':'null if baseline or peak is missing; recession-dependent class withheld while t1 is unobserved',
                'zero_baseline':'The literal below 2 * start rule cannot be met by nonnegative flow when start is zero. No replacement threshold is introduced.'}

def load(path, default=None):
    return json.loads(path.read_text()) if path.exists() else default

def instant(s):
    t=dt.datetime.fromisoformat(str(s).replace('Z','+00:00'))
    if t.tzinfo is None:
        if len(str(s))!=10: raise ValueError('time without timezone: '+str(s))
        t=t.replace(tzinfo=UTC)
    return t.astimezone(UTC)

def stamp(t): return t.astimezone(UTC).isoformat().replace('+00:00','Z')
def numeric(x):
    try: n=float(x); return n if math.isfinite(n) else None
    except (TypeError,ValueError): return None

def row(at,value,source,precision='instantaneous'):
    return dict(at=at,value=value,source=source,precision=precision)

def unique(rows):
    # Input from observations is sorted by retrieval time; latest capture wins.
    by={}
    for r in rows:
        if numeric(r['value']) is not None: by[instant(r['at'])]=r
    return [by[t] for t in sorted(by)]

def normalized_inputs(db):
    db.execute('create table if not exists storm_rain_feeds(capture text, observed_at text, agency text, site text, data text, primary key(capture,agency,site))')
    for mp in sorted((ROOT/'data/raw/hydromet/current').glob('*all-sites.meta.json')):
        m=load(mp); body=mp.with_name(mp.name.replace('.meta.json','.json'))
        if m['status']!=200 or not body.exists(): continue
        # The operator publishes rolling totals. Never reconstruct them from increments.
        sites=hm.parse_sites(body.read_bytes())
        db.executemany('insert or replace into storm_rain_feeds values(?,?,?,?,?)',[(str(body.relative_to(ROOT)),s['observed_at'],s['agency'],s['site'],json.dumps(s)) for s in sites if s['observed_at']])
    db.execute('create table if not exists storm_daily(station text, day text, value real, source text, primary key(station,day))')
    for path in sorted((ROOT/'data/history').glob('*-00060-daily-mean.csv')):
        rows=[]
        with path.open() as f:
            for r in csv.DictReader(f):
                if numeric(r['value']) is not None: rows.append((path.name.split('-')[0],r['date'],float(r['value']),str(path.relative_to(ROOT))))
        db.executemany('insert or replace into storm_daily values(?,?,?,?)',rows)
    # Versioned EAA pages are original bodies; their fetch sidecars were not exported.
    # Retain that provenance gap rather than fabricating a retrieval timestamp.
    db.execute('create table if not exists storm_eaa_daily(site text, day text, value real, source text, primary key(site,day))')
    for path in sorted((ROOT/'data/captures/eaa/details').glob('*.html.gz')):
        text=gzip.decompress(path.read_bytes()).decode('utf-8', 'replace')
        for r in eaa.parse_var(text,'wellAllDailyHighElevationJSON') or []:
            if r.get('siteId') and r.get('dailyHighDate') and numeric(r.get('waterLevelElevation')) is not None:
                db.execute('insert or replace into storm_eaa_daily values(?,?,?,?)',(r['siteId'],r['dailyHighDate'][:10],float(r['waterLevelElevation']),str(path.relative_to(ROOT))))
    db.commit()

def series(db,since=None,focus=None):
    out=defaultdict(list)
    sql="select station_id,parameter,observed_at,value,raw_path,series_id from observations where parameter in ('00060','00065')"
    args=[]
    if since: sql+=' and observed_at>=?'; args=[since]
    sql+=' order by retrieved_at,raw_path'
    for sid,param,t,v,src,ts in db.execute(sql,args): out[(sid.replace('USGS-',''),param,ts)].append({**row(t,v,src),'series_id':ts})
    tables={r[0] for r in db.execute("select name from sqlite_master where type='table'")}
    for table,param in [('usgs_peak_window','00060'),('usgs_stage_window','00065')]:
        if table not in tables: continue
        for sid,t,v,ts,q,src in db.execute('select * from '+table):
            if not since or t>=since: out[(sid,param,ts)].append({**row(t,v,src),'series_id':ts})
    grouped=defaultdict(list)
    for (sid,param,ts),rs in out.items():
        rs=unique(rs); in_window=sum(focus[0]<=instant(r['at'])<=focus[1] for r in rs) if focus else len(rs)
        grouped[(sid,param)].append((in_window,len(rs),str(ts),rs))
    selected={}
    for key,candidates in grouped.items():
        chosen=sorted(candidates,key=lambda x:(-x[0],-x[1],x[2]))[0]
        selected[key]=[{**r,'series_selection':'most readings in requested interval; then total count; then series ID; never merge distinct series',
                        'other_series_ids':[x[2] for x in candidates if x[2]!=chosen[2]]} for r in chosen[3]]
    return selected

def daily_rows(db,sid): return [row(d,v,src,'daily mean') for d,v,src in db.execute('select day,value,source from storm_daily where station=? order by day',(sid,))]

def thresholds():
    out={}
    for path in (ROOT/'data/model').glob('*-event-ledger.json'):
        e=load(path).get('event_definition')
        if e and numeric(e.get('high_threshold')) is not None: out[path.name.split('-')[0]]=e['high_threshold']
    return out

def rain_triggers(feeds):
    out=[]
    for capture,sites in feeds.items():
        reporting=[s for s in sites if s['rain_in'].get('1Day') is not None]
        wet=[s for s in reporting if s['rain_in']['1Day']>=1]
        if reporting and len(wet)/len(reporting)>=0.2:
            # Snapshot timestamp is max actual gauge report time, not retrieval clock.
            at=max(s['observed_at'] for s in reporting)
            out.append(dict(at=at,kind='rain',capture=capture,reporting=len(reporting),wet=len(wet),
                readings=[dict(site=s['agency']+':'+s['site'],at=s['observed_at'],rainfall1Day=s['rain_in']['1Day']) for s in reporting]))
    return out

def detect_windows(flows,highs,rain,as_of):
    events=[]
    for sid,rows in flows.items():
        high=highs.get(sid)
        if high is None: continue
        for prev,current in zip(rows,rows[1:]):
            # A gap is disclosed, never filled. No continuous timing inferred across it.
            if prev['value'] < high <= current['value']:
                events.append(dict(at=current['at'],kind='flow',station=sid,threshold_cfs=high,
                                   reading=current,previous=prev,gap_hours=(instant(current['at'])-instant(prev['at'])).total_seconds()/3600))
    events+=rain; events.sort(key=lambda x:instant(x['at']))
    windows=[]; i=0
    while i<len(events):
        first=events[i]; t0=instant(first['at'])-dt.timedelta(hours=24); cap=t0+dt.timedelta(days=10)
        triggered=[]; active={}; last=instant(first['at']); j=i
        # Extend while a subsequent trigger falls inside the observed episode plus tail.
        while j<len(events):
            ev=events[j]; t=instant(ev['at'])
            end=cap if any(v is None for v in active.values()) else min(cap,max([last]+list(active.values()))+dt.timedelta(hours=72))
            if t>cap or (j>i and t>end): break
            triggered.append(ev); last=t
            if ev['kind']=='flow':
                rs=flows[ev['station']]
                fall=next((instant(r['at']) for r in rs if instant(r['at'])>t and r['value']<ev['threshold_cfs']),None)
                active[ev['station']]=fall
            j+=1
        end=cap if any(v is None for v in active.values()) else min(cap,max([last]+list(active.values()))+dt.timedelta(hours=72))
        closed=end<=as_of
        windows.append(dict(t0=stamp(t0),t1=stamp(end) if closed else None,cap_at=stamp(cap),observed_through=stamp(as_of),
                            status='closed' if closed else 'open',rule=RULE,triggered_by=triggered,
                            end_candidate=stamp(end) if not any(v is None for v in active.values()) else None,
                            gauges_without_observed_recession=[k for k,v in active.items() if v is None]))
        i=j
    return windows

def candidate_windows(db,since=None):
    latest=db.execute('select max(observed_at) from observations').fetchone()[0]
    since=since or (instant(latest)-dt.timedelta(days=10)).date().isoformat()
    by=series(db,since); flows={sid:rs for (sid,p),rs in by.items() if p=='00060'}
    # Before continuous coverage, daily means supply explicitly dated, coarse triggers.
    for sid in thresholds():
        d=daily_rows(db,sid); first=instant(flows[sid][0]['at']) if flows.get(sid) else instant(latest)
        early=[r for r in d if r['at']>=since and instant(r['at'])<first-dt.timedelta(days=1)]
        flows[sid]=early+flows.get(sid,[])
    feeds=defaultdict(list)
    for cap,t,agency,sid,data in db.execute('select * from storm_rain_feeds where observed_at>=?',(since,)): feeds[cap].append(json.loads(data))
    return detect_windows(flows,thresholds(),rain_triggers(feeds),instant(latest))

def detect(since=None):
    db=sqlite3.connect(DB); normalized_inputs(db)
    windows=candidate_windows(db,since); db.close()
    for w in windows: save_window(w)

def save_window(window):
    """Exclusive creation preserves the original triggering evidence on subsequent runs."""
    STORMS.mkdir(parents=True,exist_ok=True)
    key=window['triggered_by'][0]['at'][:10]; path=STORMS/(key+'.json')
    if path.exists(): print(key+': preserved existing window'); return False
    with path.open('x') as f:
        json.dump(dict(id=key,window=window,hypotheses=[]),f,indent=2); f.write('\n')
    print(f"{key}: {window['t0']} .. {window['t1'] or 'open'}; {len(window['triggered_by'])} triggers")
    return True

def summarize(rows,t0,t1):
    rows=unique(rows)
    before=[r for r in rows if (r['at']<t0.date().isoformat() if len(r['at'])==10 else instant(r['at'])<t0)]
    inside=[r for r in rows if (t0.date().isoformat()<=r['at']<=(t1.date()-dt.timedelta(days=1) if t1.time()==dt.time(0) else t1.date()).isoformat() if len(r['at'])==10 else t0<=instant(r['at'])<=t1)]
    return dict(start=before[-1] if before else None,peak=max(inside,key=lambda r:r['value']) if inside else None,
                now=rows[-1] if rows else None,window_last=inside[-1] if inside else None)

def response(s,rows,t1,closed):
    start=s['start']; peak=s['peak']
    if not start or not peak: return None,None
    ratio=peak['value']/max(start['value'],0.1)
    if peak['value']<2*start['value'] and peak['value']<1: return 'no response',ratio
    recession=[r for r in rows if instant(peak['at'])<instant(r['at'])<=min(t1,instant(peak['at'])+dt.timedelta(hours=24)) and r['value']<2*start['value']]
    if ratio>=10 and recession: return 'flash',ratio
    if ratio>=10 and (not closed or not s['window_last'] or instant(s['window_last']['at'])<t1): return None,ratio
    if ratio>=10 and s['window_last'] and s['window_last']['value']>2*start['value']: return 'sustained',ratio
    return 'modest',ratio

def ranks(daily,peak):
    if not daily or not peak: return None,None
    x=peak['value']; higher=[r for r in daily if r['value']>=x]; record=max(daily,key=lambda r:r['value'])
    years=defaultdict(list)
    for r in daily: years[r['at'][:4]].append(r)
    maxima=[max(rs,key=lambda r:r['value']) for rs in years.values()]
    rank=dict(percentile_of_daily_means=round(hc.percentile_rank([r['value'] for r in daily],x),3),record_daily_mean=record['value'],
              days_at_or_above=len(higher),years_at_or_above=len({r['at'][:4] for r in higher}),last_such_day=max((r['at'] for r in higher),default=None),
              record_start=daily[0]['at'],record_end=daily[-1]['at'],days=len(daily),comparison='against daily means',peak_basis=peak['precision'])
    annual=dict(rank=1+sum(r['value']>x for r in maxima),years=len(years),record_daily_mean=record['value'],record_year=record['at'][:4],
                method='1 + calendar-year daily maxima strictly greater than the storm peak; ties share rank',peak_basis=peak['precision'])
    return rank,annual

def peak_rank(db,sid,peak):
    if not peak or peak['precision']!='instantaneous': return None
    rows=db.execute('select date,peak_cfs,qualifiers from usgs_peaks where station=?',(sid,)).fetchall()
    years={}; excluded=0
    for date,value,q in rows:
        codes=json.loads(q).get('peak_cd','')
        # Maximum daily averages and censored values cannot be instantaneous rankings.
        if any(c in codes for c in '1487OA'):
            excluded+=1; continue
        try: d=dt.date.fromisoformat(date)
        except (ValueError,TypeError): excluded+=1; continue
        wy=d.year+(d.month>=10)
        if wy not in years or value>years[wy][1]: years[wy]=(date,value)
    if not years: return None
    record=max(years.values(),key=lambda x:x[1])
    provenance=load(ROOT/'data/captures/usgs-peaks'/sid/'manifest.json',{}).get('annual',{})
    return dict(rank=1+sum(v>peak['value'] for d,v in years.values()),years=len(years),record_peak_cfs=record[1],record_date=record[0],
                record_first_year=min(years),record_last_year=max(years),excluded_rows=excluded,source_file=provenance.get('capture_path'),retrieved_at=provenance.get('retrieved_at'),method='water-year instantaneous maxima; excludes daily-average, censored, historic-only, opportunistic and uncertain-year peaks; qualifiers remain in CSV')

def rate_of_rise(rows,t0,t1):
    rs=[r for r in rows if t0<=instant(r['at'])<=t1 and r['precision']=='instantaneous']; by={instant(r['at']):r for r in rs}; out={}
    for minutes in (15,60):
        pairs=[(r,by[instant(r['at'])-dt.timedelta(minutes=minutes)]) for r in rs if instant(r['at'])-dt.timedelta(minutes=minutes) in by]
        pair=max(pairs,key=lambda p:p[0]['value']-p[1]['value']) if pairs else None
        out[str(minutes)+'_minutes']=dict(change_ft=round(pair[0]['value']-pair[1]['value'],4),start=pair[1],end=pair[0]) if pair else None
    return out

def volume(rows,t0,t1):
    rs=[r for r in unique(rows) if t0<=instant(r['at'])<=t1]; total=0; seconds=0; gaps=[]
    # The native Llano history is hourly. Never integrate a missing interval >1 h.
    for a,b in zip(rs,rs[1:]):
        gap=(instant(b['at'])-instant(a['at'])).total_seconds()
        if gap>3600: gaps.append(dict(after=a['at'],before=b['at'])); continue
        total+=(a['value']+b['value'])/2*gap/43560; seconds+=gap
    return dict(acre_ft=round(total,1) if seconds else None,from_at=rs[0]['at'] if rs else None,through_at=rs[-1]['at'] if rs else None,
                hours_integrated=seconds/3600,gaps=gaps,method='trapezoids over observed flow; cfs seconds / 43560; intervals >1 h excluded',
                source=None)

def rain_intensity(rows):
    rows=unique(rows); best=None; intervals=0
    # Native rain is quarter-hourly. Clock seconds drift; require four consecutive
    # quarter-hour bins and normalize by the ACTUAL elapsed seconds, not an invented
    # timestamp or a tolerance. Missing bins are never bridged.
    for i in range(4,len(rows)):
        block=rows[i-4:i+1]; times=[instant(r['at']) for r in block]
        bins=[int(t.timestamp())//900 for t in times]
        if any(b-a!=1 for a,b in zip(bins,bins[1:])): continue
        seconds=(times[-1]-times[0]).total_seconds()
        if seconds<=0 or any(r['value']<0 for r in block[1:]): continue
        amount=sum(r['value'] for r in block[1:]); rate=amount*3600/seconds; intervals+=1
        if best is None or rate>best['inches_per_hour']:
            best=dict(inches_per_hour=rate,inches_observed=round(amount,4),elapsed_seconds=seconds,
                      from_at=block[0]['at'],through_at=block[-1]['at'],source=block[-1]['source'],
                      method='sum four consecutive native quarter-hour increments, divided by actual elapsed hours; missing quarter-hour bins excluded')
    if best:
        best['inches_per_hour']=round(best['inches_per_hour'],4);best['intervals_compared']=intervals
    return best

def well_pair(rows,t0,t1,depth=False):
    s=summarize(rows,t0,t1); before=s['start']; after=s['window_last']
    changes={}
    for days in (1,7):
        previous=next((r for r in unique(rows) if after and r['at'][:10]==(instant(after['at']).date()-dt.timedelta(days=days)).isoformat()),None)
        changes[str(days)+'d']=dict(change_ft=round((after['value']-previous['value'])*(-1 if depth else 1),3),before=previous,after=after) if previous and after else None
    return dict(changes=changes,level_before=before['value'] if before else None,level_after=after['value'] if after else None,
                before_at=before['at'] if before else None,after_at=after['at'] if after else None,
                change_ft=round((after['value']-before['value'])*(-1 if depth else 1),3) if before and after else None,
                days_between=(instant(after['at'])-instant(before['at'])).total_seconds()/86400 if before and after else None,
                datum='ft below land surface; change positive when water rises' if depth else 'ft above mean sea level',readings=s)

def compute(key):
    record=load(STORMS/(key+'.json'))
    if not record: raise ValueError('no detected storm '+key)
    w=record['window']; db=sqlite3.connect(DB); normalized_inputs(db)
    t0=instant(w['t0']); latest=instant(db.execute('select max(observed_at) from observations').fetchone()[0])
    t1=instant(w['t1']) if w['t1'] else min(latest,instant(w['cap_at']))
    by=series(db,focus=(t0,t1)); locs={s['id']:s for s in load(ROOT/'data/usgs-locations-regional.json',{'locations':[]})['locations']}
    highs=thresholds()
    if w['status']=='open':
        # Reevaluate closure in derived output; the original detection file stays intact.
        feeds=defaultdict(list)
        for cap,t,agency,sid,data in db.execute('select * from storm_rain_feeds'):
            if t0<=instant(t)<=instant(w['cap_at']): feeds[cap].append(json.loads(data))
        frozen_highs={**highs,**{e['station']:e['threshold_cfs'] for e in w['triggered_by'] if e['kind']=='flow'}}
        candidates=detect_windows({sid:[r for r in rs if instant(r['at'])>=t0] for (sid,param),rs in by.items() if param=='00060'},frozen_highs,rain_triggers(feeds),latest)
        current=next((candidate for candidate in candidates if candidate['t0']==w['t0']),None)
        if current: w={**current,'original_record':str((STORMS/(key+'.json')).relative_to(ROOT))}
        elif latest>=instant(w['cap_at']): w={**w,'status':'closed','t1':w['cap_at'],'closure_basis':'recorded ten-day cap reached'}
        t1=instant(w['t1']) if w['t1'] else min(latest,instant(w['cap_at']))
    hazards=load(ROOT/'app/hazards-status.json',{}); hz={x['usgs_id']:x for x in hazards.get('gauges',[]) if x.get('usgs_id')}
    out=dict(window=w,computed_through=stamp(t1),flow={},rain={},springs={},wells={},lakes={},hypotheses=record.get('hypotheses',[]),
             caveats=['Missing readings remain null. Every peak is a maximum of readings on file, not proof of the true crest.',
                      'Daily baselines use the last complete calendar day before t0; daily values cannot locate a within-day change. Boundary-day highs and means have day precision only.',
                      'Instantaneous values ranked against daily means do not have the same sampling basis.',
                      'Start is the last available reading before t0, even across a long gap; baseline_gap_hours discloses that age. A ratio across such a gap cannot isolate the storm response.',
                      'Rolling Hydromet accumulations include rain outside the storm; their dates and fields are retained.',
                      'No EAA rain readings are available here; Hill Country rain coverage is LCRA.',
                      'Versioned EAA well detail bodies are on file, but their original fetch sidecars were not exported; source paths identify those bodies.',
                      'Post-September-30 readings are provisional; providers may revise them.',
                      'Zero baselines make the literal below-2×start recession test unreachable for nonnegative flow.',
                      'Bexar wells BDT614 and BDE608 have reported large changes; pumping or data effects remain unchecked.',
                      'Open immutable windows retain the detection-time extent; computed readings stop at the recorded cap.'])
    for sid in sorted(set(locs)|set(highs)):
        daily=daily_rows(db,sid); rows=by.get((sid,'00060'),[]); s=summarize(rows,t0,t1)
        if not s['peak']:
            coarse=summarize(daily,t0,t1)
            if coarse['peak']: rows=daily; s=coarse
        if not s['peak'] and not rows: continue
        rank,annual=ranks(daily,s['peak']); daily_peak=summarize(daily,t0,t1)['peak']; _,daily_annual=ranks(daily,daily_peak); cls,ratio=response(s,rows,t1,w['status']=='closed')
        stage=summarize(by.get((sid,'00065'),[]),t0,t1); h=hz.get(sid,{}); categories=h.get('categories_ft',{})
        cat=None
        if stage['peak'] and categories:
            reached=[(name,v) for name,v in categories.items() if numeric(v) is not None and stage['peak']['value']>=v]
            name,value=max(reached,key=lambda x:x[1]) if reached else (None,None)
            cat=dict(category=name,above_ft=round(stage['peak']['value']-value,3) if value is not None else None,peak=stage['peak'],thresholds=categories,source=h.get('source'),thresholds_as_of=hazards.get('generated_at'))
        half=next((r for r in rows if s['peak'] and instant(s['peak']['at'])<instant(r['at'])<=t1 and r['value']<=s['peak']['value']/2),None)
        site=locs.get(sid,{})
        out['flow'][sid]=dict(name=site.get('name',sid),lat=site.get('lat'),lon=site.get('lon'),readings=s,
            start_cfs=s['start']['value'] if s['start'] else None,start_at=s['start']['at'] if s['start'] else None,
            baseline_gap_hours=round((t0-instant(s['start']['at'])).total_seconds()/3600,3) if s['start'] else None,
            peak_cfs=s['peak']['value'] if s['peak'] else None,peak_at=s['peak']['at'] if s['peak'] else None,
            now_cfs=s['now']['value'] if s['now'] else None,now_at=s['now']['at'] if s['now'] else None,
            ratio=round(ratio,3) if ratio is not None else None,threshold_cfs=highs.get(sid),
            crossed=any(e.get('station')==sid for e in w['triggered_by']) if sid in highs else None,
            response_class=cls,response_thresholds=RESPONSE_RULES,rank=rank,annual_rank=annual,daily_window_peak=daily_peak,daily_window_annual_rank=daily_annual,peak_rank=peak_rank(db,sid,s['peak']),
            nws_flood_category=cat,nws_note=None if cat else 'No compatible peak stage and published NWS thresholds on file.',rate_of_rise=rate_of_rise(by.get((sid,'00065'),[]),t0,t1),
            hours_peak_to_half=(instant(half['at'])-instant(s['peak']['at'])).total_seconds()/3600 if half else None,hours_rain_to_peak=None,
            rain_timing_note='No observed rain onset linked yet.',peak_basis=s['peak']['precision'] if s['peak'] else None)
    feeds=defaultdict(list)
    for cap,t,agency,sid,data in db.execute('select * from storm_rain_feeds'): feeds[agency+':'+sid].append((t,cap,json.loads(data)))
    for key,versions in feeds.items():
        eligible=[x for x in versions if instant(x[0])>=t0 and instant(x[0])<=t1]
        t,src,s=max(eligible or versions,key=lambda x:x[0])
        available=bool(eligible)
        if s['site_type']!='rain' and not s['rain_in']: continue
        field=next((field for field,days in [('1Week',7),('30Days',30)] if available and instant(t)-dt.timedelta(days=days)<=t0 and instant(t)>=t1 and s['rain_in'].get(field) is not None),None)
        # Open storms can show a rolling total through the gauge's report, explicitly partial.
        if available and not field and w['status']=='open': field=next((f for f,d in [('1Week',7),('30Days',30)] if instant(t)-dt.timedelta(days=d)<=t0 and s['rain_in'].get(f) is not None),None)
        total=s['rain_in'].get(field) if field else None
        hist_rows=list(db.execute("select observed_at,value1 from hydromet_readings where agency=? and site=? and param='rainDaily' and value1 is not null order by observed_at",(s['agency'],s['site'])))
        hist=list({r[0]:r[1] for r in hist_rows}.values())
        rain_rows=[row(a,v,source) for a,v,source in db.execute("select observed_at,value2,source_file from hydromet_readings where agency=? and site=? and param='rain' and observed_at>=? and observed_at<=? and value2 is not null order by observed_at",(s['agency'],s['site'],stamp(t0),stamp(t1)))]
        wet=[r for r in rain_rows if r['value']>0]
        intensity=rain_intensity(rain_rows)
        out['rain'][key]=dict(agency=s['agency'],name=s['name'],lat=s['lat'],lon=s['lon'],inches_window=total,inches_30d=s['rain_in'].get('30Days') if available else None,
            observed_at=t if available else None,identity_observed_at=t,accumulation_field=field,accumulation_start=stamp(instant(t)-dt.timedelta(days=7 if field=='1Week' else 30)) if field else None,
            source='hydromet feed accumulations',source_file=src,partial=w['status']=='open',rain_onset=wet[0] if wet else None,intensity=intensity,intensity_note=('Maximum observed rate across four consecutive native intervals: '+str(intensity['inches_per_hour'])+' inches/hour from '+intensity['from_at']+' through '+intensity['through_at']+' ('+str(intensity['elapsed_seconds'])+' actual seconds; '+str(intensity['intervals_compared'])+' intervals compared). Missing quarter-hour bins are excluded.') if intensity else 'No complete hourly rain interval on file.',
            rain_rank=dict(inches_window=total,days_on_record=len(hist),rank_among_daily_totals=1+sum(v>total for v in hist),record_start=hist_rows[0][0],record_end=hist_rows[-1][0],comparison='rolling feed accumulation against daily totals, unequal durations') if hist and total is not None else None)
    for sid,s in out['flow'].items():
        gauges=[(key,r) for key,r in out['rain'].items() if r['rain_onset'] and r['lat'] is not None and s['lat'] is not None]
        if gauges and s['peak_at'] and s['peak_basis']=='instantaneous':
            key,r=min(gauges,key=lambda x:(x[1]['lat']-s['lat'])**2+(math.cos(math.radians(s['lat']))*(x[1]['lon']-s['lon']))**2)
            s['hours_rain_to_peak']=round((instant(s['peak_at'])-instant(r['rain_onset']['at'])).total_seconds()/3600,2)
            s['rain_timing_note']=dict(gauge=key,onset=r['rain_onset'],method='first positive reported rain increment in window at nearest gauge with observations; not necessarily the beginning of rainfall')
    # EAA spring daily means and USGS Barton Spring instantaneous readings stay separate.
    for sid in [r[0] for r in db.execute('select distinct site from eaa_springflow_daily')]:
        rows=[row(d,v,src,'daily mean') for d,v,src in db.execute('select date,coalesce(mean_cfs_final,mean_cfs_raw),source_file from eaa_springflow_daily where site=? order by date',(sid,)) if v is not None]
        out['springs'][sid]=spring(rows,t0,t1)
    for sid,location in locs.items():
        if location.get('kind')!='spring': continue
        out['springs'][sid]=spring(by.get((sid,'00060'),[]),t0,t1,daily_rows(db,sid))
        out['springs'][sid].update({k:location.get(k) for k in ('lat','lon','name')})
    ea=load(ROOT/'data/eaa-sites.json',{'sites':{'wells':[]}})
    for site in ea['sites']['wells']:
        sid=site['siteId']; rows=[row(d,v,src,'daily high') for d,v,src in db.execute("select date,value,source_file from eaa_well_levels where site=? and sensor='DHE' order by date",(sid,)) if v is not None]
        rows += [row(d,v,src,'daily high') for d,v,src in db.execute('select date,elevation_ft_amsl,source_file from eaa_index_daily where site=? order by date',(sid,)) if v is not None]
        rows += [row(d,v,src,'daily high') for d,v,src in db.execute('select day,value,source from storm_eaa_daily where site=? order by day',(sid,))]
        rows = unique(rows)
        out['wells']['EAA:'+sid]={**well_pair(rows,t0,t1), 'name':site['siteName'],'lat':site.get('latitude'),'lon':site.get('longitude'),'zone':site.get('aquiferZone'),'county':site.get('county'),'aquifer':site.get('aquifer')}
    for site in load(ROOT/'data/wells-regional.json',{'wells':[]})['wells']:
        sid=site['id']; rows=[row(d,v,src,'daily') for d,v,src in db.execute('select date,level_ft_bls,source_file from well_levels where well=? order by retrieved_at',(sid,)) if v is not None]
        out['wells']['TWDB:'+sid]={**well_pair(rows,t0,t1,True),**{k:site.get(k) for k in ('lat','lon','county','aquifer')},'name':sid,'zone':None}
    llano=[row(a,v,src) for a,v,src in db.execute("select observed_at,value2,source_file from hydromet_readings where agency='LCRA' and site='2641' and param='flow' and observed_at>=? and observed_at<=? order by hourly desc",(stamp(t0),stamp(t1))) if v is not None]
    inflow=volume(llano,t0,t1)
    inflow['source']='LCRA 2641, Llano River at Llano; water passing the gauge, not measured lake storage gain'
    for sid in [r[0] for r in db.execute('select distinct lake from reservoir_levels')]:
        rows=[row(d,v,src,'daily') for d,v,src in db.execute('select date,elevation_ft,source_file from reservoir_levels where lake=? order by retrieved_at',(sid,)) if v is not None]
        s=summarize(rows,t0,t1); start=s['start']; now=s['now']
        pf=db.execute('select date,percent_full from reservoir_levels where lake=? and percent_full is not null order by date desc,retrieved_at desc limit 1',(sid,)).fetchone()
        out['lakes'][sid]=dict(readings=s,elevation_t0=start['value'] if start else None,elevation_now=now['value'] if now else None,
            start_at=start['at'] if start else None,now_at=now['at'] if now else None,change_ft=round(now['value']-start['value'],3) if start and now else None,
            percent_full_now=pf[1] if pf else None,percent_full_at=pf[0] if pf else None,lake_window='through latest daily reading, including lag after storm',
            inflow= inflow if sid=='travis' else None,inflow_acre_ft_so_far=inflow['acre_ft'] if sid=='travis' else None)
    db.close(); existing=load(OUT,{'storms':{}}); existing['storms'][record['id']]=out
    existing['generated_at']=stamp(dt.datetime.now(UTC)); OUT.write_text(json.dumps(existing,indent=1,allow_nan=False)+'\n')
    print(record['id'],{k:len(out[k]) for k in ('flow','rain','springs','wells','lakes')}); return out

def spring(rows,t0,t1,daily=None):
    s=summarize(rows,t0,t1); pool=daily or rows; now=s['now']
    seasonal=[r['value'] for r in pool if hc.doy_distance(instant(r['at']).date(),t1.date())<=15]
    return dict(readings=s,start=s['start']['value'] if s['start'] else None,peak=s['peak']['value'] if s['peak'] else None,now=now['value'] if now else None,
                same_season_median=statistics.median(seasonal) if seasonal else None,percentile_of_record=hc.percentile_rank([r['value'] for r in pool],now['value']) if pool and now else None,
                comparison='against daily means' if daily or (pool and pool[0]['precision']=='daily mean') else 'against captured instantaneous readings',
                record_start=pool[0]['at'] if pool else None,record_end=pool[-1]['at'] if pool else None)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__); sub=p.add_subparsers(dest='cmd',required=True)
    d=sub.add_parser('detect'); d.add_argument('--since',type=dt.date.fromisoformat)
    c=sub.add_parser('compute'); c.add_argument('--storm'); c.add_argument('--all-open',action='store_true')
    a=p.parse_args()
    if a.cmd=='detect': detect(str(a.since) if a.since else None)
    elif a.storm: compute(a.storm)
    elif a.all_open:
        for path in sorted(STORMS.glob('*.json')):
            if load(OUT,{'storms':{}})['storms'].get(path.stem,load(path))['window']['status']=='open': compute(path.stem)
    else: p.error('compute requires --storm or --all-open')
