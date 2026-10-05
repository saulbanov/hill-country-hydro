"""Record which water-map stations also appear on the Austin Swim Map, for links from station pages. Offline.

Reads the swim map's published gauge inventory (a file in its public Site checkout) and writes the
intersection with this repo's history stations. The swim map is a downstream lens; this is a link
table with its source hash, not a dependency: without it the water map simply shows no swim links.
"""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SWIM_MAP = 'https://austin-swim-map.saul-elbein.chatgpt.site/'


def build(swim_gauges):
    body = Path(swim_gauges).read_bytes()
    gauges = json.loads(body)
    gauges = gauges if isinstance(gauges, list) else gauges.get('gauges', [])
    index = json.loads((ROOT/'app/history/index.json').read_text())['stations']
    stations = {f'USGS:{g["id"]}': {'swim_map_name': g['name'], 'anchor': 'gauge.'+g['id']} for g in gauges
                if index.get(f'USGS:{g["id"]}', {}).get('file')}
    doc = {'swim_map_url': SWIM_MAP, 'source': 'austin-swim-map public Site dist/data/gauges.json', 'source_sha256': hashlib.sha256(body).hexdigest(),
           'meaning': 'water-map stations that are also gauges on the Austin Swim Map; a link opens that gauge there. The swim map rates swimming places, not gauges.',
           'stations': dict(sorted(stations.items()))}
    text = json.dumps(doc, indent=1)+'\n'
    (ROOT/'data/model/swim-map-links.json').write_text(text); (ROOT/'app/swim-map-links.json').write_text(text)
    print(len(stations), 'stations linked to the swim map:', ', '.join(stations))
    return doc


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--swim-gauges', default=str(ROOT.parent/'austin-swim-map-public-site/dist/data/gauges.json'))
    build(p.parse_args().swim_gauges)
