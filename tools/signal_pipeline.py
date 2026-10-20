#!/usr/bin/env python3
"""Strict local signal stages: acquire -> normalize -> parse -> optional review queue.

Acquisition is intentionally elsewhere: monitor.py fetches and preserves USGS bytes.
This file never performs a network request. It only consumes saved local records.
"""
import argparse, datetime as dt, json, sqlite3
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
NORM=ROOT/'data/normalized'; PARSED=ROOT/'data/parsed'; REVIEW=ROOT/'data/review'

def normalize_collection():
    """Materialize the cross-feed canonical collection from normalized USGS rows."""
    PARSED.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(NORM/'water.sqlite')
    rows=db.execute('select provider,station_id,series_id,parameter,unit,observed_at,retrieved_at,value,qualifiers,raw_path from observations order by observed_at').fetchall()
    with (NORM/'signals.jsonl').open('w') as out:
        for r in rows:
            out.write(json.dumps(dict(zip(['provider','station_id','series_id','parameter','unit','observed_at','retrieved_at','value','qualifiers','raw_path'],r)))+'\n')
    print(f'normalized collection: {len(rows)} signals')

def parse_lines(lines,source):
    """Deterministic latest-value selection with named errors for corrupt input."""
    latest={}
    for number,line in enumerate(lines,1):
        if not line.strip(): continue
        try:
            r=json.loads(line);key=(r['station_id'],r['parameter'])
            when=dt.datetime.fromisoformat(r['observed_at'].replace('Z','+00:00'))
            if when.tzinfo is None: raise ValueError('observation time lacks timezone')
        except (json.JSONDecodeError,KeyError,TypeError,ValueError,AttributeError) as exc:
            raise ValueError(f'{source}:{number}: malformed normalized signal: {exc}') from exc
        if key not in latest or when>latest[key][0]: latest[key]=(when,r)
    return [item[1] for item in latest.values()]

def parse():
    """Deterministic parser: latest per station/parameter; no thresholds, no LLM."""
    source=NORM/'signals.jsonl'
    rows=parse_lines(source.read_text().splitlines(),source)
    (PARSED/'latest-by-station.json').write_text(json.dumps(rows,indent=2))
    print(f'parsed collection: {len(rows)} latest series values')

def review_queue():
    """Only a bounded exception queue may later be handed to an LLM for triage."""
    REVIEW.mkdir(parents=True,exist_ok=True)
    coverage=json.loads((ROOT/'data/coverage.json').read_text())
    items=[{'type':'missing_mechanical_link','place':x,'instruction':'Find an official mechanical or operator-status source; do not infer one.'} for x in coverage['no_mechanical_record_linked_yet']]
    (REVIEW/'llm-candidates.json').write_text(json.dumps(items,indent=2))
    print(f'review candidates: {len(items)}; no LLM called')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['normalize','parse','review']);a=p.parse_args()
    {'normalize':normalize_collection,'parse':parse,'review':review_queue}[a.stage]()
