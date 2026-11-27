"""Tests des règles de lot (pipeline/sources/eh_lot.py) : échec réseau avec ou sans cache, retour au succès,
tables requises."""

import io
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

from pipeline.sources import eh_iee, eh_irnr
from pipeline.sources.eh_lot import LotIncomplet, etat, telecharger, verifier
from tests.test_eh_irnr import jsonstat


class FausseSource:
    def __init__(self, raw_dir, echec=None):
        self.raw_dir, self.echec = Path(raw_dir), echec

    def download(self, url, rel, force=False):
        if self.echec:
            raise self.echec
        (self.raw_dir / rel).write_text("{}")
        (self.raw_dir / "manifest.json").write_text(json.dumps({rel: {"retrieved": "2026-11-27T10:00:00+00:00"}}))


def http503():
    return urllib.error.HTTPError("http://x", 503, "Service Unavailable", {}, io.BytesIO(b"indisponible"))


class Lot(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_echec_sans_cache(self):
        self.assertFalse(telecharger(FausseSource(self.dir, urllib.error.URLError("hors ligne")), "t", "u", True))
        e = etat(self.dir, "t")
        self.assertFalse(e["present"])
        self.assertIn("URLError", e["erreur"])

    def test_echec_avec_cache_perime(self):
        telecharger(FausseSource(self.dir), "t", "u", True)
        self.assertFalse(telecharger(FausseSource(self.dir, http503()), "t", "u", True))
        e = etat(self.dir, "t")
        self.assertTrue(e["present"] and e["perime"])
        self.assertEqual(e["recupere"], "2026-11-27T10:00:00+00:00")
        self.assertIn("HTTP 503", e["erreur"])

    def test_succes_efface_l_erreur(self):
        telecharger(FausseSource(self.dir, urllib.error.URLError("x")), "t", "u", True)
        self.assertTrue(telecharger(FausseSource(self.dir), "t", "u", True))
        e = etat(self.dir, "t")
        self.assertFalse(e["perime"])
        self.assertIsNone(e["erreur"])

    def test_requises(self):
        verifier("s", {"a": {"disponible": True}, "b": {"disponible": False}}, ("a",))
        for tables in ({"a": {"disponible": False}}, {"a": {"disponible": True, "perime": True}}, {}):
            with self.assertRaises(LotIncomplet):
                verifier("s", tables, ("a",))


class Traitement(unittest.TestCase):
    """Le traitement d'une source s'arrête quand une table requise manque ou est périmée."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_irnr_rmc_absente(self):
        dims = {"freq": ["A"], "indic_env": ["DMC"], "material": ["MF2"], "unit": ["T_HAB"], "geo": ["FR"],
                "time": ["2022"]}
        (self.dir / "dmc.json").write_text(json.dumps(jsonstat({("A", "DMC", "MF2", "T_HAB", "FR", "2022"): 1.0}, dims)))
        src = eh_irnr.EhIrnr()
        with mock.patch.object(type(src), "raw_dir", new=self.dir):
            with self.assertRaises(LotIncomplet):
                src.process()

    def test_iee_requise_perimee(self):
        src = eh_iee.EhIee()
        dims = {"freq": ["A"], "unit": ["PC"], "geo": ["FR"], "time": ["2022"]}
        for cle in eh_iee.TABLES:
            (self.dir / f"{cle}.json").write_text(json.dumps(jsonstat({("A", "PC", "FR", "2022"): 1.0}, dims)))
        (self.dir / "azote.erreur.txt").write_text("2026-12-03\nHTTP 503\n")
        with mock.patch.object(type(src), "raw_dir", new=self.dir):
            with self.assertRaises(LotIncomplet):
                src.process()
            (self.dir / "azote.erreur.txt").unlink()
            (self.dir / "eau.erreur.txt").write_text("2026-12-03\nHTTP 503\n")
            out = src.process()                       # table accessoire périmée : publiée et signalée
            self.assertTrue(out["tables"]["eau"]["perime"])


if __name__ == "__main__":
    unittest.main()
