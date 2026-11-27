"""Économie Homéostatique — séries candidates pour l'IEE (WP EH V1.0, §6.2).

L'IEE est conçu comme un indicateur synthétique des pressions exercées par les activités humaines sur les écosystèmes
et les ressources renouvelables. Le WP envisage d'y intégrer différentes formes de pollution, l'usage de ressources
renouvelables rapporté à leur capacité de renouvellement, et des dimensions d'anthropisation, d'artificialisation et
de fragmentation des territoires ; la sélection, la normalisation et l'agrégation restent à formaliser.

Ce module rassemble, pour les États membres de l'UE-27 et l'agrégat UE-27, une série publique par famille de pression :

* pollution atmosphérique et climat : émissions de gaz à effet de serre des activités économiques et des ménages
  (comptes d'émissions atmosphériques, env_ac_ainah_r2) ;
* pollution des sols et des eaux : bilans bruts de l'azote et du phosphore sur les terres agricoles (aei_pr_gnb) ;
* ressources renouvelables rapportées à leur renouvellement : indice d'exploitation de l'eau (WEI+, sdg_06_60) ;
* artificialisation : occupation du sol par grande catégorie, dont les terres artificialisées (enquête LUCAS,
  lan_lcv_ovw), en pourcentage du territoire, et imperméabilisation des sols (sdg_11_32) ;
* empreinte de consommation : émissions de gaz à effet de serre selon la production et selon la consommation
  (application FIGARO, cli_gge_foot), pour traiter les pressions déplacées par les échanges.

Les tables sont lues sans présupposer toutes leurs dimensions : chaque série publiée est conservée avec ses codes, et
la liste des dimensions de chaque table est enregistrée. Une table indisponible est signalée sans interrompre les
autres. L'IEE lui-même n'est pas calculé."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse

from ..core.source import Source, SourceInfo
from .eh_beta_pub import AGREGAT_UE27, UE27
from .eh_irnr import dimensions, lire_multi
from .eurostat import API

SINCE = 2010
GEOS = UE27 + (AGREGAT_UE27,)

# clé → (table, filtres, famille de pression)
TABLES = {
    "ges": ("env_ac_ainah_r2", {"airpol": "GHG", "nace_r2": "TOTAL_HH"}, "pollution atmosphérique et climat"),
    "azote": ("aei_pr_gnb", {}, "pollution des sols et des eaux (azote et phosphore)"),
    "eau": ("sdg_06_60", {}, "ressources renouvelables rapportées à leur renouvellement"),
    "artificialisation": ("lan_lcv_ovw", {"unit": "PC"}, "artificialisation"),
    "impermeabilisation": ("sdg_11_32", {}, "artificialisation"),
    "ges_empreinte": ("cli_gge_foot", {}, "pollution atmosphérique et climat (empreinte de consommation)"),
}


def url(table: str, filtres: dict) -> str:
    q = [("sinceTimePeriod", str(SINCE))] + list(filtres.items()) + [("geo", g) for g in GEOS]
    return API.format(table=table, query=urllib.parse.urlencode(q))


def aplatir(series: dict, ids: list[str]) -> dict:
    """{(codes...): {geo: {année: (v, s)}}} → {"dim=code|dim=code": {geo: {"année": [v, s]}}}."""
    autres = [d for d in ids if d not in ("geo", "time")]
    return {"|".join(f"{d}={c}" for d, c in zip(autres, codes)):
            {geo: {str(a): [v, s] for a, (v, s) in ans.items()} for geo, ans in rows.items()}
            for codes, rows in series.items()}


class SeriesEurostat(Source):
    """Série de tables Eurostat lues sans présupposer leurs dimensions ; une table indisponible est signalée sans
    interrompre les autres. Les sous-classes définissent `info` et `TABLES` (clé → (table, filtres, famille))."""

    TABLES: dict = {}

    def fetch(self, force=False):
        for cle, (table, filtres, _) in self.TABLES.items():
            try:
                self.download(url(table, filtres), f"{cle}.json", force=force)
            except urllib.error.HTTPError as exc:
                note = self.raw_dir / f"{cle}.erreur.txt"
                note.parent.mkdir(parents=True, exist_ok=True)
                note.write_text(f"{url(table, filtres)}\nHTTP {exc.code} {exc.reason}\n{exc.read()[:2000]!r}\n")
                print(f"    ! {table} : HTTP {exc.code}, détail dans {note.name}")

    def process(self):
        series, fichiers, tables = {}, [], {}
        for cle, (table, filtres, famille) in self.TABLES.items():
            chemin = self.raw_dir / f"{cle}.json"
            info = {"table": table, "filtres": filtres, "famille": famille}
            if not chemin.exists():
                erreur = self.raw_dir / f"{cle}.erreur.txt"
                tables[cle] = {**info, "disponible": False,
                               "erreur": erreur.read_text() if erreur.exists() else "non téléchargée"}
                print(f"    {cle:18s} {table:16s} indisponible")
                continue
            d = json.loads(chemin.read_text())
            fichiers.append(f"{cle}.json")
            s = aplatir(lire_multi(d), d["id"])
            zones = sorted({g for rows in s.values() for g in rows})
            annees = sorted({a for rows in s.values() for ans in rows.values() for a in ans})
            print(f"    {cle:18s} {table:16s} {len(s)} séries, {len(zones)} zones, "
                  f"{annees[0] if annees else '–'}–{annees[-1] if annees else '–'}")
            tables[cle] = {**info, "disponible": bool(s), "mise_a_jour": d.get("updated"),
                           "dimensions": dimensions(d), "zones": zones}
            series[cle] = s
        return {
            "vintage": "Eurostat, " + ", ".join(f"{c} {(t.get('mise_a_jour') or '')[:10]}"
                                               for c, t in tables.items() if t.get("disponible")),
            "_files": fichiers,
            "statuts": "codes Eurostat : p provisoire, e estimé, b rupture de série, d définition différente",
            "series": series,
            "tables": tables,
        }


class EhIee(SeriesEurostat):
    TABLES = TABLES
    info = SourceInfo(
        id="eh_iee",
        title="Économie Homéostatique — séries candidates pour l'IEE (pressions sur les écosystèmes)",
        publisher="Eurostat (European Commission), from the national statistical institutes and the EEA",
        homepage="https://ec.europa.eu/eurostat/web/environment/database",
        license="Free reuse (Eurostat reuse policy, CC BY 4.0)",
        description="Gaz à effet de serre (env_ac_ainah_r2), bilans de l'azote et du phosphore (aei_pr_gnb), exploitation de l'eau "
        "(sdg_06_60), occupation du sol (lan_lcv_ovw), imperméabilisation (sdg_11_32) et empreinte de gaz à effet de serre "
        "(cli_gge_foot), UE-27 et États membres.",
        used_for=["Séries candidates de l'IEE (Économie Homéostatique)"],
    )
