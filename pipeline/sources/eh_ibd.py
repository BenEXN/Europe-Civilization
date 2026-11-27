"""Économie Homéostatique — séries candidates pour l'IBD (WP EH V1.0, §6.2).

L'IBD est conçu comme un indicateur d'état de la biodiversité d'un territoire — diversité génétique, des espèces et
des écosystèmes — à construire par la combinaison de plusieurs familles de données : abondance et diversité des
espèces, état et connectivité des habitats, intégrité des écosystèmes. Le WP note que l'Indice Planète Vivante n'en
couvre qu'une partie et n'existe pas à l'échelle des États membres.

Ce module rassemble les séries publiques disponibles à cette échelle, pour les États membres de l'UE-27 et l'agrégat
UE-27 :

* abondance des espèces : indice des oiseaux communs des milieux agricoles (env_bio2) et indices des oiseaux communs
  par type d'estimation (env_bio3, agrégat UE-27) ;
* état des écosystèmes : surface touchée par la sécheresse (sdg_15_42) ;
* protection des habitats : surfaces protégées (env_bio4).

L'IBD lui-même n'est pas calculé."""

from __future__ import annotations

from ..core.source import SourceInfo
from .eh_iee import SeriesEurostat

TABLES = {
    "oiseaux_agricoles": ("env_bio2", {}, "abondance des espèces"),
    "oiseaux_communs": ("env_bio3", {}, "abondance des espèces"),
    "secheresse": ("sdg_15_42", {}, "état des écosystèmes"),
    "aires_protegees": ("env_bio4", {}, "protection des habitats"),
}


class EhIbd(SeriesEurostat):
    TABLES = TABLES
    info = SourceInfo(
        id="eh_ibd",
        title="Économie Homéostatique — séries candidates pour l'IBD (état de la biodiversité)",
        publisher="Eurostat (European Commission), from the EBCC/PECBMS and the EEA",
        homepage="https://ec.europa.eu/eurostat/web/environment/database",
        license="Free reuse (Eurostat reuse policy, CC BY 4.0)",
        description="Indices des oiseaux communs (env_bio2, env_bio3), surface des écosystèmes touchée par la sécheresse (sdg_15_42) et aires protégées (env_bio4), UE-27 et États "
        "membres.",
        used_for=["Séries candidates de l'IBD (Économie Homéostatique)"],
    )
