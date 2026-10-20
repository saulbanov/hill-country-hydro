#!/usr/bin/env python3
"""Preserve NOAA GHCN-Daily station records (rain and air temperature) for long stations near the
springs. No assessment.

Acquisition (``collect``): one request per station for NOAA's per-station file
``by_station/<STATION>.csv.gz`` (columns ID, YYYYMMDD, ELEMENT, VALUE, MFLAG, QFLAG, SFLAG, OBS-TIME).
Bytes identical to the last capture print ``UNCHANGED`` and write nothing. Otherwise the verbatim
bytes go to ``data/raw/ghcn-daily/<STATION>/`` with ``.meta.json`` (Git-ignored), and the PRCP, TMAX
and TMIN lines go gzipped to ``data/captures/noaa-ghcn-daily/<STATION>.csv.gz`` (versioned, one per
station). A provider failure prints ``SKIPPED — ghcn_daily: <url> unreachable (<reason>)`` and
exits 0.

Normalization (``normalize``): ``data/history/ghcn-<STATION>-<PRCP|TMAX|TMIN>-daily.csv`` with
``date,value,raw_value,unit,mflag,qflag,sflag``. PRCP converts tenths of millimetres to inches,
TMAX and TMIN tenths of degrees Celsius to degrees Fahrenheit. Quality-flagged values are KEPT with
their QFLAG; deciding to drop them is analysis. -9999 and absent days write no row. A malformed line
stops with ``<file>:<line>``.
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
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://www.ncei.noaa.gov/pub/data/ghcn/daily/by_station"
UA = "hill-country-hydro/0.1 ghcn_daily (+saulbanov/hill-country-hydro)"
# Long records near the springs (inventory checked 2026-10-08): San Marcos, Fischer's Store, Austin Camp
# Mabry, Austin Bergstrom, Randolph AFB, Bulverde.
STATIONS = ["USC00417983", "USC00413156", "USW00013958", "USW00013904", "USW00012911", "USC00411215"]
ELEMENTS = {"PRCP": "in", "TMAX": "degF", "TMIN": "degF"}


def paths(root: Path) -> dict:
    return {"raw": root / "data/raw/ghcn-daily", "cap": root / "data/captures/noaa-ghcn-daily",
            "history": root / "data/history", "manifest": root / "data/model/ghcn-daily-manifest.json"}


def utcnow() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def fetch(url: str) -> tuple[int, bytes, str | None]:
    try:
        with urlopen(Request(url, headers={"User-Agent": UA}), timeout=300) as r:
            return r.status, r.read(), None
    except HTTPError as e:
        return e.code, e.read() or b"", str(e)
    except (URLError, TimeoutError, OSError) as e:
        return 0, b"", str(getattr(e, "reason", e))


def load_manifest(root: Path) -> dict:
    p = paths(root)["manifest"]
    return json.loads(p.read_text()) if p.is_file() else {
        "tool": "ghcn-daily", "last_success": None, "last_attempt": None, "stations": {}, "files": [], "skipped": []}


def save_manifest(root: Path, m: dict) -> None:
    p = paths(root)["manifest"]
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(m, indent=1) + "\n")
    tmp.replace(p)


def collect(root: Path = ROOT, stations=None, pause: float = 1.0) -> int:
    P, m = paths(root), load_manifest(root)
    for st in stations or STATIONS:
        url = f"{BASE}/{st}.csv.gz"
        status, body, err = fetch(url)
        m["last_attempt"] = utcnow()
        if status != 200 or not body:
            print(f"SKIPPED — ghcn_daily: {url} unreachable ({err or f'HTTP {status}'})", flush=True)
            m["skipped"] = (m.get("skipped", []) + [{"url": url, "reason": err or f"HTTP {status}", "at": m["last_attempt"]}])[-50:]
            save_manifest(root, m)
            continue
        sha = hashlib.sha256(body).hexdigest()
        prev = m["stations"].get(st, {})
        if prev.get("sha256") == sha and (root / prev.get("capture_path", "missing")).is_file():
            print(f"UNCHANGED ghcn_daily {st}: same bytes as {prev['retrieved_at']}", flush=True)
            continue
        at = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        rd = P["raw"] / st
        rd.mkdir(parents=True, exist_ok=True)
        raw = rd / f"{at}.csv.gz"
        raw.write_bytes(body)
        meta = {"url": url, "retrieved_at": utcnow(), "status": status, "sha256": sha, "bytes": len(body)}
        raw.with_suffix(".meta.json").write_text(json.dumps(meta, indent=1) + "\n")
        try:
            text = gzip.decompress(body).decode("ascii", "replace")
        except (OSError, EOFError) as e:
            raise ValueError(f"{raw}:1: not a readable gzip ({e})") from None
        keep = "".join(l + "\n" for l in text.splitlines() if l.split(",")[2:3] and l.split(",")[2] in ELEMENTS)
        P["cap"].mkdir(parents=True, exist_ok=True)
        cap = P["cap"] / f"{st}.csv.gz"
        with gzip.open(cap, "wb", compresslevel=9) as z:
            z.write(keep.encode())
        m["stations"][st] = {**meta, "raw_path": str(raw.relative_to(root)), "capture_path": str(cap.relative_to(root)),
                             "capture_sha256": hashlib.sha256(cap.read_bytes()).hexdigest(),
                             "capture_scope": "PRCP, TMAX and TMIN lines of the provider file"}
        save_manifest(root, m)
        print(f"ghcn_daily {st}: {status} {len(body)} bytes", flush=True)
        time.sleep(pause)
    return 0


def parse(lines: list[str], source: str) -> dict[str, list]:
    out = {e: [] for e in ELEMENTS}
    for i, line in enumerate(lines, 1):
        if not line.strip():
            continue
        f = line.split(",")
        if len(f) < 7:
            raise ValueError(f"{source}:{i}: expected 8 comma-separated fields, got {len(f)}")
        el = f[2]
        if el not in ELEMENTS:
            continue
        d, raw = f[1], f[3]
        if not (len(d) == 8 and d.isdigit()):
            raise ValueError(f"{source}:{i}: date {d!r} is not YYYYMMDD")
        try:
            v = int(raw)
        except ValueError:
            raise ValueError(f"{source}:{i}: value {raw!r} is not an integer") from None
        if v == -9999:
            continue
        value = round(v / 254.0, 3) if el == "PRCP" else round(v / 10.0 * 9 / 5 + 32, 2)
        out[el].append([f"{d[:4]}-{d[4:6]}-{d[6:]}", value, raw, ELEMENTS[el], f[4], f[5], f[6]])
    for rows in out.values():
        rows.sort(key=lambda r: r[0])
    return out


def normalize(root: Path = ROOT, stations=None) -> int:
    P, m = paths(root), load_manifest(root)
    P["history"].mkdir(parents=True, exist_ok=True)
    files = [f for f in m.get("files", []) if f.get("station") not in set(stations or STATIONS)]
    wrote = 0
    for st in stations or STATIONS:
        rec = m["stations"].get(st)
        if not rec:
            print(f"SKIPPED — ghcn_daily normalize: no capture for {st}", flush=True)
            continue
        cap = root / rec["capture_path"]
        data = cap.read_bytes()
        if hashlib.sha256(data).hexdigest() != rec["capture_sha256"]:
            raise ValueError(f"{cap}: sha256 does not match the manifest")
        outs = {e: P["history"] / f"ghcn-{st}-{e}-daily.csv" for e in ELEMENTS}
        if rec.get("normalized_sha256") == rec["capture_sha256"] and all(p.is_file() for p in outs.values()):
            print(f"UNCHANGED ghcn_daily normalize {st}", flush=True)
            files += [f for f in m.get("files", []) if f.get("station") == st]
            continue
        parsed = parse(gzip.decompress(data).decode("ascii", "replace").splitlines(), str(cap.relative_to(root)))
        for el, rows in parsed.items():
            text = "date,value,raw_value,unit,mflag,qflag,sflag\n" + "".join(",".join(str(c) for c in r) + "\n" for r in rows)
            outs[el].write_text(text)
            files.append({"station": st, "element": el, "path": str(outs[el].relative_to(root)),
                          "sha256": hashlib.sha256(text.encode()).hexdigest(), "rows": len(rows),
                          "first": rows[0][0] if rows else None, "last": rows[-1][0] if rows else None,
                          "quality_flagged_rows": sum(1 for r in rows if r[5])})
            wrote += 1
        rec["normalized_sha256"] = rec["capture_sha256"]
    m.update(files=files, last_success=utcnow())
    save_manifest(root, m)
    print(f"ghcn_daily normalize: {wrote} series written", flush=True)
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
