"""Tests des fonctions de normalisation et d'agrégation de l'analyse de sensibilité de l'IED."""

import math
import unittest

from analyse.sensibilite_ied import NORMALISATIONS, moyenne_puissance


class Normalisation(unittest.TestCase):
    def test_un_au_seuil(self):
        for f in NORMALISATIONS.values():
            self.assertAlmostEqual(f(5.0, 5.0), 1.0)

    def test_bornes_et_decroissance(self):
        for f in NORMALISATIONS.values():
            vals = [f(x, 1.0) for x in (0.01, 0.5, 1, 2, 4, 100)]
            self.assertTrue(all(0 <= v <= 2 for v in vals))
            self.assertTrue(all(a >= b for a, b in zip(vals, vals[1:])))

    def test_lineaire_nulle_au_double(self):
        self.assertEqual(NORMALISATIONS["linéaire : 2 − x/T"](2.0, 1.0), 0.0)


class Agregation(unittest.TestCase):
    def test_geometrique(self):
        self.assertAlmostEqual(moyenne_puissance([1, 8, 1], [1, 1, 1], 0.0), 2.0)

    def test_minimum_et_limite(self):
        v = [0.5, 1.2, 1.8]
        self.assertEqual(moyenne_puissance(v, [1, 1, 1], -math.inf), 0.5)
        self.assertAlmostEqual(moyenne_puissance(v, [1, 1, 1], -200), 0.5, places=2)

    def test_zero_absorbant(self):
        for rho in (0.0, -1.0, -5.0, -math.inf):
            self.assertEqual(moyenne_puissance([0.0, 1.5, 1.5], [1, 1, 1], rho), 0.0)

    def test_poids(self):
        self.assertAlmostEqual(moyenne_puissance([1, 4], [1, 1], 0.0), 2.0)
        self.assertAlmostEqual(moyenne_puissance([1, 4], [1, 3], 0.0), 4 ** 0.75)


if __name__ == "__main__":
    unittest.main()
