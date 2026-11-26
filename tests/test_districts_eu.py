"""districts.json for Europe (pipeline/build/districts.py): the rule on synthetic places, the confidential-figure
estimate, and what the built file says about a few well-known cities.

What the real data shows (Eurostat regional accounts 2023 + SBS 2024):
* Frankfurt and Luxembourg are Finance cities: the Commercial hub is Frankfurt's strongest district (banking 2.9×
  the European share) and Luxembourg's (fund management and banking ~4.5×).
* Toulouse is an Aerospace city: aircraft, ships and trains (NACE C30) are ~9× the European share of jobs, though its
  manufacturing as a whole is below the norm, so the Industrial zone passes through that speciality.
* Brussels is the Capital city (public administration, education and health 1.27× Europe's share). Rome is not a
  government town in this data: Italy's public sector is small by European standards and Rome's share of these jobs
  is 0.9× Europe's (1.15× Italy's), so its strongest district is the Campus.
"""

import json
import unittest
from pathlib import Path

from pipeline.build import districts as D

WEB = Path(__file__).resolve().parents[1] / "web" / "data"


class FakeJobs:
    """part(r3, code) from a dict {(r3, code): (value, status)}."""

    def __init__(self, data):
        self.data = data

    def part(self, r3, code, year=None):
        return self.data.get((r3, code), (None, "none"))


class FakeNorm:
    def __init__(self, shares, country=None):
        self.shares, self._country = shares, country or {}

    def share(self, code):
        return self.shares.get(code)

    def of(self, codes):
        v = [self.shares[c] for c in codes if c in self.shares]
        return sum(v) if v else None

    def country(self, cc, code):
        return self._country.get((cc, code))


SHARES = {"J61": 0.003, "J62": 0.02, "J63": 0.003, "M71": 0.016, "M72": 0.003, "K": 0.023, "K64": 0.012,
          "K65": 0.0035, "K66": 0.007, "B": 0.002, "C": 0.137, "C30": 0.0035, "C29": 0.0105, "H50": 0.001,
          "H52": 0.013, "H51": 0.001, "O-Q": 0.24, "D": 0.005, "E": 0.006}


def place(values, status="ok"):
    return FakeJobs({("R1", k): (v, status) for k, v in values.items()})


class RuleTest(unittest.TestCase):
    TOTAL = 100_000

    def ds(self, values, **kw):
        return D.districts_of(place(values), FakeNorm(SHARES, kw.pop("country_shares", None)), [(1.0, "R1")],
                              self.TOTAL, **kw)

    def test_broad_district(self):
        ds = self.ds({"K": 6900, "K64": 4000, "K65": 400, "K66": 500})  # K is 3× Europe's share
        self.assertEqual([d["id"] for d in ds], ["commercial_hub"])
        d = ds[0]
        self.assertEqual(d["via"], "broad")
        self.assertAlmostEqual(d["lq"], 3.0, places=2)
        self.assertEqual(d["sub"], "K64")  # the strongest speciality with ≥ 1,000 jobs
        self.assertEqual(d["strength"], round(6900 - 6900 / 3.0))

    def test_specialty_district_and_badge(self):
        # Manufacturing below the norm, but aircraft 9× Europe's share with 3% of the jobs (Toulouse).
        ds = self.ds({"C": 10_000, "C30": 3150, "C29": 200, "B": 50, "J62": 2000, "M71": 3000, "M72": 400,
                      "J61": 300, "J63": 300})
        ind = next(d for d in ds if d["id"] == "industrial_zone")
        self.assertEqual(ind["via"], "specialty")
        self.assertLess(ind["lq"], D.MIN_LQ)
        self.assertEqual(ind["sub"], "C30")
        b = D.badge_of(ds, False, self.TOTAL)
        self.assertEqual(b["district"], "industrial_zone")  # a speciality ≥ 6× with ≥ 3% of the jobs wins the badge
        self.assertEqual(b["label"], "Aerospace city")
        self.assertIn("9.0×", b["text"])

    def test_shipyard_with_a_harbor(self):
        ds = self.ds({"C": 10_000, "C30": 3150, "H50": 600, "H52": 2000}, wet=True)
        self.assertIn("harbor", [d["id"] for d in ds])
        self.assertEqual(D.badge_of(ds, False, self.TOTAL)["label"], "Shipyard city")

    def test_harbor_and_aerodrome_tests(self):
        vals = {"H50": 600, "H52": 2000, "H51": 1500}
        self.assertEqual({d["id"] for d in self.ds(vals, wet=False, airport=False)}, set())
        self.assertEqual({d["id"] for d in self.ds(vals, wet=True, airport=True)}, {"harbor", "aerodrome"})
        self.assertEqual({d["id"] for d in self.ds(vals)}, {"harbor", "aerodrome"})  # None = no test

    def test_government_plaza_needs_its_country_unless_capital(self):
        vals = {"O-Q": 33_000}  # 1.375× Europe's share
        rich = {("XX", "O-Q"): 0.32}  # but only 1.03× its own country's
        self.assertEqual(self.ds(vals, country="XX", country_shares=rich), [])
        cap = self.ds(vals, country="XX", country_shares=rich, capital=True)
        self.assertEqual([d["id"] for d in cap], ["government_plaza"])
        self.assertAlmostEqual(cap[0]["lq_country"], 1.03, places=2)
        self.assertEqual(D.badge_of(cap, True, self.TOTAL)["label"], "Capital city")
        poor = {("XX", "O-Q"): 0.25}  # 1.32× its country's
        self.assertEqual([d["id"] for d in self.ds(vals, country="XX", country_shares=poor)], ["government_plaza"])
        self.assertEqual(D.badge_of(self.ds(vals, country="XX", country_shares=poor), False, self.TOTAL)["label"],
                         "Government town")

    def test_withheld_is_a_lower_bound(self):
        jobs = FakeJobs({("R1", "D"): (0.0, "held"), ("R1", "E"): (2000, "ok"), ("R2", "D"): (1500, "ok"),
                         ("R2", "E"): (0.0, "held")})
        emp, sup, est = D.aggregate(jobs, [(1.0, "R1"), (0.5, "R2")], ["D", "E"])
        self.assertEqual(emp, 2750)
        self.assertEqual(sup, 2)
        self.assertEqual(est, 0)

    def test_no_figures_is_none(self):
        self.assertEqual(D.aggregate(FakeJobs({}), [(1.0, "R1")], ["K64"]), (None, 0, 0))

    def test_max_five_sorted_by_strength(self):
        vals = {k: SHARES[k] * self.TOTAL * 3 for k in SHARES if k not in ("C", "O-Q")}
        ds = self.ds(vals)
        self.assertLessEqual(len(ds), D.MAX_PER_CITY)
        self.assertEqual([d["strength"] for d in ds], sorted((d["strength"] for d in ds), reverse=True))


class FakeStats:
    gdp_year = "2023"

    def __init__(self, emp):
        self.emp = emp

    def value(self, table, code, geo, year):
        return self.emp.get((geo, code))


class WithheldEstimateTest(unittest.TestCase):
    """A confidential NUTS 2 figure is what the NUTS 1 total leaves over, shared out by the size of the section."""

    def setUp(self):
        sbs = {
            "years": ["2024"],
            "values": {
                "XX1": {"2024": {"H51": 1000, "H": 30000} | {f"P{i}": 1 for i in range(20)}},
                "XX11": {"2024": {"H51": 400, "H": 10000} | {f"P{i}": 1 for i in range(20)}},
                "XX12": {"2024": {"H": 15000} | {f"P{i}": 1 for i in range(20)}},
                "XX13": {"2024": {"H": 5000} | {f"P{i}": 1 for i in range(20)}},
            },
            "withheld": {"XX12": {"2024": ["H51"]}, "XX13": {"2024": ["H51"]}},
        }
        emp = {(g, "G-I"): 10.0 for g in ("XX111", "XX121", "XX122", "XX131")}
        self.jobs = D.Jobs(FakeStats(emp), sbs, ["XX111", "XX121", "XX122", "XX131"])

    def test_estimate(self):
        v, st = self.jobs.sbs("XX12", "H51")
        self.assertEqual(st, "est")
        self.assertAlmostEqual(v, 600 * 15000 / 20000)  # (1000 − 400) shared 15:5
        self.assertAlmostEqual(self.jobs.sbs("XX13", "H51")[0], 600 * 5000 / 20000)
        self.assertEqual(self.jobs.sbs("XX11", "H51"), (400, "ok"))

    def test_share_out_to_nuts3(self):
        # XX12's estimate split between its two NUTS 3 regions by their trade-transport-hotels jobs (equal here)
        v, st = self.jobs.part("XX121", "H51")
        self.assertEqual(st, "est")
        self.assertAlmostEqual(v, 450 / 2)

    def test_not_published(self):
        self.assertEqual(self.jobs.sbs("XX11", "K64"), (None, "none"))


@unittest.skipUnless((WEB / "districts.json").exists(), "districts.json not built")
class BuiltFileTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = json.loads((WEB / "districts.json").read_text())
        cls.cities = {c["id"]: c for c in json.loads((WEB / "cities.json").read_text())}

    def row(self, name):
        ids = [k for k, c in self.cities.items() if c["name"] == name]
        self.assertTrue(ids, name)
        r = self.doc["cities"][ids[0]]
        self.assertIsNotNone(r, name)
        return r

    def test_shape(self):
        self.assertEqual([c["id"] for c in self.doc["catalog"]],
                         ["campus", "commercial_hub", "industrial_zone", "harbor", "theater_square",
                          "entertainment_complex", "aerodrome", "government_plaza", "encampment", "aqueduct"])
        self.assertTrue(self.doc["rule"]["text"])
        self.assertLessEqual(set(self.doc["cities"]), set(self.cities))
        self.assertEqual([lvl for lvl, _ in D.check(WEB) if lvl == "FAIL"], [])

    def test_finance(self):
        fra = self.row("Frankfurt")
        self.assertEqual(fra["districts"][0]["id"], "commercial_hub")
        self.assertEqual(fra["badge"]["label"], "Finance city")
        self.assertEqual(fra["districts"][0]["sub"], "K64")
        lux = self.row("Luxembourg")
        hub = next(d for d in lux["districts"] if d["id"] == "commercial_hub")
        self.assertGreater(hub["lq"], 3)
        self.assertEqual(lux["badge"]["district"], "commercial_hub")

    def test_aerospace(self):
        tls = self.row("Toulouse")
        ind = next(d for d in tls["districts"] if d["id"] == "industrial_zone")
        self.assertEqual(ind["sub"], "C30")
        self.assertGreater(ind["sub_lq"], 5)
        self.assertEqual(tls["badge"]["label"], "Aerospace city")

    def test_government(self):
        bru = self.row("Brussels")
        self.assertIn("government_plaza", [d["id"] for d in bru["districts"]])
        self.assertEqual(bru["badge"]["label"], "Capital city")
        rome = self.row("Rome")  # see the module docstring
        self.assertNotIn("government_plaza", [d["id"] for d in rome["districts"]])

    def test_harbor_and_airport(self):
        self.assertEqual(self.row("Hamburg")["badge"]["label"], "Port city")
        fra = self.row("Frankfurt")
        self.assertIn("aerodrome", [d["id"] for d in fra["districts"]])
        self.assertEqual(self.row("Wolfsburg")["badge"]["label"], "Car city")


if __name__ == "__main__":
    unittest.main()
