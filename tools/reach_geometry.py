#!/usr/bin/env python3
"""Along-channel evidence for station-to-place relationships, from the preserved OSM creek ways.

This is geometry only. It answers "where does this point sit along the mapped channel" with
the source way, the perpendicular distance from the point to the channel, and the cumulative
metres from the way's first node. It does not create a hydrologic relationship, move any
coordinate, or infer access. OSM waterway ways are digitized in the direction of flow by
mapping convention; the manifest records that convention as the basis for upstream/downstream
statements, together with the way's endpoints so a reader can check it against elevation.

Points farther than ``--max-distance`` metres from every mapped way get ``on_mapped_channel:
false`` and no along-channel position; that usually means the saved coordinate is an
approximate named place, not a water-entry point, and the record says so.
"""
import argparse, json, math
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
GEO=ROOT/'app/austin-creeks.geojson'

def haversine(a,b):
    R=6371000.0; la1,lo1=map(math.radians,a); la2,lo2=map(math.radians,b)
    h=math.sin((la2-la1)/2)**2+math.cos(la1)*math.cos(la2)*math.sin((lo2-lo1)/2)**2
    return 2*R*math.asin(math.sqrt(h))

def load_ways(path=GEO):
    geo=json.loads(Path(path).read_text()); ways=[]
    for f in geo['features']:
        if f['properties'].get('feature_kind')!='waterway' or f['geometry']['type']!='LineString': continue
        coords=[(c[1],c[0]) for c in f['geometry']['coordinates']]
        cum=[0.0]
        for i in range(1,len(coords)): cum.append(cum[-1]+haversine(coords[i-1],coords[i]))
        ways.append({'name':f['properties'].get('name'),'osm_id':f['properties'].get('osm_id'),'coords':coords,'cum':cum,'length_m':cum[-1],
                     'retrieved_at':f['properties'].get('retrieved_at'),'source':f['properties'].get('source')})
    return ways

def project(point,ways,waterbody=None,max_distance=400.0):
    """Nearest node on the nearest way (by node distance); node spacing bounds the error."""
    best=None
    for w in ways:
        if waterbody and w['name']!=waterbody: continue
        i=min(range(len(w['coords'])),key=lambda k:haversine(point,w['coords'][k]))
        d=haversine(point,w['coords'][i])
        if best is None or d<best['distance_to_channel_m']:
            best={'waterbody':w['name'],'osm_way_id':w['osm_id'],'distance_to_channel_m':round(d,1),'metres_from_way_start':round(w['cum'][i],1),
                  'way_length_m':round(w['length_m'],1),'way_start_lat_lon':[round(x,6) for x in w['coords'][0]],'way_end_lat_lon':[round(x,6) for x in w['coords'][-1]],
                  'node_index':i,'node_count':len(w['coords'])}
    if best is None: return {'on_mapped_channel':False,'reason':f'no mapped way named {waterbody!r} in the saved geometry'}
    best['on_mapped_channel']=best['distance_to_channel_m']<=max_distance
    if not best['on_mapped_channel']:
        best['reason']=f"nearest mapped {best['waterbody']} node is {best['distance_to_channel_m']} m away; coordinate is not resolved to the channel"
        best.pop('metres_from_way_start')
    return best

def relate(place_pos,station_pos):
    """Upstream/downstream only when both points resolve to the same way."""
    if not (place_pos.get('on_mapped_channel') and station_pos.get('on_mapped_channel')): return {'position':'unresolved','reason':'one or both points are not on the mapped channel'}
    if place_pos['osm_way_id']!=station_pos['osm_way_id']: return {'position':'different_mapped_ways','reason':'points resolve to different OSM ways; along-channel distance not computed across ways'}
    delta=place_pos['metres_from_way_start']-station_pos['metres_from_way_start']
    return {'position':'place_downstream_of_station' if delta>0 else 'place_upstream_of_station' if delta<0 else 'coincident',
            'along_channel_m':round(abs(delta),1),'basis':'OSM waterway ways are digitized in flow direction (way start is upstream); verify against the way endpoints and terrain'}

AUSTIN_BOX=(30.10,30.47,-97.97,-97.65)
def in_austin(lat,lon): return AUSTIN_BOX[0]<=lat<=AUSTIN_BOX[1] and AUSTIN_BOX[2]<=lon<=AUSTIN_BOX[3]

def waterbody_hints():
    """Waterbody names come from the authored relationship records, never guessed from proximity."""
    path=ROOT/'data/model/place-relationships.json'
    if not path.exists(): return {}
    data=json.loads(path.read_text())
    return {pid:rec.get('waterbody') for pid,rec in data.get('places',{}).items()}

def main(max_distance):
    ways=load_ways(); holes_path=ROOT/'data/holes.json'; holes=json.loads(holes_path.read_text()) if holes_path.exists() else []; gauges=json.loads((ROOT/'data/gauges.json').read_text()); hints=waterbody_hints()
    out={'purpose':'Geometry evidence only: nearest mapped OSM creek node for each Austin place and station. No hydrologic relationship is asserted here.',
         'geometry_source':str(GEO.relative_to(ROOT)),'attribution':'Map data © OpenStreetMap contributors, ODbL','max_distance_m':max_distance,
         'flow_direction_basis':'OSM waterway ways are drawn in the direction of flow by mapping convention; each record carries the way endpoints so this can be checked.',
         'stations':{},'places':{}}
    for g in gauges:
        if not in_austin(g['lat'],g['lon']): continue
        out['stations'][g['id']]={'name':g['name'],'lat':g['lat'],'lon':g['lon'],**project((g['lat'],g['lon']),ways,g.get('waterbody'))}
    for h in holes:
        if not in_austin(h['lat'],h['lon']): continue
        hint=hints.get(h['id'])
        rec={'name':h['name'],'lat':h['lat'],'lon':h['lon'],'coordinate_precision':h.get('coordinate_precision'),'waterbody_hint':hint}
        rec.update(project((h['lat'],h['lon']),ways,hint) if hint else {'on_mapped_channel':False,'reason':'no authored waterbody for this place; proximity alone does not pick a creek'})
        out['places'][h['id']]=rec
    (ROOT/'data/model/austin-reach-geometry.json').write_text(json.dumps(out,indent=2)+'\n')
    for k,v in out['places'].items(): print(k,v.get('waterbody'),v.get('distance_to_channel_m'),v.get('metres_from_way_start','-'))

if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--max-distance',type=float,default=400.0); a=p.parse_args(); main(a.max_distance)
