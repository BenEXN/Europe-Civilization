"""defi.json: the daily challenge's pool (pipeline/build/challenge.py)."""

import json
import re
import unittest

from pipeline.build.challenge import norm
from pipeline.core.paths import WEB_DATA


@unittest.skipUnless((WEB_DATA / "defi.json").exists(), "defi.json not built")
class Pool(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = json.loads((WEB_DATA / "defi.json").read_text())
        cls.col = {c: k for k, c in enumerate(cls.d["columns"])}

    def test_tiers_cover_the_pattern(self):
        for t in self.d["pattern"]:
            self.assertGreaterEqual(len(self.d["tiers"][t]), 100, t)

    def test_no_name_already_on_the_map(self):
        on_map = {norm(c["name"]) for c in json.loads((WEB_DATA / "cities.json").read_text())}
        on_map |= {norm(c["local_name"]) for c in json.loads((WEB_DATA / "cities.json").read_text()) if c.get("local_name")}
        for rows in self.d["tiers"].values():
            self.assertFalse([r for r in rows if norm(r[self.col["name"]]) in on_map])

    def test_each_commune_once(self):
        codes = [r[self.col["code"]] for rows in self.d["tiers"].values() for r in rows]
        self.assertEqual(len(codes), len(set(codes)))

    def test_tiers_by_population(self):
        pop = self.col["pop"]
        self.assertTrue(all(r[pop] >= 60_000 for r in self.d["tiers"]["facile"]))
        self.assertTrue(all(8_000 <= r[pop] < 20_000 for r in self.d["tiers"]["difficile"]))

    def test_latin_names_and_no_districts(self):
        name = self.col["name"]
        for rows in self.d["tiers"].values():
            self.assertFalse([r[name] for r in rows if re.search("[\u0370-\u04ff\\d]", r[name])])

    def test_norm(self):
        self.assertEqual(norm("Saint-Étienne-de-Chigny"), "saint etienne de chigny")


if __name__ == "__main__":
    unittest.main()
