"""Économie Homéostatique — règles communes de téléchargement et de complétude des lots de calibration.

* Un téléchargement réussi efface la trace d'erreur précédente de la même table : l'état courant ne montre que les
  incidents du dernier lot. L'historique horodaté des incidents est tenu par le workflow (provenance/incidents.log).
* Un échec laisse une trace d'erreur horodatée. Si une ancienne réponse reste en cache, la table est marquée
  « périmée », avec la date de cette réponse.
* Chaque source déclare ses tables requises. Une table requise absente, vide ou périmée arrête le traitement : le
  workflow échoue avant l'enregistrement, et le dernier lot publié reste en place."""

from __future__ import annotations

import json
import socket
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

ERREURS_RESEAU = (urllib.error.URLError, TimeoutError, ConnectionError, socket.timeout)


class LotIncomplet(RuntimeError):
    """Une table requise du lot est absente, vide ou périmée."""


def trace_erreur(raw_dir: Path, cle: str) -> Path:
    return raw_dir / f"{cle}.erreur.txt"


def telecharger(source, cle: str, url: str, force: bool) -> bool:
    """Télécharge une table ; True en cas de succès. Un échec réseau est consigné, sans interrompre les autres tables."""
    note = trace_erreur(source.raw_dir, cle)
    try:
        source.download(url, f"{cle}.json", force=force)
    except ERREURS_RESEAU as exc:
        detail = f"HTTP {exc.code} {exc.reason}\n{exc.read()[:2000]!r}" if isinstance(exc, urllib.error.HTTPError) \
            else f"{type(exc).__name__} : {exc}"
        note.parent.mkdir(parents=True, exist_ok=True)
        note.write_text(f"{datetime.now(timezone.utc).isoformat(timespec='seconds')}\n{url}\n{detail}\n")
        print(f"    ! {cle} : échec du téléchargement, détail dans {note.name}")
        return False
    note.unlink(missing_ok=True)
    return True


def etat(raw_dir: Path, cle: str) -> dict:
    """État d'une table dans le cache : réponse présente, périmée (échec du dernier téléchargement), erreur."""
    chemin, note = raw_dir / f"{cle}.json", trace_erreur(raw_dir, cle)
    erreur = note.read_text() if note.exists() else None
    recupere = None
    manifeste = raw_dir / "manifest.json"
    if manifeste.exists():
        recupere = json.loads(manifeste.read_text()).get(f"{cle}.json", {}).get("retrieved")
    return {"present": chemin.exists(), "perime": chemin.exists() and erreur is not None,
            "erreur": erreur, "recupere": recupere}


def verifier(source_id: str, tables: dict, requis: tuple) -> None:
    """Arrête le traitement si une table requise est absente, vide ou périmée."""
    manque = [c for c in requis if not tables.get(c, {}).get("disponible") or tables[c].get("perime")]
    if manque:
        raise LotIncomplet(f"{source_id} : tables requises absentes, vides ou périmées : {', '.join(manque)}")
