"""Build the bounded creek-map artifact from the integrated analytic layer; entirely offline."""
import argparse
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
try:
    from . import creek_analytics as analytics, reach_geometry as geo
    from .creek_normalize import stamp
except ImportError:
    import creek_analytics as analytics, reach_geometry as geo
    from creek_normalize import stamp
ROOT=Path(__file__).resolve().parents[1]


def association(identity,ways,creek,max_distance=100,half_length=500):
    """A named-channel gauge symbol, NOT a hydrologic reach assignment."""
    if identity.get('creek')!=creek: return dict(available=False,reason='provider creek identity does not match')
    coords=identity.get('coordinates')
    if not coords or any(x is None for x in coords): return dict(available=False,reason='provider coordinates unavailable')
    try: coords=[float(v) for v in coords]
    except (TypeError,ValueError): return dict(available=False,reason='invalid provider coordinates')
    if not all(math.isfinite(v) for v in coords) or not (-180<=coords[0]<=180 and -90<=coords[1]<=90): return dict(available=False,reason='invalid provider coordinates')
    pos=geo.project((coords[1],coords[0]),ways,creek,max_distance)
    if not pos.get('on_mapped_channel'): return dict(available=False,reason=pos.get('reason','no mapped named channel'),position=pos)
    way=next(w for w in ways if w['osm_id']==pos['osm_way_id']);i=pos['node_index'];lo=hi=i
    # Stop at a node used in another saved way. No topology inferred across absent ways.
    shared={xy for w in ways if w['osm_id']!=way['osm_id'] for xy in w['coords']}
    while lo>0 and way['cum'][i]-way['cum'][lo-1]<=half_length:
        if way['coords'][lo] in shared:break
        lo-=1
    while hi+1<len(way['coords']) and way['cum'][hi+1]-way['cum'][i]<=half_length:
        if way['coords'][hi] in shared:break
        hi+=1
    if hi==lo:return dict(available=False,reason='insufficient saved geometry around gauge')
    return dict(available=True,position=pos,source='OpenStreetMap',source_url=f"https://www.openstreetmap.org/way/{way['osm_id']}",
        retrieved_at=way['retrieved_at'],provider_identity=identity,
        stroke_length_m=round(way['cum'][hi]-way['cum'][lo],1),first_node=lo,last_node=hi,
        geometry=dict(type='LineString',coordinates=[[lon,lat] for lat,lon in way['coords'][lo:hi+1]]),
        meaning='Gauge-location symbol along the named channel; no reach-wide measurement or inundation extent.')


def build(root=ROOT):
    root=Path(root);folder=root/'data/normalized/creek-analytics';catalog,by=analytics.load(folder)
    policy=json.loads((root/'data/model/creek-display-policy.json').read_text());refs=json.loads((folder/'references.json').read_text())
    window=json.loads((root/f"data/model/storms/{policy['storm']}.json").read_text())['window'];start=stamp(window['t0'])
    ways=geo.load_ways(root/policy['geometry']['source']);items=[];used_sources=set()
    for entry in policy['gauge_locations']:
        gauge=entry['gauge'];identities=[i for i in catalog['identities'] if i['gauge']==gauge]
        identity=next((i for i in identities if i.get('evidence')),identities[-1] if identities else {})
        selection=catalog['display_selection'].get(gauge+':instantaneous',{})
        if gauge=='COA:122':
            # This is an explicit policy selection of a normalized feed series, not field interpretation.
            selection=dict(series_id='Hydromet:122:COA:flow:value2:reported_point:value2',reason='City native history; no daily historical comparison')
        sid=selection.get('series_id');rows=by.get(sid,[])
        series=catalog['series'].get(sid,{})
        reference=refs.get(gauge+':daily_mean',dict(available=False,reason='No verified daily-flow reference for this gauge'))
        daily=catalog['display_selection'].get(gauge+':daily_mean')
        if daily and reference!=analytics.seasonal_reference(by.get(daily['series_id'],[])):
            raise ValueError(f'{gauge}: reference artifact differs from normalized observations; rerun creek_analytics.py')
        views={}
        good=[r for r in rows if r['state']=='measured' and r['time']['instant'] and stamp(r['time']['instant'])>=start]
        for view in policy['views']:
            r=max(good,key=lambda r:(r['value'],r['time']['instant']),default=None) if view['id']=='peak' else analytics.at_or_before(rows,view['at'])
            views[view['id']]=dict(observation=r,comparison=analytics.contrast(r,reference))
            if r:used_sources.add(r['source_id'])
        points=[]
        for r in rows:
            if not r['time']['instant']:continue
            # Exact series retained; nulls/gaps break the client chart. No invented points.
            points.append(dict(at=r['time']['instant'],value=r['value'] if r['state']=='measured' else None,
                id=r['id'],source_id=r['source_id'],source_locator=r['source_locator'],approval=r['approval'],conflict=r.get('conflicting_captures',False)))
            used_sources.add(r['source_id'])
        used_sources.update(reference.get('source_ids',[]))
        if identity.get('evidence_source_id'):used_sources.add(identity['evidence_source_id'])
        items.append(dict(**entry,identity=identity,selection=selection,series=series,reference=reference,views=views,
            timeseries=points,association=association(identity,ways,entry['creek'],policy['geometry']['maximum_node_distance_m'],policy['geometry']['maximum_stroke_each_side_m']),
            conflict_count=sum(c['series_id']==sid for c in catalog['conflicts']),
            sources_page=f"https://waterdata.usgs.gov/monitoring-location/USGS-{gauge.split(':')[1]}/" if gauge.startswith('USGS:') else 'https://hydromet.lcra.org/'))
    # Expose checksums/locators and official URLs, not local paths masquerading as public links.
    sources={sid:{k:v for k,v in catalog['source_catalog'][sid].items() if k not in ('raw_path','capture_path')} for sid in sorted(used_sources)}
    # Source identity evidence retains repository-relative paths as identifiers, never anchors.
    result=dict(schema_version='creek-prototype/v1',analytic_schema=catalog['schema_version'],normalization_commit=policy['normalization_integration_commit'],
        normalized_observations_sha256=catalog['observations']['sha256'],analysis_cutoff=catalog['event_interval']['end'],
        observed_through=max((p['at'] for x in items for p in x['timeseries']),default=None),
        storm=dict(id=policy['storm'],t0=window['t0'],cap_at=window['cap_at'],status=window['status']),policy=policy,creeks=items,sources=sources,
        geometry_sha256=hashlib.sha256((root/policy['geometry']['source']).read_bytes()).hexdigest())
    (root/'app/creek-snapshot.json').write_text(json.dumps(result,separators=(',',':'),allow_nan=False)+'\n')
    (root/'data/model/creek-gauge-associations.json').write_text(json.dumps({x['gauge']:x['association'] for x in items},indent=2)+'\n')
    for x in items:print(x['creek'],x['association']['available'],x['views']['peak']['observation']['value'] if x['views']['peak']['observation'] else None,x['reference'].get('median'))
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,default=ROOT);a=p.parse_args();build(a.root)
