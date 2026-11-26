"""cities.json: every city is drawn on (or next to) the hex of its core city."""

import json
import math
import unittest

from pipeline.core.paths import WEB_DATA


@unittest.skipUnless((WEB_DATA / "cities.json").exists(), "web data not built")
class Placement(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        w = json.loads((WEB_DATA / "world.json").read_text())
        R, cols = w["grid"]["radius"], w["grid"]["cols"]
        W, H, kpu = math.sqrt(3) * R, 1.5 * R, w["km_per_unit"]
        cls.radius_km = R * kpu
        cls.owner = w["owner"]
        cls.cities = json.loads((WEB_DATA / "cities.json").read_text())
        def off(c):
            r, col = divmod(c["cell"], cols)
            return math.hypot(W * (col + 0.5 * (r & 1)) - c["x"], H * r - c["y"]) * kpu
        cls.off = {c["name"]: off(c) for c in cls.cities}

    def test_big_cities_on_their_hex(self):
        for c in self.cities:
            if c["population"] >= 500_000 and c["name"] != "Mainz":  # Mainz faces Wiesbaden across the Rhine
                self.assertLessEqual(self.off[c["name"]], self.radius_km, c["name"])

    def test_coastal_and_island_towns_stay_put(self):
        for name in ("Le Havre", "Valletta", "Palermo", "Gdańsk", "Bergen", "Thessaloniki", "Nantes", "Lisbon"):
            self.assertLessEqual(self.off[name], self.radius_km, name)

    def test_few_cities_moved_off_their_hex(self):
        far = [n for n, d in self.off.items() if d > self.radius_km]
        self.assertLessEqual(len(far), 15, far)  # those share their hex with a bigger city: one ring away
        self.assertTrue(all(d < 2.5 * self.radius_km for d in self.off.values()))

    def test_every_city_on_its_country(self):
        states = [s["abbr"] for s in json.loads((WEB_DATA / "world.json").read_text())["states"]]
        self.assertTrue(all(self.owner[c["cell"]] >= 0 and states[self.owner[c["cell"]]] == c["states"][0]
                            for c in self.cities))


if __name__ == "__main__":
    unittest.main()
