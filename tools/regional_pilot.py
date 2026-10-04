"""Build a public pilot snapshot from the integrated regional analytic reader and sourced geography."""
import datetime as dt
import hashlib,json,re,subprocess
from pathlib import Path
try:
    from .regional_analytics import Reader,exact_day,change,rank,at_or_before
    from .creek_normalize import stamp
    from .regional_geography import basin_at,association,downstream_route
    from . import regional_events as events
except ImportError:
    from regional_analytics import Reader,exact_day,change,rank,at_or_before
    from creek_normalize import stamp
    from regional_geography import basin_at,association,downstream_route
    import regional_events as events
ROOT=Path(__file__).resolve().parents[1]
INTEGRATED='646e045a508062952cf141702819b733ed8aeeb7'
RIVERS=['08150000','08151500','08152900','08153500']
# Receiving reservoirs are set only from the directed NHD route walk recorded with each gauge association.
BASINS={'Llano':{'surface_hucs':['12090202','12090203','12090204'],'receiving_reservoir':'TWDB-lake:lyndon-b-johnson','receiving_basis':'first reference waterbody on the captured NHD route below both Llano gauges'},
    'Pedernales':{'surface_hucs':['12090206'],'receiving_reservoir':'TWDB-lake:travis','receiving_basis':'first reference waterbody on the captured NHD route below both Pedernales gauges'},
    'Highland Lakes':{'surface_hucs':['12090201','12090205'],'receiving_reservoir':None,'receiving_basis':'the reservoir chain itself; no pilot river gauge lies in these subbasins'}}
DAY='2026-09-30';RAIN_AT='2026-10-02T12:00:00Z';SEASON_AT='2026-09-30T12:00:00Z'


def clean(name):
    """Provider display names carry HTML line breaks; presentation only."""
    return ' '.join(str(name).replace('<br />',' ').split()) if name else name


def rain_aligned(r,cat,key,t0,cutoff):
    """Separately labelled rain statistics for the aligned plots; never summed, never substituted for a rolling total."""
    out={}
    for name,statistic in [('daily','daily_total_boundary_unverified'),('increments','reported_increment')]:
        ids=[s['series_id'] for s in cat['series'].values() if s['site_key']==key and s['quantity']=='rain' and s['statistic']==statistic]
        if len(ids)!=1:
            out[name]={'available':False,'reason':'no single saved series with this statistic'};continue
        rows=[x for x in r.rows(ids[0]) if x['state']=='measured']
        if name=='daily':
            rows=[x for x in rows if (x['time']['date'] or x['time']['original'][:10])>='2026-09-01']
            out[name]={'available':bool(rows),'series':ids[0],'statistic':statistic,'points':[[x['time']['date'] or x['time']['original'][:10],x['value']] for x in rows],'note':'provider daily total; day boundary unverified; shown per day, not added'}
        else:
            rows=[x for x in rows if x['time']['instant'] and stamp(t0)<=stamp(x['time']['instant'])<=stamp(cutoff)]
            out[name]={'available':bool(rows),'series':ids[0],'statistic':statistic,'reports':len(rows),'first':rows[0]['time']['instant'] if rows else None,'last':rows[-1]['time']['instant'] if rows else None,
                'points':[[x['time']['instant'],x['value']] for x in rows if x['value']>0],'note':'each nonzero reported increment at its report time; interval endpoints not certified, so increments are not added; zero reports are counted but not listed here'}
    return out


def build(rain_at=RAIN_AT,storm_daily_end=None):
    """The storm window follows the store's cutoff; `storm_daily_end` defaults to the last whole date before it."""
    subprocess.run(['git','merge-base','--is-ancestor',INTEGRATED,'origin/main'],cwd=ROOT,check=True)
    r=Reader(ROOT/'data/normalized/regional-analytics');cat=r.catalog
    refs=json.loads((ROOT/'data/normalized/regional-analytics/references.json').read_text())
    channels=json.loads((ROOT/'app/regional-channels.geojson').read_text())['features'];basins=json.loads((ROOT/'app/regional-basins.geojson').read_text())['features'];lakes=json.loads((ROOT/'app/regional-lakes.geojson').read_text())['features']
    window=json.loads((ROOT/'data/model/storms/2026-09-30.json').read_text())['window'];start=stamp(window['t0']);end=stamp(cat['cutoff'])
    sources={};items=[];associations={}
    storm_end=storm_daily_end or str(stamp(cat['cutoff']).date()-dt.timedelta(days=1))
    def public(obs):
        if not obs:return None
        src=cat['sources'][obs['source_id']];sources[obs['source_id']]={k:src.get(k) for k in ('url','sha256','retrieved_at','provenance_status')}
        return obs
    def series(sid,start_day):
        if not sid:return [],[]
        rows=r.rows(sid);recent=[x for x in rows if (x['time']['date'] or x['time']['original'][:10])>=start_day]
        return rows,recent
    def chart(rows):
        # Every retained point, with source IDs: no interpolation, downsampling or invented peaks.
        return [{'at':x['time']['instant'] or x['time']['date'] or x['time']['original'],'value':x['value'] if x['state']=='measured' else None,'id':x['id'],'statistic':x['time']['statistic']} for x in rows]
    def base(key,kind):
        site=cat['sites'][key];basin=basin_at(site.get('coordinates'),basins)
        return {'id':key,'kind':kind,'name':clean(site['name']) or key,'coordinates':site.get('coordinates'),'basin':basin['name'],'huc8':basin['huc8'],'aquifer':site.get('aquifer'),'views':{},'series':{},'chart':{}}
    for site in RIVERS:
        key='USGS:'+site;item=base(key,'river');sid,why=r.choose(key,'discharge','instantaneous','USGS');rows,recent=series(sid,window['t0'][:10]);event=[x for x in recent if x['time']['instant'] and start<=stamp(x['time']['instant'])<=end];good=[x for x in event if x['state']=='measured']
        peak=max(good,key=lambda x:x['value']) if good else None
        first=at_or_before(rows,window['t0']);last=at_or_before(rows,cat['cutoff'])
        item['views']['storm']={'observation':public(peak),'basis':'largest saved instantaneous reading in the shared storm window; times differ by gauge','start':public(first),'end':public(last),'change':change(first,last),'actual_first':event[0]['time']['instant'] if event else None,'actual_last':event[-1]['time']['instant'] if event else None,'observed_points':len(good),'unknown_peak_rank':True}
        item['chart']['storm']=chart(event);item['series']['storm']={'id':sid,'selection':why}
        daily,why=r.choose(key,'discharge','daily_mean','USGS');drows,drecent=series(daily,'2026-09-01');obs=exact_day(drows,DAY);ref=refs.get(daily,{'available':False,'reason':'no daily reference'})
        item['views']['seasonal']={'observation':public(obs),'basis':'daily mean on the shared complete date','rank':rank(obs,ref),'reference':{k:v for k,v in ref.items() if k not in ('values','observation_ids','source_ids')}}
        item['chart']['seasonal']=chart([x for x in drecent if x['time']['date']<=DAY]);item['series']['seasonal']={'id':daily,'selection':why}
        item['association']=association(cat['sites'][key],channels,basins)
        if item['association']['available']:item['association']['downstream_route']=downstream_route(item['association']['channel_id'],channels,lakes)
        associations[key]=item['association'];items.append(item)
    # Native LCRA rolling totals only. Exact USGS distribution aliases are not counted twice.
    for key,site in sorted(cat['sites'].items()):
        if not key.startswith('LCRA:'):continue
        item=base(key,'rain')
        if item['basin']=='unassigned':continue
        sid,why=r.choose(key,'rain','rolling_24h','Hydromet')
        if not sid:continue
        rows,recent=series(sid,'2026-09-01')
        for view,at in [('storm',rain_at),('seasonal',SEASON_AT)]:
            obs=at_or_before(rows,at)
            item['views'][view]={'observation':public(obs),'basis':'provider rolling 24-hour rainfall; end at or up to 30 minutes before shared selection','selected_at':at,'event_total':None,'event_total_reason':'native historical increment boundaries not certified; overlapping rolling totals never added'}
            item['chart'][view]=chart(recent);item['series'][view]={'id':sid,'selection':why}
        item['aligned']=rain_aligned(r,cat,key,window['t0'],cat['cutoff'])
        items.append(item)
    for key,site in sorted(cat['sites'].items()):
        if not key.startswith('TWDB:') or site.get('kind')!='well':continue
        item=base(key,'well')
        if item['basin']=='unassigned':continue
        # Daily highs and reported points are alternatives, never combined into one time series.
        sid,why=r.choose(key,'groundwater_depth','reported_point','TWDB')
        stat='reported_point'
        if not sid:
            candidates=[s for s in cat['series'].values() if s['site_key']==key and s['quantity']=='groundwater_depth' and s['statistic']=='daily_high' and not s['original_series_id'].startswith('recent:')]
            sid=candidates[0]['series_id'] if len(candidates)==1 else None;stat='daily_high';why='single saved history daily-high series; recent feed kept separate'
        rows,recent=series(sid,'2026-09-01')
        for view,first,last in [('seasonal','2026-09-01',DAY),('storm','2026-09-28',storm_end)]:
            a=exact_day(rows,first) if stat=='daily_high' else at_or_before(rows,first+'T12:00:00Z')
            b=exact_day(rows,last) if stat=='daily_high' else at_or_before(rows,last+'T12:00:00Z')
            item['views'][view]={'observation':public(b),'start':public(a),'basis':'daily high' if stat=='daily_high' else '7 am Central point observation, maximum age 30 minutes','change':change(a,b),'from_date':first,'to_date':last,'continuity':'well location within surface watershed only; no aquifer-to-river connection inferred; screen/continuity not certified'}
            item['chart'][view]=chart([x for x in recent if x['time']['original'][:10]<=last]);item['series'][view]={'id':sid,'selection':why}
        items.append(item)
    lake_names={'buchanan':'Lake Buchanan','inks':'Inks Lake','lyndon-b-johnson':'Lake Lyndon B Johnson','marble-falls':'Lake Marble Falls','travis':'Lake Travis','austin':'Lake Austin'}
    # Dam sites are matched by the lake the provider names in the dam's own site name, never by proximity.
    provider_lake={'Lake Buchanan':'buchanan','Inks Lake':'inks','Lake LBJ':'lyndon-b-johnson','Lake Marble Falls':'marble-falls','Lake Travis':'travis','Lake Austin':'austin'};hyd_dams={}
    for dam_key,dam in sorted(cat['sites'].items()):
        named=re.search(r'\((.+)\)',dam.get('name') or '')
        if dam_key.startswith('LCRA:') and dam.get('kind')=='dam' and named and named.group(1) in provider_lake:hyd_dams[provider_lake[named.group(1)]]=dam_key
    for slug,name in lake_names.items():
        key='TWDB-lake:'+slug;item=base(key,'reservoir');item.update(name=name,basin='Highland Lakes')
        geo=next((f for f in lakes if f['properties']['name']==name),None)
        # Locate a label using the saved LCRA dam site, not an invented lake center.
        identity=cat['sites'].get(hyd_dams.get(slug),{})
        item['coordinates']=identity.get('coordinates');item['location_note']=clean(identity.get('name'));item['geometry_available']=bool(geo)
        sid,why=r.choose(key,'storage','daily_report','TWDB');rows,recent=series(sid,'2026-09-01');psid,_=r.choose(key,'percent_full','daily_report','TWDB');prows=r.rows(psid) if psid else []
        for view,first,last in [('seasonal','2026-09-01',DAY),('storm','2026-09-28',storm_end)]:
            a=exact_day(rows,first);b=exact_day(rows,last)
            item['views'][view]={'observation':public(b),'start':public(a),'percent_full':public(exact_day(prows,last)),'basis':'date-only TWDB storage report; not measured inflow','change':change(a,b),'from_date':first,'to_date':last,'causal_limit':'storage reflects inflows, releases, withdrawals and other operations; these readings do not attribute the change'}
            item['chart'][view]=chart([x for x in recent if x['time']['date']<=last]);item['series'][view]={'id':sid,'selection':why}
        items.append(item)
    for x in items:
        if x['kind']=='river':
            first=(x['association'].get('downstream_route') or {}).get('first_receiving_reservoir')
            if first!=lake_names[BASINS[x['basin']]['receiving_reservoir'].split(':')[1]]:raise ValueError(f"{x['id']}: stated receiving reservoir is not the first lake on the captured route ({first})")
    springs=[]
    for key,site in cat['sites'].items():
        if site.get('kind')!='spring':continue
        sid,why=r.choose(key,'discharge','daily_mean','USGS' if key.startswith('USGS:') else 'EAA');rows,recent=series(sid,'2026-09-01');a=exact_day(rows,'2026-09-01');b=exact_day(rows,DAY)
        springs.append({'id':key,'name':site['name'],'observation':public(b),'start':public(a),'change':change(a,b),'series':sid,'chart':chart([x for x in recent if x['time']['date']<=DAY]),'meaning':'separate regional context; not a spring in the Llano or Pedernales pilot basins'})
    r.close()
    result={'schema_version':'regional-pilot/v1','analytic_schema':cat['schema_version'],'analytic_integration_commit':INTEGRATED,'normalized_sha256':cat['observations']['sha256'],'publication_date':str(dt.date.today()),'saved_data_cutoff':cat['cutoff'],'storm':{'id':'2026-09-30','t0':window['t0'],'through':cat['cutoff'],'rain_at':rain_at,'daily_start':'2026-09-28','daily_end':storm_end},'seasonal':{'date':DAY,'start':'2026-09-01','rain_at':SEASON_AT,'reference_years':[2006,2025]},'items':items,'regional_springs':springs,'sources':sources,'basins':BASINS,'routes':{k:v.get('downstream_route') for k,v in associations.items()},'coverage':{'inventory_wells_in_pilot':sum(x['kind']=='well' for x in items),'local_springs':0,'storm_total_rain':'unavailable: interval boundaries unverified','reach_estimates':'none; gauge observations only'},'geometry_hashes':{n:hashlib.sha256((ROOT/'app'/n).read_bytes()).hexdigest() for n in ['regional-channels.geojson','regional-basins.geojson','regional-lakes.geojson']}}
    (ROOT/'app/regional-snapshot.json').write_text(json.dumps(result,separators=(',',':'),allow_nan=False)+'\n')
    (ROOT/'data/model/regional-gauge-associations.json').write_text(json.dumps(associations,indent=2)+'\n')
    earlier=json.loads((ROOT/'data/model/regional-events.json').read_text());floods={}
    for x in items:
        if x['kind']!='river':continue
        g=earlier['gauges'][x['id']];peak=x['views']['storm']['observation']
        floods[x['id']]={'name':x['name'],'basin':x['basin'],'storm_reading':{'value':peak['value'],'at':peak['time']['instant'],'statistic':peak['time']['statistic'],'approval':peak['approval']} if peak else None,
            'placement':events.place_among_peaks(peak['value'] if peak else None,g['annual_peaks']),
            'annual_peaks':[[r['date'],r['peak_cfs'],r['peak_codes'],r['gage_height_codes']] for r in g['annual_peaks']['rows']],'code_meanings':g['annual_peaks']['code_meanings'],'annual_source':g['annual_peaks']['source'],
            'daily_events':g['daily_events'],'last_daily_mean':g['last_daily_mean'],
            'storm_daily_means':'in the saved record' if peak and g['last_daily_mean'] and g['last_daily_mean']>=peak['time']['instant'][:10] else f"not in the saved record yet: the last daily mean is {g['last_daily_mean']}, before the storm’s largest saved reading"}
    (ROOT/'app/regional-events.json').write_text(json.dumps({'schema_version':'regional-events-public/v1','cutoff':cat['cutoff'],'gauges':floods,'pair_lags':earlier['pair_lags'],'limits':earlier['limits'],'history_sha256':earlier['history_sha256']},separators=(',',':'),allow_nan=False)+'\n')
    print('Pilot items',len(items),'springs',len(springs),'associations',associations)
    print('View numeric counts',{view:{kind:sum(x['kind']==kind and bool(x['views'][view]['observation']) for x in items) for kind in ['river','rain','well','reservoir']} for view in ['storm','seasonal']})
    return result

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--rain-at',default=RAIN_AT);p.add_argument('--storm-daily-end');a=p.parse_args();build(a.rain_at,a.storm_daily_end)
