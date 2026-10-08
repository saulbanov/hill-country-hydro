#!/usr/bin/env python3
"""Preserve U.S. Drought Monitor county statistics: the weekly share of each county's area in each
category, D0 (abnormally dry) to D4 (exceptional), from January 2000. Intake only: no consumer reads
this layer yet (Saul, 2026-10-08), and nothing here interprets it.

Acquisition (``collect``, daily; the map changes weekly): for a county with no history, one request
from 2000-01-01 to today. Otherwise one probe per county covering the last 21 days; when the probe
holds no map newer than the stored one, nothing is written and the run prints ``UNCHANGED``. A new map
keeps the probe itself as the capture, so no second request is made. Responses land verbatim in
``data/raw/usdm/<FIPS>/`` (Git-ignored) and gzipped in ``data/captures/usdm/<FIPS>/`` (versioned). A
provider failure prints ``SKIPPED — usdm: <url> unreachable (<reason>)`` and exits 0.

Normalization (``normalize``): ``data/history/usdm-<FIPS>-weekly.csv`` with
``map_date,none,d0,d1,d2,d3,d4,valid_start,valid_end,statistic_type,source_file``. The d-values are the
provider's cumulative percent of area, kept as given. One row per weekly map; a week the provider did
not return has no row. Later captures replace earlier ones for the same map date.
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
API = "https://usdmdataservices.unl.edu/api/CountyStatistics/GetDroughtSeverityStatisticsByAreaPercent"
UA = "hill-country-hydro/0.1 usdm (+saulbanov/hill-country-hydro)"
FIRST = dt.date(2000, 1, 1)
PROBE_DAYS = 21
FIELDS = ["mapDate", "none", "d0", "d1", "d2", "d3", "d4", "validStart", "validEnd", "statisticFormatID"]


def paths(root: Path) -> dict:
    return {"raw": root / "data/raw/usdm", "cap": root / "data/captures/usdm", "history": root / "data/history",
            "manifest": root / "data/model/usdm-manifest.json", "counties": root / "data/noaa-counties.json"}


def utcnow() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def today() -> dt.date:
    return dt.datetime.now(dt.timezone.utc).date()


def fetch(url: str) -> tuple[int, bytes, str | None]:
    try:
        with urlopen(Request(url, headers={"User-Agent": UA, "Accept": "application/json"}), timeout=120) as r:
            return r.status, r.read(), None
    except HTTPError as e:
        return e.code, e.read() or b"", str(e)
    except (URLError, TimeoutError, OSError) as e:
        return 0, b"", str(getattr(e, "reason", e))


def mdy(d: dt.date) -> str:
    return f"{d.month}/{d.day}/{d.year}"


def url_for(fips: str, start: dt.date, end: dt.date) -> str:
    return API + "?" + urlencode({"aoi": fips, "startdate": mdy(start), "enddate": mdy(end), "statisticsType": "1"})


def load_manifest(root: Path) -> dict:
    p = paths(root)["manifest"]
    return json.loads(p.read_text()) if p.is_file() else {
        "tool": "usdm", "last_success": None, "last_attempt": None, "counties": {}, "files": [], "skipped": []}


def save_manifest(root: Path, m: dict) -> None:
    p = paths(root)["manifest"]
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(m, indent=1) + "\n")
    tmp.replace(p)


def parse(body: bytes, source: str) -> list[dict]:
    try:
        rows = json.loads(body)
    except json.JSONDecodeError as e:
        raise ValueError(f"{source}:1: response is not JSON ({e})") from None
    if not isinstance(rows, list):
        raise ValueError(f"{source}:1: expected a JSON list of weekly rows")
    for i, r in enumerate(rows, 1):
        missing = [k for k in FIELDS if k not in r]
        if missing:
            raise ValueError(f"{source}: row {i} lacks {missing}")
    return rows


def counties(root: Path) -> list[str]:
    return json.loads(paths(root)["counties"].read_text())["counties"]


def collect(root: Path = ROOT, pause: float = 0.5, only=None) -> int:
    P, m = paths(root), load_manifest(root)
    new, unchanged, skipped = 0, 0, 0
    end = today()
    changed = False
    for fips in only or counties(root):
        c = m["counties"].get(fips, {})
        start = FIRST if not c.get("last_map_date") else end - dt.timedelta(days=PROBE_DAYS)
        url = url_for(fips, start, end)
        status, body, err = fetch(url)
        time.sleep(pause)
        if status != 200:
            print(f"SKIPPED — usdm: {url} unreachable ({err or f'HTTP {status}'})", flush=True)
            m["skipped"] = (m.get("skipped", []) + [{"url": url, "reason": err or f"HTTP {status}", "at": utcnow()}])[-100:]
            skipped += 1
            changed = True
            continue
        rows = parse(body, url)
        latest = max((r["mapDate"][:10] for r in rows), default=None)
        if c.get("last_map_date") and (latest is None or latest <= c["last_map_date"]):
            unchanged += 1
            continue
        stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        rd, cd = P["raw"] / fips, P["cap"] / fips
        rd.mkdir(parents=True, exist_ok=True)
        cd.mkdir(parents=True, exist_ok=True)
        sha = hashlib.sha256(body).hexdigest()
        raw = rd / f"{stamp}-{sha[:10]}.json"  # the hash keeps two captures in one second apart
        raw.write_bytes(body)
        meta = {"url": url, "retrieved_at": utcnow(), "status": status, "sha256": sha, "bytes": len(body), "rows": len(rows)}
        raw.with_suffix(".meta.json").write_text(json.dumps(meta, indent=1) + "\n")
        cap = cd / f"{stamp}-{sha[:10]}.json.gz"
        cap.write_bytes(gzip.compress(body, compresslevel=9, mtime=0))
        c.setdefault("captures", []).append({**meta, "raw_path": str(raw.relative_to(root)), "capture_path": str(cap.relative_to(root)),
                                             "capture_sha256": hashlib.sha256(cap.read_bytes()).hexdigest()})
        c["last_map_date"] = latest
        m["counties"][fips] = c
        new += 1
        changed = True
    if not changed:
        print(f"UNCHANGED usdm: no new map for {unchanged} counties", flush=True)
        return 0
    m["last_attempt"] = utcnow()
    if new:
        m["last_success"] = m["last_attempt"]
    save_manifest(root, m)
    print(f"usdm collect: {new} counties with a new map, {unchanged} unchanged, {skipped} skipped", flush=True)
    return 0


def normalize(root: Path = ROOT) -> int:
    P, m = paths(root), load_manifest(root)
    fingerprint = hashlib.sha256(json.dumps({f: [x["capture_sha256"] for x in c.get("captures", [])]
                                             for f, c in sorted(m["counties"].items())}).encode()).hexdigest()
    if m.get("normalized_from") == fingerprint and all((root / f["path"]).is_file() for f in m.get("files", [])):
        print("UNCHANGED usdm normalize", flush=True)
        return 0
    P["history"].mkdir(parents=True, exist_ok=True)
    files = []
    for fips, c in sorted(m["counties"].items()):
        weeks = {}
        for cap in c.get("captures", []):
            path = root / cap["capture_path"]
            data = path.read_bytes()
            if hashlib.sha256(data).hexdigest() != cap["capture_sha256"]:
                raise ValueError(f"{path}: sha256 does not match the manifest")
            for r in parse(gzip.decompress(data), cap["capture_path"]):
                weeks[r["mapDate"][:10]] = (r, cap["capture_path"])
        rows = []
        for d in sorted(weeks):
            r, src = weeks[d]
            rows.append([d, r["none"], r["d0"], r["d1"], r["d2"], r["d3"], r["d4"], r["validStart"][:10], r["validEnd"][:10],
                         r["statisticFormatID"], src])
        text = "map_date,none,d0,d1,d2,d3,d4,valid_start,valid_end,statistic_type,source_file\n" + "".join(
            ",".join("" if v is None else str(v) for v in row) + "\n" for row in rows)
        out = P["history"] / f"usdm-{fips}-weekly.csv"
        if not (out.is_file() and out.read_text() == text):
            out.write_text(text)
        files.append({"path": str(out.relative_to(root)), "sha256": hashlib.sha256(text.encode()).hexdigest(), "rows": len(rows),
                      "first": rows[0][0] if rows else None, "last": rows[-1][0] if rows else None})
    m.update(files=files, normalized_from=fingerprint, last_success=m.get("last_success") or utcnow())
    save_manifest(root, m)
    print(f"usdm normalize: {len(files)} counties", flush=True)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["collect", "normalize"])
    ap.add_argument("--counties", nargs="+")
    a = ap.parse_args(argv)
    return collect(only=a.counties) if a.cmd == "collect" else normalize()


if __name__ == "__main__":
    sys.exit(main())
