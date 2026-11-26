"""citizens.json for Europe (pipeline/build/citizens.py): shapes, rounding and a few known cities."""

import json
import unittest

from pipeline.build import citizens
from pipeline.core.paths import WEB_DATA

PATH = WEB_DATA / "citizens.json"
ROWS = ["workforce", "age", "commute", "education", "nativity"]


class LargestRemainderTest(unittest.TestCase):
    def test_sums_to_n_and_ties_go_to_the_earlier_key(self):
        self.assertEqual(citizens.largest_remainder({"a": 1, "b": 1, "c": 1}, ["a", "b", "c"], 10),
                         {"a": 4, "b": 3, "c": 3})
        f = citizens.largest_remainder({"a": 0.333, "b": 0.5, "c": 0.167}, ["a", "b", "c"], 20)
        self.assertEqual(sum(f.values()), 20)
        self.assertIsNone(citizens.largest_remainder({"a": 0}, ["a"], 10))

    def test_interpolated_median(self):
        self.assertEqual(citizens.interpolated_median([(0, 10, 50), (10, 20, 50)]), 10.0)
        self.assertEqual(citizens.interpolated_median([(0, 10, 25), (10, 20, 50), (20, None, 25)]), 15.0)


@unittest.skipUnless(PATH.exists(), "citizens.json not built")
class CitizensFileTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = json.loads(PATH.read_text())
        cls.keys = {r: [g["key"] for g in cls.doc["groups"][r]] for r in ROWS}

    def assert_row(self, rid, row):
        self.assertEqual(set(row["counts"]), set(self.keys[rid]), rid)
        self.assertEqual(sum(row["counts"].values()), row["total"], rid)
        self.assertAlmostEqual(sum(row["shares"].values()), 1.0, delta=0.01, msg=rid)
        if rid in self.doc["figures"]:
            self.assertEqual(sum(row["figures"].values()), self.doc["figures"][rid], rid)

    def test_big_cities_have_rows(self):
        for cid in ("FR001F", "DE003F", "PL001F"):  # Paris, Munich, Warsaw
            row = self.doc["cities"].get(cid)
            self.assertIsNotNone(row, cid)
            for rid in ("workforce", "age", "education", "nativity"):
                self.assertIsNotNone(row[rid], f"{cid} {rid}")
                self.assert_row(rid, row[rid])
            self.assertTrue(30 < row["age"]["median"] < 55, cid)
        self.assertIsNotNone(self.doc["cities"]["FR001F"]["commute"])
        self.assertIsNotNone(self.doc["cities"]["DE003F"]["commute"])

    def test_every_row_adds_up(self):
        for rid in ROWS:
            self.assert_row(rid, self.doc["national"][rid])
        for cid, row in self.doc["cities"].items():
            if row is None:
                continue
            for rid in ROWS:
                if row[rid] is not None:
                    self.assert_row(rid, row[rid])
                    self.assertIn(row[rid]["level"], ("fua", "city"))

    def test_geonames_towns_are_null_and_specialists_are_real_categories(self):
        towns = [cid for cid in self.doc["cities"] if cid.startswith("GN")]
        self.assertTrue(all(self.doc["cities"][cid] is None for cid in towns))
        for row in filter(None, self.doc["cities"].values()):
            for s in row["specialists"]:
                self.assertIn(s["key"], self.keys[s["row"]])
                self.assertTrue(s["ratio"] >= 1.5 or s["ratio"] <= 0.67)

    def test_builder_check_passes(self):
        levels = [lv for lv, _ in citizens.check(WEB_DATA)]
        self.assertIn("PASS", levels)
        self.assertNotIn("FAIL", levels)


if __name__ == "__main__":
    unittest.main()
