"""Copy the bounded public snapshot to the EXISTING Site checkout; never deploy or acquire."""
import argparse
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import shutil
from urllib.parse import urljoin,urlparse
ROOT=Path(__file__).resolve().parents[1]
SITE='appgprj_6ac12765acb88191a74ce6c2570385f5'


class Links(HTMLParser):
    def __init__(self):super().__init__();self.links=[]
    def handle_starttag(self,tag,attrs):
        for k,v in attrs:
            if k in ('src','href') and v:self.links.append(v)


def package(dest):
    dest=Path(dest);manifest=json.loads((dest/'.openai/hosting.json').read_text())
    if manifest.get('project_id')!=SITE or manifest.get('static',{}).get('directory')!='out':raise ValueError('wrong Site identity or static directory')
    out=dest/'out'
    files={f'app/{name}':name for name in ['index.html','ledger.html','map.js','creeks.js','creeks.css','creek-icon.svg','creek-snapshot.json','austin-creeks.geojson']}
    for name in ['dist/water-state.json','data/model/storms/2026-09-30.json','data/model/storms/2026-07-11.json','docs/CREEK_ANALYTICS.md','docs/CREEK_COVERAGE.md','data/model/creek-normalization-audit.json','data/model/creek-gauge-associations.json']:
        files[name]=name
    # Validate every input before copying any file. Existing unrelated assets are preserved.
    for path in files:
        if not (ROOT/path).is_file():raise FileNotFoundError(path)
    snap=json.loads((ROOT/'app/creek-snapshot.json').read_text())
    if hashlib.sha256((ROOT/'app/austin-creeks.geojson').read_bytes()).hexdigest()!=snap['geometry_sha256']:raise ValueError('geometry differs from snapshot')
    for src,dst in files.items():
        p=out/dst;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/src,p)
    for html in ['index.html','ledger.html']:
        parser=Links();parser.feed((out/html).read_text())
        for link in parser.links:
            url=urlparse(urljoin('https://local.invalid/'+html,link))
            if url.netloc!='local.invalid':continue
            if not (out/url.path.lstrip('/')).is_file():raise ValueError(f'{html}: missing public asset {link}')
    print(f'{len(files)} public files prepared in existing Site; raw archives and source history excluded')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--site-root',type=Path,required=True);a=p.parse_args();package(a.site_root)
