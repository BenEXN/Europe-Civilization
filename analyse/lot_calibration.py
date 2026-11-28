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

  python3 analyse/lot_calibration.py verifier ARCHIVE
      Vérifie l'intégrité de l'archive avant tout traitement : empreinte de chaque réponse brute contre le manifeste
      de sa source, aucune réponse hors manifeste ; si l'archive est celle de calibration/provenance/lot.json,
      empreinte de l'archive, empreintes des réponses et commit du code contre lot.json. Écart → code non nul.

  python3 analyse/lot_calibration.py rejouer ARCHIVE
      Vérifie l'intégrité de l'archive (comme « verifier »), puis rejoue hors réseau, dans un dossier temporaire, le
      traitement des sources et les analyses (sensibilité de l'IED, écodotations), et compare séries et résultats à
      ceux de calibration/. Écart → code de sortie non nul."""

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
           "eh_ibd": "ibd_series.json", "eh_entreprises": "entreprises_series.json"}


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
        ("Pays complets en 2023", len(sens["pays_complets"]), 20, 0),
    ]


NOMBRES = {20: "Vingt", 9: "neuf"}


def _cite(valeur, d):
    """Forme sous laquelle la note cite une valeur (virgule décimale ; nombres de pays en toutes lettres)."""
    if d == 0 and int(valeur) in NOMBRES:
        return NOMBRES[int(valeur)]
    return f"{valeur:.{d}f}".replace(".", ",")


def etat_note(texte: str, ligne: str) -> str:
    """Remplace la ligne d'état de la note, entre les balises etat-note."""
    debut, fin = "<!-- etat-note -->", "<!-- /etat-note -->"
    if debut not in texte or fin not in texte:
        raise ValueError("balises etat-note absentes de NOTE_SYNTHESE.md")
    i, j = texte.index(debut) + len(debut), texte.index(fin)
    return texte[:i] + "\n" + ligne + "\n" + texte[j:]


def controler():
    erreurs = []
    for f in SOURCES.values():
        d = lire(f)["data"]
        for cle, t in d.get("tables", {}).items():
            if t.get("requise") and (not t.get("disponible") or t.get("perime")):
                erreurs.append(f"{f} : table requise {cle} absente ou périmée")
    if not (lire("beta_pub.json")["data"].get("beta_pub_reference") or {}).get("beta_pub_nominal_eur"):
        erreurs.append("β_pub de référence absent")
    eco = lire("ecodotations.json")
    for geo, r in eco["pays"].items():
        rapports = [*r.get("u1", {}).values(), *(a["dtent_pib_u1"] for a in r.get("assiettes", {}).values())]
        if not all(0 < x < 100 for x in rapports):
            erreurs.append(f"écodotations {geo} : rapport au PIB non positif ou aberrant")
    if not eco["pays"].get("FR", {}).get("assiettes", {}).get("reference"):
        erreurs.append("écodotations : assiette de référence absente pour la France")
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
    note = (CAL / "NOTE_SYNTHESE.md").read_text()
    for libelle, valeur, citee, d in _note_attendus():
        if round(valeur, d) != round(citee, d):
            ecarts.append({"chiffre": libelle, "lot": round(valeur, d + 1), "note": citee})
        elif _cite(citee, d) not in note:
            ecarts.append({"chiffre": libelle, "lot": round(valeur, d + 1), "note": "introuvable dans la note"})
    lot = (json.loads((CAL / "provenance" / "lot.json").read_text()).get("lot")
           if (CAL / "provenance" / "lot.json").exists() else None)
    quand = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    ligne = (f"> État des chiffres cités : conformes au lot de calibration courant (contrôle du {quand})."
             if not ecarts else
             f"> **État des chiffres cités : {len(ecarts)} écart(s) avec le lot de calibration courant (contrôle du "
             f"{quand}) ; la note est à réviser et ses chiffres ne sont pas ceux du lot courant** "
             "(détail : `provenance/controle_note.json`).")
    (CAL / "NOTE_SYNTHESE.md").write_text(etat_note(note, ligne))
    (CAL / "provenance" / "controle_note.json").write_text(json.dumps(
        {"controle": datetime.now(timezone.utc).isoformat(timespec="seconds"), "note": "NOTE_SYNTHESE.md",
         "dernier_lot_enregistre": lot, "conforme": not ecarts, "ecarts": ecarts}, ensure_ascii=False, indent=1) + "\n")
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


# ----------------------------------------------------------------------------------------------- intégrité

class IntegriteLot(RuntimeError):
    """L'archive d'un lot ne correspond pas à ses empreintes."""


def _sha(octets: bytes) -> str:
    return hashlib.sha256(octets).hexdigest()


def verifier_integrite(archive, lot_json: Path | None = None) -> dict:
    """Contrôle l'archive avant extraction ; retourne {source: {fichier: sha256}}. Lève IntegriteLot en cas d'écart."""
    archive = Path(archive)
    lot_json = CAL / "provenance" / "lot.json" if lot_json is None else lot_json
    erreurs, reponses, env = [], {}, None
    with tarfile.open(archive) as tar:
        membres = {m.name: m for m in tar.getmembers() if m.isfile()}
        for sid in SOURCES:
            nom_man = f"raw/{sid}/manifest.json"
            if nom_man not in membres:
                erreurs.append(f"{sid} : manifeste absent")
                continue
            manifeste = json.loads(tar.extractfile(membres[nom_man]).read())
            reponses[sid] = {}
            for f, m in manifeste.items():
                nom = f"raw/{sid}/{f}"
                if nom not in membres:
                    erreurs.append(f"{nom} : réponse du manifeste absente de l'archive")
                    continue
                sha = _sha(tar.extractfile(membres[nom]).read())
                reponses[sid][f] = sha
                if sha != m.get("sha256"):
                    erreurs.append(f"{nom} : empreinte {sha[:12]}… au lieu de {str(m.get('sha256'))[:12]}…")
            for nom in membres:
                if nom.startswith(f"raw/{sid}/") and nom.endswith(".json") and nom != nom_man \
                        and nom.rsplit("/", 1)[1] not in manifeste:
                    erreurs.append(f"{nom} : réponse hors manifeste")
        if "environnement.json" in membres:
            env = json.loads(tar.extractfile(membres["environnement.json"]).read())
    if lot_json.exists():
        lot = json.loads(lot_json.read_text())
        if lot.get("archive") == archive.name:
            if _sha(archive.read_bytes()) != lot.get("archive_sha256"):
                erreurs.append("empreinte de l'archive différente de lot.json")
            if lot.get("reponses") != reponses:
                erreurs.append("empreintes des réponses différentes de lot.json")
            if env is not None and env.get("commit_code") != lot.get("commit_code"):
                erreurs.append("commit du code de l'archive différent de lot.json")
    if erreurs:
        raise IntegriteLot("; ".join(erreurs))
    return reponses


def verifier(archive):
    try:
        reponses = verifier_integrite(archive)
    except IntegriteLot as exc:
        print(f"  ✗ intégrité de l'archive : {exc}")
        sys.exit(1)
    print(f"  intégrité vérifiée : {sum(len(r) for r in reponses.values())} réponses ({Path(archive).name})")


# ----------------------------------------------------------------------------------------------- rejeu

RESULTATS = ("sensibilite_ied.json", "ecodotations.json", "evolution_ied.json")  # résultats dérivés recalculés au rejeu
ANALYSES = ("sensibilite_ied.py", "ecodotations.py", "evolution_ied.py")


def rejouer(archive):
    archive = Path(archive).resolve()
    verifier(archive)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        shutil.copytree(ROOT / "pipeline", tmp / "pipeline", ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copytree(ROOT / "analyse", tmp / "analyse", ignore=shutil.ignore_patterns("__pycache__"))
        with tarfile.open(archive) as tar:
            tar.extractall(tmp / "data", filter="data")
        subprocess.run([sys.executable, "-m", "pipeline", "process", *SOURCES, "--offline"], cwd=tmp, check=True,
                       stdout=subprocess.DEVNULL)
        differences = []
        (tmp / "calibration").mkdir()
        for sid, nom in SOURCES.items():
            rejoue_brut = (tmp / "data" / "interim" / f"{sid}.json").read_text()
            (tmp / "calibration" / nom).write_text(rejoue_brut)
            if json.loads(rejoue_brut)["data"] != lire(nom)["data"]:
                differences.append(nom)
        if not differences:
            for script in ANALYSES:
                subprocess.run([sys.executable, str(tmp / "analyse" / script)], cwd=tmp, check=True,
                               stdout=subprocess.DEVNULL)
            for nom in RESULTATS:
                if (CAL / nom).exists() and \
                        json.loads((tmp / "calibration" / nom).read_text()) != lire(nom):
                    differences.append(nom)
    if differences:
        print(f"  ✗ rejeu différent du lot publié : {', '.join(differences)}")
        sys.exit(1)
    print(f"  rejeu hors réseau identique au lot publié, séries et résultats ({archive.name})")


if __name__ == "__main__":
    commande = sys.argv[1] if len(sys.argv) > 1 else ""
    if commande == "controler":
        controler()
    elif commande == "archiver" and len(sys.argv) == 3:
        archiver(sys.argv[2])
    elif commande == "verifier" and len(sys.argv) == 3:
        verifier(sys.argv[2])
    elif commande == "rejouer" and len(sys.argv) == 3:
        rejouer(sys.argv[2])
    else:
        sys.exit(__doc__)
