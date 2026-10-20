"""Bounded official geography/documentary acquisition only; preserves bytes before any analysis."""
import argparse,datetime as dt,gzip,hashlib,json,time,urllib.request,urllib.error
from pathlib import Path
from urllib.parse import urlparse
ROOT=Path(__file__).resolve().parents[1]
def acquire(name,url,folder='regional-water'):
    host=urlparse(url).hostname or ''
    if not any(host==d or host.endswith('.'+d) for d in ['usgs.gov','nationalmap.gov','lcra.org','waterdatafortexas.org','twdb.texas.gov','beg.utexas.edu','tnris.org','geographic.texas.gov']):raise ValueError('official sources only')
    if not name.replace('-','').isalnum():raise ValueError('simple capture name required')
    if folder not in ('regional-water','regional-geology'):raise ValueError('unknown capture folder')
    folder=ROOT/'data/captures/documentary'/folder;folder.mkdir(parents=True,exist_ok=True)
    p=folder/(name+'.gz');mp=folder/(name+'.meta.json')
    if p.exists():
        if json.loads(mp.read_text())['url']!=url:raise ValueError('capture name already used for different URL')
        print('existing capture',name);return
    at=dt.datetime.now(dt.timezone.utc).isoformat()
    request=urllib.request.Request(url,headers={'User-Agent':'hill-country-hydro regional pilot; public archive'})
    try:
        with urllib.request.urlopen(request,timeout=90) as response:body=response.read();status=response.status
    except urllib.error.HTTPError as e:body=e.read();status=e.code
    p.write_bytes(gzip.compress(body,mtime=0))
    mp.write_text(json.dumps({'url':url,'retrieved_at':at,'status':status,'sha256':hashlib.sha256(body).hexdigest(),'bytes':len(body),'capture_path':str(p.relative_to(ROOT)),'interpretation':'none; verbatim official source'},indent=2)+'\n')
    print(name,status,len(body))
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('name');p.add_argument('url');p.add_argument('--folder',default='regional-water');a=p.parse_args();acquire(a.name,a.url,a.folder)
