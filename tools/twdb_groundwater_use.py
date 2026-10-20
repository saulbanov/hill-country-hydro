#!/usr/bin/env python3
"""Preserve TWDB records of groundwater use: new wells drilled per year (Submitted Drillers Reports)
and, when TWDB offers it as a file, groundwater pumpage. No assessment.

Acquisition (``collect``, first Sunday of each month): one request for TWDB's statewide
``SDRDownload.zip``. Identical bytes print ``UNCHANGED``. The zip holds owner and driller names and
addresses, so it stays under ``data/raw/twdb-sdr/`` (Git-ignored) with ``.meta.json``; the versioned
capture ``data/captures/twdb-sdr/welldata-extract.tsv.gz`` keeps only the columns listed in
EXTRACT_COLUMNS for wells in the counties of ``data/noaa-counties.json``. A provider failure prints
``SKIPPED — twdb_groundwater_use: <url> unreachable (<reason>)`` and exits 0.

Normalization (``normalize``): ``data/history/twdb-wells-drilled-<FIPS>-annual.csv`` with
``year,aquifer,use,count,source_file`` plus ``type_of_work``: one row per year, proposed use and type
of work, counting reports by drilling end date (start date when the end is blank). SDR reports carry
no aquifer, so ``aquifer`` is blank. No owner, driller or company name is ever written.

Pumpage (``pumpage``): TWDB publishes its historical pumpage estimates only through an interactive
report viewer (PUMPAGE_URLS), not a file, so this command prints ``DISABLED`` and exits 0
(swimming-hole-decline Blocker, 2026-10-08).
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import gzip
import hashlib
import io
import json
import sys
import zipfile
from collections import Counter
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
SDR_URL = "https://www.twdb.texas.gov/groundwater/data/SDRDownload.zip"
PUMPAGE_URLS = ["https://www3.twdb.texas.gov/apps/reports/WU_REP/SumFinal_Groundwater_Pumpage",
                "https://www3.twdb.texas.gov/apps/reports/WU_REP/SumFinal_CountyPumpage"]
UA = "Mozilla/5.0 (hill-country-hydro twdb_groundwater_use; +saulbanov/hill-country-hydro)"
MEMBER = "SDRDownload/WellData.txt"
EXTRACT_COLUMNS = ["WellReportTrackingNumber", "DateSubmitted", "County", "TypeOfWork", "ProposedUse",
                   "DrillingStartDate", "DrillingEndDate", "NumberOfWellsDrilled"]
NAME_COLUMNS = {"OwnerName", "OwnerAddress1", "OwnerAddress2", "CompanyName", "DrillerName", "DrillerSigned",
                "ApprenticeSigned", "SealedByName", "DrillerAddress1", "DrillerAddress2"}


def paths(root: Path) -> dict:
    return {"raw": root / "data/raw/twdb-sdr", "cap": root / "data/captures/twdb-sdr", "history": root / "data/history",
            "manifest": root / "data/model/twdb-groundwater-use-manifest.json", "counties": root / "data/noaa-counties.json"}


def utcnow() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def fetch(url: str) -> tuple[int, bytes, str | None]:
    try:
        with urlopen(Request(url, headers={"User-Agent": UA}), timeout=900) as r:
            return r.status, r.read(), None
    except HTTPError as e:
        return e.code, e.read() or b"", str(e)
    except (URLError, TimeoutError, OSError) as e:
        return 0, b"", str(getattr(e, "reason", e))


def load_manifest(root: Path) -> dict:
    p = paths(root)["manifest"]
    return json.loads(p.read_text()) if p.is_file() else {
        "tool": "twdb-groundwater-use", "last_success": None, "last_attempt": None, "sdr": None, "files": [], "skipped": [],
        "pumpage": {"status": "disabled", "urls": PUMPAGE_URLS,
                    "reason": "TWDB serves pumpage estimates only through an interactive report viewer; no file to fetch"}}


def save_manifest(root: Path, m: dict) -> None:
    p = paths(root)["manifest"]
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(m, indent=1) + "\n")
    tmp.replace(p)


def county_names(root: Path) -> dict:
    d = json.loads(paths(root)["counties"].read_text())
    return {name.upper(): fips for fips, name in d.get("names", {}).items() if fips.startswith("48")}


def extract(zbytes: bytes, wanted: dict, source: str, malformed: list | None = None) -> tuple[str, int]:
    """Name-free TSV of WellData rows in the wanted counties. Raises on a missing member or column or a
    truncated last record; a record with more fields than the header is appended to `malformed`."""
    malformed = [] if malformed is None else malformed
    try:
        zf = zipfile.ZipFile(io.BytesIO(zbytes))
        raw = zf.read(MEMBER)
    except (zipfile.BadZipFile, KeyError) as e:
        raise ValueError(f"{source}:1: cannot read {MEMBER} ({e})") from None
    lines = raw.decode("latin-1").splitlines()
    header = lines[0].split("|")
    missing = [c for c in EXTRACT_COLUMNS if c not in header]
    if missing:
        raise ValueError(f"{source}:{MEMBER}:1: columns {missing} not in the header")
    idx = [header.index(c) for c in EXTRACT_COLUMNS]
    ci = header.index("County")
    out, n = ["\t".join(EXTRACT_COLUMNS)], 0
    buf, start = "", 2
    for i, line in enumerate(lines[1:], 2):
        # A free-text field (Comments, WellLocationDescription) can hold a line break, which splits one
        # record across lines; join lines until the record has all its fields.
        buf = line if not buf else buf + " " + line
        if not buf:
            continue
        if buf.count("|") < len(header) - 1:
            continue
        if buf.count("|") > len(header) - 1:
            # A stray delimiter shifts every later column, so even County is unreliable: excluded and listed.
            malformed.append({"line": start, "tracking_number": buf.split("|", 1)[0], "fields": buf.count("|") + 1})
            buf, start = "", i + 1
            continue
        f = buf.split("|")
        if f[ci].strip().upper() in wanted:
            out.append("\t".join(f[j].replace("\t", " ").strip() for j in idx))
            n += 1
        buf, start = "", i + 1
    if buf:
        raise ValueError(f"{source}:{MEMBER}:{start}: last record is incomplete (truncated file?)")
    return "\n".join(out) + "\n", n


def collect(root: Path = ROOT) -> int:
    P, m = paths(root), load_manifest(root)
    m["last_attempt"] = utcnow()
    status, body, err = fetch(SDR_URL)
    if status != 200 or not body:
        print(f"SKIPPED — twdb_groundwater_use: {SDR_URL} unreachable ({err or f'HTTP {status}'})", flush=True)
        m["skipped"] = (m.get("skipped", []) + [{"url": SDR_URL, "reason": err or f"HTTP {status}", "at": m["last_attempt"]}])[-50:]
        save_manifest(root, m)
        return 0
    sha = hashlib.sha256(body).hexdigest()
    if (m.get("sdr") or {}).get("sha256") == sha and (root / m["sdr"]["capture_path"]).is_file():
        print(f"UNCHANGED twdb_groundwater_use: SDRDownload.zip same bytes as {m['sdr']['retrieved_at']}", flush=True)
        return 0
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    P["raw"].mkdir(parents=True, exist_ok=True)
    raw = P["raw"] / f"{stamp}-SDRDownload.zip"
    raw.write_bytes(body)
    meta = {"url": SDR_URL, "retrieved_at": utcnow(), "status": status, "sha256": sha, "bytes": len(body)}
    raw.with_suffix(".meta.json").write_text(json.dumps(meta, indent=1) + "\n")
    malformed: list = []
    text, n = extract(body, county_names(root), str(raw.relative_to(root)), malformed)
    if malformed:
        print(f"MALFORMED — twdb_groundwater_use: {len(malformed)} WellData record(s) have more fields than the header and are "
              f"excluded: {[x['tracking_number'] for x in malformed]}", flush=True)
    P["cap"].mkdir(parents=True, exist_ok=True)
    cap = P["cap"] / "welldata-extract.tsv.gz"
    cap.write_bytes(gzip.compress(text.encode(), compresslevel=9, mtime=0))
    m["sdr"] = {**meta, "raw_path": str(raw.relative_to(root)), "capture_path": str(cap.relative_to(root)),
                "capture_sha256": hashlib.sha256(cap.read_bytes()).hexdigest(), "capture_rows": n, "malformed_records": malformed,
                "capture_scope": f"{MEMBER} columns {EXTRACT_COLUMNS} for the counties in data/noaa-counties.json; no names or addresses"}
    save_manifest(root, m)
    print(f"twdb_groundwater_use: SDRDownload.zip {len(body)} bytes; {n} well reports in the listed counties", flush=True)
    return 0


def normalize(root: Path = ROOT) -> int:
    P, m = paths(root), load_manifest(root)
    sdr = m.get("sdr")
    if not sdr:
        print("SKIPPED — twdb_groundwater_use normalize: nothing collected yet", flush=True)
        return 0
    cap = root / sdr["capture_path"]
    data = cap.read_bytes()
    if hashlib.sha256(data).hexdigest() != sdr["capture_sha256"]:
        raise ValueError(f"{cap}: sha256 does not match the manifest")
    if sdr.get("normalized_sha256") == sdr["capture_sha256"] and all((root / f["path"]).is_file() for f in m.get("files", [])):
        print("UNCHANGED twdb_groundwater_use normalize", flush=True)
        return 0
    rows = list(csv.DictReader(io.StringIO(gzip.decompress(data).decode()), delimiter="\t"))
    if rows and NAME_COLUMNS & set(rows[0]):
        raise ValueError(f"{cap}:1: extract carries name columns {sorted(NAME_COLUMNS & set(rows[0]))}")
    fips_by_name = county_names(root)
    counts, undated = Counter(), Counter()
    for i, r in enumerate(rows, 2):
        fips = fips_by_name.get(r["County"].strip().upper())
        date = (r["DrillingEndDate"] or r["DrillingStartDate"]).strip()
        if not date:
            undated[fips] += 1
            continue
        if len(date) < 4 or not date[:4].isdigit():
            raise ValueError(f"{cap}:{i}: drilling date {date!r} has no year")
        counts[(fips, int(date[:4]), r["ProposedUse"].strip(), r["TypeOfWork"].strip())] += 1
    P["history"].mkdir(parents=True, exist_ok=True)
    files = []
    for fips in sorted(set(fips_by_name.values())):
        keyed = sorted((k[1], k[2], k[3], c) for k, c in counts.items() if k[0] == fips)
        text = "year,aquifer,use,count,source_file,type_of_work\n" + "".join(
            f'{y},,"{u}",{c},SDRDownload.zip:{MEMBER},"{t}"\n' for y, u, t, c in keyed)
        out = P["history"] / f"twdb-wells-drilled-{fips}-annual.csv"
        out.write_text(text)
        files.append({"path": str(out.relative_to(root)), "sha256": hashlib.sha256(text.encode()).hexdigest(),
                      "rows": len(keyed), "first": keyed[0][0] if keyed else None, "last": keyed[-1][0] if keyed else None,
                      "undated_reports": undated.get(fips, 0)})
    sdr["normalized_sha256"] = sdr["capture_sha256"]
    m.update(files=files, last_success=utcnow())
    save_manifest(root, m)
    print(f"twdb_groundwater_use normalize: {len(files)} county files, {sum(counts.values())} dated reports", flush=True)
    return 0


def pumpage(root: Path = ROOT) -> int:
    print("DISABLED — twdb_groundwater_use pumpage: TWDB serves the estimates only through its report viewer "
          f"({', '.join(PUMPAGE_URLS)}); no file to fetch", flush=True)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["collect", "normalize", "pumpage"])
    a = ap.parse_args(argv)
    return {"collect": collect, "normalize": normalize, "pumpage": pumpage}[a.cmd]()


if __name__ == "__main__":
    sys.exit(main())
