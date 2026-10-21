#!/usr/bin/env python3
"""Build and verify the county KBDI external reference-data snapshot."""
import argparse,csv,hashlib,json,re
from datetime import datetime,timezone
from datetime import date
from pathlib import Path

SCHEMA="reference-data/v1"
def canon(x): return json.dumps(x,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False)+"\n"
def sha(p):
 h=hashlib.sha256()
 with open(p,"rb") as f:
  for b in iter(lambda:f.read(1024*1024),b""): h.update(b)
 return h.hexdigest()
def manifest(root):
 out=[]
 for line in (root/"manifest.jsonl").read_text().splitlines():
  if line.strip():
   d=json.loads(line)
   if d.get("source_id")=="kbdi-county" and d.get("file","").endswith(".csv"): out.append(d)
 out.sort(key=lambda d:d["file"])
 for i,d in enumerate(out,1):
  p=root/d["file"]
  if not p.is_file() or p.stat().st_size!=d["bytes"] or sha(p)!=d["sha256"]: raise ValueError(f"input mismatch {p}")
  d=d.copy(); d["id"]=f"input-{i}"; out[i-1]=d
 return out
def main():
 p=argparse.ArgumentParser(); p.add_argument("action",choices=["describe","build","verify"]); p.add_argument("--root",type=Path,default=Path("/Volumes/Elements/reference-data")); p.add_argument("--config",type=Path,default=Path("config/reference-data-pilot.json")); p.add_argument("--output",type=Path); p.add_argument("--bundle",type=Path); a=p.parse_args()
 if a.action=="verify": return verify(a.bundle)
 rows=manifest(a.root); cfg=json.loads(a.config.read_text())
 if a.action=="describe": print(json.dumps({"source":"kbdi-county","files":len(rows),"bytes":sum(x["bytes"] for x in rows),"dates":[Path(x["file"]).stem[4:] for x in rows]},sort_keys=True,indent=2)); return
 out=a.output.resolve(); out.mkdir(parents=True,exist_ok=True); records_by_date={}; seen=set()
 for r in rows:
  m=re.fullmatch(r"summ(\d{8})\.csv",Path(r["file"]).name); assert m
  ds=f"{m.group(1)[:4]}-{m.group(1)[4:6]}-{m.group(1)[6:]}"
  with (a.root/r["file"]).open(newline="") as f: data=list(csv.DictReader(f))
  if list(data[0])!=["County","Min","Max","Average","Change"]: raise ValueError("unexpected KBDI header")
  if len(data)!=cfg["expected_counties"]: raise ValueError(f"{ds}: {len(data)} counties")
  records=[]
  for n,row in enumerate(data,2):
   county=row["County"].strip(); key=(ds,county)
   if key in seen: raise ValueError(f"duplicate {key}")
   seen.add(key)
   vals={k:float(row[k]) for k in ("Min","Max","Average")}; change=float(row["Change"])
   if not (0<=vals["Min"]<=vals["Average"]<=vals["Max"]<=800): raise ValueError(f"range {key}")
   records.append({"county":county,"date":ds,"min":vals["Min"],"max":vals["Max"],"average":vals["Average"],"change":change,"input_ref":r["id"],"locator":f"{r['file']}:row={n}:columns=County,Min,Max,Average,Change"})
  records_by_date[ds]=records
 if len(records_by_date)!=60 or len(seen)!=15240: raise ValueError(f"coverage dates={len(records_by_date)} records={len(seen)}")
 snap="sha256:"+hashlib.sha256(canon({"source":"kbdi-county","inputs":rows,"config":cfg,"schema":SCHEMA,"code":sha(Path(__file__).resolve())}).encode()).hexdigest()
 for ds,recs in sorted(records_by_date.items()):
  payload={"schema_version":SCHEMA,"source_id":"kbdi-county","snapshot_id":snap,"coverage":{"date":ds,"counties":len(recs)},"field_definitions":{"min":"publisher KBDI minimum","max":"publisher KBDI maximum","average":"publisher KBDI average","change":"publisher-reported signed change; not a difference between snapshots"},"attribution":{"publisher":"Texas A&M Forest Service / Texas Weather Connection","access_date":"2026-10-20","terms_url":"https://twc.tamu.edu/","license_status":"public source; publication rights require owner review"},"provenance":{"builder":{"owner":"hill-country-hydro","code_sha256":sha(Path(__file__).resolve())},"inputs":rows,"parameters":cfg},"records":recs}
  q=out/"dates"/(ds+".json"); q.parent.mkdir(parents=True,exist_ok=True); q.write_text(canon(payload))
 payloads=[]
 for q in sorted((out/"dates").glob("*.json")): payloads.append({"path":str(q.relative_to(out)),"bytes":q.stat().st_size,"sha256":sha(q),"records":len(json.loads(q.read_text())["records"])})
 cat={"schema_version":SCHEMA,"source_id":"kbdi-county","snapshot_id":snap,"coverage":{"start":min(records_by_date),"end":max(records_by_date),"dates":len(records_by_date),"counties":cfg["expected_counties"],"records":len(seen)},"attribution":{"publisher":"Texas A&M Forest Service / Texas Weather Connection","access_date":"2026-10-20","terms_url":"https://twc.tamu.edu/","license_status":"public source; publication rights require owner review"},"payloads":payloads}
 (out/"catalog.json").write_text(canon(cat)); verify(out)
 (a.root/"pilot-runs").mkdir(exist_ok=True)
 (a.root/"pilot-runs"/"kbdi-county-latest.json").write_text(canon({"source_id":"kbdi-county","stage":"ready_to_publish","started_at":datetime.now(timezone.utc).isoformat(),"completed_at":datetime.now(timezone.utc).isoformat(),"selected_files":[r["file"] for r in rows],"output":str(out),"validation":"verify pass","raw_source_unchanged":True}))
def verify(b):
 c=json.loads((b/"catalog.json").read_text()); assert c["schema_version"]==SCHEMA
 for p in c["payloads"]:
  q=(b/p["path"]).resolve(); assert b.resolve() in q.parents and sha(q)==p["sha256"] and q.stat().st_size==p["bytes"]
  d=json.loads(q.read_text()); assert d["snapshot_id"]==c["snapshot_id"]
  for r in d["records"]: assert any(i["id"]==r["input_ref"] for i in d["provenance"]["inputs"])
 print(json.dumps({"source_id":c["source_id"],"snapshot_id":c["snapshot_id"],"payloads":len(c["payloads"]),"ok":True},sort_keys=True))
if __name__=="__main__": main()
