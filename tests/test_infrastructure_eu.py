"""infrastructure.json for Europe: the big hubs are there, Rotterdam leads the ports, links join neighbours."""

import json
import unittest

from pipeline.build.infrastructure import road_class, route_name
from pipeline.core.hexgrid import HexGrid
from pipeline.core.paths import WEB_DATA


class RoadRules(unittest.TestCase):
    def test_classes(self):
        road = {"expressway": 0, "scalerank": 9, "type": "Road", "level": None}
        self.assertEqual(road_class({**road, "expressway": 1}), 0)
        self.assertEqual(road_class({**road, "level": "E"}), 1)
        self.assertEqual(road_class({**road, "type": "Secondary Highway", "scalerank": 6}), 1)
        self.assertIsNone(road_class(road))

    def test_route_names(self):
        self.assertEqual(route_name({"label2": "A6", "name": "15"}), "A6")
        self.assertEqual(route_name({"label2": None, "name": "15"}), "E15")
        self.assertEqual(route_name({"label2": "8", "name": None}), "Route 8")
        self.assertEqual(route_name({"label2": "23", "name": "65"}), "E65")
        self.assertIsNone(route_name({"label2": None, "name": None}))


@unittest.skipUnless((WEB_DATA / "infrastructure.json").exists() and (WEB_DATA / "world.json").exists(),
                     "web data not built")
class Infrastructure(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = json.loads((WEB_DATA / "infrastructure.json").read_text())
        w = json.loads((WEB_DATA / "world.json").read_text())
        cls.grid = HexGrid(w["grid"]["radius"], w["grid"]["cols"], w["grid"]["rows"])
        cls.owner = w["owner"]

    def test_big_airports(self):
        by_icao = {a["icao"]: a for a in self.doc["airports"]}
        for icao, state in (("EDDF", "DE"), ("EHAM", "NL")):
            a = by_icao.get(icao)
            self.assertIsNotNone(a, icao)
            self.assertEqual(a["state"], state)
            self.assertGreaterEqual(a["year"], 2023)
            self.assertGreater(a["enplanements"], 40_000_000, icao)
            self.assertEqual(a["hub"], "L")

    def test_rotterdam_is_the_top_port(self):
        ports = self.doc["ports"]
        self.assertEqual(ports[0]["name"], "Rotterdam")
        self.assertEqual(ports[0]["rank"], 1)
        self.assertEqual(ports[0]["state"], "NL")
        self.assertEqual([p["rank"] for p in ports], list(range(1, len(ports) + 1)))
        self.assertTrue(all(a["tons"] >= b["tons"] for a, b in zip(ports, ports[1:])))

    def test_links_join_neighbours(self):
        for key in ("roads", "rail"):
            links = self.doc[key]
            self.assertGreater(len(links), 1000, key)
            for link in links:
                a, b = link[0], link[1]
                self.assertLess(a, b)
                self.assertIn(b, self.grid.neighbours(a), (key, link))
                self.assertTrue(self.owner[a] >= 0 or self.owner[b] >= 0, (key, link))
                self.assertNotIn(-2, (self.owner[a], self.owner[b]), (key, link))
            self.assertEqual(len({tuple(l[:2]) for l in links}), len(links), key)

    def test_sites_on_their_country(self):
        states = [s["fips"] for s in json.loads((WEB_DATA / "world.json").read_text())["states"]]
        for site in self.doc["ports"] + self.doc["airports"]:
            self.assertEqual(states[self.owner[site["cell"]]], site["state"], site["id"])


if __name__ == "__main__":
    unittest.main()
