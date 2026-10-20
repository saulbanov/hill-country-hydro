import contextlib, datetime as dt, gzip, io, json, shutil, tempfile, unittest, zipfile
from pathlib import Path
from tools import twdb_groundwater_use as tw, usgs_field_measurements as fm, daily_mac_run as runner

HEADER = ("WellReportTrackingNumber|DateSubmitted|OwnerName|OwnerAddress1|County|TypeOfWork|ProposedUse|DrillingStartDate|"
          "DrillingEndDate|NumberOfWellsDrilled|Comments|CompanyName|DrillerName|DrillerSigned")


def sdr_zip(lines):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("SDRDownload/WellData.txt", "\n".join([HEADER] + lines) + "\n")
    return buf.getvalue()


def server(files):
    def fetch(url):
        for suffix, (status, body) in files.items():
            if suffix in url:
                return status, body, None if status == 200 else f"HTTP {status}"
        return 0, b"", "network down"
    return fetch


class Base(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="hydro-gwuse-"))
        (self.root / "data").mkdir()
        (self.root / "data/noaa-counties.json").write_text(json.dumps({"counties": ["48209", "48453"], "names": {"48209": "Hays", "48453": "Travis"}}))
        self.addCleanup(shutil.rmtree, self.root, True)
        for mod in (tw, fm):
            self.addCleanup(setattr, mod, "fetch", mod.fetch)

    def quiet(self, fn, **kw):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = fn(self.root, **kw)
        return rc, buf.getvalue()


class TwdbTests(Base):
    LINES = ["1|2020-01-02|Jane Owner|12 Secret Rd|Hays|New Well|Domestic|2019-12-01|2019-12-03|1|ok|Acme Drilling|Bob Driller|Bob D",
             "2|2021-05-02|Ann Owner|9 Hidden Ln|Hays|Replacement|Domestic|2021-04-01||1|start date only|Acme Drilling|Bob Driller|Bob D",
             "3|2021-06-02|Al Owner|1 Way|Travis|New Well|Irrigation|2021-06-01|2021-06-02|1|split",
             "comment|Acme Drilling|Bob Driller|Bob D",
             "4|2022-01-01|Ed Owner|5 Rd|Hays|New Well|Domestic|2021-12-01|2021-12-02|1|stray|pipe|Acme Drilling|Bob Driller|Bob D",
             "5|2022-01-01|Out Owner|5 Rd|Lubbock|New Well|Domestic|2021-12-01|2021-12-02|1|x|Acme|Bob|Bob"]

    def test_4_1_no_owner_or_driller_names_written_anywhere_versioned(self):
        tw.fetch = server({"SDRDownload.zip": (200, sdr_zip(self.LINES))})
        rc, out = self.quiet(tw.collect)
        self.assertIn("MALFORMED", out); self.assertIn("'4'", out)
        self.quiet(tw.normalize)
        written = [p for p in self.root.rglob("*") if p.is_file() and "raw" not in p.parts]
        blob = b"".join(gzip.decompress(p.read_bytes()) if p.suffix == ".gz" else p.read_bytes() for p in written)
        for name in (b"Jane Owner", b"Secret Rd", b"Acme Drilling", b"Bob Driller", b"Ann Owner", b"Hidden Ln"):
            self.assertNotIn(name, blob, name)
        hays = (self.root / "data/history/twdb-wells-drilled-48209-annual.csv").read_text().splitlines()
        self.assertEqual(hays[0], "year,aquifer,use,count,source_file,type_of_work")
        self.assertIn('2019,,"Domestic",1,SDRDownload.zip:SDRDownload/WellData.txt,"New Well"', hays)
        self.assertIn('2021,,"Domestic",1,SDRDownload.zip:SDRDownload/WellData.txt,"Replacement"', hays, "start date used when the end is blank")
        self.assertEqual(len(hays), 3, "the malformed record 4 is excluded, not guessed at")
        travis = (self.root / "data/history/twdb-wells-drilled-48453-annual.csv").read_text()
        self.assertIn('2021,,"Irrigation",1', travis, "a record split by a line break is joined, not dropped")
        m = json.loads((self.root / "data/model/twdb-groundwater-use-manifest.json").read_text())
        self.assertEqual([x["tracking_number"] for x in m["sdr"]["malformed_records"]], ["4"])

    def test_4_2_pumpage_disabled_and_network_failure_skips(self):
        rc, out = self.quiet(tw.pumpage)
        self.assertEqual(rc, 0); self.assertIn("DISABLED — twdb_groundwater_use pumpage", out)
        self.assertIn("SumFinal_CountyPumpage", out)
        tw.fetch = server({})
        rc, out = self.quiet(tw.collect)
        self.assertEqual(rc, 0); self.assertIn("SKIPPED — twdb_groundwater_use: https://www.twdb.texas.gov/groundwater/data/SDRDownload.zip unreachable", out)

    def test_truncated_zip_member_fails_with_line(self):
        tw.fetch = server({"SDRDownload.zip": (200, sdr_zip(["9|2020-01-02|X|Y|Hays|New Well"]))})
        with self.assertRaises(ValueError) as e:
            self.quiet(tw.collect)
        self.assertIn("WellData.txt:2: last record is incomplete", str(e.exception))

    def test_unchanged_bytes(self):
        tw.fetch = server({"SDRDownload.zip": (200, sdr_zip(self.LINES))})
        self.quiet(tw.collect); self.quiet(tw.normalize)
        rc, out = self.quiet(tw.collect)
        self.assertIn("UNCHANGED twdb_groundwater_use", out)


class FieldTests(Base):
    def page(self, feats, nxt=None):
        return json.dumps({"features": feats, "links": [{"rel": "next", "href": nxt}] if nxt else []}).encode()

    def feat(self, i, date, param, value, st="08170990"):
        return {"id": f"m{i}", "properties": {"monitoring_location_id": f"USGS-{st}", "time": date, "parameter_code": param,
                                             "value": value, "unit_of_measure": "ft^3/s" if param == "00060" else "ft", "qualifier": None}}

    def test_4_3_normalizes_and_follows_next_links(self):
        p2 = "https://api.waterdata.usgs.gov/ogcapi/v1/collections/field-measurements/items?page=2"
        fm.fetch = server({"page=2": (200, self.page([self.feat(3, "1999-05-01", "00060", "12.5")])),
                           "USGS-08170990": (200, self.page([self.feat(1, "2011-01-07", "00060", "3.47"),
                                                             self.feat(2, "2013-02-01", "00065", "nope")], nxt=p2))})
        self.quiet(fm.collect, stations=["08170990"], pause=0)
        self.quiet(fm.normalize, stations=["08170990"])
        rows = (self.root / "data/history/08170990-field-measurements.csv").read_text().splitlines()
        self.assertEqual(rows[0], "date,parameter,value,unit,measurement_id,qualifier")
        self.assertEqual(rows[1], "1999-05-01,00060,12.5,ft^3/s,m3,", "the second page is read and rows sort by date")
        self.assertIn("2013-02-01,00065,,ft,m2,", rows, "a non-numeric value is absent, never zero")

    def test_4_3_empty_response_writes_empty_csv_and_note(self):
        fm.fetch = server({"USGS-08155500": (200, self.page([]))})
        self.quiet(fm.collect, stations=["08155500"], pause=0)
        rc, out = self.quiet(fm.normalize, stations=["08155500"])
        self.assertEqual((self.root / "data/history/08155500-field-measurements.csv").read_text(),
                         "date,parameter,value,unit,measurement_id,qualifier\n")
        m = json.loads((self.root / "data/model/usgs-field-measurements-manifest.json").read_text())
        self.assertEqual(m["files"][0]["note"], "the provider returned no field measurements for this station")

    def test_network_failure_skips_and_exits_zero(self):
        fm.fetch = server({})
        rc, out = self.quiet(fm.collect, stations=["08170990"], pause=0)
        self.assertEqual(rc, 0); self.assertIn("SKIPPED — usgs_field_measurements:", out)


class PlanTests(unittest.TestCase):
    def test_twdb_first_sunday_only_field_every_sunday(self):
        names = lambda d: [s.name for s in runner.plan(d)]
        first, third, monday = dt.date(2026, 10, 4), dt.date(2026, 10, 18), dt.date(2026, 10, 5)
        self.assertIn("water.twdb_gwuse_collect", names(first))
        self.assertNotIn("water.twdb_gwuse_collect", names(third))
        self.assertIn("water.field_measurements_collect", names(third))
        self.assertNotIn("water.field_measurements_collect", names(monday))


if __name__ == "__main__":
    unittest.main()
