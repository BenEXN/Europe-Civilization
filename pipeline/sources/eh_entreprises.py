"""Économie Homéostatique — assiette 𝒴 du canal entreprises et PIB (WP EH V1.0, §4.2).

Le canal entreprises de l'écodotation s'écrit DENT = IED × 𝒴, où 𝒴 est la production de l'entreprise, mesurée par
ses charges d'exploitation (hors impôts, assurances, produits financiers et distribution de bénéfices) lissées sur les
trois dernières années. La somme des DENT d'une zone, DTENT = IED × Σ𝒴, ne demande que le total national de 𝒴.

Ce module rassemble, pour les États membres de l'UE-27 et l'agrégat UE-27, les grandeurs des comptes nationaux par
secteur institutionnel (nasa_10_nf_tr, millions d'euros courants) qui approchent ce total :

* consommations intermédiaires (P2) : achats de biens et de services aux autres unités, comptés chez chaque
  producteur ;
* rémunération des salariés versée (D1) ;
* consommation de capital fixe (P51C), proche des dotations aux amortissements ;
* production (P1), pour comparaison ;

pour les sociétés non financières (S11) et les sociétés financières (S12), ainsi que le PIB (nama_10_gdp, B1GQ) et
la population moyenne (nama_10_pe). Les comptes nationaux couvrent les 27 pays sur la même base que le PIB, ce qui
permet de rapporter les canaux de l'écodotation au PIB. Les consommations intermédiaires n'y sont pas consolidées
entre entreprises : un même bien est compté à chaque étape de la chaîne de production, comme dans une somme des 𝒴.

La lecture exige le sens attendu de chaque opération (P1 en ressources, les autres en emplois) et s'arrête sur une
erreur si une opération attendue manque ou si deux séries se confondent. Les écodotations sont calculées par
analyse/ecodotations.py."""

from __future__ import annotations

import json
import urllib.parse

from ..core.source import Source, SourceInfo
from .eh_beta_pub import AGREGAT_UE27, UE27
from .eh_irnr import SchemaInattendu, dimensions, lire_multi
from .eh_lot import etat, telecharger, verifier
from .eurostat import API

SINCE = 2015
GEOS = UE27 + (AGREGAT_UE27,)
SECTEURS = ("S11", "S12")
OPERATIONS = {"P1": "RECV", "P2": "PAID", "D1": "PAID", "P51C": "PAID"}  # opération → sens attendu

# clé → (table, filtres ; une liste donne plusieurs valeurs)
TABLES = {
    "secteurs": ("nasa_10_nf_tr", {"unit": "CP_MEUR", "sector": list(SECTEURS), "na_item": list(OPERATIONS)}),
    "pib": ("nama_10_gdp", {"unit": "CP_MEUR", "na_item": "B1GQ"}),
    "population": ("nama_10_pe", {"unit": "THS_PER", "na_item": "POP_NC"}),
}
REQUIS = tuple(TABLES)


def url(table: str, filtres: dict) -> str:
    q = [("sinceTimePeriod", str(SINCE))]
    for k, v in filtres.items():
        q += [(k, x) for x in (v if isinstance(v, list) else [v])]
    q += [("geo", g) for g in GEOS]
    return API.format(table=table, query=urllib.parse.urlencode(q))


def _serie(d: dict, voulu: dict) -> dict:
    """Unique série dont les codes contiennent `voulu` → {geo: {"année": [v, s]}} ; erreur si absente ou confondue."""
    ids = [x for x in d["id"] if x not in ("geo", "time")]
    trouvees = [rows for codes, rows in lire_multi(d).items()
                if all(dict(zip(ids, codes)).get(k) == v for k, v in voulu.items())]
    if len(trouvees) != 1:
        raise SchemaInattendu(f"{voulu} : {len(trouvees)} séries au lieu d'une")
    return {g: {str(a): [v, s] for a, (v, s) in ans.items()} for g, ans in trouvees[0].items()}


def lire_secteurs(d: dict) -> dict:
    """→ {secteur: {opération: {geo: {"année": [v, s]}}}} ; exige chaque opération dans son sens attendu."""
    codes = {dim: set(d["dimension"][dim]["category"]["index"]) for dim in d["id"]}
    if "direct" not in codes:
        raise SchemaInattendu("dimension « direct » (sens de l'opération) absente")
    out = {}
    for sec in SECTEURS:
        for op, sens in OPERATIONS.items():
            if sens not in codes["direct"]:
                raise SchemaInattendu(f"sens {sens} absent ; sens publiés : {sorted(codes['direct'])}")
            out.setdefault(sec, {})[op] = _serie(d, {"sector": sec, "na_item": op, "direct": sens})
    return out


class EhEntreprises(Source):
    info = SourceInfo(
        id="eh_entreprises",
        title="Économie Homéostatique — assiette 𝒴 du canal entreprises (comptes nationaux par secteur) et PIB",
        publisher="Eurostat (European Commission), from the national statistical institutes",
        homepage="https://ec.europa.eu/eurostat/databrowser/view/nasa_10_nf_tr/default/table",
        license="Free reuse (Eurostat reuse policy, CC BY 4.0)",
        description="Production, consommations intermédiaires, rémunération des salariés et consommation de capital fixe "
        "des sociétés non financières et financières (nasa_10_nf_tr, millions d'euros courants), PIB (nama_10_gdp) et "
        "population moyenne (nama_10_pe), UE-27 et États membres.",
        used_for=["Ordre de grandeur des canaux de l'écodotation rapportés au PIB (Économie Homéostatique)"],
    )

    def fetch(self, force=False):
        for cle, (table, filtres) in TABLES.items():
            telecharger(self, cle, url(table, filtres), force)

    def process(self):
        tables, donnees, fichiers = {}, {}, []
        for cle, (table, filtres) in TABLES.items():
            e = etat(self.raw_dir, cle)
            info = {"table": table, "filtres": filtres, "requise": cle in REQUIS}
            if not e["present"]:
                tables[cle] = {**info, "disponible": False, "erreur": e["erreur"] or "non téléchargée"}
                continue
            d = json.loads((self.raw_dir / f"{cle}.json").read_text())
            fichiers.append(f"{cle}.json")
            if cle == "secteurs":
                donnees[cle] = lire_secteurs(d)
            else:
                donnees[cle] = _serie(d, {"na_item": filtres["na_item"], "unit": filtres["unit"]})
            tables[cle] = {**info, "disponible": True, "perime": e["perime"], "recupere": e["recupere"],
                           "erreur": e["erreur"], "mise_a_jour": d.get("updated"), "dimensions": dimensions(d)}
            print(f"    {cle:12s} {table:14s} lue" + (" (réponse périmée)" if e["perime"] else ""))
        verifier(self.info.id, tables, REQUIS)
        return {
            "vintage": "Eurostat, " + ", ".join(f"{c} {(t.get('mise_a_jour') or '')[:10]}" for c, t in tables.items()),
            "_files": fichiers,
            "statuts": "codes Eurostat : p provisoire, e estimé, b rupture de série, d définition différente",
            "unites": {"secteurs": "millions d'euros courants", "pib": "millions d'euros courants",
                       "population": "milliers de personnes"},
            "secteurs": donnees["secteurs"],
            "pib": donnees["pib"],
            "population": donnees["population"],
            "tables": tables,
        }
