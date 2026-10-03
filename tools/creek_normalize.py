"""Offline prototype analytic layer. See docs/CREEK_ANALYTICS.md; no network or source writes."""
import argparse
from collections import Counter, defaultdict
import datetime as dt
import gzip
import hashlib
import json
import math
from pathlib import Path
import statistics

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = 'creek-measurements/v1'
UTC = dt.timezone.utc
USGS = {'08154700':'Bull Creek','08155300':'Barton Creek','08156800':'Shoal Creek',
        '08158600':'Walnut Creek','08158970':'Williamson Creek','08159000':'Onion Creek'}
HYD = {'LCRA:3992':'Bull Creek','LCRA:4520':'Barton Creek','LCRA:4561':'Walnut Creek',
       'LCRA:4598':'Onion Creek','COA:122':'Blunn Creek','COA:2400':'Shoal Creek','COA:950':'Williamson Creek'}
CREEKS = sorted(set(USGS.values()) | set(HYD.values()))


def stamp(s):
    try:
        t = dt.datetime.fromisoformat(str(s).replace('Z','+00:00'))
        return t.astimezone(UTC) if t.tzinfo else None
    except (ValueError, TypeError):
        return None


def temporal(s, statistic):
    """Never turn an ambiguous timestamp or daily label into an instant."""
    t = stamp(s)
    date_only = isinstance(s,str) and len(s)==10
    if date_only:
        try: dt.date.fromisoformat(s)
        except ValueError: date_only=False
    return dict(original=s, instant=t.isoformat() if t and not date_only else None,
                date=s if date_only else None, precision='date' if date_only else 'instant' if t else 'unknown',
                timezone='UTC' if t else None, original_offset=('Z' if str(s).endswith('Z') else str(s)[-6:]) if t else None,
                interval_start=None, interval_end=None, statistic=statistic)


def numeric(v):
    if v is None or v=='': return None
    try: x=float(v)
    except (ValueError,TypeError): return None
    return x if math.isfinite(x) else None


def convert(v, unit, quantity):
    factors = {'discharge': {'ft^3/s':1,'ft3/s':1,'cfs':1,'m3/s':35.31466672148859,'m^3/s':35.31466672148859},
               'stage': {'ft':1,'feet':1,'m':3.280839895013123}}
    factor=factors.get(quantity,{}).get(unit)
    return (v*factor if v is not None and factor is not None else None,
            {'discharge':'ft3/s','stage':'ft'}.get(quantity) if factor is not None else None)


def record(*, operator, feed, site, series, parameter, quantity, unit, value, when, statistic,
           source, locator, qualifiers=None, approval=None, primary=False, sampling=None, datum=None, stale=None):
    v=numeric(value); cv,cu=convert(v,unit,quantity); t=temporal(when,statistic)
    reasons=[]
    if value is None or value=='': reasons.append('missing')
    elif v is None: reasons.append('invalid_value')
    if cu is None: reasons.append('unknown_unit')
    if t['precision']=='unknown': reasons.append('ambiguous_time')
    if statistic=='instantaneous' and t['precision']!='instant': reasons.append('time_precision_mismatch')
    if quantity=='discharge' and cv is not None and cv<0: reasons.append('negative_discharge')
    q=qualifiers if isinstance(qualifiers,list) else [qualifiers] if qualifiers else []
    if str(approval).lower() in ('rejected','invalid') or any(str(x).upper() in ('REJECTED','INVALID') for x in q): reasons.append('rejected')
    if stale is True: reasons.append('provider_stale')
    sid=f'{feed}:{site}:{series}:{parameter}'
    rid=hashlib.sha256(json.dumps([sid,source,locator],separators=(',',':')).encode()).hexdigest()[:24]
    return dict(id=rid,series_id=sid,operator=operator,feed=feed,original_site_id=site,
                physical_gauge_id=f'{operator}:{site}', original_series_id=series,parameter=parameter,
                quantity=quantity,original_value=value,original_unit=unit,value=cv,unit=cu,
                vertical_datum=datum,datum_status=('unknown' if datum is None else 'known') if quantity=='stage' else 'not_applicable',
                time=t,sampling=sampling,qualifiers=q,approval=approval or 'unknown',primary=primary,
                state='unavailable' if reasons else 'measured',issues=reasons,
                source_id=source,source_locator=locator)


def resolve(records):
    """Keep every observation, flag revisions; only resolve repeated captures of ONE series."""
    groups=defaultdict(list)
    for r in records: groups[(r['series_id'],r['time']['instant'] or r['time']['original'])].append(r)
    selected=[]; conflicts=[]
    for key, rows in sorted(groups.items()):
        good=[r for r in rows if r['state']=='measured']
        vals={(r['value'],r['unit'],r['time']['statistic']) for r in good}
        if len(vals)>1:
            conflicts.append(dict(series_id=key[0],at=key[1],observation_ids=[r['id'] for r in rows],values=sorted({r['value'] for r in good})))
        winner=max(rows,key=lambda r:(stamp(r.get('retrieved_at')) or dt.datetime.min.replace(tzinfo=UTC),r['source_id'],r['id']))
        # A later rejected/missing revision is authoritative; do not resurrect an older value.
        winner['conflicting_captures']=len(vals)>1
        selected.append(winner)
    return selected,conflicts


def select_series(series):
    primary=[s for s in series if s.get('primary')]
    if len(primary)==1: return primary[0]['id'],'provider-designated primary'
    if len(series)==1: return series[0]['id'],'only saved series; primary designation unavailable'
    return None,'multiple series without a unique provider-designated primary; no stitching'


class Builder:
    def __init__(self,root):
        self.root=Path(root);self.sources={};self.rows=[];self.series={};self.identities=[];self.audit=[];self.candidates={}

    def source(self,path,meta,capture=None):
        p=self.root/(capture or path)
        body=gzip.decompress(p.read_bytes()) if p.suffix=='.gz' else p.read_bytes()
        sha=hashlib.sha256(body).hexdigest()
        if meta.get('sha256')!=sha: raise ValueError(f'{p}: source checksum mismatch')
        if meta.get('status')!=200: raise ValueError(f'{p}: unsuccessful source status')
        key=hashlib.sha256(json.dumps([path,capture,meta.get("retrieved_at"),sha]).encode()).hexdigest()[:24]
        self.sources[key]=dict(raw_path=path,capture_path=capture,url=meta.get('url'),sha256=sha,
                               retrieved_at=meta.get('retrieved_at'),bytes=len(body))
        return json.loads(body),key

    def add(self,r,creek):
        r['creek']=creek;r['retrieved_at']=self.sources[r['source_id']]['retrieved_at'];self.rows.append(r)
        s=self.series.setdefault(r['series_id'],dict(id=r['series_id'],creek=creek,operator=r['operator'],feed=r['feed'],
            site=r['original_site_id'],original_series_id=r['original_series_id'],quantity=r['quantity'],
            unit=r['unit'],statistic=r['time']['statistic'],primary=r['primary'],physical_gauge_id=r['physical_gauge_id']))
        if (s['quantity'],s['statistic'],s['unit']) != (r['quantity'],r['time']['statistic'],r['unit']):
            raise ValueError(f"{r['series_id']}: changing semantics require a distinct series")

    def usgs(self,start,end):
        for site,creek in USGS.items():
            man=json.loads((self.root/f'data/model/{site}-daily-history-manifest.json').read_text())
            metadata={x['id']:x for x in man['station_series_inventory_00060_00065']}
            paths=set()
            for folder in ['data/raw/usgs','data/raw/usgs-history']:
                paths.update(p for p in (self.root/folder).rglob(f'*{site}*.json') if not p.name.endswith('.meta.json'))
            for p in sorted(paths):
                mp=p.with_suffix('.meta.json')
                if not mp.exists(): continue
                m=json.loads(mp.read_text())
                if m.get('status')!=200 or '/continuous/' not in m.get('url','') and '/latest-continuous/' not in m.get('url',''): continue
                data,source=self.source(str(p.relative_to(self.root)),m)
                for i,f in enumerate(data.get('features',[])):
                    q=f.get('properties',{}); when=q.get('time'); t=stamp(when)
                    if q.get('monitoring_location_id')!='USGS-'+site or q.get('parameter_code') not in ('00060','00065'): continue
                    if t and not start<=t<=end: continue
                    param=q['parameter_code']; ts=q.get('time_series_id','unknown'); md=metadata.get(ts,{})
                    stat='instantaneous' if q.get('statistic_id')=='00011' else 'unknown'
                    self.add(record(operator='USGS',feed='USGS',site=site,series=ts,parameter=param,
                        quantity='discharge' if param=='00060' else 'stage',unit=q.get('unit_of_measure'),value=q.get('value'),when=when,
                        statistic=stat,source=source,locator=f'features/{i}/properties',qualifiers=q.get('qualifier'),approval=q.get('approval_status'),
                        primary=md.get('primary')=='Primary',sampling='provider instantaneous; cadence measured in audit'),creek)
            m=man['daily_request']
            if not man.get('complete_response'): raise ValueError(f'{site}: daily response incomplete')
            data,source=self.source(m['raw_path'],m,m.get('capture_path'))
            for i,f in enumerate(data['features']):
                q=f['properties']; ts=q['time_series_id']; when=q['time'][:10]
                if q.get('monitoring_location_id')!='USGS-'+site or q.get('parameter_code')!='00060' or q.get('statistic_id')!='00003':
                    raise ValueError(f'{site}: daily identity/statistic mismatch')
                self.add(record(operator='USGS',feed='USGS',site=site,series=ts,parameter='00060',quantity='discharge',unit=q.get('unit_of_measure'),
                    value=q.get('value'),when=when,statistic='daily_mean',source=source,locator=f'features/{i}/properties',
                    qualifiers=q.get('qualifier'),approval=q.get('approval_status'),primary=metadata.get(ts,{}).get('primary')=='Primary',
                    sampling='provider calendar day; original midnight is a date label, interval timezone not established'),creek)
                self.rows[-1]['source_time']=q['time']
            self.identities.append(dict(gauge=f'USGS:{site}',creek=creek,name=man['station']['monitoring_location_name'],
                coordinates=man['station']['coordinates_lon_lat'],evidence=f'data/model/{site}-daily-history-manifest.json',
                series_metadata_evidence=man['metadata_requests']['time_series_metadata']))

    def hydromet(self,start,end):
        for key,creek in HYD.items():
            agency,site=key.split(':');mp=self.root/f'data/captures/hydromet/{agency.lower()}/{site}-manifest.json';man=json.loads(mp.read_text())
            windows=[dict(w, file=k) for k,w in man['windows'].items() if w.get('param')=='flow']
            ok=[w for w in windows if w.get('status')==200]
            self.audit.append(dict(creek=creek,source=key,scope='archive window counts, not unique numeric observations',
                windows=len(windows),failed_windows=len(windows)-len(ok),empty_windows=sum(not w.get('records') for w in ok),
                records=sum(w.get('records',0) for w in ok),first=min((w['first'] for w in ok if w.get('first')),default=None),
                last=max((w['last'] for w in ok if w.get('last')),default=None),
                by_year=dict(sorted(Counter({y:sum(w.get('records',0) for w in ok if str(w.get('year'))==y) for y in {str(w.get('year')) for w in ok}}).items())),
                manifest=str(mp.relative_to(self.root)),comparison='event points only; no verified continuous sensor/datum history'))
            for w in sorted(ok,key=lambda x:x['file']):
                if not w.get('first') or not w.get('last'): continue
                if stamp(w['last'])<start or stamp(w['first'])>end: continue
                data,source=self.source(w.get('raw_path'),w,'data/captures/hydromet/'+w['file'])
                if str(data.get('siteNumber'))!=site: raise ValueError(f'{mp}: wrong site in capture')
                for i,q in enumerate(data.get('records',[])):
                    t=stamp(q.get('dateTime'))
                    if t and not start<=t<=end: continue
                    for field,kind,unit,quantity in [('value1','Stage','ft','stage'),('value2','Flow','cfs','discharge')]:
                        known=data.get(field+'Type')==kind
                        stat='unknown_daily' if data.get('isDaily') else 'hourly_unspecified' if data.get('isHourly') else 'reported_point'
                        self.add(record(operator=agency,feed='Hydromet',site=site,series=f'{agency}:flow:{field}:{stat}',parameter=field,
                            quantity=quantity if known else 'unknown',unit=unit if known else None,value=q.get(field),when=q.get('dateTime'),
                            statistic=stat,source=source,locator=f'records/{i}/{field}',sampling=stat),creek)
        # Keep native feed observations and verified distribution aliases, including absent values.
        for p in sorted((self.root/'data/raw/hydromet/current').glob('*-all-sites.json')):
            m=json.loads(p.with_suffix('.meta.json').read_text())
            if m.get('status')!=200: continue
            data,source=self.source(str(p.relative_to(self.root)),m)
            for i,q in enumerate(data):
                name=q.get('siteName',''); lowered=name.lower()
                creek=next((c for c in CREEKS if c.split()[0].lower() in lowered),None)
                if creek:
                    key=f"{q.get('agency')}:{q.get('siteNumber')}"
                    reason='selected event adapter' if key in HYD or q.get('agency')=='USGS' and str(q.get('siteNumber')) in USGS else 'outside bounded adapter'
                    if 'little walnut' in lowered or 'kincheon' in lowered: reason='tributary, not main channel'
                    if 'spgs' in lowered or 'springs' in lowered: reason='spring, not channel gauge'
                    if q.get('latitude') is not None and not (30.05<=float(q['latitude'])<=30.47 and -98.05<=float(q['longitude'])<=-97.60): reason='outside Austin prototype area; creek-name match alone rejected'
                    self.candidates[key]=dict(provider=q.get('agency'),site=str(q.get('siteNumber')),name=name,creek=creek,scope=reason,source_id=source)
                agency=q.get('agency');site=str(q.get('siteNumber'));key=f'{agency}:{site}';creek=HYD.get(key) or (USGS.get(site) if agency=='USGS' else None)
                t=stamp(q.get('dateTime'))
                if not creek or t and not start<=t<=end: continue
                for field,quantity,unit in [('stage','stage','ft'),('flow','discharge','cfs')]:
                    self.add(record(operator=agency,feed='Hydromet',site=site,series=f'{agency}:current:{field}',parameter=field,
                        quantity=quantity,unit=unit,value=q.get(field),when=q.get('dateTime'),statistic='reported_point',
                        source=source,locator=f'/{i}/{field}',stale=q.get('isStale'),sampling='snapshot of provider reported point'),creek)
                ident=dict(gauge=key,creek=creek,name=q.get('siteName'),coordinates=[q.get('longitude'),q.get('latitude')],evidence_source_id=source,
                    alias_of=f'USGS:{site}' if agency=='USGS' else None,
                    alias_basis='provider agency=USGS AND exact original USGS station number' if agency=='USGS' else 'No cross-provider alias verified; proximity/name not evidence of identity')
                self.identities.append(ident)

    def finish(self,start,end,out):
        resolved,conflicts=resolve(self.rows)
        selected=defaultdict(list)
        for r in resolved: selected[r['series_id']].append(r)
        for sid,s in self.series.items():
            rows=selected[sid];good=[r for r in rows if r['state']=='measured'];times=sorted({r['time']['instant'] for r in good if r['time']['instant']})
            gaps=[(stamp(b)-stamp(a)).total_seconds()/60 for a,b in zip(times,times[1:])]
            s['coverage']=dict(records=len(rows),measured=len(good),missing=sum('missing' in r['issues'] for r in rows),
                rejected=len(rows)-len(good),first=min((r['time']['original'] for r in good),default=None),last=max((r['time']['original'] for r in good),default=None),
                by_date=dict(sorted(Counter(r['time']['original'][:10] for r in good if r['time']['precision']=='instant').items())),
                by_year=dict(sorted(Counter(r['time']['original'][:4] for r in good).items())),
                median_spacing_minutes=statistics.median(gaps) if gaps else None,max_gap_minutes=max(gaps,default=None),gaps_over_60_minutes=sum(g>60 for g in gaps),
                approval_counts=dict(Counter(r['approval'] for r in rows)),qualifier_counts=dict(Counter(str(q) for r in rows for q in r['qualifiers'])))
        choices={}
        for site in USGS:
            for stat in ['instantaneous','daily_mean']:
                ss=[s for s in self.series.values() if s['feed']=='USGS' and s['site']==site and s['quantity']=='discharge' and s['statistic']==stat]
                sid,why=select_series(ss);choices[f'USGS:{site}:{stat}']=dict(series_id=sid,reason=why,alternates=[s['id'] for s in ss if s['id']!=sid])
        # Exact-time mirror agreement is diagnostic; it never establishes identity or replaces USGS.
        native=defaultdict(list)
        for r in resolved:
            if r['feed']=='USGS' and r['time']['statistic']=='instantaneous': native[(r['physical_gauge_id'],r['quantity'],r['time']['instant'])].append(r)
        mirrors=[]
        for r in resolved:
            if r['operator']=='USGS' and r['feed']=='Hydromet':
                matches=native[(r['physical_gauge_id'],r['quantity'],r['time']['instant'])]
                mirrors.append(dict(observation_id=r['id'],native_observation_ids=[x['id'] for x in matches],
                    status='no_exact_time_match' if not matches else 'agreement' if all(x['value']==r['value'] and x['state']==r['state'] for x in matches) else 'disagreement'))
        out.mkdir(parents=True,exist_ok=True)
        observations=out/'observations.jsonl'
        with observations.open('w') as f:
            for r in sorted(self.rows,key=lambda r:(r['series_id'],r['time']['original'] or '',r['source_id'],r['id'])):
                f.write(json.dumps(r,separators=(',',':'),allow_nan=False)+'\n')
        catalog=dict(schema_version=SCHEMA,status='prototype',event_interval=dict(start=start.isoformat(),end=end.isoformat()),
            candidate_inventory=self.candidates,source_catalog=self.sources,identities=self.identities,series=self.series,display_selection=choices,
            conflicts=conflicts,mirror_checks=mirrors,archive_coverage=self.audit,
            observations=dict(path='observations.jsonl',rows=len(self.rows),sha256=hashlib.sha256(observations.read_bytes()).hexdigest()),
            limitations=['Hydromet flow/stage units follow the captured official field legend and matching history headers.',
                'Hydromet hourly spacing is not an hourly mean; native history is reported_point, statistic not independently certified.',
                'No inferred datum, sensor crosswalk, rain/lake/well adapter, rejection flag, or missing observation is fabricated.',
                'Stage datum unknown. Station land-surface altitude datum is not the gauge datum.',
                'USGS historical daily means and instantaneous series remain distinct. Hydromet archive counts describe captured windows, not numeric completeness.'])
        (out/'catalog.json').write_text(json.dumps(catalog,indent=2,allow_nan=False)+'\n')
        return catalog


def build(root=ROOT,storm='2026-09-30',through='2026-10-03T12:15:00Z',out=None):
    root=Path(root);end=stamp(through)
    window=json.loads((root/f'data/model/storms/{storm}.json').read_text())['window']
    start=stamp(window['t0'])-dt.timedelta(hours=1)
    if not end or not start<end<=stamp(window['cap_at']): raise ValueError('invalid analysis cutoff')
    b=Builder(root);b.usgs(start,end);b.hydromet(start,end)
    catalog=b.finish(start,end,Path(out) if out else root/'data/normalized/creek-analytics')
    # Committed compact audit, generated by the same command.
    audit={k:v for k,v in catalog.items() if k not in ('source_catalog','identities','conflicts','mirror_checks')}
    audit['conflict_count']=len(catalog['conflicts']);audit['mirror_status_counts']=dict(Counter(x['status'] for x in catalog['mirror_checks']))
    audit['unit_evidence']='data/captures/documentary/hydromet-normalization/stage-flow-units.meta.json'
    audit['scope_exclusions']=['Barton Springs is a spring, not Barton Creek.','Little Walnut and Kincheon Branch are tributaries, not the named main channel.',
        'Walnut Creek at Kingsland and Rockne are different waterways.','Other Austin gauges remain in the original ledger; this adapter is bounded to six USGS and seven LCRA/COA sites.']
    (root/'data/model/creek-normalization-audit.json').write_text(json.dumps(audit,indent=2)+'\n')
    print(f"{SCHEMA}: {catalog['observations']['rows']} records, {len(catalog['series'])} series; {audit['conflict_count']} conflicts retained")
    return catalog


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,default=ROOT);p.add_argument('--storm',default='2026-09-30');p.add_argument('--through',default='2026-10-03T12:15:00Z');p.add_argument('--out',type=Path)
    a=p.parse_args();build(a.root,a.storm,a.through,a.out)
