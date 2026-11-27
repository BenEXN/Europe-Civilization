"""Tests de la carte de l'Économie Homéostatique : projection, simplification et découpage des géométries, lecture
des champs des découpages, et fidélité de web/data/eh.json aux résultats de calibration/sensibilite_ied.json."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "analyse"))

import carte_eh  # noqa: E402
from pipeline.sources import eh_decoupages  # noqa: E402


class Projection(unittest.TestCase):
    def test_sites_de_controle(self):
        self.assertLess(carte_eh.verifier_projection(carte_eh.projection()), 2.0)


class Geometrie(unittest.TestCase):
    def test_douglas_peucker_garde_les_extremites_et_les_angles(self):
        pts = [(0, 0), (1, 0.01), (2, 0), (2, 5), (0, 5), (0, 0)]
        out = carte_eh.douglas_peucker(pts, 0.5)
        self.assertEqual(out[0], (0, 0))
        self.assertEqual(out[-1], (0, 0))
        self.assertNotIn((1, 0.01), out)
        self.assertIn((2, 5), out)

    def test_decoupage_par_le_cadre(self):
        carre = [(-5, -5), (5, -5), (5, 5), (-5, 5)]
        out = carte_eh.decouper(carre, 0, 0, 10, 10)
        self.assertAlmostEqual(carte_eh.aire(out), 25.0)
        self.assertEqual(carte_eh.decouper(carre, 20, 20, 30, 30), [])

    def test_entite_projetee(self):
        proj = carte_eh.projection()
        geom = {"type": "Polygon", "coordinates": [[[-5, 45], [-1, 45], [-1, 47], [-5, 47], [-5, 45]]]}
        rings, bbox = carte_eh.projeter_entite(geom, proj, (0, 0, 1e5, 1e5))
        self.assertEqual(len(rings), 1)
        self.assertEqual(len(rings[0]) % 2, 0)
        self.assertLess(bbox[0], bbox[2])
        # Une petite île sous le seuil d'aire est omise.
        ile = {"type": "Polygon", "coordinates": [[[-5, 45], [-4.99, 45], [-4.99, 45.01], [-5, 45]]]}
        self.assertIsNone(carte_eh.projeter_entite(ile, proj, (0, 0, 1e5, 1e5)))


class Champs(unittest.TestCase):
    def test_premier_champ_present_insensible_a_la_casse(self):
        geo = {"features": [{"id": "x.1", "properties": {"Area_Full": "27.8.a", "AREA_27": "8.a"}, "geometry": None}]}
        f = eh_decoupages.entites(geo, eh_decoupages.COUCHES["ciem_zones"])[0]
        self.assertEqual(f["nom"], "27.8.a")
        self.assertEqual(f["code"], "8.a")

    def test_repli_sur_l_identifiant(self):
        geo = {"features": [{"id": "x.2", "properties": {}, "geometry": None}]}
        self.assertEqual(eh_decoupages.entites(geo, eh_decoupages.COUCHES["ciem_ecoregions"])[0]["nom"], "x.2")


class Indicateurs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = carte_eh.indicateurs()
        cls.s = json.loads((ROOT / "calibration" / "sensibilite_ied.json").read_text())

    def test_toute_la_grille(self):
        self.assertEqual(len(self.d["scenarios"]), self.s["configurations"])
        cles = {(c["n"], c["a"], c["p"], c["s"], c["b"]) for c in self.d["scenarios"]}
        self.assertEqual(len(cles), self.s["configurations"])

    def test_reference_identique(self):
        r = self.d["reference_indices"]
        sc = next(c for c in self.d["scenarios"] if all(c[k] == r[k] for k in "napsb"))
        ref = next(x for x in self.s["resultats"] if all(x[k] == v for k, v in self.s["configuration_reference"].items()
                                                         if k != "agregation") and x["agregation"] == self.s["configuration_reference"]["agregation"])
        self.assertEqual(sc["ied"], ref["ied"])

    def test_rapports_repris_tels_quels(self):
        for a, rap in self.s["rapport_au_seuil"].items():
            for k, v in rap.items():
                self.assertEqual(self.d["pays"][a]["rapports"][k], v)

    def test_composantes_coherentes_avec_l_ied(self):
        # Référence : moyenne géométrique à poids égaux de (IBD = 1, IEE, IRNR).
        r = self.d["reference_indices"]
        sc = next(c for c in self.d["scenarios"] if all(c[k] == r[k] for k in "napsb"))
        iee = next(c for c in self.d["composantes"]["iee"] if c["n"] == r["n"] and c["a"] == r["a"])["valeurs"]
        irnr = next(c for c in self.d["composantes"]["irnr"] if c["n"] == r["n"] and c["s"] == r["s"])["valeurs"]
        for g, v in sc["ied"].items():
            self.assertAlmostEqual(v, (iee[g] * irnr[g]) ** (1 / 3), places=3)

    def test_variante_rmc_totale(self):
        for a, p in self.d["pays"].items():
            if "irnr_rmc_totale" in p["mesures"]:
                self.assertAlmostEqual(p["rapports"]["irnr_rmc_totale"]["7,2 t (O'Neill)"], p["mesures"]["irnr_rmc_totale"] / 7.2, places=3)


class Decoupages(unittest.TestCase):
    def test_interim_absent(self):
        with tempfile.TemporaryDirectory() as t:
            ancien = carte_eh.INTERIM
            carte_eh.INTERIM = Path(t) / "absent.json"
            try:
                self.assertEqual(carte_eh.decoupages(carte_eh.projection()), ([], []))
            finally:
                carte_eh.INTERIM = ancien


if __name__ == "__main__":
    unittest.main()
