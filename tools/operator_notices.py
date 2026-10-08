#!/usr/bin/env python3
"""Preserve operator and official declaration pages, today and as the Internet Archive saw them.
No judgment about what a page says: turning text into "closed for low water" is analysis, done
downstream (swimming-hole-decline lens/events.py).

Pages: ``data/operator-pages.json`` ``[{page_id, kind, operator, url, place_ids, counties}]``; kind is
operator_access, drought_declaration, water_restriction, burn_ban or outlook.

``collect`` (daily): fetches each page once. ``backfill`` (once, resumable): asks the Wayback CDX index
for each page, keeps 200 HTML snapshots, collapses repeated digests, keeps at most one snapshot per
page per ISO week, and fetches each ``/web/<timestamp>id_/<url>`` at one Internet Archive request
every ``--pause`` seconds (2 s or more). Progress lives in ``data/model/operator-notices-backfill-state.json``
after every snapshot, so a killed run resumes where it stopped. A 404 or 5xx is recorded and skipped
(``--retry-failed`` asks for the 5xx ones again). A refused connection or a 429 is an outage, not an
answer: nothing is marked, and after OUTAGE_LIMIT in a row the run stops loudly and exits 0; the next
run resumes.

Every capture writes, before anything reads it:
* ``data/raw/operator-pages/<page_id>/<stamp>-<source>.<ext>`` verbatim bytes + ``.meta.json`` (Git-ignored);
* ``data/captures/operator-pages/<page_id>/text/<text_sha256>.txt.gz`` the visible text (versioned,
  one file per distinct text, so an unchanged page adds nothing);
* ``data/captures/operator-pages/<page_id>/events/<stamp>-<source>.json`` the capture record (versioned).
``normalize`` rebuilds ``data/normalized/operator-notices.jsonl`` from the capture records.
A provider failure prints ``SKIPPED — operator_notices: <url> unreachable (<reason>)`` and exits 0.
"""
from __future__ import annotations

import argparse
import datetime as dt
import gzip
import hashlib
import json
import re
import sys
import time
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
UA = "hill-country-hydro/0.1 operator_notices (+saulbanov/hill-country-hydro; public-record research)"
CDX = "https://web.archive.org/cdx/search/cdx"
WAYBACK = "https://web.archive.org/web/{ts}id_/{url}"
KINDS = {"operator_access", "drought_declaration", "water_restriction", "burn_ban", "outlook"}
HTML_TYPES = ("text/html", "application/xhtml+xml", "warc/revisit")
MIN_PAUSE = 2.0
OUTAGE_LIMIT = 3

_sleep = time.sleep
_clock = time.monotonic
_last_ia = [None]


def paths(root: Path) -> dict:
    return {"pages": root / "data/operator-pages.json", "raw": root / "data/raw/operator-pages",
            "cap": root / "data/captures/operator-pages", "index": root / "data/normalized/operator-notices.jsonl",
            "manifest": root / "data/model/operator-notices-manifest.json",
            "state": root / "data/model/operator-notices-backfill-state.json"}


def utcnow() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def fetch(url: str) -> tuple[int, bytes, str | None, str]:
    try:
        with urlopen(Request(url, headers={"User-Agent": UA}), timeout=120) as r:
            return r.status, r.read(), None, r.headers.get("Content-Type", "")
    except HTTPError as e:
        return e.code, e.read() or b"", str(e), e.headers.get("Content-Type", "") if e.headers else ""
    except (URLError, TimeoutError, OSError) as e:
        return 0, b"", str(getattr(e, "reason", e)), ""


def ia_fetch(url: str, pause: float) -> tuple[int, bytes, str | None, str]:
    """Every Internet Archive request goes through here: at most one per `pause` seconds."""
    pause = max(pause, MIN_PAUSE)
    if _last_ia[0] is not None:
        wait = pause - (_clock() - _last_ia[0])
        if wait > 0:
            _sleep(wait)
    _last_ia[0] = _clock()
    return fetch(url)


class _Text(HTMLParser):
    SKIP = {"script", "style", "noscript", "template", "svg", "head"}
    BLOCK = {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "section", "article", "header", "footer", "td", "th", "ul", "ol", "table"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
        elif tag in self.BLOCK:
            self.out.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skip:
            self.skip -= 1
        elif tag in self.BLOCK:
            self.out.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.out.append(data)


def visible_text(body: bytes, content_type: str) -> str:
    if b"%PDF" in body[:8]:
        return ""
    m = re.search(r"charset=([\w-]+)", content_type or "") or re.search(rb'charset=["\']?([\w-]+)', body[:2000])
    enc = (m.group(1).decode() if isinstance(m.group(1), bytes) else m.group(1)) if m else "utf-8"
    try:
        html = body.decode(enc, "replace")
    except LookupError:
        html = body.decode("utf-8", "replace")
    p = _Text()
    p.feed(html)
    lines = [re.sub(r"[ \t ]+", " ", l).strip() for l in "".join(p.out).splitlines()]
    return "\n".join(l for l in lines if l) + "\n"


def load_pages(root: Path) -> list[dict]:
    pages = json.loads(paths(root)["pages"].read_text())
    for i, p in enumerate(pages):
        for k in ("page_id", "kind", "operator", "url", "place_ids", "counties"):
            if k not in p:
                raise ValueError(f"{paths(root)['pages']}[{i}]: missing {k}")
        if p["kind"] not in KINDS:
            raise ValueError(f"{paths(root)['pages']}[{i}] {p['page_id']}: kind {p['kind']!r} not in {sorted(KINDS)}")
    return pages


def load_json(p: Path, default):
    return json.loads(p.read_text()) if p.is_file() else default


def save_json(p: Path, data) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1) + "\n")
    tmp.replace(p)


def manifest(root: Path) -> dict:
    return load_json(paths(root)["manifest"], {"tool": "operator-notices", "last_success": None, "last_attempt": None,
                                               "files": [], "skipped": [], "captures": 0})


def note_skip(root: Path, url: str, reason: str, at: str | None = None) -> None:
    m = manifest(root)
    m["last_attempt"] = utcnow()
    m["skipped"] = (m.get("skipped", []) + [{"url": url, "reason": reason, "at": at or m["last_attempt"]}])[-200:]
    save_json(paths(root)["manifest"], m)


def store(root: Path, page: dict, body: bytes, content_type: str, source: str, captured_at: str,
          wayback_timestamp: str | None = None, digest: str | None = None, fetched_url: str | None = None) -> dict:
    P = paths(root)
    stamp = captured_at.replace("-", "").replace(":", "").replace("+0000", "Z").split(".")[0][:15] + "Z"
    ext = "pdf" if b"%PDF" in body[:8] else "html"
    rd = P["raw"] / page["page_id"]
    rd.mkdir(parents=True, exist_ok=True)
    raw = rd / f"{stamp}-{source}.{ext}"
    raw.write_bytes(body)
    raw_sha = hashlib.sha256(body).hexdigest()
    raw.with_suffix(".meta.json").write_text(json.dumps({"url": fetched_url or page["url"], "retrieved_at": utcnow(),
                                                         "sha256": raw_sha, "bytes": len(body), "content_type": content_type}, indent=1) + "\n")
    text = visible_text(body, content_type)
    text_sha = hashlib.sha256(text.encode()).hexdigest()
    td = P["cap"] / page["page_id"] / "text"
    td.mkdir(parents=True, exist_ok=True)
    tp = td / f"{text_sha}.txt.gz"
    if not tp.is_file():
        tp.write_bytes(gzip.compress(text.encode(), compresslevel=9, mtime=0))
    rec = {"page_id": page["page_id"], "url": page["url"], "captured_at": captured_at, "source": source,
           "wayback_timestamp": wayback_timestamp, "digest": digest or f"sha256:{raw_sha}",
           "raw_path": str(raw.relative_to(root)), "raw_sha256": raw_sha, "text_path": str(tp.relative_to(root)),
           "text_sha256": text_sha, "content_type": content_type, "bytes": len(body), "text_chars": len(text),
           "fetched_url": fetched_url or page["url"], "fetched_at": utcnow()}
    ed = P["cap"] / page["page_id"] / "events"
    ed.mkdir(parents=True, exist_ok=True)
    save_json(ed / f"{stamp}-{source}.json", rec)
    return rec


def collect(root: Path = ROOT, pause: float = 1.0) -> int:
    pages = load_pages(root)
    ok = 0
    for page in pages:
        status, body, err, ctype = fetch(page["url"])
        if status != 200 or not body:
            print(f"SKIPPED — operator_notices: {page['url']} unreachable ({err or f'HTTP {status}'})", flush=True)
            note_skip(root, page["url"], err or f"HTTP {status}")
            continue
        store(root, page, body, ctype, "live", utcnow())
        ok += 1
        _sleep(pause)
    m = manifest(root)
    m["last_attempt"] = utcnow()
    if ok:
        m["last_success"] = m["last_attempt"]
    save_json(paths(root)["manifest"], m)
    print(f"operator_notices collect: {ok} of {len(pages)} pages captured", flush=True)
    return 0


def parse_cdx(body: bytes, source: str) -> list[dict]:
    """CDX JSON (first row is the header) -> rows; non-200 and non-HTML rows dropped."""
    try:
        rows = json.loads(body or b"[]")
    except json.JSONDecodeError as e:
        raise ValueError(f"{source}:1: CDX response is not JSON ({e})") from None
    if not rows:
        return []
    head = rows[0]
    need = {"timestamp", "original", "statuscode", "digest", "mimetype"}
    if not need <= set(head):
        raise ValueError(f"{source}:1: CDX header {head} lacks {sorted(need - set(head))}")
    out = []
    for i, r in enumerate(rows[1:], 2):
        if len(r) != len(head):
            continue  # a resume-key row ([] or [key]) closes a page
        d = dict(zip(head, r))
        if d["statuscode"] == "200" and d["mimetype"].startswith(HTML_TYPES):
            out.append(d)
    return out


def plan_snapshots(rows: list[dict]) -> list[dict]:
    """Collapse repeated digests (a snapshot identical to the one kept before it adds nothing), then keep
    at most one snapshot per ISO week."""
    kept, last_digest, weeks = [], None, set()
    for r in sorted(rows, key=lambda x: x["timestamp"]):
        if r["digest"] == last_digest:
            continue
        t = dt.datetime.strptime(r["timestamp"][:14], "%Y%m%d%H%M%S")
        wk = t.isocalendar()[:2]
        if wk in weeks:
            continue
        weeks.add(wk)
        kept.append(r)
        last_digest = r["digest"]
    return kept


def transient(status: int) -> bool:
    return status in (0, 429)


def cdx_rows(page: dict, pause: float) -> tuple[list[dict] | None, str | None, int]:
    rows, key = [], None
    while True:
        q = {"url": page["url"].split("://", 1)[-1], "output": "json", "fl": "timestamp,original,statuscode,digest,mimetype",
             "limit": "5000", "showResumeKey": "true"}
        if key:
            q["resumeKey"] = key
        url = CDX + "?" + urlencode(q)
        status, body, err, _ = ia_fetch(url, pause)
        if status != 200:
            return None, f"{url} ({err or f'HTTP {status}'})", status
        rows += parse_cdx(body, url)
        data = json.loads(body or b"[]")
        key = data[-1][0] if data and len(data[-1]) == 1 and len(data) > 1 and data[-2] == [] else None
        if not key:
            return rows, None, 200


def backfill(root: Path = ROOT, pause: float = MIN_PAUSE, page_ids=None, max_fetches: int | None = None,
             retry_failed: bool = False) -> int:
    P = paths(root)
    state = load_json(P["state"], {"pages": {}})
    fetched, outage = 0, 0

    def stop(why: str) -> int:
        save_json(P["state"], state)
        print(f"STOPPED — operator_notices backfill: Internet Archive unreachable {OUTAGE_LIMIT} times in a row "
              f"(last: {why}); nothing was marked failed; rerun to resume", flush=True)
        return 0

    for page in load_pages(root):
        if page_ids and page["page_id"] not in page_ids:
            continue
        st = state["pages"].setdefault(page["page_id"], {"url": page["url"], "planned": None, "done": [], "failed": []})
        if retry_failed:
            st["failed"] = [f for f in st["failed"] if not (500 <= f.get("status", 0) < 600)]
        if st["planned"] is None:
            rows, err, status = cdx_rows(page, pause)
            if rows is None:
                print(f"SKIPPED — operator_notices: {err} unreachable", flush=True)
                note_skip(root, page["url"], f"CDX {err}")
                outage = outage + 1 if transient(status) else 0
                if outage >= OUTAGE_LIMIT:
                    return stop(err)
                continue
            outage = 0
            st["planned"] = [{"timestamp": r["timestamp"], "original": r["original"], "digest": r["digest"]} for r in plan_snapshots(rows)]
            st["cdx_rows"] = len(rows)
            st["cdx_at"] = utcnow()
            save_json(P["state"], state)
            print(f"backfill {page['page_id']}: {len(rows)} CDX rows -> {len(st['planned'])} weekly snapshots", flush=True)
        done = set(st["done"]) | {f["timestamp"] for f in st["failed"]}
        for snap in st["planned"]:
            if snap["timestamp"] in done:
                continue
            if max_fetches is not None and fetched >= max_fetches:
                save_json(P["state"], state)
                return 0
            url = WAYBACK.format(ts=snap["timestamp"], url=snap["original"])
            status, body, err, ctype = ia_fetch(url, pause)
            fetched += 1
            if transient(status):
                outage += 1
                print(f"SKIPPED — operator_notices: {url} unreachable ({err or f'HTTP {status}'}); left for the next run", flush=True)
                if outage >= OUTAGE_LIMIT:
                    return stop(f"{url} ({err or status})")
                continue
            outage = 0
            if status != 200 or not body:
                st["failed"].append({"timestamp": snap["timestamp"], "status": status, "reason": err or f"HTTP {status}", "at": utcnow()})
                note_skip(root, url, err or f"HTTP {status}")
                print(f"SKIPPED — operator_notices: {url} unreachable ({err or f'HTTP {status}'})", flush=True)
            else:
                t = dt.datetime.strptime(snap["timestamp"][:14], "%Y%m%d%H%M%S").replace(tzinfo=dt.timezone.utc)
                store(root, page, body, ctype, "wayback", t.isoformat(), wayback_timestamp=snap["timestamp"],
                      digest=snap["digest"], fetched_url=url)
                st["done"].append(snap["timestamp"])
            save_json(P["state"], state)
    m = manifest(root)
    m["last_attempt"] = utcnow()
    save_json(P["manifest"], m)
    return 0


def normalize(root: Path = ROOT) -> int:
    P = paths(root)
    recs = []
    for f in sorted(P["cap"].glob("*/events/*.json")):
        r = json.loads(f.read_text())
        recs.append({k: r.get(k) for k in ("page_id", "url", "captured_at", "source", "wayback_timestamp", "digest",
                                           "raw_path", "raw_sha256", "text_path", "text_sha256")} | {"event_path": str(f.relative_to(root))})
    recs.sort(key=lambda r: (r["page_id"], r["captured_at"]))
    P["index"].parent.mkdir(parents=True, exist_ok=True)
    text = "".join(json.dumps(r, sort_keys=True) + "\n" for r in recs)
    if not (P["index"].is_file() and P["index"].read_text() == text):
        P["index"].write_text(text)
    m = manifest(root)
    by_page = {}
    for r in recs:
        by_page.setdefault(r["page_id"], []).append(r)
    m["files"] = [{"path": str(P["index"].relative_to(root)), "sha256": hashlib.sha256(text.encode()).hexdigest(),
                   "rows": len(recs), "first": min((r["captured_at"] for r in recs), default=None),
                   "last": max((r["captured_at"] for r in recs), default=None)}]
    m["captures"] = len(recs)
    m["pages"] = {p: {"captures": len(v), "wayback": sum(1 for x in v if x["source"] == "wayback"),
                      "first": v[0]["captured_at"], "last": v[-1]["captured_at"]} for p, v in by_page.items()}
    save_json(P["manifest"], m)
    print(f"operator_notices normalize: {len(recs)} captures across {len(by_page)} pages", flush=True)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["collect", "backfill", "normalize"])
    ap.add_argument("--pause", type=float, default=None)
    ap.add_argument("--pages", nargs="+")
    ap.add_argument("--max-fetches", type=int)
    ap.add_argument("--retry-failed", action="store_true", help="ask again for snapshots that answered 5xx")
    a = ap.parse_args(argv)
    if a.cmd == "collect":
        return collect(pause=a.pause if a.pause is not None else 1.0)
    if a.cmd == "backfill":
        return backfill(pause=max(a.pause or MIN_PAUSE, MIN_PAUSE), page_ids=a.pages, max_fetches=a.max_fetches,
                        retry_failed=a.retry_failed)
    return normalize()


if __name__ == "__main__":
    sys.exit(main())
