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
                "par_annee": {"2021": {"facteur_deflation": 0.8}, "2022": {"facteur_deflation": 0.8},
                              "2023": {"facteur_deflation": 0.8}}}
        mes = {"iee_co2_empreinte": 6.0, "iee_azote": 30.0, "iee_phosphore": 2.0, "irnr_rmc_totale": 12.0}
        sens = {"annee": 2023, "configuration_reference": {"ibd": 1.0},
                "resultats": [{"ibd": 0.5, "ied": {"FR": 0.1}}, {"ibd": 1.0, "ied": {"FR": 0.5}}],
                "pays_complets": ["FR"], "mesures": {"FR": mes}}
        return ent, beta, sens

    def test_canaux(self):
        res = eco.calculer(*self.donnees())
        fr = res["pays"]["FR"]
        # β_pub courant = 20 000 / 0,8 = 25 000 € ; DTETA = 25 000 × 50 000 hab = 1 250 M€ ; PIB 4 000 M€
        self.assertAlmostEqual(fr["u1"]["dteta_pib"], 0.3125)
        self.assertEqual(fr["u1"]["dtcit_pib"], fr["u1"]["dteta_pib"])
        # 𝒴 de référence lissé : 2 secteurs × 3 opérations, moyenne de 900, 1 000, 1 100 → 6 000 M€
        ref = fr["assiettes"]["reference"]
        self.assertAlmostEqual(ref["y_mio_eur"], 6000.0)
        self.assertAlmostEqual(ref["dtent_pib_u1"], 1.5)
        self.assertAlmostEqual(ref["dg_pib_u1"], 2.125)
        self.assertAlmostEqual(fr["assiettes"]["sans_amortissements"]["dtent_pib_u1"], 1.0)
        self.assertAlmostEqual(fr["assiettes"]["societes_non_financieres"]["dtent_pib_u1"], 0.75)
        # u = IED de la configuration de référence (0,5), pas d'une autre configuration
        self.assertAlmostEqual(fr["u_ied"]["dg_pib_reference"], 1.0625)

    def test_zone(self):
        ent, beta, sens = self.donnees()
        # Deux pays : la zone agrège les grandeurs par habitant, pondérées par la population.
        for k in ("FR", "DE"):
            ent["population"].setdefault(k, {"2023": [50.0 if k == "FR" else 150.0, ""]})
        sens["pays_complets"] = ["DE", "FR"]
        sens["mesures"]["DE"] = {k: 2 * v for k, v in sens["mesures"]["FR"].items()}
        z = eco.ied_zone(ent, sens)
        self.assertAlmostEqual(z["mesures_par_habitant"]["iee_azote"], (30 * 50 + 60 * 150) / 200)
        self.assertEqual(len(z["grille"]), 480)
        # Zone d'un seul pays : même IED que le pays.
        sens["pays_complets"] = ["FR"]
        si = eco._sensibilite()
        ref = next(g["ied"] for g in eco.ied_zone(ent, sens)["grille"]
                   if all(g[k] == v for k, v in si.REFERENCE.items()))
        iee_ids = [k for k, v in si.SOUS_INDICATEURS.items() if v["composante"] == "IEE"]
        attendu = si.ied_pays(sens["mesures"], "FR", si.NORMALISATIONS[si.REFERENCE["normalisation"]], 0.0, 0.0,
                              (1, 1, 1), 7.2, 1.0, iee_ids)
        self.assertAlmostEqual(ref, round(attendu, 4))

    def test_lissage_valeur_constante(self):
        ent, beta, sens = self.donnees()
        # Prix en hausse : chaque millésime est ramené à la valeur de 2023 avant la moyenne (CAL-001).
        beta["par_annee"] = {"2021": {"facteur_deflation": 1.0, "deflateur_ue27": 100.0},
                             "2022": {"facteur_deflation": 0.9, "deflateur_ue27": 110.0},
                             "2023": {"facteur_deflation": 0.8, "deflateur_ue27": 125.0}}
        ref = eco.calculer(ent, beta, sens)["pays"]["FR"]["assiettes"]["reference"]
        attendu = 6 * (900 * 1.25 + 1000 * 125 / 110 + 1100) / 3
        self.assertAlmostEqual(ref["y_mio_eur"], round(attendu, 1))
        self.assertAlmostEqual(ref["y_mio_eur_nominal"], 6000.0)

    def test_variante_spa(self):
        ent, beta, sens = self.donnees()
        beta["beta_pub_reference"]["variante_spa"] = {"beta_pub_spa_constants": 16000.0, "pays": []}
        beta["niveau_prix"] = {"FR": {"2023": [110.0, ""]}}
        r = eco.calculer(ent, beta, sens)
        fr_ = r["pays"]["FR"]
        attendu = 16000.0 / 0.8 * 1.10 * fr_["population_milliers"] * 1e3 / (fr_["pib_mio_eur"] * 1e6)
        self.assertAlmostEqual(fr_["variante_spa"]["dteta_pib"], attendu)
        self.assertAlmostEqual(fr_["variante_spa"]["dg_pib_u1"] - 2 * attendu,
                               fr_["assiettes"]["reference"]["dtent_pib_u1"])

    def test_deflateur_absent(self):
        ent, beta, sens = self.donnees()
        del beta["par_annee"]["2021"]
        with self.assertRaises(ValueError):
            eco.calculer(ent, beta, sens)

    def test_unite_inattendue(self):
        c = {(f, "WRONG_UNIT", *k[2:]): v for k, v in cellules().items() for f in ["A"]}
        d = jsonstat(c, {**DIMS, "unit": ["WRONG_UNIT"]})
        with self.assertRaises(SchemaInattendu):
            lire_secteurs(d)

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
