"""Tests de l'assiette 𝒴 (pipeline/sources/eh_entreprises.py) et des écodotations rapportées au PIB
(analyse/ecodotations.py)."""

import importlib.util
import unittest
from pathlib import Path

from pipeline.sources.eh_entreprises import OPERATIONS, SECTEURS, lire_secteurs, url
from pipeline.sources.eh_irnr import SchemaInattendu
from tests.test_eh_irnr import jsonstat

spec = importlib.util.spec_from_file_location("ecodotations", Path(__file__).resolve().parents[1] / "analyse" / "ecodotations.py")
eco = importlib.util.module_from_spec(spec)
spec.loader.exec_module(eco)

DIMS = {"freq": ["A"], "unit": ["CP_MEUR"], "direct": ["PAID", "RECV"], "sector": list(SECTEURS),
        "na_item": list(OPERATIONS), "geo": ["FR"], "time": ["2021", "2022", "2023"]}


def cellules(sens_p1="RECV"):
    c = {}
    for sec in SECTEURS:
        for op, sens in OPERATIONS.items():
            for an in DIMS["time"]:
                c[("A", "CP_MEUR", sens_p1 if op == "P1" else sens, sec, op, "FR", an)] = 100.0
    return c


class Entreprises(unittest.TestCase):
    def test_url_valeurs_multiples(self):
        u = url("nasa_10_nf_tr", {"sector": ["S11", "S12"], "unit": "CP_MEUR"})
        self.assertIn("sector=S11&sector=S12", u)
        self.assertIn("geo=EU27_2020", u)

    def test_lire_secteurs(self):
        d = jsonstat(cellules(), DIMS)
        s = lire_secteurs(d)
        self.assertEqual(s["S11"]["P2"]["FR"]["2023"], [100.0, ""])
        self.assertEqual(set(s), set(SECTEURS))

    def test_sens_inattendu(self):
        d = jsonstat(cellules(sens_p1="PAID"), DIMS)  # P1 publié en emplois seulement
        with self.assertRaises(SchemaInattendu):
            lire_secteurs(d)

    def test_source_enregistree(self):
        from pipeline.sources import BY_ID
        self.assertIn("eh_entreprises", BY_ID)


def serie(valeurs):
    return {"FR": {str(a): [v, ""] for a, v in valeurs.items()}}


class Ecodotations(unittest.TestCase):
    def donnees(self):
        sec = {s: {op: serie({2021: 900.0, 2022: 1000.0, 2023: 1100.0}) for op in OPERATIONS} for s in SECTEURS}
        ent = {"secteurs": sec, "pib": serie({2023: 4000.0}), "population": serie({2023: 50.0})}
        beta = {"beta_pub_reference": {"beta_pub_eur_constants": 20000.0},
                "par_annee": {"2023": {"facteur_deflation": 0.8}}}
        sens = {"annee": 2023, "configuration_reference": {"ibd": 1.0},
                "resultats": [{"ibd": 0.5, "ied": {"FR": 0.1}}, {"ibd": 1.0, "ied": {"FR": 0.5}}]}
        return ent, beta, sens

    def test_canaux(self):
        res = eco.calculer(*self.donnees())
        fr = res["pays"]["FR"]
        # β_pub courant = 20 000 / 0,8 = 25 000 € ; DTETA = 25 000 × 50 000 hab = 1 250 M€ ; PIB 4 000 M€
        self.assertAlmostEqual(fr["u1"]["dteta_pib"], 0.3125)
        self.assertEqual(fr["u1"]["dtcit_pib"], fr["u1"]["dteta_pib"])
        # 𝒴 de référence lissé : (2×900 + 2×1000 + 2×1100) / 3 = 2 000 M€
        ref = fr["assiettes"]["reference"]
        self.assertAlmostEqual(ref["y_mio_eur"], 2000.0)
        self.assertAlmostEqual(ref["dtent_pib_u1"], 0.5)
        self.assertAlmostEqual(ref["dg_pib_u1"], 1.125)
        self.assertAlmostEqual(fr["assiettes"]["avec_amortissements"]["dtent_pib_u1"], 0.75)
        self.assertAlmostEqual(fr["assiettes"]["avec_societes_financieres"]["dtent_pib_u1"], 1.0)
        # u = IED de la configuration de référence (0,5), pas d'une autre configuration
        self.assertAlmostEqual(fr["u_ied"]["dg_pib_reference"], 0.5625)

    def test_terme_manquant(self):
        ent, beta, sens = self.donnees()
        del ent["secteurs"]["S11"]["D1"]["FR"]["2021"]
        fr = eco.calculer(ent, beta, sens)["pays"]["FR"]
        self.assertNotIn("reference", fr["assiettes"])
        self.assertIn("u1", fr)

    def test_pays_absent(self):
        self.assertFalse(eco.calculer(*self.donnees())["pays"]["DE"]["disponible"])


if __name__ == "__main__":
    unittest.main()
