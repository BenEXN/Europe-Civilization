"""Tests de la mise à plat des séries de l'IEE (pipeline/sources/eh_iee.py)."""

import unittest

from pipeline.sources.eh_iee import TABLES, aplatir
from pipeline.sources.eh_irnr import lire_multi
from tests.test_eh_irnr import jsonstat


class Iee(unittest.TestCase):
    def test_aplatir(self):
        dims = {"freq": ["A"], "unit": ["PC", "KM2"], "geo": ["FR"], "time": ["2018", "2022"]}
        d = jsonstat({("A", "PC", "FR", "2018"): 5.5, ("A", "PC", "FR", "2022"): (5.7, "p"),
                      ("A", "KM2", "FR", "2022"): 31000.0}, dims)
        s = aplatir(lire_multi(d), d["id"])
        self.assertEqual(s["freq=A|unit=PC"]["FR"], {"2018": [5.5, ""], "2022": [5.7, "p"]})
        self.assertEqual(s["freq=A|unit=KM2"]["FR"]["2022"], [31000.0, ""])

    def test_familles(self):
        familles = {f for _, _, f in TABLES.values()}
        self.assertIn("ressources renouvelables rapportées à leur renouvellement", familles)


if __name__ == "__main__":
    unittest.main()
