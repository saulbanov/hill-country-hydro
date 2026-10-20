"""Reusable deterministic comparisons over creek-measurements/v1; no map/provider branches."""
from collections import Counter,defaultdict
import datetime as dt
import hashlib
import json
from pathlib import Path
import statistics
try:
    from .creek_normalize import SCHEMA, stamp, resolve
except ImportError:
    from creek_normalize import SCHEMA, stamp, resolve


def load(folder):
    folder=Path(folder);catalog=json.loads((folder/'catalog.json').read_text())
    if catalog['schema_version']!=SCHEMA: raise ValueError('unsupported analytic schema')
    data=(folder/catalog['observations']['path']).read_bytes()
    if hashlib.sha256(data).hexdigest()!=catalog['observations']['sha256']: raise ValueError('observation checksum mismatch')
    records=[json.loads(line) for line in data.splitlines()]
    rows,_=resolve(records);by=defaultdict(list)
    for r in rows: by[r['series_id']].append(r)
    return catalog,by


def seasonal_reference(rows,anchor=dt.date(2026,10,1),minimum_years=5):
    """Daily medians in ±15 calendar days of the anchor, prior years only.

    A year contributes only with >=25 of 31 dates; require 5 such years and >=80%
    coverage of all potential dates in the previous 20 years.
    No pooling distinct sensor series, provisional values, units, or statistics.
    """
    if len({r['series_id'] for r in rows})>1: return dict(available=False,reason='multiple sensors')
    eligible=[]
    for r in rows:
        if r['state']!='measured' or r['quantity']!='discharge' or r['unit']!='ft3/s' or r['time']['statistic']!='daily_mean' or r['approval']!='Approved': continue
        day=dt.date.fromisoformat(r['time']['date'])
        if not anchor.year-20<=day.year<anchor.year: continue
        # Map month/day to leap year 2000 for stable February 29 and year-wrap handling.
        a=dt.date(2000,anchor.month,anchor.day);b=dt.date(2000,day.month,day.day);distance=abs((a-b).days)
        if min(distance,366-distance)<=15: eligible.append(r)
    counts=Counter(r['time']['date'][:4] for r in eligible);years=sorted(y for y,n in counts.items() if n>=25)
    pool=[r for r in eligible if r['time']['date'][:4] in years]
    coverage=len(pool)/(31*20)
    result=dict(available=False,statistic='daily_mean',unit='ft3/s',anchor_date=str(anchor),half_window_days=15,
        reference_years=[anchor.year-20,anchor.year-1],by_year=dict(sorted(counts.items())),accepted_years=years,days=len(pool),calendar_coverage=round(coverage,4),
        excluded_partial_years=[y for y,n in sorted(counts.items()) if n<25],minimum_years=minimum_years)
    if len(years)<minimum_years or coverage<.8:
        return dict(result,reason='insufficient seasonal daily coverage (5 years and 80% required)')
    vals=sorted(r['value'] for r in pool)
    return dict(result,available=True,median=statistics.median(vals),p10=vals[max(0,int(.1*len(vals))-1)],p90=vals[max(0,int(.9*len(vals))-1)],
        zero_share=sum(v==0 for v in vals)/len(vals),first_year=years[0],last_year=years[-1],
        observation_ids=[r['id'] for r in pool],source_ids=sorted({r['source_id'] for r in pool}),
        qualifier_days=sum(bool(r['qualifiers']) for r in pool),
        method='median of Approved daily means within ±15 calendar days of anchor in previous 20 years; years require >=25/31 dates')


def contrast(reading,reference):
    if not reading or reading['state']!='measured': return dict(available=False,reason='missing or rejected observation')
    if not reference.get('available'): return dict(available=False,reason=reference.get('reason','no daily reference'))
    if reading['quantity']!='discharge' or reading['unit']!=reference['unit']: return dict(available=False,reason='incompatible quantity/units')
    if reading['time']['statistic'] not in ('instantaneous','daily_mean'): return dict(available=False,reason='sampling/aggregation not established')
    median=reference['median'];value=reading['value']
    return dict(available=True,difference_cfs=value-median,ratio_to_daily_median=value/median if median>0 else None,
        ratio_reason='zero daily median' if median==0 else None,instantaneous_percentile=None,
        comparison='instantaneous flow minus seasonal median daily flow' if reading['time']['statistic']=='instantaneous' else 'daily mean minus seasonal median daily flow',
        sampling_match=reading['time']['statistic']=='daily_mean')


def at_or_before(rows,time,max_age_minutes=30):
    t=stamp(time)
    if t is None: raise ValueError('selection requires an unambiguous instant')
    candidates=[r for r in rows if r['time']['instant'] and stamp(r['time']['instant'])<=t]
    if not candidates: return None
    r=max(candidates,key=lambda x:stamp(x['time']['instant']))
    if r['state']!='measured' or (t-stamp(r['time']['instant'])).total_seconds()>60*max_age_minutes: return None
    return r


def report(folder,output):
    catalog,by=load(folder);refs={};lines=['# Creek source coverage and comparisons','',
        'Generated offline from creek-measurements/v1. Counts below are resolved observations. The JSON audit preserves per-day and per-year distributions, qualifiers, gaps, missingness and archive-window coverage.','',
        '| Creek | Feed / original site | Series / statistic | Numeric / missing | Saved interval | Largest gap (minutes) |',
        '|---|---|---|---:|---|---:|']
    for s in catalog['series'].values():
        c=s['coverage'];lines.append(f"| {s['creek']} | {s['feed']} / {s['operator']}:{s['site']} | {s['original_series_id']} / {s['statistic']} | {c['measured']} / {c['missing']} | {c['first']} → {c['last']} | {c['max_gap_minutes']} |")
    lines += ['', '## Seasonal daily reference', '', 'Twenty prior calendar years (2006–2025), September 16–October 16, Approved daily discharge. At least 25 of 31 dates per contributing year and 80% of all 620 possible dates are required. Instantaneous observations are contrasted with this daily reference, never ranked as instantaneous historical percentiles.', '', '| Gauge | Median daily flow (cfs) | Days / 620 | Accepted years | Availability |','|---|---:|---:|---:|---|']
    for key,choice in catalog['display_selection'].items():
        if not key.endswith(':daily_mean'):continue
        ref=seasonal_reference(by.get(choice['series_id'],[]));refs[key]=ref
        lines.append(f"| {key} | {ref.get('median','—')} | {ref['days']} | {len(ref['accepted_years'])} | {ref.get('reason','available')} |")
    lines += ['', '## Candidate inventory', '', '| Provider / site | Name | Scope |', '|---|---|---|']
    for key,candidate in sorted(catalog['candidate_inventory'].items()):
        lines.append(f"| {key} | {candidate['name']} | {candidate['scope']} |")
    lines += ['', '## Scope and exclusions', '',
        'Blunn has City reported flow but no verified USGS daily baseline. City Shoal (2400) and Williamson (950) history has stage but no numeric flow in this event. Stage datum continuity is unverified, so no historical stage comparison is supplied. LCRA hourly points remain hourly_unspecified, not hourly averages.', '',
        'The candidate inventory includes Little Walnut and Kincheon Branch tributaries, Barton Springs, and separate Walnut creeks at Kingsland and Rockne. Those names do not establish an association with the seven saved Austin main channels. Other gauges remain accessible in the existing ledger.', '',
        f"Repeated captures contain {len(catalog['conflicts'])} conflicting series/timestamp values. All originals remain in observations.jsonl; the most recently retrieved copy within one series is selected with a conflict flag. Sensors and feeds are never averaged or stitched.", '',
        'USGS-labeled Hydromet entries with an exact USGS station ID share a physical-gauge identity but retain separate feed series. LCRA-numbered neighbors are not treated as aliases. Exact-time mirror comparisons and all source hashes/locators are in catalog.json.', '',
        'Units: USGS body fields; Hydromet Stage/Flow headers plus captured official Stage (feet) / Flow (cfs) legend. Stage vertical datum remains unknown. Every record retains original unit, time, retrieval time, qualifiers and capture reference. Missing and rejected observations remain explicit; measured zero remains numeric zero.', '',
        'Raw audit: data/model/creek-normalization-audit.json. Provenance: data/normalized/creek-analytics/catalog.json. Official Hydromet field legend: https://hydromet.lcra.org/Reports/RiverStageFlow .', '']
    Path(output).write_text('\n'.join(lines))
    (Path(folder)/'references.json').write_text(json.dumps(refs,indent=2)+'\n')
    print('Coverage and references written:',output)


if __name__=='__main__':
    import argparse
    root=Path(__file__).resolve().parents[1];p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',type=Path,default=root/'data/normalized/creek-analytics');p.add_argument('--report',type=Path,default=root/'docs/CREEK_COVERAGE.md')
    args=p.parse_args();report(args.input,args.report)
