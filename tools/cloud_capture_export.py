#!/usr/bin/env python3
"""Export one session's raw captures into a git-tracked folder so a cloud session's evidence survives.

data/raw/ is intentionally git-ignored: on Saul's Mac it is the reproducible evidence cache.
A cloud checkout has no such cache and its container disappears, so anything it fetched
must travel with the branch. This copies every capture whose filename stamp falls on the
given UTC day into _cloud-captures/<session>/ and writes manifest.jsonl with one
spool-format row per file: ts, tool, request, body_sha256, body_bytes, session, origin.

Large USGS JSON responses are stored gzip-compressed; body_sha256 and body_bytes always
describe the original bytes, so a local ingest gunzips and verifies before copying the
files back into data/raw/. Nothing is interpreted here.
"""
import argparse
import gzip
import hashlib
import json
import shutil
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
RAW=ROOT/'data/raw'
GZIP_SUFFIXES={'.json','.csv','.html','.geojson'}
GZIP_MIN_BYTES=200_000

def rows_for(day,dedupe=False):
    metas=[m for m in sorted(RAW.rglob('*.meta.json')) if m.name.removesuffix('.meta.json').startswith(day)]
    if dedupe:
        # Same request repeated within the day (the USGS two-day window pulled by several collect runs):
        # keep the newest file whose name, minus its timestamp, matches; older same-day repeats stay in data/raw only.
        newest={}
        for m in metas: newest[(m.parent,m.name.removesuffix('.meta.json')[27:] or m.name)]=m
        metas=sorted(newest.values())
    for meta_path in metas:
        stem=meta_path.name.removesuffix('.meta.json')
        siblings=[p for p in meta_path.parent.iterdir() if p.name.startswith(stem) and p!=meta_path]
        if len(siblings)!=1: raise ValueError(f'{meta_path}: expected exactly one body file, found {len(siblings)}')
        yield meta_path,siblings[0],json.loads(meta_path.read_text())

def main(day,session,dedupe=False):
    out=ROOT/'_cloud-captures'/session; out.mkdir(parents=True,exist_ok=True)
    manifest=out/'manifest.jsonl'; count=0; total=0
    with manifest.open('w') as m:
        for meta_path,body_path,meta in rows_for(day,dedupe):
            body=body_path.read_bytes(); sha=hashlib.sha256(body).hexdigest()
            if meta.get('sha256') and meta['sha256']!=sha: raise ValueError(f'{body_path}: checksum mismatch against its meta file')
            rel=body_path.relative_to(RAW); dest=out/rel; dest.parent.mkdir(parents=True,exist_ok=True)
            stored=str(rel)
            if body_path.suffix in GZIP_SUFFIXES and len(body)>=GZIP_MIN_BYTES:
                dest=dest.with_name(dest.name+'.gz'); stored+='.gz'
                with gzip.open(dest,'wb',compresslevel=9) as z: z.write(body)
            else: shutil.copyfile(body_path,dest)
            shutil.copyfile(meta_path,out/meta_path.relative_to(RAW))
            tool=body_path.parts[len(RAW.parts)]
            m.write(json.dumps({'ts':meta.get('retrieved_at'),'tool':tool,'request':meta.get('url'),'body_sha256':sha,'body_bytes':len(body),
                                'session':session,'origin':'claude-code-web','http_status':meta.get('status'),'stored_as':stored,
                                'restore_to':str(body_path.relative_to(ROOT)),'meta':str(meta_path.relative_to(RAW))})+'\n')
            count+=1; total+=len(body)
    (out/'README.md').write_text(f"""# Cloud captures · session {session}

Raw source bytes fetched by a Claude Code on the web session on {day[:4]}-{day[4:6]}-{day[6:]} (UTC).
`data/raw/` is git-ignored, so these files ride the branch instead. One manifest row per file in
`manifest.jsonl` (spool format: ts, tool, request, body_sha256, body_bytes, session, origin).

Files ending in `.gz` are gzip-compressed copies; `body_sha256` and `body_bytes` describe the
original bytes. A local session restores each file to `restore_to`, verifies the checksum, and then
deletes this folder. No script does that restore yet; it is tracked in knowledge-architecture.
""")
    print(f'exported {count} captures ({total/1e6:.1f} MB original) to {out.relative_to(ROOT)}')

if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--date',required=True,help='UTC day YYYYMMDD'); p.add_argument('--session',required=True); p.add_argument('--dedupe',action='store_true',help='keep only the newest same-day repeat of an identical request')
    a=p.parse_args(); main(a.date,a.session,a.dedupe)
