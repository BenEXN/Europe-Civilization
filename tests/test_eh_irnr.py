"""Tests de la lecture des comptes de flux de matières (pipeline/sources/eh_irnr.py) sur un JSON-stat construit à la main."""

import unittest

from pipeline.sources.eh_irnr import CATEGORIES, SchemaInattendu, dimensions, extraire, lire_multi


def jsonstat(cellules: dict, dims: dict) -> dict:
    """cellules {(code par dimension, dans l'ordre de dims): valeur} → JSON-stat 2.0 ; dims {dimension: [codes]}."""
    ids = list(dims)
    size = [len(dims[d]) for d in ids]
    stride = [1] * len(ids)
    for k in range(len(ids) - 2, -1, -1):
        stride[k] = stride[k + 1] * size[k + 1]
    value, status = {}, {}
    for codes, v in cellules.items():
        statut = ""
        if isinstance(v, tuple):
            v, statut = v
        idx = sum(dims[d].index(c) * stride[k] for k, (d, c) in enumerate(zip(ids, codes)))
        value[str(idx)] = v
        if statut:
            status[str(idx)] = statut
    dimension = {d: {"category": {"index": {c: i for i, c in enumerate(dims[d])},
                                  "label": {c: c.lower() for c in dims[d]}}} for d in ids}
    return {"id": ids, "size": size, "dimension": dimension, "value": value, "status": status}


DIMS = {"freq": ["A"], "material": ["TOTAL", "MF1", "MF2", "MF3", "MF4"], "indic_env": ["DMC"],
        "unit": ["T_HAB"], "geo": ["FR", "DE"], "time": ["2021", "2022"]}


class Irnr(unittest.TestCase):
    def setUp(self):
        self.d = jsonstat({
            ("A", "MF1", "DMC", "T_HAB", "FR", "2022"): 3.0,
            ("A", "MF2", "DMC", "T_HAB", "FR", "2022"): 0.5,
            ("A", "MF3", "DMC", "T_HAB", "FR", "2021"): 6.1,
            ("A", "MF3", "DMC", "T_HAB", "FR", "2022"): (6.2, "p"),
            ("A", "MF4", "DMC", "T_HAB", "DE", "2022"): 2.4,
            ("A", "TOTAL", "DMC", "T_HAB", "DE", "2022"): 13.0,
        }, DIMS)

    def test_lecture(self):
        s = lire_multi(self.d)
        self.assertEqual(s[("A", "MF3", "DMC", "T_HAB")]["FR"], {2021: (6.1, ""), 2022: (6.2, "p")})

    def test_categories_non_renouvelables_seulement(self):
        out = extraire(lire_multi(self.d), self.d["id"])
        self.assertEqual(set(out), {"MF2", "MF3", "MF4"})
        self.assertTrue(set(out) <= set(CATEGORIES))
        self.assertEqual(out["MF3"]["FR"]["2022"], [6.2, "p"])
        self.assertEqual(out["MF4"]["DE"]["2022"], [2.4, ""])

    def test_filtre_indicateur(self):
        dims = dict(DIMS, indic_env=["DMC", "RMC"])
        d = jsonstat({("A", "MF2", "DMC", "T_HAB", "FR", "2022"): 0.5,
                      ("A", "MF2", "RMC", "T_HAB", "FR", "2022"): 1.9}, dims)
        out = extraire(lire_multi(d), d["id"], filtre={"indic_env": "RMC"})
        self.assertEqual(out["MF2"]["FR"]["2022"], [1.9, ""])

    def test_unites_confondues(self):
        # Une dimension résiduelle non fixée (deux unités) ne doit pas écraser une série par l'autre.
        dims = dict(DIMS, unit=["T_HAB", "THS_T"])
        d = jsonstat({("A", "MF2", "DMC", "T_HAB", "FR", "2022"): 1.0,
                      ("A", "MF2", "DMC", "THS_T", "FR", "2022"): 999.0}, dims)
        with self.assertRaises(SchemaInattendu):
            extraire(lire_multi(d), d["id"])
        out = extraire(lire_multi(d), d["id"], filtre={"unit": "T_HAB"})
        self.assertEqual(out["MF2"]["FR"]["2022"], [1.0, ""])

    def test_dimension_attendue_absente(self):
        with self.assertRaises(SchemaInattendu):
            extraire(lire_multi(self.d), self.d["id"], filtre={"indic_env_bis": "RMC"})

    def test_total(self):
        out = extraire(lire_multi(self.d), self.d["id"], categories={"TOTAL": "total"})
        self.assertEqual(out, {"TOTAL": {"DE": {"2022": [13.0, ""]}}})

    def test_dimensions(self):
        self.assertEqual(dimensions(self.d)["material"]["MF2"], "mf2")
        self.assertNotIn("geo", dimensions(self.d))


if __name__ == "__main__":
    unittest.main()
