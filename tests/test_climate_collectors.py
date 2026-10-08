import contextlib, datetime as dt, gzip, io, json, shutil, tempfile, unittest
from pathlib import Path
from tools import nclimdiv as nc, ghcn_daily as gh, daily_mac_run as runner

DATE = "20261006"


def county_line(ncdc, element, year, values):
    return f"{ncdc}{element}{year:04d}" + "".join(f"{v:7.2f}" for v in values) + "\n"


def fake_server(files):
    """fetch() stand-in: url suffix -> (status, bytes); anything else is a network failure."""
    calls = []
    def fetch(url):
        calls.append(url)
        for suffix, (status, body) in files.items():
            if url.endswith(suffix):
                return status, body, None if status == 200 else f"HTTP {status}"
        return 0, b"", "network down"
    return fetch, calls


class Fixture(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="hydro-climate-"))
        (self.root / "data").mkdir()
        (self.root / "data/noaa-counties.json").write_text(json.dumps({"counties": ["48209", "48453"]}))
        self.addCleanup(shutil.rmtree, self.root, True)
        self.orig_nc, self.orig_gh = nc.fetch, gh.fetch
        self.addCleanup(setattr, nc, "fetch", self.orig_nc)
        self.addCleanup(setattr, gh, "fetch", self.orig_gh)

    def climdiv_files(self, pcpn_body=None):
        mapping = b"header line\n\nPOSTAL_FIPS_ID NCDC_FIPS_ID CLIMDIV_ID\n48209 41209 4107\n48453 41453 4107\n01001 01001 0101\n"
        pc = pcpn_body or (county_line("41209", "01", 2023, [1.0, 2.0, 0.5, 0, 0, 0, 0.1, 0.0, 3.3, 1, 1, 1])
                           + county_line("41453", "01", 2023, [2.0] * 12)
                           + county_line("41209", "01", 2026, [1.0] * 9 + [-9.99, -9.99, -9.99])
                           + county_line("41453", "01", 2026, [2.0] * 9 + [-9.99] * 3)
                           + county_line("01001", "01", 2023, [9.0] * 12)).encode()
        temp = lambda base: (county_line("41209", "27", 2026, [base] * 9 + [-99.99] * 3)
                             + county_line("41453", "27", 2026, [base] * 9 + [-99.99] * 3)).encode()
        return {"procdate.txt": (200, DATE.encode() + b"\n"), "county-to-climdivs.txt": (200, mapping),
                f"climdiv-pcpncy-v1.0.0-{DATE}": (200, pc), f"climdiv-tmaxcy-v1.0.0-{DATE}": (200, temp(90.0)),
                f"climdiv-tmincy-v1.0.0-{DATE}": (200, temp(70.0)), f"climdiv-tmpccy-v1.0.0-{DATE}": (200, temp(80.0))}


class NClimDivTests(Fixture):
    def run_quiet(self, fn):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = fn(self.root)
        return rc, buf.getvalue()

    def test_3_1_sentinel_writes_no_row_and_a_real_zero_stays(self):
        nc.fetch, _ = fake_server(self.climdiv_files())
        self.assertEqual(self.run_quiet(nc.collect)[0], 0)
        self.assertEqual(self.run_quiet(nc.normalize)[0], 0)
        rows = (self.root / "data/history/climdiv-48209-pcpn-monthly.csv").read_text().splitlines()
        self.assertEqual(rows[0], "month,value,raw_value,unit,source_file")
        months = [r.split(",")[0] for r in rows[1:]]
        self.assertIn("2026-09", months)
        self.assertNotIn("2026-10", months, "a -9.99 sentinel is missing, never zero")
        self.assertIn("2023-04,0.0,0.00,in,climdiv-pcpncy-v1.0.0-20261006", rows, "a real zero is kept")
        tmax = (self.root / "data/history/climdiv-48453-tmax-monthly.csv").read_text()
        self.assertNotIn("-99.99", tmax)
        self.assertNotIn("01001", (self.root / "data/history/climdiv-48453-pcpn-monthly.csv").read_text())
        cap = gzip.decompress((self.root / f"data/captures/noaa-nclimdiv/climdiv-pcpncy-v1.0.0-{DATE}.tx-nm.gz").read_bytes())
        self.assertNotIn(b"01001", cap, "the versioned capture keeps Texas and New Mexico lines only")
        m = json.loads((self.root / "data/model/nclimdiv-manifest.json").read_text())
        self.assertEqual(set(m) >= {"tool", "last_success", "last_attempt", "files", "skipped"}, True)
        self.assertTrue(all({"path", "sha256", "rows", "first", "last"} <= set(f) for f in m["files"]))

    def test_3_2_truncated_file_fails_with_file_and_line(self):
        good = county_line("41209", "01", 2023, [1.0] * 12) + county_line("41453", "01", 2023, [1.0] * 12)
        nc.fetch, _ = fake_server(self.climdiv_files(pcpn_body=(good + county_line("41209", "01", 2024, [1.0] * 12)[:40] + "\n").encode()))
        self.run_quiet(nc.collect)
        with self.assertRaises(ValueError) as e:
            self.run_quiet(nc.normalize)
        self.assertIn(f"climdiv-pcpncy-v1.0.0-{DATE}:3:", str(e.exception))
        bad = good.replace("   1.00", "   x.00", 1)
        shutil.rmtree(self.root / "data/captures"); (self.root / "data/model/nclimdiv-manifest.json").unlink()
        nc.fetch, _ = fake_server(self.climdiv_files(pcpn_body=bad.encode()))
        self.run_quiet(nc.collect)
        with self.assertRaises(ValueError) as e:
            self.run_quiet(nc.normalize)
        self.assertIn(":1: month 1 value", str(e.exception))

    def test_3_3_unchanged_file_date_rewrites_nothing(self):
        nc.fetch, calls = fake_server(self.climdiv_files())
        self.run_quiet(nc.collect); self.run_quiet(nc.normalize)
        watched = [p for p in (self.root / "data").rglob("*") if p.is_file()]
        before = {p: (p.stat().st_mtime_ns, p.read_bytes()) for p in watched}
        n = len(calls)
        rc, out = self.run_quiet(nc.collect)
        self.assertEqual(rc, 0); self.assertIn("UNCHANGED nclimdiv: NOAA file date 20261006", out)
        self.assertEqual(len(calls), n + 1, "only procdate.txt is asked again")
        rc, out = self.run_quiet(nc.normalize)
        self.assertIn("UNCHANGED", out)
        self.assertEqual(before, {p: (p.stat().st_mtime_ns, p.read_bytes()) for p in watched})

    def test_3_4_network_failure_prints_skipped_and_exits_zero(self):
        nc.fetch, _ = fake_server({})
        rc, out = self.run_quiet(nc.collect)
        self.assertEqual(rc, 0)
        self.assertIn("SKIPPED — nclimdiv: https://www.ncei.noaa.gov/monitoring-content/data/us/climdiv/monthly/current/procdate.txt unreachable (network down)", out)
        m = json.loads((self.root / "data/model/nclimdiv-manifest.json").read_text())
        self.assertEqual(m["skipped"][-1]["reason"], "network down")
        files = self.climdiv_files(); files[f"climdiv-tmincy-v1.0.0-{DATE}"] = (503, b"")
        nc.fetch, _ = fake_server(files)
        rc, out = self.run_quiet(nc.collect)
        self.assertEqual(rc, 0); self.assertIn("SKIPPED — nclimdiv:", out); self.assertIn("HTTP 503", out)
        self.assertIsNone(json.loads((self.root / "data/model/nclimdiv-manifest.json").read_text())["noaa_file_date"],
                          "a half-collected date never becomes the current one")

    def test_unknown_county_fails_naming_it(self):
        (self.root / "data/noaa-counties.json").write_text(json.dumps({"counties": ["48209", "48999"]}))
        nc.fetch, _ = fake_server(self.climdiv_files())
        self.run_quiet(nc.collect)
        with self.assertRaises(ValueError) as e:
            self.run_quiet(nc.normalize)
        self.assertIn("48999", str(e.exception))


class GhcnTests(Fixture):
    BODY = "\n".join([
        "USC00417983,19500101,PRCP,254,,,6,",          # 25.4 mm -> 1.000 in
        "USC00417983,19500102,PRCP,0,T,,6,",           # trace, kept
        "USC00417983,19500103,PRCP,-9999,,,6,",        # missing: no row
        "USC00417983,19500101,TMAX,350,,,6,",          # 35.0 C -> 95.0 F
        "USC00417983,19500102,TMAX,500,,X,6,",         # quality-flagged: kept with its flag
        "USC00417983,19500101,TMIN,-50,,,6,",          # -5.0 C -> 23.0 F
        "USC00417983,19500101,SNOW,0,,,6,",            # other element: ignored
    ]) + "\n"

    def run_quiet(self, fn, **kw):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = fn(self.root, **kw)
        return rc, buf.getvalue()

    def test_3_5_flags_kept_units_converted_missing_absent(self):
        gh.fetch, _ = fake_server({"USC00417983.csv.gz": (200, gzip.compress(self.BODY.encode()))})
        self.run_quiet(gh.collect, stations=["USC00417983"], pause=0)
        self.run_quiet(gh.normalize, stations=["USC00417983"])
        h = self.root / "data/history"
        prcp = (h / "ghcn-USC00417983-PRCP-daily.csv").read_text().splitlines()
        self.assertEqual(prcp, ["date,value,raw_value,unit,mflag,qflag,sflag",
                                "1950-01-01,1.0,254,in,,,6", "1950-01-02,0.0,0,in,T,,6"])
        tmax = (h / "ghcn-USC00417983-TMAX-daily.csv").read_text().splitlines()
        self.assertEqual(tmax[1:], ["1950-01-01,95.0,350,degF,,,6", "1950-01-02,122.0,500,degF,,X,6"])
        self.assertEqual((h / "ghcn-USC00417983-TMIN-daily.csv").read_text().splitlines()[1], "1950-01-01,23.0,-50,degF,,,6")
        m = json.loads((self.root / "data/model/ghcn-daily-manifest.json").read_text())
        self.assertEqual(next(f for f in m["files"] if f["element"] == "TMAX")["quality_flagged_rows"], 1)

    def test_unchanged_bytes_and_network_failure(self):
        body = gzip.compress(self.BODY.encode())
        gh.fetch, _ = fake_server({"USC00417983.csv.gz": (200, body)})
        self.run_quiet(gh.collect, stations=["USC00417983"], pause=0)
        self.run_quiet(gh.normalize, stations=["USC00417983"])
        out_csv = self.root / "data/history/ghcn-USC00417983-PRCP-daily.csv"
        t0 = out_csv.stat().st_mtime_ns
        rc, out = self.run_quiet(gh.collect, stations=["USC00417983"], pause=0)
        self.assertIn("UNCHANGED ghcn_daily USC00417983", out)
        rc, out = self.run_quiet(gh.normalize, stations=["USC00417983"])
        self.assertIn("UNCHANGED", out); self.assertEqual(out_csv.stat().st_mtime_ns, t0)
        gh.fetch, _ = fake_server({})
        rc, out = self.run_quiet(gh.collect, stations=["USC00417983"], pause=0)
        self.assertEqual(rc, 0); self.assertIn("SKIPPED — ghcn_daily: https://www.ncei.noaa.gov/pub/data/ghcn/daily/by_station/USC00417983.csv.gz unreachable", out)

    def test_malformed_line_names_file_and_line(self):
        gh.fetch, _ = fake_server({"USC00417983.csv.gz": (200, gzip.compress(b"USC00417983,19500101,PRCP,abc,,,6,\n"))})
        self.run_quiet(gh.collect, stations=["USC00417983"], pause=0)
        with self.assertRaises(ValueError) as e:
            self.run_quiet(gh.normalize, stations=["USC00417983"])
        self.assertIn("USC00417983.csv.gz:1: value 'abc'", str(e.exception))


class RunnerPlanTests(unittest.TestCase):
    def test_3_6_climate_steps_run_only_on_sunday_after_histories(self):
        names = lambda day: [s.name for s in runner.plan(day)]
        sunday, monday = dt.date(2026, 10, 11), dt.date(2026, 10, 12)
        climate = ["water.nclimdiv_collect", "water.nclimdiv_normalize", "water.ghcn_collect", "water.ghcn_normalize"]
        for c in climate:
            self.assertIn(c, names(sunday)); self.assertNotIn(c, names(monday))
        s = names(sunday)
        self.assertLess(s.index("water.nclimdiv_collect"), s.index("water.nclimdiv_normalize"))
        self.assertLess(s.index("water.ghcn_normalize"), s.index("water.publish_bundle"))


if __name__ == "__main__":
    unittest.main()
