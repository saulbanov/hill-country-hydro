#!/usr/bin/env python3
"""Preserve NOAA nClimDiv monthly county and climate-division series. No assessment.

Acquisition (``collect``): reads NOAA's ``procdate.txt``. When that date equals the manifest's
``noaa_file_date`` and every expected history CSV exists, prints ``UNCHANGED`` and writes nothing.
Otherwise it downloads each element file once (one request per file per run) and
``county-to-climdivs.txt``, and writes before anything parses:

* ``data/raw/nclimdiv/<date>/<file>`` the verbatim bytes plus ``.meta.json`` (url, retrieved_at,
  status, sha256, bytes); Git-ignored like all raw.
* ``data/captures/noaa-nclimdiv/<file>.tx-nm.gz`` the lines for NCDC state codes 41 (Texas) and 29
  (New Mexico), gzipped and versioned; its sha256 and the full file's sha256 are in the manifest.

A provider failure prints ``SKIPPED — nclimdiv: <url> unreachable (<reason>)``, records it in the
manifest and exits 0, so the daily chain continues.

Normalization (``normalize``): for each county in ``data/noaa-counties.json`` writes
``data/history/climdiv-<FIPS>-<element>-monthly.csv`` (``month,value,raw_value,unit,source_file``).
County FIPS map to NCDC ids through NOAA's own ``county-to-climdivs.txt``. NOAA's missing-value
sentinels write no row (missing is never zero). A short or non-numeric record stops with
``<file>:<line>`` and exits nonzero. Unchanged inputs rewrite nothing.
"""
from __future__ import annotations

import argparse
import datetime as dt
import gzip
import hashlib
import json
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://www.ncei.noaa.gov/monitoring-content/data/us/climdiv/monthly/current"
UA = "hill-country-hydro/0.1 nclimdiv (+saulbanov/hill-country-hydro)"
STATES = {"41": "48", "29": "35"}  # NCDC state code -> FIPS state code (Texas, New Mexico)
# element file code -> (history name, unit, kind, missing sentinels)
COUNTY_ELEMENTS = {
    "pcpncy": ("pcpn", "in", "county", {-9.99}),
    "tmaxcy": ("tmax", "degF", "county", {-99.99, -99.9}),
    "tmincy": ("tmin", "degF", "county", {-99.99, -99.9}),
    "tmpccy": ("tmpc", "degF", "county", {-99.99, -99.9}),
}
# Drought intake (Tier 1, Saul 2026-10-08): collected with no consumer yet. County Palmer indices and
# climate-division standardized precipitation indices; NCDC ids map to FIPS, the NCDC id kept in a column.
DROUGHT_COUNTY = {code: (code[:4], "index", "county_drought", {-99.99}) for code in ("pdsicy", "phdicy", "pmdicy", "zndxcy")}
DIVISION = {code: (code[:4], "index", "division", {-99.99})
            for code in ("pdsidv", "sp01dv", "sp02dv", "sp03dv", "sp06dv", "sp09dv", "sp12dv", "sp24dv")}
ELEMENTS = {**COUNTY_ELEMENTS, **DROUGHT_COUNTY, **DIVISION}
MAPPING_FILE = "county-to-climdivs.txt"


def paths(root: Path) -> dict:
    return {"raw": root / "data/raw/nclimdiv", "cap": root / "data/captures/noaa-nclimdiv",
            "history": root / "data/history", "manifest": root / "data/model/nclimdiv-manifest.json",
            "counties": root / "data/noaa-counties.json"}


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
    if p.is_file():
        return json.loads(p.read_text())
    return {"tool": "nclimdiv", "noaa_file_date": None, "last_success": None, "last_attempt": None,
            "raw": [], "files": [], "skipped": [], "normalized_from": None}


def save_manifest(root: Path, m: dict) -> None:
    p = paths(root)["manifest"]
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(m, indent=1) + "\n")
    tmp.replace(p)


def counties(root: Path) -> list[str]:
    p = paths(root)["counties"]
    if not p.is_file():
        raise SystemExit(f"{p}: missing county list")
    return json.loads(p.read_text())["counties"]


def division_ids(root: Path) -> list[str] | None:
    """Climate divisions of the listed counties, from the captured NOAA mapping; None before it exists."""
    m = load_manifest(root)
    rec = next((r for r in m.get("raw", []) if r["file"] == MAPPING_FILE and r.get("noaa_file_date") == m.get("noaa_file_date")), None)
    if not rec or not (root / rec["capture_path"]).is_file():
        return None
    mapping = fips_to_ncdc(read_capture(root, rec), MAPPING_FILE)
    return sorted({mapping[f]["climdiv"] for f in counties(root) if f in mapping})


def expected_outputs(root: Path, elements=None) -> list[Path]:
    h = paths(root)["history"]
    out, divs = [], None
    for code, (name, _u, kind, _s) in (elements or ELEMENTS).items():
        if kind in ("county", "county_drought"):
            out += [h / f"climdiv-{f}-{name}-monthly.csv" for f in counties(root)]
        elif kind == "division":
            divs = division_ids(root) if divs is None else divs
            out += [h / f"climdiv-div{d}-{name}-monthly.csv" for d in divs] if divs else [h / "climdiv-div-pending"]
    return out


def skip(root: Path, m: dict, url: str, reason: str) -> int:
    print(f"SKIPPED — nclimdiv: {url} unreachable ({reason})", flush=True)
    m["last_attempt"] = utcnow()
    m["skipped"] = (m.get("skipped", []) + [{"url": url, "reason": reason, "at": m["last_attempt"]}])[-50:]
    save_manifest(root, m)
    return 0


def tx_nm_lines(body: bytes, mapping: bool) -> bytes:
    keep = []
    for line in body.splitlines(keepends=True):
        s = line.decode("ascii", "replace")
        if mapping:
            if s[:2] in STATES.values() or not s[:1].isdigit():
                keep.append(line)
        elif s[:2] in STATES:
            keep.append(line)
    return b"".join(keep)


def collect(root: Path = ROOT, elements=None) -> int:
    P, m = paths(root), load_manifest(root)
    elements = elements or ELEMENTS
    status, body, err = fetch(f"{BASE}/procdate.txt")
    if status != 200 or not body.strip():
        return skip(root, m, f"{BASE}/procdate.txt", err or f"HTTP {status}")
    date = body.decode().strip()
    if not (len(date) == 8 and date.isdigit()):
        raise ValueError(f"{BASE}/procdate.txt:1: expected YYYYMMDD, got {date[:40]!r}")
    have = {r["file"] for r in m.get("raw", []) if r.get("noaa_file_date") == date}
    wanted = [f"climdiv-{c}-v1.0.0-{date}" for c in elements] + [MAPPING_FILE]
    if m.get("noaa_file_date") == date and set(wanted) <= have | {MAPPING_FILE} and all(p.is_file() for p in expected_outputs(root, elements)):
        print(f"UNCHANGED nclimdiv: NOAA file date {date}", flush=True)
        return 0
    raw_dir = P["raw"] / date
    raw_dir.mkdir(parents=True, exist_ok=True)
    P["cap"].mkdir(parents=True, exist_ok=True)
    records = [r for r in m.get("raw", []) if r.get("noaa_file_date") == date]
    for name in wanted:
        if name in {r["file"] for r in records} and (root / next(r["capture_path"] for r in records if r["file"] == name)).is_file():
            continue
        url = f"{BASE}/{name}"
        status, body, err = fetch(url)
        if status != 200 or not body:
            return skip(root, m, url, err or f"HTTP {status}")
        raw = raw_dir / name
        raw.write_bytes(body)
        meta = {"url": url, "retrieved_at": utcnow(), "status": status, "sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body)}
        raw.with_name(name + ".meta.json").write_text(json.dumps(meta, indent=1) + "\n")
        sub = tx_nm_lines(body, name == MAPPING_FILE)
        cap = P["cap"] / f"{name}.tx-nm.gz"
        with gzip.open(cap, "wb", compresslevel=9) as z:
            z.write(sub)
        for old in P["cap"].glob(f"{name.rsplit('-', 1)[0]}-*.tx-nm.gz") if name != MAPPING_FILE else []:
            if old != cap:
                old.unlink()  # one versioned capture per element; raw copies stay under data/raw
        records = [r for r in records if r["file"] != name] + [{
            "file": name, "noaa_file_date": date, **meta, "raw_path": str(raw.relative_to(root)),
            "capture_path": str(cap.relative_to(root)), "capture_sha256": hashlib.sha256(cap.read_bytes()).hexdigest(),
            "capture_lines": sub.count(b"\n"), "capture_scope": "NCDC states 41 (TX) and 29 (NM)"}]
        n_lines = sub.count(b"\n")
        print(f"nclimdiv {name}: {status} {len(body)} bytes; {n_lines} TX/NM lines captured", flush=True)
    m.update(noaa_file_date=date, last_attempt=utcnow(), raw=records)
    save_manifest(root, m)
    return 0


def read_capture(root: Path, rec: dict) -> list[str]:
    path = root / rec["capture_path"]
    if not path.is_file():
        raise FileNotFoundError(f"{path}: capture named in the manifest is missing")
    if hashlib.sha256(path.read_bytes()).hexdigest() != rec["capture_sha256"]:
        raise ValueError(f"{path}: sha256 does not match the manifest")
    return gzip.decompress(path.read_bytes()).decode("ascii", "replace").splitlines()


def fips_to_ncdc(lines: list[str], source: str) -> dict[str, dict]:
    out = {}
    for i, line in enumerate(lines, 1):
        parts = line.split()
        if len(parts) == 3 and parts[0].isdigit() and len(parts[0]) == 5:
            if not (parts[1].isdigit() and len(parts[1]) == 5 and parts[2].isdigit() and len(parts[2]) == 4):
                raise ValueError(f"{source}:{i}: expected POSTAL_FIPS NCDC_FIPS CLIMDIV, got {line[:60]!r}")
            out[parts[0]] = {"ncdc": parts[1], "climdiv": parts[2]}
    return out


def parse_county_lines(lines: list[str], source: str, sentinels: set, wanted_ncdc: set) -> dict[str, list]:
    """{ncdc_id: [(YYYY-MM, value_or_None, raw_text)]} for the wanted NCDC county ids."""
    out: dict[str, list] = {}
    for i, line in enumerate(lines, 1):
        if not line.strip():
            continue
        if len(line.rstrip("\n")) < 95:
            raise ValueError(f"{source}:{i}: record is {len(line)} characters, expected 95 (truncated file?)")
        head = line[:11]
        if not head.isdigit():
            raise ValueError(f"{source}:{i}: record id {head!r} is not numeric")
        ncdc, year = head[:5], int(head[7:11])
        if ncdc not in wanted_ncdc:
            continue
        rows = out.setdefault(ncdc, [])
        for mth in range(12):
            text = line[11 + 7 * mth: 18 + 7 * mth]
            try:
                v = float(text)
            except ValueError:
                raise ValueError(f"{source}:{i}: month {mth + 1} value {text!r} is not a number") from None
            rows.append((f"{year:04d}-{mth + 1:02d}", None if round(v, 2) in sentinels else v, text.strip()))
    return out


def parse_division_lines(lines: list[str], source: str, sentinels: set, known: set, wanted: set) -> dict[str, list]:
    """Division records: state(2) division(2) element(2) year(4), then 12 values of 7 characters.
    A division id not in NOAA's county-to-division mapping stops with <file>:<line>."""
    out: dict[str, list] = {}
    for i, line in enumerate(lines, 1):
        if not line.strip():
            continue
        if len(line.rstrip("\n")) < 94:
            raise ValueError(f"{source}:{i}: record is {len(line)} characters, expected 94 (truncated file?)")
        head = line[:10]
        if not head.isdigit():
            raise ValueError(f"{source}:{i}: record id {head!r} is not numeric")
        div, year = head[:4], int(head[6:10])
        if div not in known:
            raise ValueError(f"{source}:{i}: climate division {div} is not in NOAA {MAPPING_FILE}")
        if div not in wanted:
            continue
        rows = out.setdefault(div, [])
        for mth in range(12):
            text = line[10 + 7 * mth: 17 + 7 * mth]
            try:
                v = float(text)
            except ValueError:
                raise ValueError(f"{source}:{i}: month {mth + 1} value {text!r} is not a number") from None
            rows.append((f"{year:04d}-{mth + 1:02d}", None if round(v, 2) in sentinels else v, text.strip()))
    return out


def write_csv(path: Path, header: list[str], rows: list[list]) -> dict:
    text = ",".join(header) + "\n" + "".join(",".join("" if c is None else str(c) for c in r) + "\n" for r in rows)
    data = text.encode()
    if not (path.is_file() and path.read_bytes() == data):
        path.write_bytes(data)
    return {"path": str(path), "sha256": hashlib.sha256(data).hexdigest(), "rows": len(rows),
            "first": rows[0][0] if rows else None, "last": rows[-1][0] if rows else None}


def normalize(root: Path = ROOT, elements=None) -> int:
    P, m = paths(root), load_manifest(root)
    elements = elements or ELEMENTS
    date = m.get("noaa_file_date")
    if not date:
        print("SKIPPED — nclimdiv normalize: nothing collected yet", flush=True)
        return 0
    if m.get("normalized_from") == date and all(p.is_file() for p in expected_outputs(root, elements)):
        print(f"UNCHANGED nclimdiv normalize: outputs already built from NOAA file date {date}", flush=True)
        return 0
    recs = {r["file"]: r for r in m["raw"] if r.get("noaa_file_date") == date}
    mapping = fips_to_ncdc(read_capture(root, recs[MAPPING_FILE]), MAPPING_FILE)
    wanted = counties(root)
    unknown = [f for f in wanted if f not in mapping]
    if unknown:
        raise ValueError(f"{P['counties']}: county FIPS {unknown} not in NOAA {MAPPING_FILE}")
    P["history"].mkdir(parents=True, exist_ok=True)
    files = []
    by_ncdc = {v["ncdc"]: k for k, v in mapping.items()}
    divisions = sorted({mapping[f]["climdiv"] for f in wanted})
    for code, (name, unit, kind, sentinels) in elements.items():
        fname = f"climdiv-{code}-v1.0.0-{date}"
        lines = read_capture(root, recs[fname])
        if kind == "division":
            parsed = parse_division_lines(lines, fname, sentinels, {v["climdiv"] for v in mapping.values()}, set(divisions))
            for d in divisions:
                rows = [[mo, v, raw, unit, d, fname] for mo, v, raw in parsed.get(d, []) if v is not None]
                if not rows:
                    raise ValueError(f"{fname}: no records for climate division {d}")
                info = write_csv(P["history"] / f"climdiv-div{d}-{name}-monthly.csv",
                                 ["month", "value", "raw_value", "unit", "ncdc_id", "source_file"], rows)
                info["path"] = str(Path(info["path"]).relative_to(root))
                files.append(info)
            continue
        if kind == "county_drought":
            for i, line in enumerate(lines, 1):  # every county line must map to a FIPS code
                if line.strip() and line[:5].isdigit() and line[:5] not in by_ncdc:
                    raise ValueError(f"{fname}:{i}: NCDC county id {line[:5]} is not in NOAA {MAPPING_FILE}")
        parsed = parse_county_lines(lines, fname, sentinels, {mapping[f]["ncdc"] for f in wanted})
        for f in wanted:
            ncdc = mapping[f]["ncdc"]
            rows = [[mo, v, raw, unit, fname] for mo, v, raw in parsed.get(ncdc, []) if v is not None]
            if not rows:
                raise ValueError(f"{fname}: no records for county {f} (NCDC {ncdc})")
            header = ["month", "value", "raw_value", "unit", "source_file"]
            if kind == "county_drought":
                rows = [[mo, v, raw, u, ncdc, src] for mo, v, raw, u, src in rows]
                header = ["month", "value", "raw_value", "unit", "ncdc_id", "source_file"]
            info = write_csv(P["history"] / f"climdiv-{f}-{name}-monthly.csv", header, rows)
            info["path"] = str(Path(info["path"]).relative_to(root))
            files.append(info)
    m.update(files=files, normalized_from=date, last_success=utcnow())
    save_manifest(root, m)
    print(f"nclimdiv normalize: {len(files)} county series from NOAA file date {date}", flush=True)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["collect", "normalize"])
    a = ap.parse_args(argv)
    return collect() if a.cmd == "collect" else normalize()


if __name__ == "__main__":
    sys.exit(main())
