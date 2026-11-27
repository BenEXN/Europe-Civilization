"""Économie Homéostatique — calibration de β_pub (WP EH V1.0, §4.2, note 47).

β_pub est le paramètre de base du canal État : DETA = IED × β_pub × c. La note 47 le calibre comme la moyenne
arithmétique des dépenses publiques par habitant des dix États membres de l'UE-27 où elles sont les plus élevées :
dépenses totales des administrations publiques (secteur S13, poste TE, euros courants) rapportées à la population
moyenne. Le WP exprime β_pub en euros constants 2017 ; les autres millésimes sont ramenés en euros 2017 par le
déflateur implicite du PIB de l'UE-27.

Millésime de référence : 2017. Pour chaque millésime sont publiés : les codes Eurostat (provisoire, estimé, rupture,
définition différente) des valeurs des dix pays retenus et du déflateur ; ceux des dix-sept autres pays, dont une
révision peut modifier la sélection ; l'écart relatif entre le 10e et le 11e pays, qui mesure la marge de la
sélection. Un millésime est dit « sans drapeau » quand aucune valeur des 27 pays ni du déflateur ne porte de code.
L'absence de code ne garantit pas l'absence de révision ultérieure : la stabilité se constate d'un lot à l'autre."""

from __future__ import annotations

import json
import urllib.parse

from ..core.source import Source, SourceInfo
from .eurostat import API

SINCE = 2015
ANNEE_REFERENCE = 2017
ANNEE_BASE_PRIX = 2017
N_PAYS = 10

UE27 = ("AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE", "EL", "ES", "FI", "FR", "HR", "HU", "IE", "IT", "LT", "LU",
        "LV", "MT", "NL", "PL", "PT", "RO", "SE", "SI", "SK")
AGREGAT_UE27 = "EU27_2020"

# id → (table, filtres)
TABLES = {
    "depenses": ("gov_10a_main", {"sector": "S13", "na_item": "TE", "unit": "MIO_EUR"}),
    "population": ("nama_10_pe", {"na_item": "POP_NC", "unit": "THS_PER"}),
    "deflateur": ("nama_10_gdp", {"na_item": "B1GQ", "unit": "PD15_EUR"}),
}

STATUTS = {"p": "provisoire", "e": "estimé", "b": "rupture de série", "d": "définition différente"}


def url(table: str, filtres: dict) -> str:
    q = [("sinceTimePeriod", str(SINCE))] + list(filtres.items())
    return API.format(table=table, query=urllib.parse.urlencode(q))


def lire(d: dict) -> dict:
    """JSON-stat 2.0 à une seule série (toutes les dimensions fixées sauf geo et time)
    → {geo: {année: (valeur, statut)}}."""
    dims, size = d["id"], d["size"]
    stride = [1] * len(dims)
    for k in range(len(dims) - 2, -1, -1):
        stride[k] = stride[k + 1] * size[k + 1]
    gi, ti = dims.index("geo"), dims.index("time")
    for k, dim in enumerate(dims):
        if k not in (gi, ti) and size[k] != 1:
            raise ValueError(f"dimension {dim!r} non fixée ({size[k]} valeurs)")
    valeurs, statuts = d["value"], d.get("status") or {}
    if isinstance(valeurs, list):
        valeurs = {str(i): v for i, v in enumerate(valeurs) if v is not None}
    if isinstance(statuts, list):
        statuts = {str(i): s for i, s in enumerate(statuts) if s}
    geos = d["dimension"]["geo"]["category"]["index"]
    annees = d["dimension"]["time"]["category"]["index"]
    out: dict = {}
    for geo, g in geos.items():
        for annee, t in annees.items():
            cle = str(g * stride[gi] + t * stride[ti])
            if cle in valeurs and valeurs[cle] is not None:
                out.setdefault(geo, {})[int(annee)] = (valeurs[cle], statuts.get(cle, ""))
    return out


def drapeaux(statut: str) -> list[str]:
    return [STATUTS[c] for c in statut if c in STATUTS]


def calculer(depenses: dict, population: dict, deflateur: dict) -> dict:
    """β_pub pour chaque année où les trois tables sont disponibles pour toute l'UE-27."""
    def_ue = deflateur.get(AGREGAT_UE27, {})
    if ANNEE_BASE_PRIX not in def_ue:
        raise ValueError(f"déflateur UE-27 absent pour l'année de base {ANNEE_BASE_PRIX}")
    annees = sorted(a for a in def_ue
                    if all(a in depenses.get(g, {}) and a in population.get(g, {}) for g in UE27))
    resultats = {}
    for a in annees:
        for g in UE27:
            if not (depenses[g][a][0] >= 0 and population[g][a][0] > 0):
                raise ValueError(f"{g} {a} : dépenses négatives ou population non positive")
        for an in (a, ANNEE_BASE_PRIX):
            if not def_ue[an][0] > 0:
                raise ValueError(f"déflateur UE-27 {an} non positif")
        par_hab = {g: depenses[g][a][0] * 1e6 / (population[g][a][0] * 1e3) for g in UE27}
        classement = sorted(par_hab, key=par_hab.get, reverse=True)
        tete, reste = classement[:N_PAYS], classement[N_PAYS:]
        nominal = sum(par_hab[g] for g in tete) / N_PAYS
        facteur = def_ue[ANNEE_BASE_PRIX][0] / def_ue[a][0]

        def codes(pays):
            out = []
            for g in pays:
                for nom, table in (("dépenses", depenses), ("population", population)):
                    for f in drapeaux(table[g][a][1]):
                        out.append(f"{g} {nom} : {f}")
            return sorted(set(out))

        selection = codes(tete)
        for nom, an in (("déflateur UE-27", a), (f"déflateur UE-27 {ANNEE_BASE_PRIX}", ANNEE_BASE_PRIX)):
            for f in drapeaux(def_ue[an][1]):
                selection.append(f"{nom} : {f}")
        hors = codes(reste)
        v10, v11 = par_hab[tete[-1]], par_hab[reste[0]]
        resultats[str(a)] = {
            "pays": [{"geo": g, "depense_par_habitant_eur": round(par_hab[g], 2)} for g in tete],
            "onzieme": {"geo": reste[0], "depense_par_habitant_eur": round(v11, 2)},
            "marge_10_11": round((v10 - v11) / v10, 6),
            "beta_pub_nominal_eur": round(nominal, 2),
            "beta_pub_eur_constants": round(nominal * facteur, 2),
            "facteur_deflation": round(facteur, 6),
            "drapeaux_selection": sorted(set(selection)),
            "drapeaux_hors_selection": hors,
            "sans_drapeau": not selection and not hors,
        }
    return resultats


class EhBetaPub(Source):
    info = SourceInfo(
        id="eh_beta_pub",
        title="Économie Homéostatique — calibration de β_pub (note 47 du WP V1.0)",
        publisher="Eurostat (European Commission), from the national statistical institutes",
        homepage="https://ec.europa.eu/eurostat/databrowser/view/gov_10a_main/default/table",
        license="Free reuse (Eurostat reuse policy, CC BY 4.0)",
        description="Dépenses totales des administrations publiques (gov_10a_main, S13, TE, millions d'euros), "
        "population moyenne (nama_10_pe, POP_NC) et déflateur implicite du PIB (nama_10_gdp, PD15_EUR) : moyenne des "
        f"dix États membres de l'UE-27 aux dépenses publiques par habitant les plus élevées, en euros {ANNEE_BASE_PRIX}.",
        used_for=["Calibration du canal État (DETA) de l'Économie Homéostatique"],
    )

    def fetch(self, force=False):
        for cle, (table, filtres) in TABLES.items():
            self.download(url(table, filtres), f"{cle}.json", force=force)

    def process(self):
        donnees = {cle: lire(json.loads((self.raw_dir / f"{cle}.json").read_text())) for cle in TABLES}
        mises_a_jour = {cle: json.loads((self.raw_dir / f"{cle}.json").read_text()).get("updated") for cle in TABLES}
        resultats = calculer(donnees["depenses"], donnees["population"], donnees["deflateur"])
        ref = resultats.get(str(ANNEE_REFERENCE))
        for a, r in resultats.items():
            n_s, n_h = len(r["drapeaux_selection"]), len(r["drapeaux_hors_selection"])
            etat = "sans drapeau" if r["sans_drapeau"] else f"drapeaux : {n_s} dans la sélection, {n_h} hors sélection"
            etat += f", marge 10e/11e {100 * r['marge_10_11']:.1f} %"
            print(f"    {a}  β_pub = {r['beta_pub_nominal_eur']:>9.0f} € courants, "
                  f"{r['beta_pub_eur_constants']:>9.0f} €{ANNEE_BASE_PRIX}  ({etat})")
        return {
            "vintage": "Eurostat, " + ", ".join(f"{c} {(u or '')[:10]}" for c, u in mises_a_jour.items()),
            "_files": [f"{cle}.json" for cle in TABLES],
            "annee_reference": ANNEE_REFERENCE,
            "annee_base_prix": ANNEE_BASE_PRIX,
            "beta_pub_reference": ref,
            "par_annee": resultats,
            "tables": {cle: {"table": t, "filtres": f, "mise_a_jour": mises_a_jour[cle]}
                       for cle, (t, f) in TABLES.items()},
        }
