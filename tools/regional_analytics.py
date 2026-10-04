"""Read and compare regional-measurements/v1 without fetching or changing source data."""
from collections import Counter,defaultdict
import datetime as dt
import hashlib
import json
from pathlib import Path
import sqlite3
import statistics
import zlib
try:
    from .regional_normalize import SCHEMA,ROOT
    from .creek_normalize import resolve,stamp,select_series
    from .creek_analytics import at_or_before
except ImportError:
    from regional_normalize import SCHEMA,ROOT
    from creek_normalize import resolve,stamp,select_series
    from creek_analytics import at_or_before

class Reader:
    def __init__(self,folder,verify=True):
        folder=Path(folder);self.catalog=json.loads((folder/'catalog.json').read_text())
        if self.catalog['schema_version']!=SCHEMA:raise ValueError('unsupported regional schema')
        path=folder/self.catalog['observations']['path']
        if verify and hashlib.sha256(path.read_bytes()).hexdigest()!=self.catalog['observations']['sha256']:raise ValueError('normalized checksum mismatch')
        self.db=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)
    def rows(self,series,resolved=True):
        rows=[json.loads(zlib.decompress(x[0])) for x in self.db.execute('select payload from observations where series=? order by at,retrieved,id',(series,))]
        return resolve(rows)[0] if resolved else rows
    def choose(self,site,quantity,statistic,feed=None):
        ss=[dict(s,id=s['series_id']) for s in self.catalog['series'].values() if s['site_key']==site and s['quantity']==quantity and s['statistic']==statistic and (feed is None or s['feed']==feed)]
        return select_series(ss)
    def close(self):self.db.close()


def exact_day(rows,day):
    candidates=[r for r in rows if r['time']['date']==day]
    return candidates[0] if len(candidates)==1 and candidates[0]['state']=='measured' else None


def compatible(a,b):
    if not a or not b or a['state']!='measured' or b['state']!='measured':return False
    keys=('series_id','quantity','unit','vertical_datum')
    if any(a[k]!=b[k] for k in keys) or a['time']['statistic']!=b['time']['statistic']:return False
    if a['quantity'] in ('stage','groundwater_elevation','reservoir_elevation') and not a['vertical_datum']:return False
    if a['quantity']=='percent_full' and (not a.get('capacity') or a.get('capacity',{}).get('conservation_capacity_af')!=b.get('capacity',{}).get('conservation_capacity_af')):return False
    return True


def change(a,b):
    if not compatible(a,b):return {'available':False,'reason':'missing endpoint or incompatible series, units, datum or sampling'}
    delta=b['value']-a['value'];q=b['quantity']
    return {'available':True,'difference':delta,'unit':b['unit'],'water_level_change':-delta if q=='groundwater_depth' else delta,
        'from_id':a['id'],'to_id':b['id'],'from_time':a['time']['original'],'to_time':b['time']['original'],
        'meaning':'positive depth change is a lower water level' if q=='groundwater_depth' else 'reported quantity change',
        'continuity_note':b.get('continuity')}


def seasonal_reference(rows,day,years=20,half_window=15):
    """Exact daily sampling only; prior 20 calendar years, circular month/day window.

    Expected dates enumerated in each real calendar year (Feb 29 exists only in leap years).
    80% of dates in a year and 80% overall plus 5 years required. Midrank ties include zeros.
    """
    anchor=dt.date.fromisoformat(day);end=anchor.year-1;start=anchor.year-years
    out={'available':False,'reference_years':[start,end],'anchor':day,'half_window_days':half_window,'tie_rule':'100*(below + half ties)/n; measured zeros retained','leap_rule':'circular month/day distance on leap calendar; expected dates enumerated in each actual year'}
    if len({r['series_id'] for r in rows})!=1:return dict(out,reason='no single sensor series')
    out['series_id']=rows[0]['series_id']
    if any(r['quantity']!='discharge' or r['unit']!='ft3/s' or r['time']['statistic']!='daily_mean' for r in rows):return dict(out,reason='requires daily mean discharge')
    def near(d):
        n=abs((dt.date(2000,d.month,d.day)-dt.date(2000,anchor.month,anchor.day)).days);return min(n,366-n)<=half_window
    expected={}
    for y in range(start,end+1):
        d=dt.date(y,1,1);n=0
        while d.year==y:
            n+=int(near(d));d+=dt.timedelta(days=1)
        expected[str(y)]=n
    eligible={}
    for r in rows:
        if r['state']!='measured' or r['approval']!='Approved' or not r['time']['date']:continue
        d=dt.date.fromisoformat(r['time']['date'])
        if start<=d.year<=end and near(d):eligible[str(d)]=r
    counts=Counter(d[:4] for d in eligible);accepted=[y for y,n in expected.items() if counts[y]>=.8*n]
    pool=[r for d,r in eligible.items() if d[:4] in accepted];coverage=len(pool)/sum(expected.values())
    out.update(expected_by_year=expected,numeric_by_year=dict(counts),accepted_years=accepted,days=len(pool),expected_days=sum(expected.values()),coverage=coverage)
    if len(accepted)<5 or coverage<.8:return dict(out,reason='requires 5 qualifying years and 80% of all expected days')
    vals=sorted(r['value'] for r in pool)
    return dict(out,available=True,median=statistics.median(vals),zero_share=vals.count(0)/len(vals),values=vals,observation_ids=[r['id'] for r in pool],source_ids=sorted({r['source_id'] for r in pool}))


def rank(reading,reference):
    if not reading or reading['state']!='measured' or not reference.get('available'):return {'available':False,'reason':'missing daily reading or insufficient historical coverage'}
    if reading['series_id']!=reference.get('series_id') or reading['quantity']!='discharge' or reading['unit']!='ft3/s' or reading['time']['statistic']!='daily_mean':return {'available':False,'reason':'instantaneous values cannot receive a daily rank'}
    vals=reference['values'];x=reading['value'];med=reference['median']
    return {'available':True,'percentile':100*(sum(v<x for v in vals)+.5*sum(v==x for v in vals))/len(vals),'ratio_to_daily_median':x/med if med else None,'median':med,'days':len(vals),'reference_years':reference['reference_years']}


def rain_total(rows,start,end):
    """Only certified, adjoining incremental intervals can supply a total."""
    a=stamp(start);b=stamp(end)
    if not a or not b or b<=a:raise ValueError('invalid rain interval')
    if not rows:return {'available':False,'reason':'no intervals'}
    if len({(r['series_id'],r['unit']) for r in rows})!=1:return {'available':False,'reason':'mixed sensors or units'}
    if any(r['quantity']!='rain' or r['time']['statistic']!='incremental' or r['state']!='measured' or not r['time']['interval_start'] or not r['time']['interval_end'] for r in rows):return {'available':False,'reason':'only verified incremental intervals may be added; rolling/counter/unknown boundaries withheld'}
    cursor=a;total=0
    for r in sorted(rows,key=lambda x:x['time']['interval_start']):
        lo=stamp(r['time']['interval_start']);hi=stamp(r['time']['interval_end'])
        if lo!=cursor or hi<=lo or hi>b:return {'available':False,'reason':'gap, overlap, reset or out-of-window interval'}
        if r['value']<0:return {'available':False,'reason':'negative/reset increment'}
        cursor=hi;total+=r['value']
    return {'available':cursor==b,'total':total if cursor==b else None,'reason':None if cursor==b else 'incomplete interval coverage'}


def audit(folder,root=ROOT):
    reader=Reader(folder);c=reader.catalog;out={};day='2026-09-30';refs={}
    for sid,s in c['series'].items():
        rows=reader.rows(sid);good=[r for r in rows if r['state']=='measured'];times=sorted({r['time']['instant'] for r in good if r['time']['instant']});gaps=[(stamp(b)-stamp(a)).total_seconds()/60 for a,b in zip(times,times[1:])]
        site=c['sites'].get(s['site_key'],{})
        out[sid]={'provider':s['feed'],'station':s['site_key'],'basin':site.get('basin','unassigned'),'quantity':s['quantity'],'statistic':s['statistic'],'unit':s['unit'],'records':len(rows),'numeric':len(good),'unavailable':len(rows)-len(good),'by_year':dict(Counter(r['time']['original'][:4] for r in good)),'by_date':dict(Counter((r['time']['date'] or r['time']['original'][:10]) for r in good if r['time']['original'][:4]=='2026')),'first':min((r['time']['original'] for r in good),default=None),'last':max((r['time']['original'] for r in good),default=None),'median_spacing_minutes':statistics.median(gaps) if gaps else None,'largest_gap_minutes':max(gaps,default=None),'quality':dict(Counter(r['approval'] for r in rows)),'issues':dict(Counter(i for r in rows for i in r['issues'])),'conflicts':sum(r.get('conflicting_captures',False) for r in rows)}
        if s['quantity']=='discharge' and s['statistic']=='daily_mean':refs[sid]=seasonal_reference(rows,day)
    reader.close()
    report={'schema_version':SCHEMA,'cutoff':c['cutoff'],'seasonal_day':day,'series':out,'source_gaps':c['gaps'],'archive_audit':'data/model/regional-normalization-audit.json','count_basis':'resolved observations within retained adapter period; archive numeric audit counts all original rows'}
    (Path(root)/'data/model/regional-coverage.json').write_text(json.dumps(report,indent=2)+'\n')
    (Path(folder)/'references.json').write_text(json.dumps(refs,separators=(',',':'))+'\n')
    lines=['# Regional source coverage','',f"Saved-data cutoff: {c['cutoff']}. Seasonal comparison: {day}. Generated offline; counts distinguish retained normalized records from full archive inspection.",'','| Provider | Quantity / sampling | Series | Numeric records | Unavailable |','|---|---|---:|---:|---:|']
    groups=defaultdict(list)
    for s in out.values():groups[(s['provider'],s['quantity'],s['statistic'])].append(s)
    for (feed,q,st),ss in sorted(groups.items()):lines.append(f"| {feed} | {q} / {st} | {len(ss)} | {sum(s['numeric'] for s in ss)} | {sum(s['unavailable'] for s in ss)} |")
    lines+=['','Full station, basin, date, year, spacing, quality and conflict distributions: `data/model/regional-coverage.json`. Original numeric source-row counts and source failures: `data/model/regional-normalization-audit.json`. Unassigned basin means no verified surface watershed association yet; aquifer connection is never inferred.','', 'Rainfall event sums are withheld where interval boundaries are unverified. Rolling 24-hour observations stay separate. EAA rain/stream inventories are not measured coverage. Missing original EAA retrieval metadata is retained as a provenance gap. No local pilot spring is borrowed from another basin.','']
    (Path(root)/'docs/REGIONAL_COVERAGE.md').write_text('\n'.join(lines));print('Audited',len(out),'series;',sum(x['numeric'] for x in out.values()),'resolved numeric records')
    return report

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,default=ROOT/'data/normalized/regional-analytics');a=p.parse_args();audit(a.input)
