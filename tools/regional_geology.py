"""Derive bounded geological context from preserved official captures. Offline; no acquisition.

Mapped geology is interpretation, not measurement. Nothing here assigns a well to a producing unit
from a surface polygon, infers an underground connection, or invents a depth or thickness.
See docs/REGIONAL_GEOLOGY.md.
"""
from collections import Counter
import csv
import gzip
import hashlib
import html
import io
import json
from pathlib import Path
import re
try:
    from .regional_geography import inside
except ImportError:
    from regional_geography import inside

ROOT = Path(__file__).resolve().parents[1]
CAP = ROOT/'data/captures/documentary/regional-geology'
BOX = (-100.35, 29.95, -97.55, 31.05)
MATCH = {'Hickory': ('Riley', 'Hickory'), 'Ellenburger-San Saba': ('Ellenburger', 'San Saba', 'Wilberns', 'Tanyard', 'Gorman', 'Honeycut'),
         'Marble Falls': ('Marble Falls',)}
# Quoted relationships. build() refuses to run unless each sentence is found verbatim in its capture.
RELATIONSHIPS = [
    ('usgs-ha730e-text10-minor-aquifers', 'Hickory aquifer', 'The aquifer is underlain by Precambrian rocks and is overlain and separated from the Ellenburger-San Saba aquifer by the Cap Mountain Limestone and the Lion Mountain Sandstone Members of the Riley Formation.'),
    ('usgs-ha730e-text10-minor-aquifers', 'Ellenburger-San Saba aquifer', 'The aquifer is a sequence of limestone and dolomite beds that crop out in a circular pattern around the Llano Uplift and dip radially into the subsurface away from the center of the uplift.'),
    ('usgs-ha730e-text10-minor-aquifers', 'Marble Falls aquifer', 'The Marble Falls aquifer consists of the Marble Falls Limestone of Pennsylvanian age, which crops out along the flanks of the Llano Uplift, primarily in McCulloch, San Saba, Lam-pasas, and Burnet Counties.'),
    ('usgs-ha730e-text8-edwards-trinity', 'Trinity aquifer', 'In the Hill Country, water might flow laterally into the Trinity aquifer from the adjacent Edwards-Trinity aquifer.'),
    ('usgs-ha730e-text8-edwards-trinity', 'Trinity aquifer', 'In the Hill Country, the largest yields from wells completed in the Trinity aquifer are in the outcrop areas of the lower part of the Glen Rose Limestone and the upper part of the Travis Peak Formation.'),
    ('usgs-ha730e-text8-edwards-trinity', 'Edwards aquifer', 'The Edwards aquifer is underlain by the much less permeable Walnut Formation or Glen Rose Limestone of the Trinity aquifer.'),
]
SECTIONS = [
    {'capture': 'usgs-ha730e-fig112', 'file': 'geology/usgs-ha730e-fig112.gif', 'figure': 'Figure 112', 'kind': 'published hydrogeologic section', 'applies_to_basins': ['Pedernales'],
     'caption': 'In the Hill Country of south-central Texas, the southward-dipping Trinity aquifer is juxtaposed with the highly permeable Edwards aquifer as a result of faulting. The line of the hydrogeologic section is shown in figure 108.',
     'credit': 'U.S. Geological Survey, Ground Water Atlas of the United States, HA 730-E (Ryder, 1996), fig. 112; modified from Ashworth, J.B., 1983, Texas Department of Water Resources Report 273.',
     'relevance': 'Section C–C′ runs from Gillespie County through Kendall County into Bexar County and crosses the Pedernales River. Its vertical scale is greatly exaggerated and its potentiometric surface is dated 1975.',
     'limits': 'A published interpretation from a 1983 report, with a water-level surface dated 1975. It is not a measurement of today’s water levels and it does not cross the Llano River watershed.'},
    {'capture': 'usgs-ha730e-fig079', 'file': 'geology/usgs-ha730e-fig079.gif', 'figure': 'Figure 79', 'kind': 'published diagrammatic section, not to scale', 'applies_to_basins': [],
     'caption': 'A diagrammatic section through the Edwards-Trinity aquifer system shows how the three aquifers relate to each other and to contiguous rocks.',
     'credit': 'U.S. Geological Survey, Ground Water Atlas of the United States, HA 730-E (Ryder, 1996), fig. 79; modified from E.L. Kuniansky, U.S. Geological Survey, written communication, 1990.',
     'relevance': 'Northwest to southeast across the Edwards Plateau, the Llano Uplift, the Hill Country and the Balcones Fault Zone.',
     'limits': 'Diagrammatic and marked “not to scale”: it shows the order and juxtaposition of units, with no depths or thicknesses. It does not name the Paleozoic aquifers of the Llano Uplift.'},
]
GAPS = [
    'No free, reproducible cross-section through the Llano River watershed is shown. TWDB Report 346 (1996) holds Llano Uplift sections in its figures 3–7; its reuse grant covers original material and those figures are adapted from other authors, so the report is linked and its figures are not reproduced.',
    'TWDB publishes aquifer extents with a numeric outcrop/subsurface code whose meaning is not stated in the layer or shapefile metadata. The meaning used here was checked against the Geologic Atlas of Texas surface units; the check is reported below.',
    'Eleven of the 37 pilot wells have no casing, screen or open-hole rows in the TWDB Groundwater Database. Their completion interval is not documented; no interval is assumed.',
    'BEG mapping was not audited beyond the Geologic Atlas of Texas sheets as digitized and served by TWDB. USGS statewide geology downloads over 40 MB were not captured.',
    'No recharge-zone polygons and no confining-unit polygons were acquired. Confining relationships appear only as the quoted USGS sentences.',
]


def capture(name, binary=False):
    meta = json.loads((CAP/(name+'.meta.json')).read_text())
    body = gzip.decompress((CAP/(name+'.gz')).read_bytes())
    if meta['status'] != 200 or hashlib.sha256(body).hexdigest() != meta['sha256']:
        raise ValueError('unverified geology capture: '+name)
    return (body if binary else body.decode('utf-8-sig', errors='replace')), meta


def plain(page):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', page)))


def clip_ring(ring, box=BOX):
    """Sutherland-Hodgman against the pilot rectangle. Display clipping only."""
    x0, y0, x1, y1 = box
    def cut(points, keep, cross):
        out = []
        for a, b in zip(points, points[1:]+points[:1]):
            if keep(b):
                if not keep(a):
                    out.append(cross(a, b))
                out.append(b)
            elif keep(a):
                out.append(cross(a, b))
        return out
    def at_x(x):
        return lambda a, b: [x, a[1]+(b[1]-a[1])*(x-a[0])/(b[0]-a[0])]
    def at_y(y):
        return lambda a, b: [a[0]+(b[0]-a[0])*(y-a[1])/(b[1]-a[1]), y]
    points = [p[:2] for p in ring[:-1]]
    for keep, cross in [(lambda p: p[0] >= x0, at_x(x0)), (lambda p: p[0] <= x1, at_x(x1)), (lambda p: p[1] >= y0, at_y(y0)), (lambda p: p[1] <= y1, at_y(y1))]:
        points = cut(points, keep, cross)
        if not points:
            return []
    return points+[points[0]]


def simplify(line, tolerance):
    """Douglas-Peucker; endpoints kept. Display simplification of mapped lines, never of measurements."""
    if len(line) < 3:
        return line
    keep = [False]*len(line); keep[0] = keep[-1] = True; stack = [(0, len(line)-1)]
    while stack:
        a, b = stack.pop(); ax, ay = line[a][:2]; bx, by = line[b][:2]; dx, dy = bx-ax, by-ay; best, index = 0, None
        for i in range(a+1, b):
            px, py = line[i][:2]
            d = abs(dy*(px-ax)-dx*(py-ay))/((dx*dx+dy*dy)**.5) if dx or dy else ((px-ax)**2+(py-ay)**2)**.5
            if d > best:
                best, index = d, i
        if index is not None and best > tolerance:
            keep[index] = True; stack += [(a, index), (index, b)]
    return [[round(p[0], 5), round(p[1], 5)] for p, k in zip(line, keep) if k]


def polygons(geometry):
    return geometry['coordinates'] if geometry['type'] == 'MultiPolygon' else [geometry['coordinates']]


def shape(geometry, tolerance, clip=True):
    out = []
    for poly in polygons(geometry):
        rings = []
        for ring in poly:
            ring = clip_ring(ring) if clip else [p[:2] for p in ring]
            ring = simplify(ring, tolerance) if ring else []
            if len(ring) >= 4:
                rings.append(ring)
            elif not rings:
                break
        if rings:
            out.append(rings)
    return {'type': 'MultiPolygon', 'coordinates': out} if out else None


def interior_point(geometry):
    """A point inside the first polygon: its vertex mean when that is inside, else a nudged edge midpoint."""
    ring = polygons(geometry)[0][0]
    c = [sum(p[0] for p in ring[:-1])/(len(ring)-1), sum(p[1] for p in ring[:-1])/(len(ring)-1)]
    if inside(c, geometry):
        return c
    for a, b in zip(ring, ring[1:]):
        for sign in (1, -1):
            m = [(a[0]+b[0])/2+sign*(b[1]-a[1])*1e-3, (a[1]+b[1])/2-sign*(b[0]-a[0])*1e-3]
            if inside(m, geometry):
                return m
    return None


class Units:
    """Geologic Atlas of Texas surface units with a bounding-box prefilter."""
    def __init__(self, features):
        self.items = []
        for f in features:
            xs = [p[0] for poly in polygons(f['geometry']) for p in poly[0]]; ys = [p[1] for poly in polygons(f['geometry']) for p in poly[0]]
            self.items.append((min(xs), min(ys), max(xs), max(ys), f))
    def at(self, point):
        if not point or any(v is None for v in point):
            return None
        found = [f['properties'] for x0, y0, x1, y1, f in self.items if x0 <= point[0] <= x1 and y0 <= point[1] <= y1 and inside(point, f['geometry'])]
        if len(found) != 1:
            return {'available': False, 'reason': f'{len(found)} mapped units contain this point'}
        p = found[0]
        return {'available': True, 'unit': p['RockUnitName'], 'code': p['RockUnitCode'], 'period': p['Period'], 'sheet': p['SheetName'],
                'meaning': 'rock mapped at the land surface at this point (Geologic Atlas of Texas, 1:250,000); not the unit a well draws from'}


def well_record(text):
    """Parse one TWDB Groundwater Database well report CSV. Owner and driller names are not carried forward."""
    blocks = [b for b in re.split(r'\r?\n\s*\r?\n', text) if b.strip()]
    tables = {}
    for b in blocks:
        rows = list(csv.reader(io.StringIO(b)))
        if rows and len(rows[0]) > 1:
            tables[rows[0][0]] = [dict(zip(rows[0], r)) for r in rows[1:] if any(r)]
    head = tables['StateWellNumber'][0]
    num = lambda v: float(v) if v not in (None, '') else None
    casing = [{'type': r['CasingType'] or None, 'top_ft': num(r['CasTopDepth']), 'bottom_ft': num(r['CasBottomDepth']), 'material': r['CasingMaterial'] or None,
               'diameter_in': num(r['CasDiameter'])} for r in tables.get('CASING', [])]
    open_rows = [c for c in casing if c['type'] and c['type'].lower() != 'blank' and c['top_ft'] is not None and c['bottom_ft'] is not None]
    return {'well': head['StateWellNumber'], 'county': head['County'], 'gwdb_aquifer_code': head['AquiferCode'] or None, 'gwdb_aquifer': head['Aquifer'] or None,
            'aquifer_pick_method': head['AquiferPickMethod'] or None, 'well_depth_ft': num(head['WellDepth']), 'well_depth_source': head['WellDepthSource'] or None,
            'land_surface_elevation_ft': num(head['LandSurfaceElevation']), 'land_surface_elevation_method': head['LandSurfaceElevationMethod'] or None,
            'borehole_completion': (head['BoreholeCompletion'] or '').strip() or None, 'drilling_end_date': head['DrillingEndDate'] or None,
            'casing_rows': casing, 'screen_or_open_intervals': [{'type': c['type'], 'top_ft': c['top_ft'], 'bottom_ft': c['bottom_ft']} for c in open_rows],
            'interval_status': 'documented' if open_rows else 'casing recorded without a screen or open interval' if casing else 'not documented in the Groundwater Database',
            'lithology_rows': len(tables.get('LITHOLOGY', [])),
            'lithology': [{'top_ft': num(r['LithTopDepth']), 'bottom_ft': num(r['LithBottomDepth']), 'description': r['LithDescription'].strip()} for r in tables.get('LITHOLOGY', [])]}


def build():
    sources = {}
    def take(name, binary=False):
        body, meta = capture(name, binary)
        sources[name] = {k: meta[k] for k in ('url', 'retrieved_at', 'sha256', 'bytes')}
        return body
    texts = {}
    for name, subject, sentence in RELATIONSHIPS:
        texts.setdefault(name, plain(take(name)))
        if sentence not in texts[name]:
            raise ValueError('quoted relationship not found verbatim in '+name)
    rock = []
    for i in range(1, 9):
        rock += json.loads(take(f'twdb-gat-rockunit-bbox-p{i:02d}'))['features']
    if len({f['properties']['ObjectId'] for f in rock}) != len(rock):
        raise ValueError('duplicate rock-unit pages')
    units = Units(rock)
    aquifers = []; check = {}
    for name, rank in [('twdb-major-aquifers-bbox', 'major'), ('twdb-minor-aquifers-bbox', 'minor')]:
        for f in json.loads(take(name))['features']:
            p = f['properties']; code = p['AquiferNumName'][:1]
            if p['AquiferName'] in MATCH and code in '12':
                point = interior_point(f['geometry']); unit = units.at(point) if point else None
                tally = check.setdefault(p['AquiferName'], {'1': Counter(), '2': Counter()})[code]
                if not unit or not unit['available']:
                    tally['no single mapped unit'] += 1
                else:
                    tally['matching surface unit' if any(w in unit['unit'] for w in MATCH[p['AquiferName']]) else 'other surface unit'] += 1
            g = shape(f['geometry'], .0015)
            if g:
                aquifers.append({'type': 'Feature', 'geometry': g, 'properties': {'layer': 'aquifer', 'aquifer': p['AquiferName'], 'rank': rank, 'code': code,
                                 'extent': {'1': 'outcrop', '2': 'subsurface'}.get(code, 'unstated'), 'source': name}})
    verification = {a: {c: dict(t) for c, t in codes.items()} for a, codes in check.items()}
    ones = sum(t['1'].get('matching surface unit', 0) for t in check.values()); ones_all = sum(sum(t['1'].values()) for t in check.values())
    twos = sum(t['2'].get('matching surface unit', 0) for t in check.values()); twos_all = sum(sum(t['2'].values()) for t in check.values())
    faults = []
    for name in ('twdb-gat-structure-bbox-p1', 'twdb-gat-structure-bbox-p2'):
        for f in json.loads(take(name))['features']:
            lines = f['geometry']['coordinates'] if f['geometry']['type'] == 'MultiLineString' else [f['geometry']['coordinates']]
            faults.append({'type': 'Feature', 'geometry': {'type': 'MultiLineString', 'coordinates': [simplify(l, .0008) for l in lines]},
                           'properties': {'layer': 'fault', 'fault_type': f['properties']['FaultType']}})
    surface = []
    for f in rock:
        g = shape(f['geometry'], .003)
        if g:
            p = f['properties']
            surface.append({'type': 'Feature', 'geometry': g, 'properties': {'layer': 'surface_unit', 'unit': p['RockUnitName'], 'code': p['RockUnitCode'], 'period': p['Period'], 'sheet': p['SheetName']}})
    inventory = {w['id']: w for w in json.loads((ROOT/'data/wells-regional.json').read_text())['wells']}
    stations = json.loads((ROOT/'data/model/regional-history-stations.json').read_text())['stations']
    usgs = {s['id']: s for s in json.loads((ROOT/'data/usgs-locations-regional.json').read_text())['locations']}
    wells = {}
    for key, meta in sorted(stations.items()):
        if meta['kind'] != 'well':
            continue
        wid = key.split(':')[1]; record = well_record(take('gwdb-welldata-'+wid)); feed = inventory[wid]
        if record['well'] != wid:
            raise ValueError('well report mismatch '+wid)
        record.update(feed_aquifer=feed['aquifer'], feed_aquifer_type=feed.get('aquifer_type'), basin=meta.get('basin'),
                      aquifer_assignment={'source': 'TWDB provider assignment (Water Data for Texas feed and Groundwater Database code)',
                                          'agreement': 'same aquifer name' if record['gwdb_aquifer'] == feed['aquifer'] else 'names differ between the two TWDB records',
                                          'pick_method': record['aquifer_pick_method'] or 'not recorded'},
                      surface_unit=units.at([feed['lon'], feed['lat']]), capture='gwdb-welldata-'+wid)
        wells[key] = record
    gauges = {}
    for key, meta in sorted(stations.items()):
        if meta['kind'] == 'river':
            s = usgs[key.split(':')[1]]; gauges[key] = {'name': s['name'], 'surface_unit': units.at([s['lon'], s['lat']])}
    # What is mapped at each station's coordinates. Extents are the display-simplified ones (about 150 m).
    def aquifers_at(point):
        return sorted({(f['properties']['aquifer'], f['properties']['extent']) for f in aquifers if inside(point, f['geometry'])})
    stations_at = {}
    catalog = ROOT/'data/normalized/regional-analytics/catalog.json'
    for key, site in sorted(json.loads(catalog.read_text())['sites'].items()) if catalog.exists() else []:
        point = site.get('coordinates')
        if not point or any(v is None for v in point) or not (BOX[0] <= point[0] <= BOX[2] and BOX[1] <= point[1] <= BOX[3]):
            continue
        stations_at[key] = {'surface_unit': units.at(point), 'aquifer_extents': [{'aquifer': a, 'extent': e} for a, e in aquifers_at(point)]}
    figures = []
    (ROOT/'app/geology').mkdir(parents=True, exist_ok=True)
    for s in SECTIONS:
        (ROOT/'app'/s['file']).write_bytes(take(s['capture'], binary=True))
        figures.append(dict(s, url=sources[s['capture']]['url'], sha256=sources[s['capture']]['sha256']))
    for name in ('usgs-copyrights-and-credits-page', 'twdb-gisdata-page', 'twdb-map-disclaimer', 'twdb-gat-index-page', 'twdb-r346-paleozoic-aquifers-central-texas-pdf',
                 'twdb-r377-hill-country-trinity-gam-pdf', 'twdb-major-aquifers-shp-zip', 'twdb-minor-aquifers-shp-zip', 'txgio-gat-collection-json'):
        take(name, binary=True)
    doc = {'schema_version': 'regional-geology/v1', 'evidence_class': 'mapped and published geological interpretation; no instrument observation',
           'pilot_box_lon_lat': BOX, 'sources': sources,
           'aquifer_extents': {'features': len(aquifers), 'by_aquifer': dict(Counter(f"{f['properties']['aquifer']} · {f['properties']['extent']}" for f in aquifers)),
                               'publisher': 'Texas Water Development Board; major aquifers dated December 2006 and minor aquifers December 2017 on the TWDB GIS data page; source scale 1:250,000 stated for the major-aquifer shapefile',
                               'processing': 'clipped to the pilot rectangle and simplified to about 150 m for display',
                               'code_meaning': {'1': 'outcrop', '2': 'subsurface (downdip)', 'basis': 'not stated in TWDB layer metadata; checked by overlaying each coded Llano Uplift minor-aquifer polygon on Geologic Atlas of Texas surface units',
                                                'check': verification, 'summary': f'{ones} of {ones_all} code-1 polygons sit on a surface unit of the aquifer’s own formations; {twos} of {twos_all} code-2 polygons do'}},
           'faults': {'features': len(faults), 'by_type': dict(Counter(f['properties']['fault_type'] for f in faults)), 'publisher': 'Geologic Atlas of Texas (Bureau of Economic Geology, 1:250,000 sheets) as digitized and served by TWDB',
                      'limit': 'a mapped fault trace at the surface; it does not show whether water moves along or across the fault'},
           'surface_units': {'features': len(surface), 'by_period': dict(Counter(f['properties']['period'] for f in surface)), 'processing': 'clipped and simplified to about 300 m for display; station lookups use the unsimplified captured polygons'},
           'stations': stations_at, 'station_basis': 'Surface unit from the unsimplified Geologic Atlas polygons; aquifer extents from the TWDB polygons simplified to about 150 m, so a point near a boundary may fall on the wrong side. Being on an extent does not connect a station to that aquifer.',
           'wells': wells, 'well_summary': dict(Counter(w['interval_status'] for w in wells.values())), 'river_gauges': gauges,
           'sections': figures, 'relationships': [{'source': n, 'url': sources[n]['url'], 'subject': s, 'quote': q} for n, s, q in RELATIONSHIPS],
           'linked_not_reproduced': [{'title': 'TWDB Report 346, Paleozoic aquifers of central Texas (1996): Llano Uplift sections, figures 3–7', 'url': sources['twdb-r346-paleozoic-aquifers-central-texas-pdf']['url']},
                                     {'title': 'TWDB Report 377, Hill Country Trinity groundwater availability model (2011): hydrostratigraphic column fig. 3-14, sections fig. 3-17', 'url': sources['twdb-r377-hill-country-trinity-gam-pdf']['url']}],
           'evidence_gaps': GAPS,
           'limits': ['Surface watersheds (USGS WBD) and aquifer extents are different things; neither bounds the other.', 'A surface polygon does not identify a well’s producing unit; aquifer assignments are the provider’s.',
                      'No underground connection between any well, spring, stream or reservoir is inferred from position or timing.', 'Published sections are reproduced as published; no depth, thickness, water level or flow path is added.']}
    text = json.dumps(doc, indent=1)+'\n'
    (ROOT/'data/model/regional-geology.json').write_text(text); (ROOT/'app/regional-geology.json').write_text(text)
    for name, features in [('regional-aquifers.geojson', aquifers), ('regional-faults.geojson', faults), ('regional-surface-geology.geojson', surface)]:
        (ROOT/'app'/name).write_text(json.dumps({'type': 'FeatureCollection', 'features': features}, separators=(',', ':'))+'\n')
        print(name, len(features), (ROOT/'app'/name).stat().st_size)
    print('Outcrop-code check:', doc['aquifer_extents']['code_meaning']['summary']); print('Wells:', doc['well_summary'])
    return doc


if __name__ == '__main__':
    build()
