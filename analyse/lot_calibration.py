"""Économie Homéostatique — contrôle, archivage et rejeu d'un lot de calibration.

Un lot est l'ensemble des réponses Eurostat téléchargées par un passage du workflow « Calibration EH », avec les
résultats calculés à partir d'elles.

  python3 analyse/lot_calibration.py controler
      Contrôles après calcul : tables requises présentes et à jour, scores dans [0, 2], corrélations dans [−1, 1] ou
      sans objet, β_pub de référence présent. Échec → code de sortie non nul, rien n'est enregistré par le workflow.
      Vérifie aussi les chiffres cités par calibration/NOTE_SYNTHESE.md et consigne les écarts dans
      calibration/provenance/controle_note.json : un écart signale une note à réviser après une révision des sources.

  python3 analyse/lot_calibration.py archiver DOSSIER
      Écrit DOSSIER/<lot>.tar.gz (réponses brutes data/raw/eh_*, manifestes, environnement d'exécution) et
      calibration/provenance/lot.json (nom du lot, empreinte de l'archive, commit du code, environnement).

  python3 analyse/lot_calibration.py rejouer ARCHIVE
      Rejoue le traitement hors réseau à partir d'une archive, dans un dossier temporaire, et compare les séries
      obtenues à celles de calibration/. Différence → code de sortie non nul."""

from __future__ import annotations

import hashlib
import io
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CAL = ROOT / "calibration"
RAW = ROOT / "data" / "raw"
SOURCES = {"eh_beta_pub": "beta_pub.json", "eh_irnr": "irnr_series.json", "eh_iee": "iee_series.json",
           "eh_ibd": "ibd_series.json"}


def lire(nom):
    return json.loads((CAL / nom).read_text())


# ----------------------------------------------------------------------------------------------- contrôle

def _note_attendus():
    """(libellé, valeur dans le lot, valeur citée par la note, décimales)."""
    irnr, iee = lire("irnr_series.json")["data"], lire("iee_series.json")["data"]
    sens = lire("sensibilite_ied.json")

    def cel(rows, a="2023"):
        return rows["FR"][a][0]

    def s(series, *codes):
        return next(v for k, v in series.items() if all(c in k.split("|") for c in codes))

    ef = s(iee["series"]["ges_empreinte"], "airpol=CO2", "indic_env=AEMIS_CONS_FP", "unit=KG_HAB")
    return [
        ("France 2023, DMC minerais métalliques (t/hab)", cel(irnr["series"]["dmc"]["MF2"]), 0.21, 2),
        ("France 2023, RMC minerais métalliques (t/hab)", cel(irnr["series"]["rmc"]["MF2"]), 1.03, 2),
        ("France 2023, RMC fossiles (t/hab)", cel(irnr["series"]["rmc"]["MF4"]), 1.91, 2),
        ("France 2023, RMC minéraux non métalliques (t/hab)", cel(irnr["series"]["rmc"]["MF3"]), 5.76, 2),
        ("France 2023, empreinte CO2 (t/hab)", cel(ef) / 1000, 6.0, 1),
        ("France 2023, azote fixé (kg/hab)", sens["mesures"]["FR"]["iee_azote"], 30.6, 1),
        ("France 2023, phosphore minéral (kg/hab)", sens["mesures"]["FR"]["iee_phosphore"], 1.9, 1),
        ("France 2023, WEI+ (%)", cel(s(iee["series"]["eau"], "statinfo=VAL_A")), 3.2, 1),
        ("Pays complets en 2023", len(sens["pays_complets"]), 9, 0),
    ]


def controler():
    erreurs = []
    for f in SOURCES.values():
        d = lire(f)["data"]
        for cle, t in d.get("tables", {}).items():
            if t.get("requise") and (not t.get("disponible") or t.get("perime")):
                erreurs.append(f"{f} : table requise {cle} absente ou périmée")
    if not (lire("beta_pub.json")["data"].get("beta_pub_reference") or {}).get("beta_pub_nominal_eur"):
        erreurs.append("β_pub de référence absent")
    sens = lire("sensibilite_ied.json")
    if not sens["pays_complets"]:
        erreurs.append("aucun pays complet")
    for r in sens["resultats"] + sens["agregation_separee"]:
        if not all(0.0 <= v <= 2.0 for v in r["ied"].values()):
            erreurs.append(f"score hors de [0, 2] : {r}")
        sp = r["spearman_vs_reference"]
        if sp is not None and not -1 - 1e-9 <= sp <= 1 + 1e-9:
            erreurs.append(f"corrélation hors de [−1, 1] : {r}")
        if len(set(r["ied"].values())) == 1 and sp is not None:
            erreurs.append(f"corrélation numérique pour un IED constant : {r}")

    ecarts = []
    for libelle, valeur, citee, d in _note_attendus():
        if round(valeur, d) != round(citee, d):
            ecarts.append({"chiffre": libelle, "lot": round(valeur, d + 1), "note": citee})
    (CAL / "provenance" / "controle_note.json").write_text(json.dumps(
        {"controle": datetime.now(timezone.utc).isoformat(timespec="seconds"), "note": "NOTE_SYNTHESE.md",
         "conforme": not ecarts, "ecarts": ecarts}, ensure_ascii=False, indent=1) + "\n")
    for e in ecarts:
        print(f"  note à réviser : {e['chiffre']} = {e['lot']} dans le lot, {e['note']} dans la note")
    if erreurs:
        print("\n".join(f"  ✗ {e}" for e in erreurs))
        sys.exit(1)
    print(f"  lot conforme ; note {'conforme' if not ecarts else f'à réviser ({len(ecarts)} écart(s))'}")


# ----------------------------------------------------------------------------------------------- archive

def environnement():
    def git(*a):
        try:
            return subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            return None
    return {"commit_code": os.environ.get("GITHUB_SHA") or git("rev-parse", "HEAD"),
            "execution": os.environ.get("GITHUB_RUN_ID"), "depot": os.environ.get("GITHUB_REPOSITORY"),
            "python": platform.python_version(), "systeme": platform.platform(),
            "image_runner": " ".join(filter(None, (os.environ.get("ImageOS"), os.environ.get("ImageVersion")))) or None}


def archiver(dossier):
    dossier = Path(dossier)
    dossier.mkdir(parents=True, exist_ok=True)
    date = datetime.now(timezone.utc)
    lot = "calibration-eh-" + date.strftime("%Y%m%dT%H%MZ")
    env = {"lot": lot, "date": date.isoformat(timespec="seconds"), **environnement()}
    archive = dossier / f"{lot}.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        for sid in SOURCES:
            tar.add(RAW / sid, arcname=f"raw/{sid}")
        info = tarfile.TarInfo("environnement.json")
        octets = json.dumps(env, ensure_ascii=False, indent=1).encode()
        info.size = len(octets)
        tar.addfile(info, io.BytesIO(octets))
    sha = hashlib.sha256(archive.read_bytes()).hexdigest()
    manifestes = {sid: json.loads((RAW / sid / "manifest.json").read_text()) for sid in SOURCES}
    (CAL / "provenance" / "lot.json").write_text(json.dumps(
        {**env, "archive": archive.name, "archive_sha256": sha,
         "reponses": {sid: {f: m["sha256"] for f, m in man.items()} for sid, man in manifestes.items()}},
        ensure_ascii=False, indent=1) + "\n")
    print(f"  {archive.name} ({archive.stat().st_size / 1e6:.1f} Mo), sha256 {sha}")
    return archive


# ----------------------------------------------------------------------------------------------- rejeu

def rejouer(archive):
    archive = Path(archive).resolve()
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        shutil.copytree(ROOT / "pipeline", tmp / "pipeline", ignore=shutil.ignore_patterns("__pycache__"))
        with tarfile.open(archive) as tar:
            tar.extractall(tmp / "data", filter="data")
        subprocess.run([sys.executable, "-m", "pipeline", "process", *SOURCES, "--offline"], cwd=tmp, check=True,
                       stdout=subprocess.DEVNULL)
        differences = []
        for sid, nom in SOURCES.items():
            rejoue = json.loads((tmp / "data" / "interim" / f"{sid}.json").read_text())["data"]
            publie = lire(nom)["data"]
            if rejoue != publie:
                differences.append(nom)
    if differences:
        print(f"  ✗ rejeu différent du lot publié : {', '.join(differences)}")
        sys.exit(1)
    print(f"  rejeu hors réseau identique au lot publié ({archive.name})")


if __name__ == "__main__":
    commande = sys.argv[1] if len(sys.argv) > 1 else ""
    if commande == "controler":
        controler()
    elif commande == "archiver" and len(sys.argv) == 3:
        archiver(sys.argv[2])
    elif commande == "rejouer" and len(sys.argv) == 3:
        rejouer(sys.argv[2])
    else:
        sys.exit(__doc__)
