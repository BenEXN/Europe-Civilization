"""Tests du calcul de β_pub (pipeline/sources/eh_beta_pub.py) sur un JSON-stat construit à la main.

Les valeurs 2017 sont celles relevées sur Eurostat le 27/11/2026 ; le calcul doit retrouver les dix pays de la
note 47 du WP EH V1.0, dans le même ordre."""

import unittest

from pipeline.sources.eh_beta_pub import UE27, calculer, lire

TE_2017 = {"BE": 231699.4, "BG": 18265.4, "CZ": 75680.2, "DK": 148947.7, "DE": 1484552.0, "EE": 9448.6,
           "IE": 77954.4, "EL": 86172.0, "ES": 479908.0, "FR": 1321444.6, "HR": 22269.6, "IT": 851546.0,
           "CY": 7823.2, "LV": 10296.2, "LT": 14106.8, "LU": 24355.2, "HU": 59345.8, "MT": 4099.9,
           "NL": 320928.0, "AT": 182990.1, "PL": 192933.1, "PT": 88929.0, "RO": 62556.3, "SI": 19015.5,
           "SK": 33800.3, "FI": 118756.0, "SE": 238848.7}
POP_2017 = {"BE": 11375.20, "BG": 6803.47, "CZ": 10520.95, "DK": 5765.10, "DE": 82038.00, "EE": 1315.60,
            "IE": 4821.08, "EL": 10684.57, "ES": 46510.46, "FR": 66830.00, "HR": 4038.50, "IT": 60002.30,
            "CY": 874.25, "LV": 1941.16, "LT": 2842.64, "LU": 596.98, "HU": 9726.76, "MT": 467.39,
            "NL": 17131.00, "AT": 8795.11, "PL": 37962.32, "PT": 10340.12, "RO": 19592.93, "SI": 2065.82,
            "SK": 5438.39, "FI": 5508.20, "SE": 10057.70}


def jsonstat(serie: dict, statuts: dict | None = None, autres: tuple = ("unit", "na_item")) -> dict:
    """{geo: {année: valeur}} → JSON-stat 2.0, dimensions fixes d'abord, puis geo, puis time."""
    geos = sorted(serie)
    annees = sorted({a for row in serie.values() for a in row})
    ids = list(autres) + ["geo", "time"]
    size = [1] * len(autres) + [len(geos), len(annees)]
    value, status = {}, {}
    for g, geo in enumerate(geos):
        for t, a in enumerate(annees):
            if a in serie[geo]:
                value[str(g * len(annees) + t)] = serie[geo][a]
                s = (statuts or {}).get((geo, a))
                if s:
                    status[str(g * len(annees) + t)] = s
    dims = {d: {"category": {"index": {"X": 0}}} for d in autres}
    dims["geo"] = {"category": {"index": {geo: i for i, geo in enumerate(geos)}}}
    dims["time"] = {"category": {"index": {str(a): i for i, a in enumerate(annees)}}}
    return {"id": ids, "size": size, "dimension": dims, "value": value, "status": status}


class BetaPub(unittest.TestCase):
    def setUp(self):
        self.dep = lire(jsonstat({g: {2017: v} for g, v in TE_2017.items()}))
        self.pop = lire(jsonstat({g: {2017: v} for g, v in POP_2017.items()}))
        self.defl = lire(jsonstat({"EU27_2020": {2017: 102.060}}))

    def test_couverture(self):
        self.assertEqual(set(TE_2017), set(UE27))

    def test_note_47(self):
        r = calculer(self.dep, self.pop, self.defl)["2017"]
        self.assertEqual([p["geo"] for p in r["pays"]],
                         ["LU", "DK", "SE", "FI", "AT", "BE", "FR", "NL", "DE", "IE"])
        self.assertAlmostEqual(r["beta_pub_nominal_eur"], 22589, delta=1)
        self.assertEqual(r["beta_pub_nominal_eur"], r["beta_pub_eur_constants"])
        self.assertTrue(r["sans_drapeau"])
        self.assertEqual(r["onzieme"]["geo"], "IT")
        self.assertGreater(r["marge_10_11"], 0.10)

    def test_statut_provisoire(self):
        dep = lire(jsonstat({g: {2017: v} for g, v in TE_2017.items()}, {("LU", 2017): "p"}))
        r = calculer(dep, self.pop, self.defl)["2017"]
        self.assertFalse(r["sans_drapeau"])
        self.assertEqual(r["drapeaux_selection"], ["LU dépenses : provisoire"])
        self.assertEqual(r["drapeaux_hors_selection"], [])

    def test_pays_hors_selection_signale(self):
        # Un 11e pays provisoire, proche du 10e : sa révision peut changer la sélection.
        r0 = calculer(self.dep, self.pop, self.defl)["2017"]
        onzieme = r0["onzieme"]["geo"]
        te = dict(TE_2017)
        te[onzieme] = r0["pays"][-1]["depense_par_habitant_eur"] * 0.999 * POP_2017[onzieme] / 1000
        dep = lire(jsonstat({g: {2017: v} for g, v in te.items()}, {(onzieme, 2017): "p"}))
        r = calculer(dep, self.pop, self.defl)["2017"]
        self.assertFalse(r["sans_drapeau"])
        self.assertEqual(r["drapeaux_selection"], [])
        self.assertEqual(r["drapeaux_hors_selection"], [f"{onzieme} dépenses : provisoire"])
        self.assertLess(r["marge_10_11"], 0.002)

    def test_population_non_positive(self):
        pop = dict(POP_2017, FR=-1.0)
        with self.assertRaises(ValueError):
            calculer(self.dep, lire(jsonstat({g: {2017: v} for g, v in pop.items()})), self.defl)

    def test_deflation(self):
        dep = lire(jsonstat({g: {2017: v, 2025: v} for g, v in TE_2017.items()}))
        pop = lire(jsonstat({g: {2017: v, 2025: v} for g, v in POP_2017.items()}))
        defl = lire(jsonstat({"EU27_2020": {2017: 102.060, 2025: 130.635}}))
        r = calculer(dep, pop, defl)["2025"]
        self.assertAlmostEqual(r["beta_pub_eur_constants"], 22589 * 102.060 / 130.635, delta=1)

    def test_dimension_non_fixee(self):
        d = jsonstat({"FR": {2017: 1.0}})
        d["size"][0] = 2
        with self.assertRaises(ValueError):
            lire(d)


if __name__ == "__main__":
    unittest.main()
