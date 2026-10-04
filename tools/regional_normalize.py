"""Offline regional-measurements/v1 adapters over preserved raw bodies. No network calls."""
import argparse
from collections import Counter, defaultdict
import csv
import datetime as dt
import gzip
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import zlib
try:
    from .creek_normalize import record, numeric, stamp, select_series
    from .eaa import parse_var
except ImportError:
    from creek_normalize import record, numeric, stamp, select_series
    from eaa import parse_var

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = 'regional-measurements/v1'
PARAMS = {'00060': ('discharge', None), '00065': ('stage', None),
          '72019': ('groundwater_depth', 'land surface'), '62610': ('groundwater_elevation', 'NGVD29'),
          '62611': ('groundwater_elevation', 'NAVD88'), '62614': ('reservoir_elevation', 'NGVD29'),
          '62615': ('reservoir_elevation', 'NAVD88'), '00045': ('rain', None)}
UNITS = {'rain': {'in': 1, 'inches': 1, 'mm': 1/25.4},
         'groundwater_depth': {'ft': 1, 'm': 3.280839895013123},
         'groundwater_elevation': {'ft': 1, 'm': 3.280839895013123},
         'reservoir_elevation': {'ft': 1, 'm': 3.280839895013123},
         'storage': {'acre-ft': 1}, 'conservation_storage': {'acre-ft': 1},
         'percent_full': {'%': 1}}
CANON = {'rain':'in', 'groundwater_depth':'ft', 'groundwater_elevation':'ft',
         'reservoir_elevation':'ft', 'storage':'acre-ft', 'conservation_storage':'acre-ft', 'percent_full':'%'}


def measurement(**kw):
    """Extend the original creek record without changing its v1 contract or output."""
    extra = kw.pop('extra', {})
    r = record(**kw)
    q = r['quantity']; v = numeric(r['original_value'])
    if q in UNITS:
        factor = UNITS[q].get(r['original_unit'])
        if factor is not None:
            r['unit'] = CANON[q]; r['value'] = v*factor if v is not None else None
            r['issues'] = [s for s in r['issues'] if s != 'unknown_unit']
        if q in ('rain','storage','conservation_storage','percent_full') and v is not None and v < 0:
            r['issues'].append('negative_quantity')
    if q in ('groundwater_depth','groundwater_elevation','reservoir_elevation','stage'):
        r['datum_status'] = 'known' if r['vertical_datum'] else 'unknown'
    r.update(extra)
    r['state'] = 'unavailable' if r['issues'] else 'measured'
    return r


class Builder:
    def __init__(self, root, out, since, through, daily_start='2006-01-01', only=None, audit_path='data/model/regional-normalization-audit.json', hydromet_params=None):
        """`only` restricts adaptation to named site keys before bodies are read (full-history partitions);
        `daily_start` is the retention gate for daily USGS, reservoir and spring records."""
        self.root=Path(root); self.out=Path(out); self.out.mkdir(parents=True,exist_ok=True)
        self.since=since; self.through=through; self.daily_start=daily_start; self.only=set(only) if only else None; self.audit_path=audit_path; self.hydromet_params=set(hydromet_params) if hydromet_params else None; self.sources={};self.series={};self.sites={};self.gaps=[];self.audits={}
        # A new scratch database is atomically published only after a successful build.
        self.dbpath=self.out/'building.sqlite';self.db=sqlite3.connect(self.dbpath)
        self.db.execute('drop table if exists observations')
        self.db.execute('create table observations(id text primary key, series text, at text, retrieved text, payload blob)')
        self.n=0

    def wanted(self,key):
        return self.only is None or key in self.only

    def source(self,path,meta=None,capture=None,url=None):
        p=self.root/(capture or path)
        if not p.exists():
            self.gaps.append({'path':str(capture or path),'reason':'capture missing'});return None,None
        body=gzip.decompress(p.read_bytes()) if p.suffix=='.gz' else p.read_bytes()
        sha=hashlib.sha256(body).hexdigest();meta=meta or {}
        if meta.get('sha256') and meta['sha256']!=sha:raise ValueError(f'checksum mismatch: {p}')
        if meta.get('status',200)!=200:
            self.gaps.append({'path':str(path),'reason':f"HTTP {meta.get('status')}"});return None,None
        sid=hashlib.sha256((str(path)+str(meta.get('retrieved_at'))+sha).encode()).hexdigest()[:24]
        self.sources[sid]={'raw_path':path,'capture_path':capture,'sha256':sha,'bytes':len(body),
            'url':meta.get('url',url),'retrieved_at':meta.get('retrieved_at'),
            'provenance_status':'verified_capture' if meta.get('sha256') and meta.get('retrieved_at') else 'original_fetch_metadata_missing'}
        return body,sid

    def inspect(self, key, when, value, quality=None):
        a=self.audits.setdefault(key,{'records':0,'numeric':0,'missing_or_invalid':0,'by_year':{},'quality':{}})
        a['records']+=1;good=numeric(value) is not None;a['numeric']+=int(good);a['missing_or_invalid']+=int(not good)
        y=str(when)[:4];c=a['by_year'].setdefault(y,{'records':0,'numeric':0});c['records']+=1;c['numeric']+=int(good)
        q=str(quality or 'unknown');a['quality'][q]=a['quality'].get(q,0)+1

    def add(self,r):
        r['retrieved_at']=self.sources[r['source_id']]['retrieved_at']
        r['provenance_status']=self.sources[r['source_id']]['provenance_status']
        sid=r['series_id'];s=self.series.setdefault(sid,{k:r[k] for k in ('series_id','operator','feed','original_site_id','original_series_id','quantity','unit','vertical_datum','primary')})
        s['statistic']=r['time']['statistic'];s['sampling']=r['sampling'];s['site_key']=r['physical_gauge_id']
        if (s['quantity'],s['unit'],s['vertical_datum'])!=(r['quantity'],r['unit'],r['vertical_datum']):raise ValueError('changing series semantics')
        b=json.dumps(r,separators=(',',':'),allow_nan=False).encode()
        self.db.execute('insert or ignore into observations values(?,?,?,?,?)',(r['id'],sid,r['time']['instant'] or r['time']['original'],r['retrieved_at'],zlib.compress(b)))
        self.n+=1

    def usgs(self):
        inventory=json.loads((self.root/'data/usgs-locations-regional.json').read_text())['locations']
        self.sites.update({'USGS:'+s['id']:{'name':s['name'],'coordinates':[s['lon'],s['lat']],'kind':s['kind'],'basin':'unassigned','evidence':'data/usgs-locations-regional.json'} for s in inventory})
        metadata={}
        for p in sorted((self.root/'data/model').glob('*-daily-history-manifest.json')):
            site=p.name.split('-')[0]
            if not self.wanted('USGS:'+site):continue
            man=json.loads(p.read_text());m=man['daily_request']
            if 'station' in man:
                metadata[site]={x['id']:x for x in man['station_series_inventory_00060_00065']}
                self.sites['USGS:'+site].update(huc=man['station'].get('hydrologic_unit_code'),basin={'12090204':'Llano','12090206':'Pedernales'}.get(str(man['station'].get('hydrologic_unit_code'))[:8],'regional context'))
            if m.get('next_link') or m.get('feature_count',0)>=50000:
                self.gaps.append({'path':str(p.relative_to(self.root)),'reason':'incomplete USGS response'});continue
            body,source=self.source(m['raw_path'],m,m.get('capture_path'))
            if body is None:continue
            for i,f in enumerate(json.loads(body).get('features',[])):
                x=f['properties'];param=x.get('parameter_code');ts=x['time_series_id'];when=x['time'][:10]
                self.inspect(f'USGS:{site}:{ts}:{param}:daily',when,x.get('value'),x.get('approval_status'))
                if param not in PARAMS or when<self.daily_start or when>self.through[:10]:continue
                quantity,datum=PARAMS[param];stat={'00003':'daily_mean','00006':'daily_sum','00001':'daily_max','00002':'daily_min'}.get(x.get('statistic_id'),'unknown_daily')
                self.add(measurement(operator='USGS',feed='USGS',site=site,series=ts,parameter=param,quantity=quantity,unit=x.get('unit_of_measure'),value=x.get('value'),when=when,statistic=stat,source=source,locator=f'features/{i}/properties',qualifiers=x.get('qualifier'),approval=x.get('approval_status'),datum=datum,primary=metadata.get(site,{}).get(ts,{}).get('primary')=='Primary',sampling='provider calendar day; timezone not established',extra={'source_time':x['time'],'last_modified':x.get('last_modified')}))
        for folder in ['data/raw/usgs','data/raw/usgs-history']:
            for p in sorted((self.root/folder).rglob('*.meta.json')):
                m=json.loads(p.read_text());url=m.get('url','')
                if m.get('status')!=200 or not any(x in url for x in ['/continuous/','/latest-continuous/']):continue
                raw=str(p.relative_to(self.root)).replace('.meta.json','.json');body,source=self.source(raw,m)
                if body is None:continue
                for i,f in enumerate(json.loads(body).get('features',[])):
                    x=f['properties'];site=x.get('monitoring_location_id','').replace('USGS-','');param=x.get('parameter_code');when=x.get('time','');t=stamp(when)
                    if 'USGS:'+site not in self.sites or not self.wanted('USGS:'+site) or param not in PARAMS or (t and not stamp(self.since+'T00:00:00Z')<=t<=stamp(self.through)):continue
                    quantity,datum=PARAMS[param];ts=x.get('time_series_id','unknown');stat='instantaneous' if x.get('statistic_id')=='00011' else 'unknown'
                    self.inspect(f'USGS:{site}:{ts}:{param}:continuous',when,x.get('value'),x.get('approval_status'))
                    self.add(measurement(operator='USGS',feed='USGS',site=site,series=ts,parameter=param,quantity=quantity,unit=x.get('unit_of_measure'),value=x.get('value'),when=when,statistic=stat,source=source,locator=f'features/{i}/properties',qualifiers=x.get('qualifier'),approval=x.get('approval_status'),datum=datum,primary=metadata.get(site,{}).get(ts,{}).get('primary')=='Primary',sampling='provider point',extra={'last_modified':x.get('last_modified')}))
        self.db.commit(); print('USGS normalized',self.n,flush=True)

    def hydromet(self):
        for p in sorted((self.root/'data/raw/hydromet/current').glob('*all-sites.json')):
            m=json.loads(p.with_suffix('.meta.json').read_text());body,source=self.source(str(p.relative_to(self.root)),m)
            if body is None:continue
            for i,x in enumerate(json.loads(body)):
                agency=x['agency'];site=str(x['siteNumber']);key=f'{agency}:{site}'
                if not self.wanted(key):continue
                if agency!='USGS':self.sites[key]={'name':x['siteName'],'coordinates':[numeric(x.get('longitude')),numeric(x.get('latitude'))],'kind':x.get('siteType'),'basin':'unassigned','evidence_source_id':source}
                fields=[('stage','stage','ft','reported_point'),('flow','discharge','cfs','reported_point'),('rainfall1Day','rain','in','rolling_24h'),('rainfallToday','rain','in','since_midnight')]
                for field,q,u,stat in fields:
                    if field not in x:continue
                    r=measurement(operator=agency,feed='Hydromet',site=site,series=f'{agency}:current:{field}',parameter=field,quantity=q,unit=u,value=x[field],when=x['dateTime'],statistic=stat,source=source,locator=f'/{i}/{field}',approval='provisional',stale=x.get('isStale'),sampling='snapshot; rainfall windows overlap',extra={'alias_basis':'exact provider USGS station ID' if agency=='USGS' else None})
                    if r['time']['instant'] and stamp(r['time']['instant'])>stamp(self.through):continue
                    if stat=='rolling_24h' and r['time']['instant']:
                        r['time'].update(interval_start=(stamp(r['time']['instant'])-dt.timedelta(hours=24)).isoformat(),interval_end=r['time']['instant'])
                    self.add(r)
        windows={}
        for p in sorted((self.root/'data/captures/hydromet').glob('*/*manifest.json')):windows.update(json.loads(p.read_text()).get('windows',{}))
        sources=[]
        for path,m in sorted(windows.items()):sources.append((m.get('raw_path'),m,'data/captures/hydromet/'+path,m.get('agency'),str(m.get('site')),m.get('param')))
        for p in sorted((self.root/'data/raw/hydromet/history').rglob('*rain-window.meta.json')):
            m=json.loads(p.read_text());sources.append((str(p.relative_to(self.root)).replace('.meta.json','.json'),m,None,'LCRA',p.parent.name,'rain'))
        for path,m,cap,agency,site,param in sources:
            if not self.wanted(f'{agency}:{site}') or (self.hydromet_params is not None and param not in self.hydromet_params):continue
            if m.get('status')!=200:
                self.gaps.append({'path':path,'reason':f"HTTP {m.get('status')}"});continue
            body,source=self.source(path,m,cap)
            if body is None:continue
            d=json.loads(body)
            if str(d.get('siteNumber'))!=site:raise ValueError('Hydromet site mismatch')
            stat='hourly_unspecified' if d.get('isHourly') else 'reported_point'
            fields={'flow':[('value1','stage','ft',stat),('value2','discharge','cfs',stat)],'lakelevel':[('value1','reservoir_elevation','ft',stat)],'rain':[('value1','rain','in','cumulative_counter'),('value2','rain','in','reported_increment')],'rainDaily':[('value1','rain','in','daily_total_boundary_unverified')]}.get(param,[])
            expected={'flow':'Stage','lakelevel':'Elevation','rain':'PC','rainDaily':'dailyRain'}.get(param)
            if expected and d.get('value1Type')!=expected:
                self.gaps.append({'path':path,'reason':f"unsupported header {d.get('value1Type')} for {param}"});continue
            for i,x in enumerate(d.get('records',[])):
                when=x.get('dateTime','')
                for field,q,u,st in fields:
                    self.inspect(f'Hydromet:{agency}:{site}:{param}:{field}:{st}',when,x.get(field))
                    if when[:10]<self.since or (stamp(when) and stamp(when)>stamp(self.through)):continue
                    self.add(measurement(operator=agency,feed='Hydromet',site=site,series=f'{agency}:{param}:{field}:{st}',parameter=field,quantity=q,unit=u,value=x.get(field),when=when,statistic=st,source=source,locator=f'records/{i}/{field}',approval='provisional',sampling=st,extra={'header':{k:d.get(k) for k in ('isDaily','isHourly','value1Type','value2Type')},'interval_note':'increment interval endpoints and daily-total day boundary not certified; totals withheld' if q=='rain' else None}))
        self.db.commit();print('Hydromet normalized',self.n,flush=True)

    def wells(self):
        wells=json.loads((self.root/'data/wells-regional.json').read_text())['wells']
        self.sites.update({'TWDB:'+w['id']:{'name':w['id']+' · '+w['aquifer'],'coordinates':[w['lon'],w['lat']],'kind':'well','basin':'unassigned','aquifer':w['aquifer'],'screen':None,'county':w['county'],'evidence':'data/wells-regional.json'} for w in wells})
        man=json.loads((self.root/'data/captures/twdb-wells/manifest.json').read_text());sources=[]
        for site,m in sorted(man.items()):sources.append((site,m['raw_path'],m,m.get('capture_path')))
        for site,path,m,cap in sources:
            if not self.wanted('TWDB:'+site):continue
            body,source=self.source(path,m,cap)
            if body is None:continue
            for i,x in enumerate(json.loads(body).get('values',[])):
                for field,value in x.items():
                    if 'water_level(' not in field and 'water_elevation(' not in field:continue
                    when=x.get('datetime','');self.inspect(f'TWDB:{site}:{field}',when,value,x.get('status'))
                    if when[:10]<self.since or when[:10]>=self.through[:10]:continue
                    daily=field.startswith('daily_high');st='daily_high' if daily else 'reported_point';original=when
                    when=when[:10] if daily else when+(x.get('timezone') or '')
                    q='groundwater_depth' if 'below land surface' in field else 'groundwater_elevation'
                    self.add(measurement(operator='TWDB',feed='TWDB',site=site,series=field,parameter=field,quantity=q,unit='ft',value=value,when=when,statistic=st,source=source,locator=f'values/{i}/{field}',qualifiers=[x.get('status'),x.get('comment')],datum='land surface' if q=='groundwater_depth' else None,sampling=st,extra={'source_time':original,'source_operator':x.get('source'),'provider_status':x.get('status'),'aquifer':self.sites.get('TWDB:'+site,{}).get('aquifer'),'screen':None,'continuity':'not certified'}))
        for p in sorted((self.root/'data/raw/twdb/daily').glob('*recent-conditions.json')):
            body,source=self.source(str(p.relative_to(self.root)),json.loads(p.with_suffix('.meta.json').read_text()))
            if body is None:continue
            for i,x in enumerate(json.loads(body).get('values',[])):
                site=str(x['state_well_number']);field='daily_high_water_level(ft below land surface)'
                if 'TWDB:'+site not in self.sites or not self.wanted('TWDB:'+site) or x['date']>=self.through[:10]:continue
                self.add(measurement(operator='TWDB',feed='TWDB',site=site,series='recent:'+field,parameter=field,quantity='groundwater_depth',unit='ft',value=x.get(field),when=x['date'],statistic='daily_high',source=source,locator=f'values/{i}/{field}',datum='land surface',sampling='daily high',extra={'continuity':'not certified'}))
        self.db.commit();print('TWDB wells normalized',self.n,flush=True)

    def reservoirs(self):
        man=json.loads((self.root/'data/captures/twdb-reservoirs/manifest.json').read_text());sources=[(site,m['raw_path'],m,m.get('capture_path')) for site,m in sorted(man.items())]
        for p in sorted((self.root/'data/raw/twdb-reservoirs/daily').glob('*.csv')):
            sources.append((p.stem.split('-',1)[1],str(p.relative_to(self.root)),json.loads(p.with_suffix('.meta.json').read_text()),None))
        for site,path,m,cap in sources:
            if not self.wanted('TWDB-lake:'+site):continue
            body,source=self.source(path,m,cap)
            if body is None:continue
            self.sites['TWDB-lake:'+site]={'name':site,'kind':'reservoir','basin':'Highland Lakes' if site in ('austin','travis','buchanan','inks','lyndon-b-johnson','marble-falls') else 'regional context','coordinates':None,'evidence_source_id':source}
            text=body.decode();lines=[(i,s) for i,s in enumerate(text.splitlines()) if s and not s.startswith('#')];reader=csv.DictReader([s for i,s in lines])
            for i,x in enumerate(reader):
                for field,q,u in [('water_level','reservoir_elevation','ft'),('reservoir_storage','storage','acre-ft'),('conservation_storage','conservation_storage','acre-ft'),('percent_full','percent_full','%')]:
                    self.inspect(f'TWDB-lake:{site}:{field}',x['date'],x.get(field))
                    if x['date']<self.daily_start or x['date']>=self.through[:10]:continue
                    self.add(measurement(operator='TWDB-lake',feed='TWDB',site=site,series=field,parameter=field,quantity=q,unit=u,value=x.get(field),when=x['date'],statistic='daily_report',source=source,locator=f'line/{lines[i+1][0]+1}/{field}',sampling='date-only report; not a daily mean',extra={'capacity':{'conservation_capacity_af':numeric(x.get('conservation_capacity')),'dead_pool_capacity_af':numeric(x.get('dead_pool_capacity')),'definition':'percent_full = 100 × conservation_storage / conservation_capacity; conservation_storage capped at capacity','version':None,'effective_date':x['date'],'evidence_source_id':source},'continuity':'capacity values preserved per date; survey version not supplied'}))
        self.db.commit();print('Reservoirs normalized',self.n,flush=True)

    def eaa(self):
        inventory=json.loads((self.root/'data/eaa-sites.json').read_text())['sites']
        for w in inventory['wells']:
            self.sites['EAA:'+w['siteId']]={'name':w['siteName'],'coordinates':[w['longitude'],w['latitude']],'kind':'well','aquifer':w.get('aquifer'),'basin':w.get('basin'),'screen':None,'evidence':'data/eaa-sites.json'}
        scoped=self.only is None or any(k.startswith('EAA:') for k in self.only)
        for p in sorted((self.root/'data/raw/eaa/details/wells').glob('*/*.html')) if scoped else []:
            mp=p.with_suffix('.meta.json');meta=json.loads(mp.read_text()) if mp.exists() else None
            body,source=self.source(str(p.relative_to(self.root)),meta,url=None)
            if body is None:continue
            for i,x in enumerate(parse_var(body.decode(errors='replace'),'wellAllDailyHighElevationJSON') or []):
                site=x['siteId'];when=x['dailyHighDate'][:10]
                if not self.wanted('EAA:'+site):continue
                for field,q in [('depthFromLsd','groundwater_depth'),('waterLevelElevation','groundwater_elevation')]:
                    self.inspect(f'EAA:{site}:{field}',when,x.get(field),x.get('measStatusDesc'))
                    if when<self.since or when>=self.through[:10]:continue
                    self.add(measurement(operator='EAA',feed='EAA',site=site,series=field,parameter=field,quantity=q,unit='ft',value=x.get(field),when=when,statistic='daily_high',source=source,locator=f'wellAllDailyHighElevationJSON/{i}/{field}',approval=x.get('measStatusDesc'),qualifiers=x.get('comments'),datum='land surface' if q=='groundwater_depth' else None,sampling='daily high, not mean',extra={'source_time':x['dailyHighDate'],'continuity':'not certified'}))
        for p in sorted((self.root/'data/raw/eaa/conditions').glob('*aquifer-conditions.html')) if scoped else []:
            mp=p.with_suffix('.meta.json');body,source=self.source(str(p.relative_to(self.root)),json.loads(mp.read_text()) if mp.exists() else None)
            if body is None:continue
            for i,x in enumerate(parse_var(body.decode(errors='replace'),'springsHistoricalDailyMeanCFS') or []):
                site=str(x['siteNo']).zfill(8);when=x['meanDate'][:10]
                if not self.wanted('EAA:'+site):continue
                self.sites['EAA:'+site]={'name':x['siteName']+' Springs','kind':'spring','basin':'regional context','coordinates':None,'evidence_source_id':source}
                self.inspect(f'EAA:{site}:meanCfsFin',when,x.get('meanCfsFin'))
                if when<self.daily_start or when>=self.through[:10]:continue
                self.add(measurement(operator='EAA',feed='EAA',site=site,series='meanCfsFin',parameter='flow',quantity='discharge',unit='cfs',value=x.get('meanCfsFin'),when=when,statistic='daily_mean',source=source,locator=f'springsHistoricalDailyMeanCFS/{i}/meanCfsFin',approval='unknown',sampling='daily mean',extra={'source_time':x['meanDate'],'provider_raw_value':x.get('meanCfsRaw'),'last_modified':x.get('lastUpdateDate')}))
        for kind in ('rain','streams'):
            self.gaps.append({'provider':'EAA','kind':kind,'inventory_count':len(inventory[kind]),'reason':'inventory is not numeric coverage; rain download refusals, stream detail acquisition not in this adapter; two conditions-page spring series adapted separately'})
        self.db.commit();print('EAA normalized',self.n,flush=True)

    def finish(self):
        self.db.execute('create index obs_series_time on observations(series,at)');self.db.commit()
        counts=dict(self.db.execute('select series,count(*) from observations group by series'))
        for sid,s in self.series.items():s['original_records']=counts[sid]
        self.db.close();self.dbpath.replace(self.out/'observations.sqlite')
        result={'schema_version':SCHEMA,'event_id':'2026-09-30','recent_start':self.since,'cutoff':self.through,'historical_daily_start':self.daily_start,'sources':self.sources,'sites':self.sites,'series':self.series,'gaps':self.gaps,'archive_audit':self.audits,'observations':{'path':'observations.sqlite','rows':sum(counts.values()),'sha256':hashlib.sha256((self.out/'observations.sqlite').read_bytes()).hexdigest()},'limits':['Full numeric archive audit counts original records, including repeat captures; never station-days.','Point history retained from recent_start; compatible daily USGS and reservoir histories retained from 2006.','Hydromet rain counter/increments retain unknown interval boundaries; no event accumulation fabricated.','Unassigned basin is explicit until a sourced surface watershed association is made. No aquifer connection inferred.']}
        if self.only is not None:
            result['scope']={'only':sorted(self.only),'hydromet_history_params':sorted(self.hydromet_params) if self.hydromet_params else 'all','meaning':'full-history partition for named stations; other stations are not adapted here'}
            result['sites']={k:v for k,v in self.sites.items() if k in self.only}
        (self.out/'catalog.json').write_text(json.dumps(result,indent=2)+'\n')
        audit={k:v for k,v in result.items() if k not in ('sources',)}
        audit['source_count']=len(self.sources);audit['missing_fetch_metadata']=sum(x['provenance_status']!='verified_capture' for x in self.sources.values())
        if self.audit_path:(self.root/self.audit_path).write_text(json.dumps(audit,indent=2)+'\n')
        print('COMPLETE',result['observations'],flush=True);return result


def build(root=ROOT,out=None,since='2026-09-01',through='2026-10-03T12:15:00Z',**kw):
    b=Builder(root,out or Path(root)/'data/normalized/regional-analytics',since,through,**kw)
    b.usgs();b.hydromet();b.wells();b.reservoirs();b.eaa();return b.finish()

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,default=ROOT);p.add_argument('--out',type=Path);p.add_argument('--since',default='2026-09-01');p.add_argument('--through',default='2026-10-03T12:15:00Z');a=p.parse_args();build(a.root,a.out,a.since,a.through)
