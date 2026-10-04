"""Copy the public regional pilot, the Austin prototype and the original ledger to the EXISTING Site checkout.

Public derived assets only. Never deploys, never acquires, never copies raw captures, SQLite stores,
repository metadata or collectors. Refuses to finish if a packaged file names a private path.
"""
import argparse
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import shutil
from urllib.parse import urljoin, urlparse
ROOT = Path(__file__).resolve().parents[1]
SITE = 'appgprj_6ac12765acb88191a74ce6c2570385f5'
APP = ['index.html', 'regional.js', 'regional-plots.js', 'regional.css', 'regional-snapshot.json', 'regional-channels.geojson', 'regional-basins.geojson',
       'regional-lakes.geojson', 'regional-aquifers.geojson', 'regional-faults.geojson', 'regional-surface-geology.geojson', 'regional-geology.json', 'regional-events.json',
       'austin.html', 'creeks.js', 'creeks.css', 'creek-icon.svg', 'creek-snapshot.json', 'austin-creeks.geojson', 'ledger.html', 'map.js']
OTHER = ['dist/water-state.json', 'data/model/storms/2026-09-30.json', 'data/model/storms/2026-07-11.json', 'docs/CREEK_ANALYTICS.md', 'docs/CREEK_COVERAGE.md',
         'data/model/creek-normalization-audit.json', 'data/model/creek-gauge-associations.json', 'docs/REGIONAL_ANALYTICS.md', 'docs/REGIONAL_COVERAGE.md',
         'docs/REGIONAL_HISTORY.md', 'docs/REGIONAL_HISTORY_TABLE.md', 'docs/REGIONAL_GEOGRAPHY.md', 'docs/REGIONAL_GEOLOGY.md',
         'data/model/regional-gauge-associations.json']
FORBIDDEN = [re.compile(p) for p in (r'/Users/', r'/private/tmp', r'@gmail\.com', r'"Owner"\s*:', r',Owner,', r'OwnerWellNumber', r'"Driller"\s*:')]
BLOCKED_SUFFIXES = ('.sqlite', '.gz', '.py', '.meta.json', '.zip', '.pdf')
PAGES = ['index.html', 'austin.html', 'ledger.html']


class Links(HTMLParser):
    def __init__(self):
        super().__init__(); self.links = []
    def handle_starttag(self, tag, attrs):
        for k, v in attrs:
            if k in ('src', 'href') and v:
                self.links.append(v)


def plan():
    files = {f'app/{name}': name for name in APP}
    files.update({name: name for name in OTHER})
    for p in sorted((ROOT/'app/history').glob('*.json')):
        files[f'app/history/{p.name}'] = f'history/{p.name}'
    for p in sorted((ROOT/'app/geology').iterdir()):
        files[f'app/geology/{p.name}'] = f'geology/{p.name}'
    return files


def check_inputs(files):
    for path in files:
        if not (ROOT/path).is_file():
            raise FileNotFoundError(path)
    snap = json.loads((ROOT/'app/regional-snapshot.json').read_text())
    for name, digest in snap['geometry_hashes'].items():
        if hashlib.sha256((ROOT/'app'/name).read_bytes()).hexdigest() != digest:
            raise ValueError(f'{name} differs from the snapshot it was built with')
    creek = json.loads((ROOT/'app/creek-snapshot.json').read_text())
    if hashlib.sha256((ROOT/'app/austin-creeks.geojson').read_bytes()).hexdigest() != creek['geometry_sha256']:
        raise ValueError('Austin geometry differs from its snapshot')
    index = json.loads((ROOT/'app/history/index.json').read_text())
    for key, entry in index['stations'].items():
        if entry['file'] and 'app/'+entry['file'] not in files:
            raise FileNotFoundError(entry['file'])
    return snap


def private_hits(path):
    if path.suffix.lower() in ('.gif', '.png', '.jpg', '.svg'):
        return []
    text = path.read_text(errors='replace')
    return [p.pattern for p in FORBIDDEN if p.search(text)]


def check_links(out):
    for page in PAGES:
        parser = Links(); parser.feed((out/page).read_text())
        for link in parser.links:
            url = urlparse(urljoin('https://local.invalid/'+page, link))
            if url.netloc == 'local.invalid' and url.path != '/' and not (out/url.path.lstrip('/')).is_file():
                raise ValueError(f'{page}: missing public asset {link}')


def package(dest):
    dest = Path(dest); manifest = json.loads((dest/'.openai/hosting.json').read_text())
    if manifest.get('project_id') != SITE or manifest.get('static', {}).get('directory') != 'out':
        raise ValueError('wrong Site identity or static directory')
    files = plan(); snap = check_inputs(files)
    if any(src.endswith(BLOCKED_SUFFIXES) for src in files):
        raise ValueError('a raw capture, store or collector is in the package plan')
    for src in files:
        hits = private_hits(ROOT/src)
        if hits:
            raise ValueError(f'{src}: private content {hits}')
    out = dest/'out'
    for stale in ('history', 'geology'):
        if (out/stale).is_dir():
            shutil.rmtree(out/stale)
    for src, dst in files.items():
        p = out/dst; p.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(ROOT/src, p)
    check_links(out)
    total = sum((out/d).stat().st_size for d in files.values())
    print(f'{len(files)} public files, {total} bytes prepared in the existing Site; publication date in snapshot {snap["publication_date"]}; raw archives, stores and source history excluded')
    return files


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--site-root', type=Path, required=True); a = p.parse_args(); package(a.site_root)
