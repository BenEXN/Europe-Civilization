"""The Europe map layers resources.json (power plants) and wonders.json (UNESCO World Heritage): name helpers, the
builders' checks, and a few facts the built files must hold."""

import json
import tempfile
from collections import Counter
import unittest
from pathlib import Path

from pipeline.build import resources, wonders
from pipeline.core.paths import WEB_DATA

RES, WON, WORLD = WEB_DATA / "resources.json", WEB_DATA / "wonders.json", WEB_DATA / "world.json"


def load(path):
    return json.loads(path.read_text())


class NamesTest(unittest.TestCase):
    def test_clean_plant_names(self):
        self.assertEqual(resources.clean_name("Gravelines 1"), "Gravelines")
        self.assertEqual(resources.clean_name("Belchatow Phase"), "Belchatow")
        self.assertEqual(resources.clean_name("Rance Tidal Rance Tidal"), "Rance Tidal")
        self.assertEqual(resources.clean_name("Psw Goldisthal Pss"), "Goldisthal")
        self.assertEqual(resources.clean_name("Fljótsdalsvirkjun (Kárahnjúkar )"), "Fljótsdalsvirkjun (Kárahnjúkar)")
        self.assertIsNone(resources.clean_name(None))

    def test_wonder_labels(self):
        self.assertEqual(wonders.short_name("80", "Mont-Saint-Michel and its Bay"), "Mont-Saint-Michel")
        self.assertEqual(wonders.short_name("0", "Historic Centre of Kraków"), "Kraków")
        self.assertEqual(wonders.short_name("0", "Hanseatic City of Lübeck"), "Lübeck")
        self.assertEqual(wonders.short_name("0", "Acropolis, Athens"), "Acropolis")
        self.assertLessEqual(len(wonders.short_name("0", "A" * 80)), 30)

    def test_components_in_reference_order(self):
        refs = ["80ter-002", "80ter-001", "823-001B", "1133quinquies-013", "1133-002"]
        self.assertEqual(sorted(refs, key=wonders._ref_key)[:2], ["80ter-001", "823-001B"])


class ChecksTest(unittest.TestCase):
    def test_missing_files_are_notes(self):
        with tempfile.TemporaryDirectory() as d:
            for mod in (resources, wonders):
                self.assertEqual([lv for lv, _ in mod.check(Path(d))], ["NOTE"])

    @unittest.skipUnless(RES.exists() and WON.exists(), "layers not built")
    def test_built_files_pass(self):
        for mod in (resources, wonders):
            levels = [lv for lv, _ in mod.check(WEB_DATA)]
            self.assertNotIn("FAIL", levels, mod.check(WEB_DATA))
            self.assertIn("PASS", levels)


@unittest.skipUnless(RES.exists() and WORLD.exists(), "resources.json not built")
class ResourcesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc, cls.world = load(RES), load(WORLD)

    def test_big_french_nuclear_plant(self):
        big = [it for it in self.doc["items"] if it["type"] == "nuclear" and it["state"] == "FR" and it["value"] >= 5000]
        self.assertTrue(big, "no French nuclear plant of 5,000 MW or more")
        self.assertTrue(any(it["name"] == "Gravelines" for it in big))

    def test_retired_plants_are_gone(self):
        names = {it["name"] for it in self.doc["items"] if it["type"] == "nuclear"}
        for gone in ("Fessenheim", "Isar", "Doel 1", "Tihange 1"):
            self.assertNotIn(gone, names)

    def test_cells_are_map_land(self):
        owner = self.world["owner"]
        codes = {s["abbr"] for s in self.world["states"]}
        for it in self.doc["items"]:
            self.assertGreaterEqual(owner[it["cell"]], 0, it)
            self.assertIn(it["state"], codes, it)

    def test_types_have_icons_the_browser_knows(self):
        icons = (WEB_DATA.parent / "js" / "icons.js").read_text()
        for t in self.doc["types"]:
            self.assertIn(f"'{t['icon']}'", icons, t["id"])

    def test_readable_size(self):
        self.assertLess(len(self.doc["items"]), 1200)
        self.assertLess(RES.stat().st_size, 300_000)


@unittest.skipUnless(WON.exists() and WORLD.exists(), "wonders.json not built")
class WondersTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc, cls.world = load(WON), load(WORLD)

    def test_iconic_sites(self):
        short = {w["short"] for w in self.doc["wonders"]}
        self.assertTrue({"Acropolis", "Mont-Saint-Michel"} & short)
        acropolis = next(w for w in self.doc["wonders"] if w["id"] == "whs-404")
        self.assertEqual(acropolis["state"], "EL")

    def test_cells_are_map_land_and_unique(self):
        owner = self.world["owner"]
        cells = Counter(w["cell"] for w in self.doc["wonders"])
        shared = {w["state"] for w in self.doc["wonders"] if cells[w["cell"]] > 1}
        self.assertLessEqual(shared, {"MT"})  # only Malta, a single hex, stacks its wonders
        for w in self.doc["wonders"]:
            self.assertGreaterEqual(owner[w["cell"]], 0, w["id"])

    def test_rule_and_ranks(self):
        rules = {r["id"]: r for r in self.doc["rules"]}
        ws = self.doc["wonders"]
        self.assertTrue(150 <= len(ws) <= 250, len(ws))
        self.assertEqual([w["rank"] for w in ws], list(range(1, len(ws) + 1)))
        for w in ws:
            self.assertIn(w["kind"], rules[w["rule"]]["kinds"])
            if w["metrics"]["category"] != "Cultural":
                self.assertEqual(w["kind"], "natural")

    def test_every_country_with_a_site_shows_one(self):
        shown = {w["state"] for w in self.doc["wonders"]}
        for code in ("BE", "EE", "LV", "LU", "MT", "CY", "IS"):
            self.assertIn(code, shown)


if __name__ == "__main__":
    unittest.main()
