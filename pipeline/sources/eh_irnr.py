"""Économie Homéostatique — séries candidates pour l'IRNR (WP EH V1.0, §6.2).

L'IRNR mesure la consommation de ressources non renouvelables d'une zone économique. Le WP en esquisse une
spécification candidate, ressource par ressource, rapportant la consommation de la zone à une référence annuelle par
habitant dérivée des stocks disponibles et d'un horizon choisi, et la fonde sur les comptes de flux de matières
d'Eurostat (EW-MFA), avec l'empreinte matière (RMC) comme point de comparaison méthodologique.

Ce module rassemble les séries de consommation par habitant des trois catégories non renouvelables des comptes de
flux de matières (minerais métalliques MF2, minéraux non métalliques MF3, matières énergétiques fossiles MF4), pour
les États membres de l'UE-27 et l'agrégat UE-27 :

* consommation intérieure de matières (DMC, table env_ac_mfa), en tonnes par habitant ;
* empreinte matière (RMC, table env_ac_rme), en tonnes par habitant, ventilée par catégorie lorsque la table publie
  cette ventilation, et en total (toutes matières, biomasse comprise) pour l'ensemble des États membres.

La lecture exige les codes attendus (indicateur, unité) et s'arrête sur une erreur si deux séries publiées se
confondent après sélection, ou si l'indicateur RMC est absent : un changement de schéma de la table ne peut pas
modifier en silence l'unité ou l'indicateur retenu.

Il ne calcule pas l'IRNR : les références par habitant (stocks, horizon, recyclage, substitutions admises) et les
repères 0, 1 et 2 de la normalisation relèvent de la spécification du cadre."""

from __future__ import annotations

import json
import urllib.parse

from ..core.source import Source, SourceInfo
from .eh_beta_pub import UE27, AGREGAT_UE27
from .eh_lot import etat, telecharger, verifier
from .eurostat import API

SINCE = 2010
GEOS = UE27 + (AGREGAT_UE27,)
CATEGORIES = {
    "MF2": "minerais métalliques",
    "MF3": "minéraux non métalliques",
    "MF4": "matières énergétiques fossiles",
}

TABLES = {
    "dmc": ("env_ac_mfa", {"indic_env": "DMC", "unit": "T_HAB"}),
    "rmc": ("env_ac_rme", {"unit": "T_HAB"}),
}
REQUIS = ("dmc", "rmc")
TOTAL = "TOTAL"  # code Eurostat du total des matières


class SchemaInattendu(ValueError):
    """La réponse ne correspond pas au schéma attendu (codes absents, séries confondues)."""


def url(table: str, filtres: dict) -> str:
    q = [("sinceTimePeriod", str(SINCE))] + list(filtres.items()) + [("geo", g) for g in GEOS]
    return API.format(table=table, query=urllib.parse.urlencode(q))


def lire_multi(d: dict) -> dict:
    """JSON-stat 2.0 → {(code, ...) des dimensions autres que geo et time: {geo: {année: (valeur, statut)}}}."""
    dims, size = d["id"], d["size"]
    stride = [1] * len(dims)
    for k in range(len(dims) - 2, -1, -1):
        stride[k] = stride[k + 1] * size[k + 1]
    valeurs, statuts = d["value"], d.get("status") or {}
    if isinstance(valeurs, list):
        valeurs = {str(i): v for i, v in enumerate(valeurs) if v is not None}
    if isinstance(statuts, list):
        statuts = {str(i): s for i, s in enumerate(statuts) if s}
    cats = {dim: {i: c for c, i in d["dimension"][dim]["category"]["index"].items()} for dim in dims}
    autres = [dim for dim in dims if dim not in ("geo", "time")]
    out: dict = {}
    for cle, v in valeurs.items():
        if v is None:
            continue
        reste, pos = int(cle), {}
        for k, dim in enumerate(dims):
            pos[dim], reste = divmod(reste, stride[k])
        code = {dim: cats[dim][pos[dim]] for dim in dims}
        serie = tuple(code[dim] for dim in autres)
        out.setdefault(serie, {}).setdefault(code["geo"], {})[int(code["time"])] = (v, statuts.get(cle, ""))
    return out


def dimensions(d: dict) -> dict:
    """{dimension: {code: libellé}}, pour documenter ce que la table publie."""
    return {dim: {c: d["dimension"][dim]["category"].get("label", {}).get(c, c)
                  for c in d["dimension"][dim]["category"]["index"]}
            for dim in d["id"] if dim not in ("geo", "time")}


def extraire(series: dict, dims: list[str], material_dim: str = "material", filtre: dict | None = None,
             categories=CATEGORIES) -> dict:
    """Garde les séries des catégories demandées (MF2–MF4 par défaut) qui portent les codes de `filtre`
    → {catégorie: {geo: {année: [valeur, statut]}}}.

    Chaque dimension de `filtre` doit exister dans la table. Deux séries distinctes retenues pour une même catégorie
    (dimension résiduelle non fixée : unité, indicateur…) arrêtent la lecture."""
    autres = [d for d in dims if d not in ("geo", "time")]
    absentes = [k for k in (filtre or {}) if k not in autres]
    if absentes or material_dim not in autres:
        raise SchemaInattendu(f"dimensions attendues absentes : {absentes or [material_dim]} (table : {autres})")
    out, origine = {}, {}
    for serie, rows in series.items():
        code = dict(zip(autres, serie))
        if code.get(material_dim) not in categories:
            continue
        if any(code.get(k) != v for k, v in (filtre or {}).items()):
            continue
        cat = code[material_dim]
        if cat in origine and origine[cat] != serie:
            raise SchemaInattendu(f"catégorie {cat} : séries confondues après sélection {origine[cat]} et {serie}")
        origine[cat] = serie
        dest = out.setdefault(cat, {})
        for geo, ans in rows.items():
            dest.setdefault(geo, {}).update({str(a): [v, s] for a, (v, s) in ans.items()})
    return out


class EhIrnr(Source):
    info = SourceInfo(
        id="eh_irnr",
        title="Économie Homéostatique — séries candidates pour l'IRNR (comptes de flux de matières)",
        publisher="Eurostat (European Commission), from the national statistical institutes",
        homepage="https://ec.europa.eu/eurostat/databrowser/view/env_ac_mfa/default/table",
        license="Free reuse (Eurostat reuse policy, CC BY 4.0)",
        description="Consommation intérieure de matières (DMC, env_ac_mfa) et empreinte matière (RMC, env_ac_rme) par "
        "habitant pour les minerais métalliques, les minéraux non métalliques et les matières énergétiques fossiles, "
        "États membres de l'UE-27 et agrégat UE-27.",
        used_for=["Séries candidates de l'IRNR (Économie Homéostatique)"],
    )

    def fetch(self, force=False):
        for cle, (table, filtres) in TABLES.items():
            telecharger(self, cle, url(table, filtres), force)

    def process(self):
        resultat, fichiers, tables = {}, [], {}
        for cle, (table, filtres) in TABLES.items():
            e = etat(self.raw_dir, cle)
            if not e["present"]:
                tables[cle] = {"table": table, "filtres": filtres, "disponible": False,
                               "erreur": e["erreur"] or "non téléchargée"}
                continue
            d = json.loads((self.raw_dir / f"{cle}.json").read_text())
            fichiers.append(f"{cle}.json")
            dims = dimensions(d)
            attendu = dict(filtres)
            if cle == "rmc":
                # Indicateur RMC dans la dimension qui le porte, quel que soit son nom dans la table.
                porteuses = [dim for dim, codes in dims.items() if "RMC" in codes]
                if len(porteuses) != 1:
                    raise SchemaInattendu(f"{table} : indicateur RMC introuvable ou ambigu ({porteuses})")
                attendu[porteuses[0]] = "RMC"
            brut = lire_multi(d)
            series = extraire(brut, d["id"], filtre=attendu)
            pays = sorted({g for cat in series.values() for g in cat})
            annees = sorted({a for cat in series.values() for rows in cat.values() for a in rows})
            print(f"    {cle} {table}: {len(series)} catégories, {len(pays)} zones, "
                  f"{annees[0] if annees else '–'}–{annees[-1] if annees else '–'}"
                  + (" (réponse périmée)" if e["perime"] else ""))
            tables[cle] = {"table": table, "filtres": filtres, "codes_exiges": attendu, "disponible": bool(series),
                           "perime": e["perime"], "recupere": e["recupere"], "erreur": e["erreur"],
                           "mise_a_jour": d.get("updated"), "dimensions": dims}
            resultat[cle] = series
            if cle == "rmc" and TOTAL in dims.get("material", {}):
                total = extraire(brut, d["id"], filtre=attendu, categories={TOTAL: "total"}).get(TOTAL, {})
                resultat["rmc_total"] = total
                tables[cle]["total_zones"] = sorted(total)
        verifier(self.info.id, tables, REQUIS)
        return {
            "vintage": "Eurostat, " + ", ".join(f"{c} {(t.get('mise_a_jour') or '')[:10]}"
                                               for c, t in tables.items() if t.get("disponible")),
            "_files": fichiers,
            "unite": "tonnes par habitant",
            "statuts": "codes Eurostat : p provisoire, e estimé, b rupture de série, d définition différente",
            "categories": CATEGORIES,
            "rmc_total": "empreinte matière toutes matières (code TOTAL, biomasse comprise), même unité",
            "series": resultat,
            "tables": tables,
        }
