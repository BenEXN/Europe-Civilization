"""Évolution de l'IED (analyse/evolution_ied.py) : panel, décomposition, robustesse, mesures sans recul."""

import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "analyse"))
import evolution_ied as ev  # noqa: E402
import sensibilite_ied as si  # noqa: E402


class Evolution(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.e = ev.analyser()

    def test_panel_complet_chaque_annee(self):
        for a in self.e["annees"]:
            self.assertTrue(set(self.e["panel"]) <= set(self.e["par_annee"][str(a)]["complets"]))

    def test_sans_recul(self):
        # Une année est mesurée avec ses seules données : une valeur absente n'est pas reprise d'une autre année.
        for a in self.e["annees"]:
            mes, trace = si.mesures(a, recul=0)
            for g in self.e["par_annee"][str(a)]["complets"]:
                for k in ev.iee_ids() + [si.CLE_IRNR]:
                    self.assertEqual(trace[g][k]["annee"], a)

    def test_decomposition_exacte(self):
        for g, t in self.e["tendances"].items():
            self.assertAlmostEqual(t["contribution_iee"] + t["contribution_irnr"], t["variation_ln"], places=12)
            self.assertAlmostEqual(math.exp(t["variation_ln"]) - 1, t["variation_relative"], places=12)

    def test_reference_concorde_sensibilite(self):
        # Pour un pays complet sans recul en 2023, l'IED de référence est celui de l'analyse de sensibilité.
        a = si.analyser()
        for g in self.e["par_annee"]["2023"]["complets"]:
            self.assertAlmostEqual(self.e["par_annee"]["2023"]["pays"][g]["ied"], a["ied_reference_brut"][g],
                                   places=12)

    def test_robustesse_somme(self):
        n = self.e["robustesse"]["configurations"]
        for g, p in self.e["robustesse"]["pays"].items():
            self.assertEqual(p["hausse"] + p["baisse"] + p["stable"], n)

    def test_pente(self):
        self.assertAlmostEqual(ev.pente([1, 2, 3], [2, 4, 6]), 2.0)


if __name__ == "__main__":
    unittest.main()
