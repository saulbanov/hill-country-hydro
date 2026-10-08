import contextlib, datetime as dt, io, json, shutil, tempfile, unittest
from pathlib import Path
from tools import usdm, nclimdiv as nc, operator_notices as on, daily_mac_run as runner
from tests.test_climate_collectors import Fixture, fake_server, drought_files, county_line, division_line, DATE


def week(d, d0="100.00", d1="55.26", d2="0.00"):
    return {"mapDate": f"{d}T00:00:00", "fips": "48209", "county": "Hays County", "state": "TX", "none": 0.0, "d0": float(d0),
            "d1": float(d1), "d2": float(d2), "d3": 0.0, "d4": 0.0, "validStart": f"{d}T00:00:00", "validEnd": f"{d}T23:59:59", "statisticFormatID": 1}


class UsdmTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="hydro-usdm-"))
        (self.root / "data").mkdir()
        (self.root / "data/noaa-counties.json").write_text(json.dumps({"counties": ["48209"]}))
        self.addCleanup(shutil.rmtree, self.root, True)
        self.addCleanup(setattr, usdm, "fetch", usdm.fetch)
        self.addCleanup(setattr, usdm, "today", usdm.today)
        usdm.today = lambda: dt.date(2026, 10, 8)
        self.calls = []

    def serve(self, rows):
        def fetch(url):
            self.calls.append(url)
            return (200, json.dumps(rows).encode(), None) if rows is not None else (0, b"", "network down")
        usdm.fetch = fetch

    def quiet(self, fn, **kw):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = fn(self.root, **kw) if fn is usdm.normalize else fn(self.root, pause=0, **kw)
        return rc, buf.getvalue()

    def test_5b_1_one_row_per_week_cumulative_as_given_missing_week_absent(self):
        self.serve([week("2026-09-29", d1="99.24"), week("2026-09-15"), week("2026-09-15")])  # 09-22 missing
        self.quiet(usdm.collect)
        self.quiet(usdm.normalize)
        rows = (self.root / "data/history/usdm-48209-weekly.csv").read_text().splitlines()
        self.assertEqual(rows[0], "map_date,none,d0,d1,d2,d3,d4,valid_start,valid_end,statistic_type,source_file")
        self.assertEqual([r.split(",")[0] for r in rows[1:]], ["2026-09-15", "2026-09-29"], "one row per week; no invented 09-22")
        self.assertTrue(rows[2].startswith("2026-09-29,0.0,100.0,99.24,0.0,0.0,0.0,2026-09-29,2026-09-29,1,data/captures/usdm/48209/"))
        self.assertIn("startdate=1%2F1%2F2000", self.calls[0], "a county with no history asks from 2000")

    def test_5b_2_no_new_map_one_probe_per_county_rewrites_nothing(self):
        self.serve([week("2026-09-29")])
        self.quiet(usdm.collect); self.quiet(usdm.normalize)
        files = [p for p in (self.root / "data").rglob("*") if p.is_file()]
        before = {p: (p.stat().st_mtime_ns, p.read_bytes()) for p in files}
        self.calls.clear()
        rc, out = self.quiet(usdm.collect)
        self.assertIn("UNCHANGED usdm: no new map for 1 counties", out)
        self.assertEqual(len(self.calls), 1, "one probe per county")
        self.assertIn("startdate=9%2F17%2F2026", self.calls[0], "the probe covers the last 21 days only")
        rc, out = self.quiet(usdm.normalize)
        self.assertIn("UNCHANGED", out)
        self.assertEqual(before, {p: (p.stat().st_mtime_ns, p.read_bytes()) for p in files})
        self.serve([week("2026-10-06"), week("2026-09-29")])
        self.quiet(usdm.collect); self.quiet(usdm.normalize)
        self.assertIn("2026-10-06", (self.root / "data/history/usdm-48209-weekly.csv").read_text(), "a new map is kept from the probe itself")

    def test_5b_3_network_failure_skips_and_exits_zero(self):
        self.serve(None)
        rc, out = self.quiet(usdm.collect)
        self.assertEqual(rc, 0)
        self.assertIn("SKIPPED — usdm: https://usdmdataservices.unl.edu/api/CountyStatistics/GetDroughtSeverityStatisticsByAreaPercent?aoi=48209", out)

    def test_bad_payload_names_the_source(self):
        usdm.fetch = lambda url: (200, b'[{"mapDate":"2026-01-01"}]', None)
        with self.assertRaises(ValueError) as e:
            self.quiet(usdm.collect)
        self.assertIn("row 1 lacks", str(e.exception))


class ClimdivDroughtTests(Fixture):
    def run_quiet(self, fn):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = fn(self.root)
        return rc, buf.getvalue()

    def test_5b_4_county_and_division_indices_map_to_fips_and_keep_ncdc(self):
        nc.fetch, _ = fake_server(self.climdiv_files())
        self.run_quiet(nc.collect); self.run_quiet(nc.normalize)
        h = self.root / "data/history"
        rows = (h / "climdiv-48209-pdsi-monthly.csv").read_text().splitlines()
        self.assertEqual(rows[0], "month,value,raw_value,unit,ncdc_id,source_file")
        self.assertEqual(rows[1], f"2023-01,-1.5,-1.50,index,41209,climdiv-pdsicy-v1.0.0-{DATE}")
        self.assertNotIn("2023-12", "".join(rows), "-99.99 is missing, never a value")
        div = (h / "climdiv-div4107-sp24-monthly.csv").read_text().splitlines()
        self.assertEqual(div[1], f"2023-01,0.5,0.50,index,4107,climdiv-sp24dv-v1.0.0-{DATE}")
        self.assertFalse((h / "climdiv-div4106-sp24-monthly.csv").exists(), "only divisions of the listed counties")

    def test_5b_4_unknown_county_code_fails_naming_the_line(self):
        files = self.climdiv_files()
        files.update({k: v for k, v in drought_files(county_extra=county_line("41999", "05", 2023, [1.0] * 12)).items() if "pdsicy" in k})
        nc.fetch, _ = fake_server(files)
        self.run_quiet(nc.collect)
        with self.assertRaises(ValueError) as e:
            self.run_quiet(nc.normalize)
        self.assertIn(f"climdiv-pdsicy-v1.0.0-{DATE}:3: NCDC county id 41999", str(e.exception))

    def test_5b_4_unknown_division_fails_naming_the_line(self):
        files = self.climdiv_files()
        files.update({k: v for k, v in drought_files(division_extra=division_line("4199", "77", 2023, [1.0] * 12)).items() if "sp24dv" in k})
        nc.fetch, _ = fake_server(files)
        self.run_quiet(nc.collect)
        with self.assertRaises(ValueError) as e:
            self.run_quiet(nc.normalize)
        self.assertIn(f"climdiv-sp24dv-v1.0.0-{DATE}:3: climate division 4199", str(e.exception))


class DeclarationPageTests(unittest.TestCase):
    def test_5b_5_declaration_pages_carry_a_valid_kind(self):
        pages = on.load_pages(Path(__file__).resolve().parents[1])
        kinds = {p["kind"] for p in pages}
        self.assertTrue({"drought_declaration", "water_restriction", "burn_ban", "outlook", "operator_access"} <= kinds, kinds)
        self.assertEqual(len({p["page_id"] for p in pages}), len(pages))

    def test_usdm_is_a_daily_step(self):
        for d in (dt.date(2026, 10, 12), dt.date(2026, 10, 11)):
            names = [s.name for s in runner.plan(d)]
            self.assertIn("water.usdm_collect", names); self.assertIn("water.usdm_normalize", names)


if __name__ == "__main__":
    unittest.main()
