#!/usr/bin/env python3
"""Preserve USGS field measurements (hand discharge and gage-height measurements) for stations whose
continuous record starts late, such as Jacob's Well (08170990, continuous from 2005). No assessment.

Acquisition (``collect``, Sundays): one request per station to the OGC API ``field-measurements``
collection, following ``next`` links. Bytes land in ``data/raw/usgs-field/<station>/`` (Git-ignored)
with ``.meta.json`` and gzipped in ``data/captures/usgs-field/<station>/`` (newest kept). A provider
failure prints ``SKIPPED — usgs_field_measurements: <url> unreachable (<reason>)`` and exits 0.

Normalization (``normalize``): ``data/history/<station>-field-measurements.csv`` with
``date,parameter,value,unit,measurement_id,qualifier``. A station the provider returns no
measurements for gets a header-only CSV and a manifest note. A value that is not a number stays out of
``value`` (it is never zero) and is counted.
"""
from __future__ import annotations

import argparse
import datetime as dt
import gzip
import hashlib
import json
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://api.waterdata.usgs.gov/ogcapi/v1/collections/field-measurements/items"
UA = "hill-country-hydro/0.1 usgs_field_measurements (+saulbanov/hill-country-hydro)"
STATIONS = ["08170990", "08155500"]
LIMIT = 10000


def paths(root: Path) -> dict:
    return {"raw": root / "data/raw/usgs-field", "cap": root / "data/captures/usgs-field", "history": root / "data/history",
            "manifest": root / "data/model/usgs-field-measurements-manifest.json"}


def utcnow() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def fetch(url: str) -> tuple[int, bytes, str | None]:
    try:
        with urlopen(Request(url, headers={"User-Agent": UA}), timeout=180) as r:
            return r.status, r.read(), None
    except HTTPError as e:
        return e.code, e.read() or b"", str(e)
    except (URLError, TimeoutError, OSError) as e:
        return 0, b"", str(getattr(e, "reason", e))


def load_manifest(root: Path) -> dict:
    p = paths(root)["manifest"]
    return json.loads(p.read_text()) if p.is_file() else {
        "tool": "usgs-field-measurements", "last_success": None, "last_attempt": None, "stations": {}, "files": [], "skipped": []}


def save_manifest(root: Path, m: dict) -> None:
    p = paths(root)["manifest"]
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(m, indent=1) + "\n")
    tmp.replace(p)


def collect(root: Path = ROOT, stations=None, pause: float = 1.0) -> int:
    P, m = paths(root), load_manifest(root)
    for st in stations or STATIONS:
        url = BASE + "?" + urlencode({"f": "json", "monitoring_location_id": f"USGS-{st}", "limit": str(LIMIT)})
        pages, page_meta = [], []
        while url:
            status, body, err = fetch(url)
            m["last_attempt"] = utcnow()
            if status != 200:
                print(f"SKIPPED — usgs_field_measurements: {url} unreachable ({err or f'HTTP {status}'})", flush=True)
                m["skipped"] = (m.get("skipped", []) + [{"url": url, "reason": err or f"HTTP {status}", "at": m["last_attempt"]}])[-50:]
                save_manifest(root, m)
                pages = None
                break
            try:
                payload = json.loads(body)
            except json.JSONDecodeError as e:
                raise ValueError(f"{url}:1: response is not JSON ({e})") from None
            pages.append(body)
            page_meta.append({"url": url, "sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body),
                              "features": len(payload.get("features", []))})
            url = next((l.get("href") for l in payload.get("links", []) if l.get("rel") == "next"), None)
            if url:
                time.sleep(pause)
        if pages is None:
            continue
        stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        rd, cd = P["raw"] / st, P["cap"] / st
        rd.mkdir(parents=True, exist_ok=True)
        cd.mkdir(parents=True, exist_ok=True)
        combined = b"[" + b",".join(pages) + b"]"
        raw = rd / f"{stamp}.json"
        raw.write_bytes(combined)
        meta = {"retrieved_at": utcnow(), "pages": page_meta, "sha256": hashlib.sha256(combined).hexdigest(), "bytes": len(combined)}
        raw.with_suffix(".meta.json").write_text(json.dumps(meta, indent=1) + "\n")
        cap = cd / "field-measurements.json.gz"
        cap.write_bytes(gzip.compress(combined, compresslevel=9, mtime=0))
        m["stations"][st] = {**meta, "raw_path": str(raw.relative_to(root)), "capture_path": str(cap.relative_to(root)),
                             "capture_sha256": hashlib.sha256(cap.read_bytes()).hexdigest()}
        save_manifest(root, m)
        print(f"usgs_field_measurements {st}: {sum(p['features'] for p in page_meta)} measurements in {len(pages)} page(s)", flush=True)
        time.sleep(pause)
    return 0


def normalize(root: Path = ROOT, stations=None) -> int:
    P, m = paths(root), load_manifest(root)
    P["history"].mkdir(parents=True, exist_ok=True)
    files = [f for f in m.get("files", []) if f.get("station") not in set(stations or STATIONS)]
    for st in stations or STATIONS:
        rec = m["stations"].get(st)
        if not rec:
            print(f"SKIPPED — usgs_field_measurements normalize: no capture for {st}", flush=True)
            continue
        cap = root / rec["capture_path"]
        data = gzip.decompress(cap.read_bytes())
        rows, non_numeric = [], 0
        for page_no, page in enumerate(json.loads(data), 1):
            for feat in page.get("features", []):
                p = feat.get("properties", {})
                if p.get("monitoring_location_id") != f"USGS-{st}":
                    raise ValueError(f"{cap}: page {page_no} feature {feat.get('id')} belongs to {p.get('monitoring_location_id')}")
                raw = p.get("value")
                try:
                    v = float(raw)
                except (TypeError, ValueError):
                    non_numeric += 1
                    v = None
                date = (p.get("time") or "")[:10]
                rows.append([date, p.get("parameter_code"), "" if v is None else v, p.get("unit_of_measure") or "",
                             feat.get("id") or p.get("field_visit_id") or "", p.get("qualifier") or ""])
        rows.sort(key=lambda r: (r[0], r[1], r[4]))
        text = "date,parameter,value,unit,measurement_id,qualifier\n" + "".join(
            ",".join(str(c).replace(",", ";") for c in r) + "\n" for r in rows)
        out = P["history"] / f"{st}-field-measurements.csv"
        out.write_text(text)
        note = None if rows else "the provider returned no field measurements for this station"
        files.append({"station": st, "path": str(out.relative_to(root)), "sha256": hashlib.sha256(text.encode()).hexdigest(),
                      "rows": len(rows), "first": rows[0][0] if rows else None, "last": rows[-1][0] if rows else None,
                      "non_numeric_values": non_numeric, "note": note})
        print(f"usgs_field_measurements normalize {st}: {len(rows)} rows" + (f" ({note})" if note else ""), flush=True)
    m.update(files=files, last_success=utcnow())
    save_manifest(root, m)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["collect", "normalize"])
    ap.add_argument("--stations", nargs="+")
    ap.add_argument("--pause-seconds", type=float, default=1.0)
    a = ap.parse_args(argv)
    return collect(stations=a.stations, pause=a.pause_seconds) if a.cmd == "collect" else normalize(stations=a.stations)


if __name__ == "__main__":
    sys.exit(main())
