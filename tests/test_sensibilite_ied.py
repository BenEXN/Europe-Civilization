"""Tests des fonctions de normalisation, d'agrégation, de rang et de mesure de l'analyse de sensibilité de l'IED."""

import math
import random
import unittest

from analyse.sensibilite_ied import (AGREGATIONS, NATURES, NORMALISATIONS, POIDS, SOUS_INDICATEURS, VALEURS_IBD,
                                     analyser, inversions, mesures, moyenne_puissance, rangs_moyens, spearman)


class Normalisation(unittest.TestCase):
    def test_un_au_seuil(self):
        for f in NORMALISATIONS.values():
            self.assertAlmostEqual(f(5.0, 5.0), 1.0)

    def test_bornes_et_decroissance(self):
        for f in NORMALISATIONS.values():
            vals = [f(x, 1.0) for x in (0.0, 0.01, 0.5, 1, 2, 4, 100)]
            self.assertTrue(all(0 <= v <= 2 for v in vals))
            self.assertTrue(all(a >= b for a, b in zip(vals, vals[1:])))

    def test_lineaire_nulle_au_double(self):
        self.assertEqual(NORMALISATIONS["linéaire : 2 − x/T"](2.0, 1.0), 0.0)

    def test_domaine(self):
        for f in NORMALISATIONS.values():
            for x, t in ((-0.5, 1.0), (-1.0, 1.0), (1.0, 0.0), (1.0, -2.0), (math.nan, 1.0), (math.inf, 1.0)):
                with self.assertRaises(ValueError, msg=(f, x, t)):
                    f(x, t)


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

    def test_poids_nul_ecarte_avant_le_zero(self):
        for rho in (0.0, -1.0, -5.0, -math.inf):
            self.assertAlmostEqual(moyenne_puissance([0.0, 1.5, 1.5], [0, 1, 1], rho), 1.5)

    def test_poids(self):
        self.assertAlmostEqual(moyenne_puissance([1, 4], [1, 1], 0.0), 2.0)
        self.assertAlmostEqual(moyenne_puissance([1, 4], [1, 3], 0.0), 4 ** 0.75)

    def test_ordre_des_moyennes(self):
        v, w = [0.4, 1.1, 1.7], [1, 1, 1]
        m = [moyenne_puissance(v, w, rho) for rho in AGREGATIONS.values()]
        self.assertTrue(all(a >= b for a, b in zip(m, m[1:])))

    def test_contrats(self):
        for valeurs, poids in (([1, 2, 3], [1, 1]), ([], []), ([1, -0.1], [1, 1]), ([1, math.nan], [1, 1]),
                               ([1, 2], [1, -1]), ([1, 2], [0, 0]), ([1, 2], [1, math.inf])):
            with self.assertRaises(ValueError, msg=(valeurs, poids)):
                moyenne_puissance(valeurs, poids, 0.0)


class Rangs(unittest.TestCase):
    def test_constante_sans_objet(self):
        self.assertIsNone(spearman({"A": 1, "B": 2, "C": 3}, {"A": 0, "B": 0, "C": 0}))

    def test_constante_independante_de_l_ordre(self):
        a = {"A": 3, "B": 2, "C": 1}
        for b in ({"A": 0, "B": 0, "C": 0}, {"C": 0, "B": 0, "A": 0}):
            self.assertIsNone(spearman(a, b))

    def test_ex_aequo_rangs_moyens(self):
        self.assertEqual(rangs_moyens({"A": 3, "B": 2, "C": 2, "D": 1}), {"A": 1, "B": 2.5, "C": 2.5, "D": 4})

    def test_ex_aequo_formule_independante(self):
        a = {"A": 4, "B": 3, "C": 2, "D": 1}
        b = {"A": 2, "B": 2, "C": 1, "D": 1}
        # rangs a : 1 2 3 4 ; rangs b : 1,5 1,5 3,5 3,5 → corrélation de Pearson des rangs = 2/√5
        self.assertAlmostEqual(spearman(a, b), 2 / math.sqrt(5))

    def test_invariance_aux_permutations(self):
        rnd = random.Random(1)
        a = {g: rnd.random() for g in "ABCDEFGH"}
        b = {g: round(v, 1) for g, v in a.items()}
        s = spearman(a, b)
        cles = list(a)
        for _ in range(5):
            rnd.shuffle(cles)
            self.assertAlmostEqual(spearman({g: a[g] for g in cles}, {g: b[g] for g in reversed(cles)}), s)

    def test_inversion(self):
        self.assertEqual(inversions({"A": 3, "B": 2, "C": 1}, {"A": 3, "B": 1, "C": 2}), [("B", "C")])


def series(rmc, n_min, n_bio, p_min, pop, co2, rmc_total=None):
    def s(d):
        return {g: {str(a): [v, st] for a, (v, st) in ans.items()} for g, ans in d.items()}
    return ({"series": {"rmc": {"MF2": s(rmc[0]), "MF3": s(rmc[1]), "MF4": s(rmc[2])},
                        "rmc_total": s(rmc_total or {})}},
            {"series": {"population": {"freq=A|unit=THS_PER|na_item=POP_NC": s(pop)},
                        "ges_empreinte": {"freq=A|airpol=CO2|indic_env=AEMIS_CONS_FP|unit=KG_HAB": s(co2)},
                        "azote": {"freq=A|nutrient=N|indic_ag=I_FRT_MIN": s(n_min),
                                  "freq=A|nutrient=N|indic_ag=I_OTH_BIO": s(n_bio),
                                  "freq=A|nutrient=P|indic_ag=I_FRT_MIN": s(p_min)}}})


class Mesures(unittest.TestCase):
    def setUp(self):
        x = {"FR": {2022: (1.0, "")}}
        self.irnr, self.iee = series(
            rmc=(x, x, {"FR": {2020: (2.0, "b"), 2022: (2.0, "")}}),
            n_min={"FR": {2020: (1000.0, "")}}, n_bio={"FR": {2020: (500.0, "")}},
            p_min={"FR": {2022: (100.0, "p")}},
            pop={"FR": {2020: (1000.0, ""), 2022: (2000.0, "")}},
            co2={"FR": {2022: (5000.0, "e")}}, rmc_total={"FR": {2021: (6.0, "")}})

    def test_annee_par_element_et_denominateur_contemporain(self):
        m, t = mesures(2022, irnr=self.irnr, iee=self.iee)
        self.assertEqual(t["FR"]["iee_azote"]["annee"], 2020)
        self.assertEqual(t["FR"]["iee_azote"]["termes"]["population (milliers)"]["annee"], 2020)
        self.assertAlmostEqual(m["FR"]["iee_azote"], 1.5)        # (1000 + 500) t / 1 000 milliers d'habitants
        self.assertEqual(t["FR"]["iee_phosphore"]["annee"], 2022)
        self.assertAlmostEqual(m["FR"]["iee_phosphore"], 0.05)   # 100 t / 2 000 milliers d'habitants
        self.assertEqual(t["FR"]["irnr_rmc_abiotique"]["annee"], 2022)
        self.assertEqual(t["FR"]["irnr_rmc_totale"]["annee"], 2021)
        self.assertAlmostEqual(m["FR"]["irnr_rmc_totale"], 6.0)

    def test_rmc_totale_requise(self):
        irnr = {"series": {"rmc": self.irnr["series"]["rmc"]}}
        with self.assertRaises(KeyError):
            mesures(2022, irnr=irnr, iee=self.iee)

    def test_statuts_conserves(self):
        _, t = mesures(2022, irnr=self.irnr, iee=self.iee)
        self.assertEqual(t["FR"]["iee_phosphore"]["statuts"], ["p"])
        self.assertEqual(t["FR"]["iee_co2_empreinte"]["statuts"], ["e"])

    def test_recul_borne(self):
        m, _ = mesures(2022, recul=0, irnr=self.irnr, iee=self.iee)
        self.assertNotIn("iee_azote", m["FR"])
        m, _ = mesures(2023, irnr=self.irnr, iee=self.iee)
        self.assertIn("iee_azote", m["FR"])                      # 2020 = 2023 − 3 : dans la fenêtre
        m, _ = mesures(2024, irnr=self.irnr, iee=self.iee)
        self.assertNotIn("iee_azote", m["FR"])                   # 2020 = 2024 − 4 : hors fenêtre

    def test_population_non_positive(self):
        irnr, iee = series(rmc=({}, {}, {}), n_min={"FR": {2022: (1.0, "")}}, n_bio={"FR": {2022: (1.0, "")}},
                           p_min={}, pop={"FR": {2022: (-5.0, "")}}, co2={})
        with self.assertRaises(ValueError):
            mesures(2022, irnr=irnr, iee=iee)

    def test_appels_independants(self):
        m1, t1 = mesures(2022, irnr=self.irnr, iee=self.iee)
        avant = repr(t1)
        mesures(2020, irnr=self.irnr, iee=self.iee)
        self.assertEqual(repr(t1), avant)


class Seuils(unittest.TestCase):
    def test_metadonnees(self):
        for k, s in SOUS_INDICATEURS.items():
            for t in s["seuils"].values():
                self.assertGreater(t["valeur"], 0, k)
                self.assertIn(t["nature"], NATURES, k)
                self.assertTrue(t["perimetre"], k)


class ContratsNumeriques(unittest.TestCase):
    def test_rho_non_fini_refuse(self):
        from analyse.sensibilite_ied import moyenne_puissance
        for rho in (float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                moyenne_puissance([1.0, 1.0], [1, 1], rho)

    def test_ces_petites_valeurs_fini(self):
        from analyse.sensibilite_ied import moyenne_puissance
        v = moyenne_puissance([1e-100, 1.0], [1, 1], -5.0)
        self.assertTrue(math.isfinite(v))
        self.assertAlmostEqual(math.log(v), math.log(1e-100) + math.log(2) / 5, places=9)

    def test_ces_concorde_forme_directe(self):
        from analyse.sensibilite_ied import moyenne_puissance
        for rho in (-5.0, -1.0, 0.5, 2.0):
            v, w = [0.3, 1.2, 1.9], [1, 2, 1]
            direct = (sum(wi / 4 * vi ** rho for vi, wi in zip(v, w))) ** (1 / rho)
            self.assertAlmostEqual(moyenne_puissance(v, w, rho), direct, places=12)


class Irnr(unittest.TestCase):
    def test_reference_rmc_totale(self):
        from analyse.sensibilite_ied import CLE_IRNR
        self.assertEqual(CLE_IRNR, "irnr_rmc_totale")
        self.assertEqual(SOUS_INDICATEURS[CLE_IRNR]["composante"], "IRNR")
        self.assertNotEqual(SOUS_INDICATEURS["irnr_rmc_abiotique"]["composante"], "IEE")


class Analyse(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.a = analyser(2023)

    def test_grille(self):
        n = len(NORMALISATIONS) * len(AGREGATIONS) * len(POIDS) * 2 * len(VALEURS_IBD)
        self.assertEqual(len(self.a["resultats"]), n)
        for r in self.a["resultats"]:
            self.assertTrue(all(0.0 <= v <= 2.0 for v in r["ied"].values()))
            sp = r["spearman_vs_reference"]
            self.assertTrue(sp is None or -1 - 1e-9 <= sp <= 1 + 1e-9)

    def test_constantes_sans_objet(self):
        for r in self.a["resultats"]:
            if len(set(r["ied"].values())) == 1:
                self.assertIsNone(r["spearman_vs_reference"])

    def test_irnr_reference_et_variante(self):
        a = self.a
        r0 = next(r for r in a["resultats"] if all(r[k] == v for k, v in a["configuration_reference"].items()))
        for g, v in r0["ied"].items():
            self.assertAlmostEqual(v, round(a["ied_reference_brut"][g], 4))
            self.assertIn("irnr_rmc_totale", a["mesures"][g])
        p = a["variante_irnr_abiotique"]
        for n, vals in p["seuils"].items():
            for g, v in vals.items():
                if g in p["reference"][n]:
                    # Même repère, part non renouvelable ≤ total : rapport au repère plus faible, score plus élevé.
                    self.assertGreaterEqual(v, p["reference"][n][g] - 1e-9)

    def test_resultats_independants(self):
        avant = repr(self.a["trace"])
        analyser(2010)
        self.assertEqual(repr(self.a["trace"]), avant)


if __name__ == "__main__":
    unittest.main()
