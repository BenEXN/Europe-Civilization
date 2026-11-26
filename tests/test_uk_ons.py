"""sources/uk_ons.py: the pure helpers, then sanity checks on data/interim/uk_ons.json (skipped when it is missing)."""

import json
import unittest

from pipeline.core.europe import EU
from pipeline.core.geo import Shape
from pipeline.core.paths import INTERIM
from pipeline.sources import uk_ons


class HelperTest(unittest.TestCase):
    def test_uk_code(self):
        self.assertEqual(uk_ons.uk_code("TLC31"), "UKC31")
        self.assertEqual(uk_ons.uk_code("TLN0"), "UKN0")
        self.assertEqual(uk_ons.uk_code("TLI"), "UKI")
        self.assertEqual(uk_ons.uk_code("K02000001"), "UK")
        with self.assertRaises(ValueError):
            uk_ons.uk_code("E06000001")

    def test_median_age(self):
        self.assertAlmostEqual(uk_ons.median_age([10, 10]), 1.0)  # half of 20 reached at the end of age 0
        self.assertAlmostEqual(uk_ons.median_age([0, 4, 0, 4]), 2.0)  # half reached at the end of age 1
        self.assertAlmostEqual(uk_ons.median_age([2, 2, 2, 2]), 2.0)
        self.assertIsNone(uk_ons.median_age([0, 0]))

    def test_interior_point_of_a_u_shape(self):
        # A U whose centroid falls in the notch: the point must still be inside.
        u = [(0, 0), (3, 0), (3, 3), (2, 3), (2, 1), (1, 1), (1, 3), (0, 3), (0, 0)]
        x, y = uk_ons.interior_point([u])
        self.assertTrue(Shape([u]).contains(x, y), (x, y))
        square = [(0, 0), (2, 0), (2, 2), (0, 2), (0, 0)]
        self.assertEqual(uk_ons.interior_point([square]), (1.0, 1.0))

    def test_norm_name(self):
        self.assertEqual(uk_ons.norm_name("Eilean á Chèo"), "eilean a cheo")
        self.assertEqual(uk_ons.norm_name("Fens & Greatham"), "fens and greatham")

    def test_jsonstat(self):
        d = {"id": ["geo", "time"], "size": [1, 2],
             "dimension": {"geo": {"category": {"index": {"UK": 0}}},
                           "time": {"category": {"index": {"2023": 0, "2024": 1}}}},
             "value": {"1": 0.85}}
        self.assertEqual(uk_ons.jsonstat(d), [({"geo": "UK", "time": "2024"}, 0.85)])

    def test_num(self):
        self.assertEqual(uk_ons.num("1,234"), 1234.0)
        for marker in ("[x]", "[c]", "*", "", None, ".."):
            self.assertIsNone(uk_ons.num(marker))


@unittest.skipUnless((INTERIM / "uk_ons.json").exists(), "data/interim/uk_ons.json missing: run pipeline process uk_ons")
class InterimTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = json.loads((INTERIM / "uk_ons.json").read_text())["data"]
        cls.t = cls.d["tables"]
        es = INTERIM / "eurostat.json"
        cls.es = json.loads(es.read_text())["data"]["tables"] if es.exists() else None

    def latest(self, row):
        y = max(row)
        return y, row[y]

    def test_regions(self):
        nuts = self.d["nuts"]
        by_level = {lv: [n for n in nuts if n["level"] == lv] for lv in range(4)}
        print(f"\n  regions: {[len(by_level[lv]) for lv in range(4)]} (UK, ITL1, ITL2, ITL3)")
        self.assertEqual([len(by_level[lv]) for lv in range(3)], [1, 12, 46])
        self.assertTrue(175 <= len(by_level[3]) <= 190)
        keys = ["code", "level", "country", "name", "local", "mount", "urban", "coast"]
        for n in nuts:
            self.assertEqual(list(n)[:8], keys)
            self.assertEqual(n["country"], "UK")
            self.assertTrue(n["code"].startswith("UK"))
            self.assertEqual(bool(n.get("county")), n["level"] == 3)
            self.assertEqual("rings" in n, n["level"] == 3)
        size = len(json.dumps([n["rings"] for n in by_level[3]]))
        print(f"  ITL3 rings: {size / 1e6:.2f} MB")
        self.assertLess(size, 3e6)

    def test_population(self):
        pop = self.t["pop3"]["NR|T|TOTAL"]
        y, uk = self.latest(pop["UK"])
        itl3 = sum(row[y] for g, row in pop.items() if len(g) == 5 and y in row)
        print(f"\n  population {y} (mid-{int(y) - 1}): UK {uk:,}, ITL3 sum {itl3:,}")
        self.assertLess(abs(itl3 / uk - 1), 0.01)
        self.assertTrue(68.5e6 < uk < 71e6, uk)
        parts = sum(self.t["pop3"][k]["UK"][y] for k in ("NR|T|Y_LT15", "NR|T|Y15-64", "NR|T|Y_GE65"))
        self.assertLess(abs(parts - uk), 10)
        med = self.t["medage3"]["MEDAGEPOP|YR"]["UK"][y]
        print(f"  median age {med}")
        self.assertTrue(38 < med < 43)
        self.assertEqual(self.t["pop0"]["NR|TOTAL|T"]["UK"][y], uk)

    def test_wards(self):
        lau = self.d["lau"]
        self.assertEqual(lau["columns"], ["id", "country", "name", "pop", "area", "lon", "lat"])
        rows = lau["rows"]
        total = sum(r[3] or 0 for r in rows)
        print(f"\n  wards: {len(rows):,}, census population {total:,}, "
              f"{sum(1 for r in rows if r[3] is None)} without population")
        self.assertTrue(8300 <= len(rows) <= 8600)
        self.assertLess(abs(total / 67e6 - 1), 0.02)
        self.assertEqual(len({r[0] for r in rows}), len(rows))
        for r in rows:
            self.assertTrue(r[0].startswith("UK_"))
            self.assertTrue(-8.7 < r[5] < 1.8 and 49.8 < r[6] < 60.9, r)
            self.assertGreater(r[4], 0)

    def test_gdp(self):
        gdp = self.t["gdp3"]
        uk23 = gdp["MIO_EUR"]["UK"]["2023"]
        print(f"\n  UK GDP 2023: {uk23 / 1e6:.2f} trillion euros")
        self.assertTrue(2.8e6 < uk23 < 3.6e6, uk23)
        self.assertEqual(self.t["gdp0"]["CP_MEUR|B1GQ"]["UK"]["2023"], round(uk23, 1))
        # London has the highest GDP per head of the ITL1 regions.
        y = max(gdp["EUR_HAB"]["UKI"])
        itl1 = {g: row[y] for g, row in gdp["EUR_HAB"].items() if len(g) == 3}
        print(f"  GDP per head {y}, ITL1: " + ", ".join(f"{g} {v:,}" for g, v in sorted(itl1.items(), key=lambda t: -t[1])))
        self.assertEqual(max(itl1, key=itl1.get), "UKI")

    @unittest.skipIf(not (INTERIM / "eurostat.json").exists(), "eurostat interim missing")
    def test_pps_against_eu(self):
        y = "2023"
        gdp0, pop0 = self.es["gdp0"]["series"]["CP_MEUR|B1GQ"], self.es["pop0"]["series"]["NR|TOTAL|T"]
        eu = sum(gdp0[c][y] for c in EU) * 1e6 / sum(pop0[c][y] for c in EU)  # EU27: one PPS is one euro
        uk = self.t["gdp3"]["PPS_EU27_2020_HAB"]["UK"][y]
        vi = self.t["gdpidx0"]["VI_PPS_EU27_2020_HAB|GDP"]["UK"][y]
        print(f"\n  GDP per head {y}: UK {uk:,} PPS, EU27 {eu:,.0f}; ratio {uk / eu:.3f}, Eurostat index {vi}")
        self.assertLess(abs(uk / (0.98 * eu) - 1), 0.10)
        self.assertLess(abs(uk / (vi / 100 * eu) - 1), 0.10)

    def test_urban_audit(self):
        fuas, cities = self.d["fuas"], self.d["cities"]
        codes = {f["code"] for f in fuas}
        print(f"\n  {len(fuas)} FUAs, {len(cities)} cities")
        self.assertTrue(80 <= len(fuas) <= 95)
        self.assertIn("UK001F", codes)
        london = next(f for f in fuas if f["code"] == "UK001F")
        self.assertTrue(london["nuts3"].startswith("UKI"))
        capital = [c for c in cities if c["capital"]]
        self.assertEqual([c["code"] for c in capital], ["UK001C"])
        self.assertTrue(-0.2 < capital[0]["lon"] < 0.0 and 51.48 < capital[0]["lat"] < 51.54, capital[0])
        self.assertTrue(capital[0]["nuts3"].startswith("UKI3"), capital[0])
        itl3 = {n["code"] for n in self.d["nuts"] if n["level"] == 3}
        for c in cities:
            self.assertIn(c["fua"], codes)
            self.assertIn(c["nuts3"], itl3)
            self.assertTrue(c["code"].endswith("C"))
        for f in fuas:
            self.assertIn(f["nuts3"], itl3)
            self.assertTrue(f["rings"])

    def test_tables_cover_the_levels(self):
        itl = {lv: {n["code"] for n in self.d["nuts"] if n["level"] == lv} for lv in range(4)}
        for t in ("pop3", "medage3", "gdp3", "gva3", "emp3"):
            for key, series in self.t[t].items():
                for lv in range(4):
                    self.assertLessEqual(itl[lv], set(series), (t, key, lv))
        for t in ("unemp2", "emprate2", "tertiary2", "income2", "lifeexp2"):
            for key, series in self.t[t].items():
                for lv in (0, 1, 2):
                    self.assertLessEqual(itl[lv], set(series), (t, key, lv))
        jobs = self.t["emp3"]
        total = jobs["THS|EMP|TOTAL"]["UK"]["2024"]
        branches = sum(jobs[f"THS|EMP|{b}"]["UK"]["2024"] for b in uk_ons.BRANCHES if b not in ("TOTAL", "C"))
        print(f"\n  jobs 2024: {total:,.0f} thousand")
        self.assertLess(abs(branches - total), 1)
        self.assertTrue(30_000 < total < 36_000)

    @unittest.skipIf(not (INTERIM / "eurostat.json").exists(), "eurostat interim missing")
    def test_series_keys_match_eurostat(self):
        for t, series in self.t.items():
            self.assertIn(t, self.es)
            self.assertLessEqual(set(series), set(self.es[t]["series"]), t)
            for s in series.values():
                for row in s.values():
                    for y in row:
                        self.assertRegex(y, r"^\d{4}$")

    def test_every_year_everywhere(self):
        """pop3 (all age bands) and medage3 for every region and the UK, mid-2013…mid-2025 (filed 2014-2026); jobs
        for 2023 (the map's economic year) and 2024."""
        geos = {n["code"] for n in self.d["nuts"]}
        years = {str(y) for y in range(2014, 2027)}
        for t, series in (("pop3", self.t["pop3"]), ("medage3", self.t["medage3"])):
            for key, s in series.items():
                for g in geos:
                    self.assertLessEqual(years, set(s.get(g, {})), (t, key, g))
        for key, s in list(self.t["emp3"].items()) + list(self.t["emp0"].items()):
            for g in (geos if key.startswith("THS|EMP") else {"UK"}):
                self.assertLessEqual({"2023", "2024"}, set(s[g]), (key, g))
        j23, j24 = (self.t["emp3"]["THS|EMP|TOTAL"]["UK"][y] for y in ("2023", "2024"))
        print(f"\n  jobs: 2023 {j23:,.0f}, 2024 {j24:,.0f} thousand")
        self.assertLess(abs(j23 / j24 - 1), 0.05)

    def test_airports(self):
        ref = json.loads((INTERIM / "airports.json").read_text())["data"] if (INTERIM / "airports.json").exists() else None
        air = self.d["airports"]
        traffic, pos = air["traffic"], air["positions"]
        lhr = traffic["EGLL"]["pax"]["2024"]
        print(f"\n  airports: {len(traffic)}, Heathrow 2024 {lhr / 1e6:.1f} M passengers")
        self.assertTrue(80e6 < lhr < 87e6, lhr)
        self.assertTrue(30 <= len(traffic) <= 70)
        for icao in ("EGJJ", "EGJB", "EGJA", "EGNS"):  # Jersey, Guernsey, Alderney, Isle of Man
            self.assertNotIn(icao, traffic)
        self.assertLessEqual(set(pos), set(traffic))
        for icao, t in traffic.items():
            self.assertEqual(t["country"], "UK")
            self.assertTrue(icao.startswith("EG"), icao)
            if t["pax"].get("2024", 0) >= 50_000:  # closed airports (Doncaster Sheffield…) may lack a position
                self.assertIn(icao, pos)
        for icao, p in pos.items():
            self.assertTrue(-8.7 < p["lon"] < 1.8 and 49.8 < p["lat"] < 60.9, icao)
        if ref:
            some = next(iter(ref["traffic"].values()))
            self.assertEqual(set(traffic["EGLL"]), set(some))
            self.assertEqual(set(pos["EGLL"]), set(next(iter(ref["positions"].values()))))

    def test_ports(self):
        ports = self.d["ports"]
        total = sum(p["tons"] for p in ports)
        print(f"\n  ports: {len(ports)} major ports, {ports[0]['year']}: {total / 1e6:.1f} Mt; top: "
              + ", ".join(f"{p['name']} {p['tons'] / 1e6:.1f}" for p in ports[:3]))
        self.assertTrue(380e6 < total < 460e6, total)
        top = [p["code"] for p in ports[:4]]
        self.assertIn("UK_GBLON", top)
        self.assertIn("UK_GBIMM", top)
        keys = ["code", "country", "name", "eurostat_name", "area", "locode", "locode_name", "tons", "in", "out", "year",
                "positions"]
        for p in ports:
            self.assertEqual(list(p), keys)
            self.assertEqual(set(p["positions"]), {"locode", "wikidata"})
            self.assertTrue(p["positions"]["locode"] or p["positions"]["wikidata"], p["name"])
            if p["in"] is not None and p["out"] is not None:
                self.assertLess(abs(p["in"] + p["out"] - p["tons"]), 0.01 * p["tons"] + 1000, p["name"])
        ref = INTERIM / "ports.json"
        if ref.exists():
            self.assertEqual(list(json.loads(ref.read_text())["data"]["ports"][0]), keys)

    def test_notes(self):
        notes = self.d["notes"]
        text = " ".join(notes)
        for word in ("gross disposable", "AB", "self-employed", "16-64", "middle year", "1 January", "2022 census"):
            self.assertIn(word.lower(), text.lower(), word)


if __name__ == "__main__":
    unittest.main()
