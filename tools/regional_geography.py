"""Derive pilot geography from saved USGS NHD/WBD. No acquisition or water estimation."""
from collections import Counter,defaultdict
import gzip,hashlib,json,math
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
CAP=ROOT/'data/captures/documentary/regional-water'
NAMES={'Llano River':'Llano','North Llano River':'Llano','South Llano River':'Llano','Pedernales River':'Pedernales','Colorado River':'Highland Lakes','Sandy Creek':'Highland Lakes'}

def capture(name):
    m=json.loads((CAP/(name+'.meta.json')).read_text());b=gzip.decompress((CAP/(name+'.gz')).read_bytes())
    if m['status']!=200 or hashlib.sha256(b).hexdigest()!=m['sha256']:raise ValueError('unverified geography capture')
    d=json.loads(b)
    if d.get('error'):raise ValueError(d['error'])
    return d,m


def inside_ring(point,ring):
    x,y=point;inside=False
    for a,b in zip(ring,ring[1:]+ring[:1]):
        if (a[1]>y)!=(b[1]>y) and x<(b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0]:inside=not inside
    return inside


def inside(point,geometry):
    if not point or any(x is None for x in point):return False
    polygons=geometry['coordinates'] if geometry['type']=='MultiPolygon' else [geometry['coordinates']]
    return any(inside_ring(point,p[0]) and not any(inside_ring(point,h) for h in p[1:]) for p in polygons)


def basin_at(point,basins):
    matches=[f['properties']['huc8'] for f in basins if inside(point,f['geometry'])]
    if len(matches)!=1:return {'name':'unassigned','huc8':None}
    h=matches[0];return {'name':'Llano' if h in ('12090202','12090203','12090204') else 'Pedernales' if h=='12090206' else 'Highland Lakes','huc8':h}


def segment_distance(point,a,b):
    scale=math.cos(math.radians(point[1]));x=(point[0]-a[0])*scale;y=point[1]-a[1];dx=(b[0]-a[0])*scale;dy=b[1]-a[1]
    t=max(0,min(1,(x*dx+y*dy)/(dx*dx+dy*dy))) if dx*dx+dy*dy else 0
    return math.hypot(x-t*dx,y-t*dy)*111195


def association(site,features,basins):
    point=site.get('coordinates');basin=basin_at(point,basins)
    if not point or not basin['huc8']:return {'available':False,'reason':'no unique sourced surface watershed location'}
    text=site.get('name','').lower();name=next((n for n in NAMES if n.lower() in text or n.replace('River','Rv').lower() in text),None)
    if not name:return {'available':False,'reason':'provider names no pilot river'}
    choices=[]
    for f in features:
        p=f['properties']
        if p['name']!=name or str(p.get('reachcode',''))[:8]!=basin['huc8']:continue
        line=f['geometry']['coordinates'];distance=min(segment_distance(point,a,b) for a,b in zip(line,line[1:]))
        choices.append((distance,p['id']))
    if not choices:return {'available':False,'reason':'no same-name channel in the same surface watershed'}
    distance,ident=min(choices)
    if distance>250:return {'available':False,'reason':'named channel farther than 250 m','distance_m':distance}
    return {'available':True,'channel_id':ident,'distance_m':round(distance,1),'basis':'provider river name, WBD watershed containment and distance to NHD line','reach_estimate':None,'meaning':'position association only; no measured reach or causal relationship'}


def gauge_stroke(point,line,half_m=500):
    """A display stroke of at most `half_m` each side of the gauge along ONE saved line.

    It locates the gauge reading on its channel. It never crosses onto another piece and is
    not a measured or inferred reach.
    """
    scale=math.cos(math.radians(point[1]));metres=lambda a,b:math.hypot((a[0]-b[0])*scale,a[1]-b[1])*111195
    best=None
    for i,(a,b) in enumerate(zip(line,line[1:])):
        dx=(b[0]-a[0])*scale;dy=b[1]-a[1];t=max(0,min(1,(((point[0]-a[0])*scale)*dx+(point[1]-a[1])*dy)/(dx*dx+dy*dy))) if dx*dx+dy*dy else 0
        q=[a[0]+t*(b[0]-a[0]),a[1]+t*(b[1]-a[1])];d=metres(point,q)
        if best is None or d<best[0]:best=(d,i,q)
    _,i,q=best
    def walk(points):
        out=[];left=half_m;prev=q
        for p in points:
            step=metres(prev,p)
            if step>=left:
                f=left/step if step else 0;out.append([prev[0]+f*(p[0]-prev[0]),prev[1]+f*(p[1]-prev[1])]);return out
            out.append(list(p[:2]));left-=step;prev=p
        return out
    back=walk(line[i::-1]);ahead=walk(line[i+1:])
    return [[round(x,6),round(y,6)] for x,y in back[::-1]+[q]+ahead]


def topology(features):
    nodes=defaultdict(list)
    for f in features:
        line=f['geometry']['coordinates']
        for p in (line[0],line[-1]):nodes[tuple(round(v,6) for v in p[:2])].append(f['properties']['id'])
    graph=defaultdict(set)
    for ids in nodes.values():
        for a in ids:graph[a].update(ids)
    seen=set();components=[]
    for ident in graph:
        if ident in seen:continue
        todo=[ident];found=set()
        while todo:
            k=todo.pop()
            if k in found:continue
            found.add(k);todo.extend(graph[k]-found)
        seen.update(found);components.append(sorted(found))
    return {'endpoint_precision_degrees':.000001,'component_sizes':sorted([len(c) for c in components],reverse=True),'components':components,'junctions':[{'coordinate':list(p),'channel_ids':ids} for p,ids in nodes.items() if len(set(ids))>=3],'rule':'only matching saved endpoints connect; no invented bridges; named channels may stop at reservoir waterbody paths'}


def downstream_route(channel_id,features,lakes):
    """Follow saved NHD pieces start-to-end (flowdir 1 = with digitized direction) from one piece.

    A step exists only where a piece's last coordinate equals exactly one next piece's first
    coordinate. Divergences and dead ends stop the walk and are reported; nothing is bridged.
    """
    key=lambda p:(round(p[0],6),round(p[1],6));byid={f['properties']['id']:f for f in features};starts=defaultdict(list)
    for f in features:starts[key(f['geometry']['coordinates'][0])].append(f)
    names={f['properties']['id']:f['properties']['name'] for f in lakes}
    f=byid.get(channel_id);seen=set();channels=[];waterbodies=[];stop='no such channel piece'
    while f:
        p=f['properties']
        if p['flowdir']!=1:stop='flow direction not with digitized direction';break
        if p['id'] in seen:stop='loop';break
        seen.add(p['id'])
        if not channels or channels[-1]!=p['name']:channels.append(p['name'])
        w=names.get(p.get('waterbody_id'))
        if w and (not waterbodies or waterbodies[-1]!=w):waterbodies.append(w)
        nxt=starts.get(key(f['geometry']['coordinates'][-1]),[])
        if len(nxt)>1:stop=f'divergence into {len(nxt)} pieces';break
        if not nxt:stop='end of saved network';break
        f=nxt[0]
    return {'from_channel_id':channel_id,'pieces':len(seen),'channel_names_in_order':channels,'reference_waterbodies_in_order':waterbodies,
        'first_receiving_reservoir':waterbodies[0] if waterbodies else None,'stopped':stop,
        'basis':'directed walk over captured NHD flowlines whose artificial paths carry the NHD waterbody identifier of a saved reference lake outline',
        'limit':'establishes the mapped channel route only; no travel time, discharge, loss or inflow volume is inferred'}


def describe_components(features,topo):
    byid={f['properties']['id']:f['properties'] for f in features};out=[]
    for c in sorted(topo['components'],key=len,reverse=True):
        out.append({'pieces':len(c),'names':dict(Counter(byid[i]['name'] for i in c)),'huc8':sorted({str(byid[i]['reachcode'])[:8] for i in c})})
    return out


def build():
    first,m1=capture('regional-channels-ordered');second,m2=capture('regional-channels-page2');paths,mp=capture('reservoir-channel-paths')
    if second.get('exceededTransferLimit') or paths.get('exceededTransferLimit'):raise ValueError('truncated network')
    basins,mb=capture('regional-basins');lakes,ml=capture('regional-lakes');extra,me=capture('regional-other-lakes')
    seen={};sources={}
    for d,m in [(first,m1),(second,m2),(paths,mp)]:
        for f in d['features']:
            p=f['properties'];ident=str(p['permanent_identifier']);sources[ident]=m['sha256']
            seen[ident]={'type':'Feature','geometry':f['geometry'],'properties':{'id':ident,'name':p.get('gnis_name') or 'Reservoir channel','reachcode':p['reachcode'],'flowdir':p['flowdir'],'waterbody_id':p.get('wbarea_permanent_identifier'),'meaning':'geographic context; unmeasured reach'}}
    fs=list(seen.values());geo={'type':'FeatureCollection','features':fs,'source':'USGS NHD high-resolution legacy map service; geographic context, not inundation'}
    lbs=[]
    for f in lakes['features']+extra['features']:
        p=f['properties'];lbs.append({'type':'Feature','geometry':f['geometry'],'properties':{'name':p['GNIS_NAME'],'id':p['PERMANENT_IDENTIFIER'],'meaning':'reference waterbody outline, not current water extent'}})
    manifest={'sources':[m1,m2,mp,mb,ml,me],'channel_sources':sources,'topology':topology(fs),'limits':['Legacy NHD high-resolution service, source feature dates retained in raw captures; not a live channel survey.','WBD is surface drainage, not an aquifer boundary.','Reference lake outlines are not measured current inundation.','Inks Lake outline absent from selected named waterbody responses; no polygon fabricated.','Flow direction is supplied by NHD (1 = with digitized direction); no velocity or travel time inferred.']}
    manifest['component_summary']=describe_components(fs,manifest['topology'])
    for name,d in [('regional-channels.geojson',geo),('regional-basins.geojson',basins),('regional-lakes.geojson',{'type':'FeatureCollection','features':lbs})]:(ROOT/'app'/name).write_text(json.dumps(d,separators=(',',':'))+'\n')
    (ROOT/'data/model/regional-geography.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print('Geography:',len(fs),'channel pieces;',len(lbs),'lake outlines;',len(basins['features']),'basins; components',manifest['topology']['component_sizes'][:10])
    return geo,basins,lbs,manifest

if __name__=='__main__':build()
