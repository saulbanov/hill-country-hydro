#!/usr/bin/env python3
"""Export checksummed historical-acquisition coverage without versioning raw payloads."""
import argparse, json
from datetime import datetime
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def main(station,target_start,target_end):
    root=ROOT/'data/raw/usgs-history'/station
    windows=[]
    for path in sorted(root.glob('*.meta.json')):
        m=json.loads(path.read_text())
        windows.append({k:m.get(k) for k in ('start','end_exclusive','status','feature_count','next_link','sha256','url','retrieved_at')})
    complete=[x for x in windows if x['status']==200 and x['feature_count'] is not None and x['feature_count']<10000 and not x['next_link']]
    chronological=sorted(complete,key=lambda x:x['start'])
    window_gaps=[]
    for prior,current in zip(chronological,chronological[1:]):
        if prior['end_exclusive'] != current['start']:
            window_gaps.append({'after':prior['end_exclusive'],'before':current['start']})
    complete_target=(bool(chronological) and chronological[0]['start']==target_start and chronological[-1]['end_exclusive']==target_end and not window_gaps)
    output={'version':'v1','purpose':'Versionable provenance and coverage index for local raw USGS history excluded from Git.',
      'station_id':'USGS-'+station,'raw_payload_location':str(root.relative_to(ROOT))+'/',
      'completeness_rule':'A window is complete only if HTTP 200, feature_count < requested limit, and next_link is null.',
      'windows':windows,'summary':{'window_count':len(windows),'complete_window_count':len(complete),
        'first_window_start':chronological[0]['start'] if chronological else None,
        'last_window_end_exclusive':chronological[-1]['end_exclusive'] if chronological else None,
        'window_gap_count':len(window_gaps),'window_gaps':window_gaps,
        'target_window':{'start_inclusive':target_start,'end_exclusive':target_end,'complete_non_overlapping_raw_coverage':complete_target},
        'warning':'Complete raw-request coverage does not establish a gap-free measurement series; inspect the normalized replay gap report.'}}
    destination=ROOT/'data/model'/f'{station}-historical-archive-manifest.json'
    destination.write_text(json.dumps(output,indent=2))
    print(f'wrote {destination.relative_to(ROOT)} with {len(complete)}/{len(windows)} complete windows')

if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--station',required=True)
    p.add_argument('--target-start',default='2021-01-01T00:00:00+00:00')
    p.add_argument('--target-end',default='2026-01-01T00:00:00+00:00')
    a=p.parse_args(); main(a.station,a.target_start,a.target_end)
