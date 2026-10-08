import contextlib, datetime as dt, gzip, io, json, shutil, tempfile, unittest
from pathlib import Path
from tools import operator_notices as on, daily_mac_run as runner

PAGE = {"page_id": "jacobs", "kind": "operator_access", "operator": "Hays County Parks", "url": "https://www.example.gov/jacobs-well",
        "place_ids": ["jacobs-well"], "counties": ["48209"]}
CDX_HEAD = ["timestamp", "original", "statuscode", "digest", "mimetype"]


def cdx_body(rows, resume=None):
    data = [CDX_HEAD] + rows
    if resume:
        data += [[], [resume]]
    return json.dumps(data).encode()


def html(text):
    return f"<html><head><title>t</title><script>var x='Closed';</script></head><body><p>{text}</p></body></html>".encode()


class FakeIA:
    """Records every request with a fake clock; serves CDX pages and snapshots from dicts."""
    def __init__(self, cdx_pages, snaps, live=None):
        self.cdx_pages, self.snaps, self.live = cdx_pages, snaps, live or {}
        self.t, self.calls, self.kill_after = 0.0, [], None

    def clock(self):
        return self.t

    def sleep(self, s):
        self.t += s

    def fetch(self, url):
        self.calls.append((self.t, url))
        self.t += 0.3  # the request itself takes time
        if self.kill_after is not None and sum(1 for _, u in self.calls if "/web/" in u) > self.kill_after:
            raise KeyboardInterrupt
        if "cdx/search" in url:
            key = "resume" if "resumeKey" in url else "first"
            return 200, self.cdx_pages[key], None, "application/json"
        if "/web/" in url:
            ts = url.split("/web/")[1].split("id_")[0]
            status, body = self.snaps.get(ts, (404, b""))
            return status, body, None if status == 200 else f"HTTP {status}", "text/html; charset=utf-8"
        status, body = self.live.get(url, (0, b""))
        return status, body, None if status == 200 else "network down", "text/html"


class Base(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="hydro-operator-"))
        (self.root / "data").mkdir()
        (self.root / "data/operator-pages.json").write_text(json.dumps([PAGE]))
        self.addCleanup(shutil.rmtree, self.root, True)
        for name in ("fetch", "_sleep", "_clock"):
            self.addCleanup(setattr, on, name, getattr(on, name))
        on._last_ia[0] = None

    def use(self, ia):
        on.fetch, on._sleep, on._clock = ia.fetch, ia.sleep, ia.clock
        on._last_ia[0] = None

    def quiet(self, fn, **kw):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = fn(self.root, **kw)
        return rc, buf.getvalue()


class BackfillTests(Base):
    ROWS = [["20200106120000", PAGE["url"], "200", "AAA", "text/html"],
            ["20200107120000", PAGE["url"], "200", "AAA", "text/html"],   # same digest: collapses
            ["20200108120000", PAGE["url"], "200", "BBB", "text/html"],   # same ISO week: one per week
            ["20200115120000", PAGE["url"], "200", "CCC", "text/html"],
            ["20200116120000", PAGE["url"], "404", "DDD", "text/html"],   # not a 200 capture
            ["20200122120000", PAGE["url"], "200", "EEE", "application/pdf"],  # not HTML
            ["20200129120000", PAGE["url"], "200", "FFF", "text/html"]]
    MORE = [["20200205120000", PAGE["url"], "200", "GGG", "text/html"]]

    def ia(self):
        return FakeIA({"first": cdx_body(self.ROWS, resume="key1"), "resume": cdx_body(self.MORE)},
                      {"20200106120000": (200, html("Swimming open")), "20200115120000": (200, html("Closed: low water")),
                       "20200129120000": (503, b""), "20200205120000": (200, html("Swimming open"))})

    def test_5_1_cdx_parses_and_duplicates_collapse(self):
        rows = on.parse_cdx(cdx_body(self.ROWS, resume="k"), "fixture")
        self.assertEqual([r["timestamp"] for r in rows], ["20200106120000", "20200107120000", "20200108120000", "20200115120000", "20200129120000"])
        kept = on.plan_snapshots(rows)
        self.assertEqual([r["timestamp"] for r in kept], ["20200106120000", "20200115120000", "20200129120000"])
        with self.assertRaises(ValueError) as e:
            on.parse_cdx(b"<html>Temporarily Offline</html>", "cdx-url")
        self.assertIn("cdx-url:1: CDX response is not JSON", str(e.exception))

    def test_5_2_backfill_resumes_after_a_kill(self):
        ia = self.ia()
        self.use(ia)
        ia.kill_after = 1
        with self.assertRaises(KeyboardInterrupt):
            self.quiet(on.backfill, pause=2.0)
        st = json.loads((self.root / "data/model/operator-notices-backfill-state.json").read_text())["pages"]["jacobs"]
        self.assertEqual(st["done"], ["20200106120000"])
        self.assertEqual(len(st["planned"]), 4, "the resumed CDX page added a fourth week")
        ia.kill_after = None
        self.quiet(on.backfill, pause=2.0)
        snaps = [u for _, u in ia.calls if "/web/" in u]
        self.assertEqual(snaps.count("https://web.archive.org/web/20200106120000id_/" + PAGE["url"]), 1, "a done snapshot is never refetched")
        self.assertEqual(sum(1 for _, u in ia.calls if "cdx/search" in u), 2, "the CDX index is read once, two pages")
        st = json.loads((self.root / "data/model/operator-notices-backfill-state.json").read_text())["pages"]["jacobs"]
        self.assertEqual(sorted(st["done"]), ["20200106120000", "20200115120000", "20200205120000"])

    def test_5_3_pacing_holds_two_seconds(self):
        ia = self.ia()
        self.use(ia)
        self.quiet(on.backfill, pause=0.5)  # a pause below 2 s is raised to 2 s
        starts = [t for t, u in ia.calls if "archive.org" in u]
        gaps = [b - a for a, b in zip(starts, starts[1:])]
        self.assertTrue(gaps and min(gaps) >= 2.0 - 1e-9, gaps)

    def test_5_4_wayback_errors_recorded_and_skipped(self):
        self.use(self.ia())
        rc, out = self.quiet(on.backfill, pause=2.0)
        self.assertEqual(rc, 0)
        self.assertIn("SKIPPED — operator_notices: https://web.archive.org/web/20200129120000id_/", out)
        st = json.loads((self.root / "data/model/operator-notices-backfill-state.json").read_text())["pages"]["jacobs"]
        self.assertEqual(st["failed"][0]["status"], 503)
        m = json.loads((self.root / "data/model/operator-notices-manifest.json").read_text())
        self.assertTrue(any("20200129120000" in s["url"] for s in m["skipped"]))

    def test_cdx_outage_skips_the_page(self):
        ia = FakeIA({}, {})
        ia.fetch = lambda url: (503, b"<html>Temporarily Offline</html>", "HTTP 503", "text/html")
        self.use(ia)
        on.fetch = ia.fetch
        rc, out = self.quiet(on.backfill, pause=2.0)
        self.assertEqual(rc, 0); self.assertIn("SKIPPED — operator_notices:", out)

    def test_normalize_index_has_contract_fields_and_text_is_deduplicated(self):
        self.use(self.ia())
        self.quiet(on.backfill, pause=2.0)
        self.quiet(on.normalize)
        rows = [json.loads(l) for l in (self.root / "data/normalized/operator-notices.jsonl").read_text().splitlines()]
        self.assertEqual(len(rows), 3)
        need = {"page_id", "url", "captured_at", "source", "wayback_timestamp", "digest", "raw_path", "raw_sha256", "text_path", "text_sha256"}
        self.assertTrue(all(need <= set(r) for r in rows))
        self.assertEqual(rows[0]["source"], "wayback"); self.assertEqual(rows[0]["captured_at"], "2020-01-06T12:00:00+00:00")
        self.assertEqual(rows[0]["text_path"], rows[2]["text_path"], "identical page text is stored once")
        text = gzip.decompress((self.root / rows[1]["text_path"]).read_bytes()).decode()
        self.assertIn("Closed: low water", text); self.assertNotIn("var x", text, "script text is not page text")

    def test_connection_refused_is_an_outage_not_a_failure(self):
        ia = self.ia()
        real = ia.fetch
        ia.refuse = False
        def fetch(url):
            if ia.refuse and "/web/" in url:
                ia.calls.append((ia.t, url)); ia.t += 0.3
                return 0, b"", "[Errno 61] Connection refused", ""
            return real(url)
        ia.fetch = fetch
        self.use(ia)
        ia.refuse = True
        rc, out = self.quiet(on.backfill, pause=2.0)
        self.assertEqual(rc, 0); self.assertIn("STOPPED — operator_notices backfill", out)
        st = json.loads((self.root / "data/model/operator-notices-backfill-state.json").read_text())["pages"]["jacobs"]
        self.assertEqual(st["failed"], [], "an outage marks nothing failed")
        self.assertEqual(st["done"], [])
        ia.refuse = False
        self.quiet(on.backfill, pause=2.0)
        st = json.loads((self.root / "data/model/operator-notices-backfill-state.json").read_text())["pages"]["jacobs"]
        self.assertEqual(len(st["done"]), 3, "the next run resumes every snapshot")
        ia.snaps["20200129120000"] = (200, html("Closed for repairs"))
        self.quiet(on.backfill, pause=2.0, retry_failed=True)
        st = json.loads((self.root / "data/model/operator-notices-backfill-state.json").read_text())["pages"]["jacobs"]
        self.assertEqual(len(st["done"]), 4, "--retry-failed asks a 5xx snapshot again")
        self.assertEqual(st["failed"], [])

    def test_cdx_503_is_retried_once_after_a_wait(self):
        ia = self.ia()
        real = ia.fetch
        seen = {"n": 0}
        def fetch(url):
            if "cdx/search" in url and "resumeKey" not in url and seen["n"] == 0:
                seen["n"] += 1
                ia.calls.append((ia.t, url)); ia.t += 0.3
                return 503, b"<html>Temporarily Offline</html>", "HTTP 503", "text/html"
            return real(url)
        ia.fetch = fetch
        self.use(ia)
        t0 = ia.t
        self.quiet(on.backfill, pause=2.0)
        st = json.loads((self.root / "data/model/operator-notices-backfill-state.json").read_text())["pages"]["jacobs"]
        self.assertIsNotNone(st["planned"], "the retry planned the page")
        cdx = [t for t, u in ia.calls if "cdx/search" in u]
        self.assertGreaterEqual(cdx[1] - cdx[0], on.CDX_RETRY_WAIT, "the retry waited")


class CollectTests(Base):
    def test_5_5_collect_is_a_daily_step_and_captures_today(self):
        names = lambda d: [s.name for s in runner.plan(d)]
        for d in (dt.date(2026, 10, 12), dt.date(2026, 10, 11)):
            self.assertIn("water.operator_notices_collect", names(d))
            self.assertIn("water.operator_notices_normalize", names(d))
        ia = FakeIA({}, {}, live={PAGE["url"]: (200, html("Swimming is canceled until further notice due to low water"))})
        self.use(ia)
        rc, out = self.quiet(on.collect, pause=0)
        self.assertIn("1 of 1 pages captured", out)
        events = list((self.root / "data/captures/operator-pages/jacobs/events").glob("*-live.json"))
        self.assertEqual(len(events), 1)
        m = json.loads((self.root / "data/model/operator-notices-manifest.json").read_text())
        self.assertIsNotNone(m["last_success"])

    def test_live_failure_skips_and_exits_zero(self):
        self.use(FakeIA({}, {}))
        rc, out = self.quiet(on.collect, pause=0)
        self.assertEqual(rc, 0); self.assertIn("SKIPPED — operator_notices: https://www.example.gov/jacobs-well unreachable", out)

    def test_bad_kind_is_refused_by_name(self):
        (self.root / "data/operator-pages.json").write_text(json.dumps([{**PAGE, "kind": "vibes"}]))
        with self.assertRaises(ValueError) as e:
            on.load_pages(self.root)
        self.assertIn("jacobs: kind 'vibes'", str(e.exception))


if __name__ == "__main__":
    unittest.main()
