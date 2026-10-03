"""Offline comparison of the handoff's worked figures with computed storm readings."""
import json, sqlite3, statistics
from pathlib import Path
from storm_delta import ROOT, DB, candidate_windows


def build():
    storms=json.loads((ROOT/'app/storm-delta.json').read_text())['storms']
    october=storms['2026-09-30']; july=storms['2026-07-11']; checks=[]
    def check(name,expected,actual,evidence,note=''):
        checks.append(dict(name=name,handoff=expected,actual=actual,matches=expected==actual,evidence=evidence,note=note))
    for sid,name,expected in [('08156800','Shoal peak',541),('08158600','Walnut peak',650),('08150000','Junction peak',35000),('08155300','Barton Loop peak',0.1),('08154700','Bull peak',14.9)]:
        f=october['flow'][sid];check(name,expected,f['peak_cfs'],f['readings']['peak'],'Barton Loop is 0.05 cfs, rounded to one decimal in the handoff.' if sid=='08155300' else '')
    for sid,name,expected,field in [('08158600','Walnut start',0,'start'),('08154700','Bull latest',0.45,'now')]:
        f=october['flow'][sid];check(name,expected,f[field+'_cfs'],f['readings'][field],'Start means the last available reading before the detected t0; any long gap remains visible.')
    f=october['flow']['08150000']
    check('Junction daily-mean percentile',99.9,f['rank']['percentile_of_daily_means'],f['rank'],'An instantaneous peak compared with daily means has a different sampling basis.')
    check('Junction record year',2018,int(f['peak_rank']['record_date'][:4]),f['peak_rank'],'The saved annual peak record is June 14, 1935 (319,000 cfs); the October 8, 2018 peak is 121,000 cfs. October 2026 is 14th against 109 calendar-year daily maxima and 32nd against 105 saved water-year instantaneous maxima.')
    b=october['springs']['08155500']
    check('Barton Springs start',16.5,b['start'],b['readings']['start'],'The detected start is earlier than the handoff baseline.')
    check('Barton Springs peak',26.5,b['peak'],b['readings']['peak'])
    check('Barton Springs percentile rounded',17,round(b['percentile_of_record']),dict(percentile=b['percentile_of_record'],record_start=b['record_start'],record_end=b['record_end'],reading=b['readings']['now']))
    c=october['springs']['Comal'];check('Comal latest daily mean',136,c['now'],c['readings'],'The EAA summary separately reports 147 cfs on Oct 2; 136 is the Oct 1 daily mean, not evidence that no subsequent response occurred.')
    j=october['wells']['EAA:J17WL'];check('J17 daily high',640.07,j['level_after'],j['readings']['window_last'])
    check('J17 one-day rise rounded',1.7,round(j['changes']['1d']['change_ft'],1),j['changes']['1d'])
    pairs={k:v for k,v in october['wells'].items() if k.startswith('EAA:') and v['changes']['7d']}
    for name,rows,expected in [('EAA reporting wells',pairs,36),('EAA seven-day median',pairs,.05),('Recharge-zone seven-day median',{k:v for k,v in pairs.items() if v['zone']=='Recharge Zone'},-.11)]:
        actual=len(rows) if name=='EAA reporting wells' else statistics.median(v['changes']['7d']['change_ft'] for v in rows.values())
        check(name,expected,actual,{k:v['changes']['7d'] for k,v in rows.items()})
    l=october['lakes']['travis'];check('Travis change',.2,l['change_ft'],l['readings'],'The last complete day before t0 is Sep 28: 674.75 ft. Sep 29 is 674.65 ft, producing +0.20 to Oct 2, but its clock time is not recorded.')
    check('Llano integrated acre-feet',16600,l['inflow_acre_ft_so_far'],l['inflow'],'Only observed intervals <=1 hour are integrated. No extrapolation to an unobserved endpoint.')
    check('First flow crossing',dict(station='08158970',at='2026-10-01T17:30Z'),october['window']['triggered_by'][0],october['window']['triggered_by'],'First actual crossing occurs September 30, not at the handoff probe time.')
    for sid,name,rank,years,value in [('08167000','Comfort',2,88,52900),('08166200','Kerrville',3,41,29400),('08151500','Llano',7,88,53600),('08153500','Pedernales',15,88,23600),('08150000','Junction',14,109,30400)]:
        f=july['flow'][sid];a=f['daily_window_annual_rank']
        check('July '+name+' daily rank and maximum',dict(rank=rank,years=years,cfs=value),dict(rank=a['rank'],years=a['years'],cfs=f['daily_window_peak']['value']),dict(daily_peak=f['daily_window_peak'],daily_annual_rank=a,instantaneous_peak=f['readings']['peak'],instantaneous_annual_rank=f['peak_rank']))
    db=sqlite3.connect(DB)
    feeds={}
    for (raw,) in db.execute('select data from storm_rain_feeds order by observed_at'):
        r=json.loads(raw);feeds[r['agency']+':'+r['site']]=r
    city=[r for r in feeds.values() if r['agency']=='COA' and r['rain_in'].get('1Day') is not None]
    check('City 24-hour median rain',1.5,statistics.median(r['rain_in']['1Day'] for r in city),[dict(site=r['site'],at=r['observed_at'],inches=r['rain_in']['1Day']) for r in city],'Includes every reporting City site with a rain sensor, including creek sites.')
    j=feeds['LCRA:2306'];check('Junction weekly rain within 7–8 inches',True,7<=j['rain_in']['1Week']<=8,j,'This is a gauge-level rolling accumulation, not an area average or event-only total.')
    coverage=[dict(day=d,rows=n,stations=c,first=a,last=b) for d,n,c,a,b in db.execute("select substr(observed_at,1,10),count(*),count(distinct station_id),min(observed_at),max(observed_at) from observations where observed_at>='2026-09-29' and observed_at<'2026-10-03' group by 1")]
    updated_candidates=candidate_windows(db,'2026-07-01')
    db.close()
    result=dict(source='HANDOFF_2026-10-03_storm-delta-map.md sections 0, 2, 5 and 8',checks=checks,observation_coverage=coverage,
      enriched_record_candidates=[dict(t0=w['t0'],t1=w['t1'],first_trigger=w['triggered_by'][0]) for w in updated_candidates],
      limits=['The handoff response wording is not fully reproduced: literal zero-start recession rules cannot identify flash flow; thresholds are unchanged.',
              'The original July 11 detection used daily means and remains frozen. After acquiring July continuous readings, the first candidate crossing is July 10 at 23:40 UTC (t0 July 9 at 23:40). A post-cap July 19 candidate also appears. Neither rewrites the reviewed original window; candidate readings are included for review.',
              'No October 3 cloud export was present. USGS observations stop October 2 at 12:10 UTC; later native rain requests do not extend USGS coverage.'])
    path=ROOT/'data/model/storm-delta-validation.json';path.write_text(json.dumps(result,indent=2)+'\n')
    print(f'{len(checks)} comparisons; {sum(c["matches"] for c in checks)} exact/explicitly-rounded matches; {sum(not c["matches"] for c in checks)} differences')
    return result

if __name__=='__main__':build()
