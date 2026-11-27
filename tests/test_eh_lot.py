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


class Integrite(unittest.TestCase):
    """Vérification des empreintes d'une archive de lot avant rejeu (analyse/lot_calibration.py)."""

    @classmethod
    def setUpClass(cls):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "lot_calibration", Path(__file__).resolve().parents[1] / "analyse" / "lot_calibration.py")
        cls.lc = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.lc)

    def archive(self, dossier, alterer=None, hors_manifeste=False):
        import hashlib
        import tarfile
        chemin = Path(dossier) / "calibration-eh-test.tar.gz"
        with tarfile.open(chemin, "w:gz") as tar:
            def ajouter(nom, octets):
                info = tarfile.TarInfo(nom)
                info.size = len(octets)
                tar.addfile(info, io.BytesIO(octets))
            for sid in self.lc.SOURCES:
                octets = b'{"a": 1}'
                man = {"t.json": {"sha256": hashlib.sha256(octets).hexdigest()}}
                ajouter(f"raw/{sid}/manifest.json", json.dumps(man).encode())
                ajouter(f"raw/{sid}/t.json", octets + (b" " if alterer == sid else b""))
                if hors_manifeste:
                    ajouter(f"raw/{sid}/autre.json", b"{}")
            ajouter("environnement.json", json.dumps({"commit_code": "abc"}).encode())
        return chemin

    def test_archive_conforme(self):
        with tempfile.TemporaryDirectory() as t:
            r = self.lc.verifier_integrite(self.archive(t), lot_json=Path(t) / "absent.json")
            self.assertEqual(set(r), set(self.lc.SOURCES))

    def test_reponse_alteree(self):
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaises(self.lc.IntegriteLot):
                self.lc.verifier_integrite(self.archive(t, alterer="eh_beta_pub"), lot_json=Path(t) / "absent.json")

    def test_reponse_hors_manifeste(self):
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaises(self.lc.IntegriteLot):
                self.lc.verifier_integrite(self.archive(t, hors_manifeste=True), lot_json=Path(t) / "absent.json")

    def test_lot_json_archive_et_commit(self):
        import hashlib
        with tempfile.TemporaryDirectory() as t:
            a = self.archive(t)
            reponses = self.lc.verifier_integrite(a, lot_json=Path(t) / "absent.json")
            lot = Path(t) / "lot.json"
            base = {"archive": a.name, "archive_sha256": hashlib.sha256(a.read_bytes()).hexdigest(),
                    "reponses": reponses, "commit_code": "abc"}
            lot.write_text(json.dumps(base))
            self.lc.verifier_integrite(a, lot_json=lot)
            for cle, val in (("archive_sha256", "0" * 64), ("commit_code", "autre")):
                lot.write_text(json.dumps({**base, cle: val}))
                with self.assertRaises(self.lc.IntegriteLot):
                    self.lc.verifier_integrite(a, lot_json=lot)


if __name__ == "__main__":
    unittest.main()
