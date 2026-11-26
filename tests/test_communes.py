"""communes.json: one row per local unit, each on a hex of its country, urban areas that exist in cities.json."""

import json
import unittest

from pipeline.core.paths import WEB_DATA


@unittest.skipUnless((WEB_DATA / "communes.json").exists(), "communes.json not built")
class Communes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        d = json.loads((WEB_DATA / "communes.json").read_text())
        cls.rows = [dict(zip(d["columns"], r)) for r in d["rows"]]
        world = json.loads((WEB_DATA / "world.json").read_text())
        cls.size = world["grid"]["cols"] * world["grid"]["rows"] if "grid" in world else None
        cls.cities = {c["id"] for c in json.loads((WEB_DATA / "cities.json").read_text())}

    def test_every_commune_once(self):
        codes = [r["code"] for r in self.rows]
        self.assertGreater(len(codes), 95_000)
        self.assertEqual(len(codes), len(set(codes)))

    def test_on_the_map(self):
        self.assertTrue(all(r["cell"] is not None and r["cell"] >= 0 for r in self.rows))
        if self.size:
            self.assertTrue(all(r["cell"] < self.size for r in self.rows))

    def test_aires_exist(self):
        self.assertTrue(all(r["aav"] is None or r["aav"] in self.cities for r in self.rows))

    def test_known_places(self):
        cham = next(r for r in self.rows if r["code"] == "FR_74056")
        self.assertEqual(cham["name"], "Chamonix-Mont-Blanc")
        self.assertEqual(cham["dep"], "FR")
        self.assertEqual(cham["region"], "FRK28")
        veles = next(r for r in self.rows if r["code"] == "MK_MK00101")
        self.assertEqual(veles["name"], "Veles")  # Cyrillic and Greek names are transliterated

    def test_population_adds_up(self):
        total = sum(r["pop"] or 0 for r in self.rows)
        # EU, EFTA and the Western Balkans at the 2021 census, Bosnia, Montenegro and Kosovo by their GeoNames
        # settlements, the United Kingdom at its 2021-2022 censuses
        self.assertTrue(540_000_000 < total < 556_000_000, total)


if __name__ == "__main__":
    unittest.main()
