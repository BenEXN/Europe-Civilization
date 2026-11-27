"""Économie Homéostatique — analyse de sensibilité de l'IED (WP EH V1.0, §5.5 et §6.2 ; problèmes T3, E4, I5).

L'IED agrège IBD, IEE et IRNR, normalisés sur [0, 2], la valeur 1 servant de référence de la normalisation. Ce script
retient pour la valeur 1 des repères normatifs publiés (cibles, budgets ou limites globales répartis à parts égales
par habitant), chacun avec sa nature et son périmètre, et fait varier les autres choix de construction :

* la fonction de normalisation (trois formes, non croissantes pour une pression, égales à 1 au repère) ;
* la fonction d'agrégation, appliquée conjointement aux deux étages (sous-indicateurs de l'IEE, puis composantes de
  l'IED), et séparément à chaque étage pour en identifier l'effet ;
* les pondérations entre composantes ;
* le repère retenu quand la littérature en propose plusieurs ;
* la valeur de l'IBD, faute de mesure : valeurs communes à tous les pays, puis scénarios propres à un pays.

Règles de mesure :

* une valeur manquante pour l'année étudiée est remplacée par la plus récente des RECUL_MAX années précédentes ;
* une somme et un ratio ne sont formés qu'à partir de termes de la même année (le dénominateur population est celui
  de l'année des flux) ; l'année, la valeur et le statut Eurostat de chaque terme sont conservés ;
* les valeurs marquées p, e, b, d (ou d'un autre code) sont retenues et signalées ; b et d (rupture, définition
  différente) sont signalés comme limitant la comparabilité.

IRNR : la mesure retenue est l'empreinte matière totale (RMC, biomasse comprise), de même périmètre que les repères ;
elle ne mesure pas l'objet IRNR du WP (la biomasse est renouvelable et recoupe l'IEE). La part non renouvelable
(MF2–MF4) est calculée en variante.

Entrées : calibration/irnr_series.json, calibration/iee_series.json (workflow « Calibration EH »).
Sorties : calibration/sensibilite_ied.json et calibration/SENSIBILITE_IED.md.

Usage : python3 analyse/sensibilite_ied.py [année]"""

from __future__ import annotations

import copy
import itertools
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CAL = ROOT / "calibration"
ANNEE = 2023

UE27 = ("AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE", "EL", "ES", "FI", "FR", "HR", "HU", "IE", "IT", "LT", "LU",
        "LV", "MT", "NL", "PL", "PT", "RO", "SE", "SI", "SK")

# ----------------------------------------------------------------------------------------------- repères

SOURCES = {
    "oneill2018": "O'Neill, D. W., Fanning, A. L., Lamb, W. F., & Steinberger, J. K. (2018). A good life for all within "
                  "planetary boundaries. Nature Sustainability, 1, 88–95. https://doi.org/10.1038/s41893-018-0021-4 "
                  "(tableau 1 et supplément ; valeurs globales réparties par habitant pour une population mondiale "
                  "d'environ 7 milliards)",
    "bringezu2015": "Bringezu, S. (2015). Possible target corridor for sustainable use of global material resources. "
                    "Resources, 4(1), 25–54. https://doi.org/10.3390/resources4010025 (résumé et §5.2 : corridor de 3 à 6 t/hab "
                    "d'empreinte matière, matières biotiques et abiotiques utilisées, d'ici 2050 ; 5 t proposé comme cible)",
}

# Nature d'un repère : ce qu'est la valeur globale de départ et comment elle est ramenée par habitant.
NATURES = {
    "cible": "cible de soutenabilité répartie à parts égales par habitant",
    "cible_2050": "cible prospective pour 2050 (corridor), par habitant",
    "budget": "budget cumulé réparti à parts égales par habitant et par an",
    "limite_globale": "limite planétaire globale répartie à parts égales par habitant",
    "limite_regionale": "limite planétaire définie à l'échelle régionale, répartie à parts égales par habitant",
}

# Pour chaque sous-indicateur : repères candidats {nom: {valeur, source, nature, perimetre}}.
SOUS_INDICATEURS = {
    "irnr_rmc_totale": {
        "composante": "IRNR",
        "libelle": "Empreinte matière totale (RMC, biomasse comprise)",
        "unite": "t/hab",
        "seuils": {
            "7,2 t (O'Neill)": {"valeur": 7.2, "source": "oneill2018", "nature": "cible",
                                "perimetre": "empreinte matière totale, biomasse comprise"},
            "5 t (Bringezu)": {"valeur": 5.0, "source": "bringezu2015", "nature": "cible_2050",
                               "perimetre": "empreinte matière totale (matières utilisées biotiques et abiotiques)"},
        },
        "note": "Mesure retenue pour la composante IRNR de cette analyse : la RMC totale porte sur le même périmètre que "
                "les deux repères (7,2 t chez O'Neill ; corridor de 3 à 6 t d'ici 2050 chez Bringezu, qui propose 5 t "
                "comme cible) et elle est publiée pour les 27 États membres. Elle ne mesure pas l'objet IRNR du WP : la "
                "biomasse, ressource renouvelable, y entre et recoupe le périmètre de l'IEE ; la composante mesure ici la "
                "pression matérielle totale. Aucun repère publié ne porte sur la seule part non renouvelable. La "
                "déplétion des stocks (§6.2 du WP : stocks disponibles, horizon, recyclage, substitutions) demande une "
                "référence propre, sans équivalent publié. Le corridor abiotique de Bringezu (6 à 12 t/hab) est exprimé "
                "en consommation matérielle totale (TMC), extraction inutilisée comprise, et se compare à la TMC.",
    },
    "irnr_rmc_abiotique": {
        "composante": "IRNR (variante)",
        "libelle": "Empreinte matière non renouvelable (RMC, minerais métalliques + minéraux non métalliques + fossiles)",
        "unite": "t/hab",
        "seuils": {
            "7,2 t (O'Neill)": {"valeur": 7.2, "source": "oneill2018", "nature": "cible",
                                "perimetre": "empreinte matière totale, biomasse comprise"},
            "5 t (Bringezu)": {"valeur": 5.0, "source": "bringezu2015", "nature": "cible_2050",
                               "perimetre": "empreinte matière totale (matières utilisées biotiques et abiotiques)"},
        },
        "note": "Variante : périmètre proche de l'objet IRNR du WP (matières non renouvelables), rapporté à des repères "
                "qui portent sur l'empreinte totale ; le rapport au repère est alors inférieur ou égal à celui de "
                "l'empreinte totale. La ventilation de la RMC par catégorie de matières n'est publiée que pour une "
                "partie des États membres.",
    },
    "iee_co2_empreinte": {
        "composante": "IEE",
        "libelle": "Empreinte CO2 de la consommation",
        "unite": "t CO2/hab",
        "seuils": {"1,61 t (O'Neill)": {"valeur": 1.61, "source": "oneill2018", "nature": "budget",
                                        "perimetre": "CO2 seul, 1 000 Gt sur 2011–2100 (2 °C, probabilité 66 %)"}},
        "note": "Repère daté : le budget restant s'est réduit depuis 2011, et sa révision demande les émissions "
                "cumulées, l'horizon, la trajectoire et la probabilité retenus. Il porte sur le seul CO2.",
    },
    "iee_azote": {
        "composante": "IEE",
        "libelle": "Azote fixé (engrais minéraux + fixation biologique agricole)",
        "unite": "kg N/hab",
        "seuils": {"8,9 kg (O'Neill)": {"valeur": 8.9, "source": "oneill2018", "nature": "limite_globale",
                                        "perimetre": "fixation industrielle et biologique intentionnelle, 62 Tg N/an"}},
        "note": "La série est une entrée de nouvel azote agricole sur le territoire (engrais minéraux + fixation "
                "biologique), mesurée côté production ; le repère d'O'Neill est appliqué côté consommation. La série "
                "renseigne une pression d'entrée, distincte de l'excédent du bilan et des transferts vers les eaux.",
    },
    "iee_phosphore": {
        "composante": "IEE",
        "libelle": "Phosphore minéral appliqué aux sols agricoles",
        "unite": "kg P/hab",
        "seuils": {"0,89 kg (O'Neill)": {"valeur": 0.89, "source": "oneill2018", "nature": "limite_regionale",
                                         "perimetre": "6,2 Tg P/an extraits et appliqués aux sols érodables"}},
        "note": "Mesure territoriale des apports minéraux ; le transfert vers les rivières et les océans, sur lequel "
                "porte la limite, dépend des sols et des bassins.",
    },
}

SANS_SEUIL = {
    "IEE — eau douce": "La référence d'O'Neill (574 m³/hab/an d'eau bleue consommée) répartit une limite globale "
        "par habitant et s'applique à une empreinte de consommation, sans série nationale homogène. Le WEI+ "
        "(sdg_06_60) mesure une consommation nette — prélèvements moins restitutions — rapportée aux ressources "
        "renouvelables du territoire ; l'Agence européenne pour l'environnement le publie aussi par bassin et par "
        "saison. C'est une mesure de tension locale, avec un seuil de stress conventionnel (20 %), et sa valeur "
        "nationale ne se convertit pas en m³/hab. Choix de construction de cette analyse : l'eau est tenue hors de "
        "l'IED, pour ne pas agréger une tension territoriale à des repères globaux par habitant. Son intégration, par "
        "bassin, est une piste ouverte.",
    "IEE — artificialisation (LUCAS) et imperméabilisation": "La limite planétaire du changement d'usage des sols porte "
        "sur le couvert forestier ; aucun repère d'artificialisation par habitant n'a été retenu.",
    "IEE — gaz à effet de serre autres que le CO2": "Le repère d'O'Neill porte sur le seul CO2 ; CH4 et N2O demandent "
        "un repère propre.",
    "IBD — toutes séries": "Les limites de l'intégrité de la biosphère (extinctions par million d'espèces-années, part "
        "de la production primaire appropriée) n'ont pas été traduites ici à l'échelle nationale ; l'indice des oiseaux "
        "communs mesure des tendances d'abondance rapportées à une année de base nationale. L'IBD est traité comme une "
        "inconnue, explorée par scénarios.",
}

STATUTS = {"p": "provisoire", "e": "estimé", "b": "rupture de série", "d": "définition différente"}
COMPARABILITE = {"b", "d"}  # codes signalés comme limitant la comparabilité


def signification(code: str) -> list[str]:
    return [STATUTS.get(c, f"code Eurostat {c}") for c in code]


# ----------------------------------------------------------------------------------------------- normalisation

def _domaine(x, t):
    if not (isinstance(x, (int, float)) and isinstance(t, (int, float)) and math.isfinite(x) and math.isfinite(t)):
        raise ValueError(f"valeur ou repère non fini : x={x!r}, T={t!r}")
    if t <= 0:
        raise ValueError(f"repère non positif : T={t}")
    if x < 0:
        raise ValueError(f"pression négative : x={x}")


def norm_lineaire(x, t):
    _domaine(x, t)
    return min(2.0, max(0.0, 2.0 - x / t))


def norm_ratio(x, t):
    _domaine(x, t)
    return 2.0 if x <= t / 2 else t / x


def norm_hyperbolique(x, t):
    _domaine(x, t)
    return 2.0 / (1.0 + x / t)


NORMALISATIONS = {
    "linéaire : 2 − x/T": norm_lineaire,
    "ratio : T/x": norm_ratio,
    "hyperbolique : 2/(1 + x/T)": norm_hyperbolique,
}

# ----------------------------------------------------------------------------------------------- agrégation

def moyenne_puissance(valeurs, poids, rho):
    """M_ρ = (Σ w_i v_i^ρ)^(1/ρ), poids normalisés ; ρ = 0 : moyenne géométrique ; ρ = −∞ : minimum.

    Valeurs finies et positives ou nulles ; poids finis, positifs ou nuls, de somme positive. Les composantes de poids
    nul sont écartées avant le calcul. Pour ρ ≤ 0, une valeur nulle de poids positif donne 0."""
    valeurs, poids = list(valeurs), list(poids)
    if not valeurs or len(valeurs) != len(poids):
        raise ValueError(f"valeurs et poids de tailles différentes : {len(valeurs)} et {len(poids)}")
    for v in valeurs:
        if not (isinstance(v, (int, float)) and math.isfinite(v) and v >= 0):
            raise ValueError(f"valeur hors domaine : {v!r}")
    for p in poids:
        if not (isinstance(p, (int, float)) and math.isfinite(p) and p >= 0):
            raise ValueError(f"poids hors domaine : {p!r}")
    if not (isinstance(rho, (int, float)) and (math.isfinite(rho) or rho == -math.inf)):
        raise ValueError(f"paramètre ρ hors domaine : {rho!r}")
    total = sum(poids)
    if total <= 0:
        raise ValueError("somme des poids nulle")
    paires = [(v, p / total) for v, p in zip(valeurs, poids) if p > 0]
    if rho == -math.inf:
        return min(v for v, _ in paires)
    if any(v == 0 for v, _ in paires):
        if rho <= 0:
            return 0.0
        paires = [(v, w) for v, w in paires if v > 0]
        if not paires:
            return 0.0
    if rho == 0:
        return math.exp(sum(w * math.log(v) for v, w in paires))
    # Forme logarithmique (log-somme-exp) : finie pour de très petites ou très grandes valeurs.
    termes = [math.log(w) + rho * math.log(v) for v, w in paires]
    m = max(termes)
    return math.exp((m + math.log(sum(math.exp(t - m) for t in termes))) / rho)


AGREGATIONS = {
    "moyenne géométrique (V1.0)": 0.0,
    "CES ρ = −1 (harmonique)": -1.0,
    "CES ρ = −5": -5.0,
    "minimum": -math.inf,
}

POIDS = {
    "égaux (V1.0)": (1, 1, 1),
    "IBD renforcé (2, 1, 1)": (2, 1, 1),
    "IEE renforcé (1, 2, 1)": (1, 2, 1),
    "IRNR renforcé (1, 1, 2)": (1, 1, 2),
}

VALEURS_IBD = (0.0, 0.5, 1.0, 1.5, 2.0)
IBD_HETEROGENE = 0.5  # scénario : un seul pays à cette valeur, les autres à 1

CLE_IRNR = "irnr_rmc_totale"            # mesure de la composante IRNR dans la grille
CLE_IRNR_VARIANTE = "irnr_rmc_abiotique"  # variante de périmètre (MF2–MF4)

REFERENCE = {"normalisation": "hyperbolique : 2/(1 + x/T)", "agregation": "moyenne géométrique (V1.0)",
             "poids": "égaux (V1.0)", "seuil_irnr": "7,2 t (O'Neill)", "ibd": 1.0}

# ----------------------------------------------------------------------------------------------- données

RECUL_MAX = 3  # années de recul admises quand une série n'est pas encore publiée pour l'année étudiée


def charger(nom):
    return json.loads((CAL / nom).read_text())["data"]


def serie(series, cle_contient):
    trouve = [k for k in series if all(c in k.split("|") for c in cle_contient)]
    if len(trouve) != 1:
        raise KeyError(f"{cle_contient}: {trouve}")
    return series[trouve[0]]


def meme_annee(termes, geo, annee, recul=RECUL_MAX):
    """Année la plus récente de [annee − recul, annee] où tous les termes sont publiés pour geo.

    termes : {nom: {geo: {"année": [valeur, statut]}}}. Retourne (année, {nom: {annee, valeur, statut}}) ou None."""
    for a in range(annee, annee - recul - 1, -1):
        cel = {n: rows.get(geo, {}).get(str(a)) for n, rows in termes.items()}
        if all(c is not None and c[0] is not None for c in cel.values()):
            return a, {n: {"annee": a, "valeur": c[0], "statut": c[1] or ""} for n, c in cel.items()}
    return None


def mesures(annee=ANNEE, recul=RECUL_MAX, irnr=None, iee=None):
    """Mesures par pays et trace de chaque terme : ({geo: {sous-indicateur: valeur}}, {geo: {sous-indicateur: trace}}).

    État local à chaque appel : deux appels successifs ne partagent aucun objet modifiable."""
    irnr = irnr if irnr is not None else charger("irnr_series.json")
    iee = iee if iee is not None else charger("iee_series.json")
    pop = serie(iee["series"]["population"], ["unit=THS_PER"])
    co2 = serie(iee["series"]["ges_empreinte"], ["airpol=CO2", "indic_env=AEMIS_CONS_FP", "unit=KG_HAB"])
    az = iee["series"]["azote"]
    n_min, n_bio = serie(az, ["nutrient=N", "indic_ag=I_FRT_MIN"]), serie(az, ["nutrient=N", "indic_ag=I_OTH_BIO"])
    p_min = serie(az, ["nutrient=P", "indic_ag=I_FRT_MIN"])
    rmc = irnr["series"]["rmc"]
    rmc_total = irnr["series"].get("rmc_total")
    if rmc_total is None:
        raise KeyError("série rmc_total absente : la RMC totale est la mesure de l'IRNR dans cette analyse")
    definitions = {
        # sous-indicateur : (termes, fonction des valeurs)
        "irnr_rmc_abiotique": ({"RMC MF2": rmc.get("MF2", {}), "RMC MF3": rmc.get("MF3", {}),
                                "RMC MF4": rmc.get("MF4", {})},
                               lambda v: v["RMC MF2"] + v["RMC MF3"] + v["RMC MF4"]),
        "iee_co2_empreinte": ({"CO2 empreinte (kg/hab)": co2}, lambda v: v["CO2 empreinte (kg/hab)"] / 1000),
        "iee_azote": ({"N engrais minéraux (t)": n_min, "N fixation biologique (t)": n_bio, "population (milliers)": pop},
                      lambda v: _par_hab(v["N engrais minéraux (t)"] + v["N fixation biologique (t)"],
                                         v["population (milliers)"])),
        "iee_phosphore": ({"P engrais minéraux (t)": p_min, "population (milliers)": pop},
                          lambda v: _par_hab(v["P engrais minéraux (t)"], v["population (milliers)"])),
    }
    definitions["irnr_rmc_totale"] = ({"RMC totale": rmc_total}, lambda v: v["RMC totale"])
    out, trace = {}, {}
    for g in UE27:
        m, t = {}, {}
        for k, (termes, f) in definitions.items():
            r = meme_annee(termes, g, annee, recul)
            if r is None:
                continue
            a, cel = r
            valeur = f({n: c["valeur"] for n, c in cel.items()})
            if not (math.isfinite(valeur) and valeur >= 0):
                raise ValueError(f"{g} {k} : valeur hors domaine {valeur!r}")
            m[k] = valeur
            t[k] = {"annee": a, "recul": annee - a, "termes": cel,
                    "statuts": sorted({s for c in cel.values() for s in c["statut"]})}
        out[g], trace[g] = m, t
    return out, trace


def _par_hab(tonnes, milliers):
    if not (milliers > 0):
        raise ValueError(f"population non positive : {milliers!r}")
    return tonnes * 1000 / (milliers * 1000)


# ----------------------------------------------------------------------------------------------- rangs

def rangs_moyens(d):
    """Rang 1 = valeur la plus élevée ; ex æquo : moyenne des rangs qu'ils occupent. Indépendant de l'ordre des clés."""
    ordre = sorted(d, key=lambda g: (-d[g], g))
    out, i = {}, 0
    while i < len(ordre):
        j = i
        while j + 1 < len(ordre) and d[ordre[j + 1]] == d[ordre[i]]:
            j += 1
        for g in ordre[i:j + 1]:
            out[g] = (i + j) / 2 + 1
        i = j + 1
    return out


def spearman(a, b):
    """Corrélation de Pearson des rangs moyens ; None (sans objet) si n < 3 ou si l'un des vecteurs est constant."""
    cles = sorted(a)
    if sorted(b) != cles or len(cles) < 3:
        return None
    ra, rb = rangs_moyens(a), rangs_moyens(b)
    x, y = [ra[g] for g in cles], [rb[g] for g in cles]
    mx, my = sum(x) / len(x), sum(y) / len(y)
    vx, vy = sum((v - mx) ** 2 for v in x), sum((v - my) ** 2 for v in y)
    if vx == 0 or vy == 0:
        return None
    return sum((u - mx) * (v - my) for u, v in zip(x, y)) / math.sqrt(vx * vy)


def inversions(a, b):
    """Paires (g, h) classées g avant h dans a et h avant g dans b."""
    cles = sorted(a, key=lambda g: (-a[g], g))
    return [(g, h) for i, g in enumerate(cles) for h in cles[i + 1:] if a[g] > a[h] and b[g] < b[h]]


# ----------------------------------------------------------------------------------------------- calcul

def iee_pays(mes, g, fn, rho_iee, iee_ids):
    s_iee = [fn(mes[g][k], next(iter(SOUS_INDICATEURS[k]["seuils"].values()))["valeur"]) for k in iee_ids]
    return moyenne_puissance(s_iee, [1] * len(s_iee), rho_iee)


def ied_pays(mes, g, fn, rho_iee, rho_ied, w, t_irnr, ibd, iee_ids, cle_irnr=CLE_IRNR):
    iee = iee_pays(mes, g, fn, rho_iee, iee_ids)
    irnr = fn(mes[g][cle_irnr], t_irnr)
    return moyenne_puissance([ibd, iee, irnr], w, rho_ied)


def composantes(mes, iee_ids, cle_irnr=CLE_IRNR):
    """Scores des composantes IEE et IRNR, pour chaque pays qui dispose des séries de la composante. L'IEE dépend de la
    normalisation et de l'agrégation entre ses sous-indicateurs ; l'IRNR, de la normalisation et du repère."""
    avec_iee = sorted(g for g, m in mes.items() if all(k in m for k in iee_ids))
    avec_irnr = sorted(g for g, m in mes.items() if cle_irnr in m)
    iee = [{"normalisation": nn, "agregation": na,
            "valeurs": {g: round(iee_pays(mes, g, fn, rho, iee_ids), 4) for g in avec_iee}}
           for (nn, fn), (na, rho) in itertools.product(NORMALISATIONS.items(), AGREGATIONS.items())]
    irnr = [{"normalisation": nn, "seuil_irnr": ns, "valeurs": {g: round(fn(mes[g][cle_irnr], s["valeur"]), 4) for g in avec_irnr}}
            for (nn, fn), (ns, s) in itertools.product(NORMALISATIONS.items(), SOUS_INDICATEURS[cle_irnr]["seuils"].items())]
    return {"iee": iee, "irnr": irnr, "pays_iee": avec_iee, "pays_irnr": avec_irnr}


def analyser(annee=ANNEE, irnr=None, iee=None):
    mes, trace = mesures(annee, irnr=irnr, iee=iee)
    iee_ids = [k for k, s in SOUS_INDICATEURS.items() if s["composante"] == "IEE"]
    requis = iee_ids + [CLE_IRNR]
    complets = sorted(g for g, m in mes.items() if all(k in m for k in requis))
    mes0, _ = mesures(annee, recul=0, irnr=irnr, iee=iee)
    complets_sans_recul = sorted(g for g, m in mes0.items() if all(k in m for k in requis))

    depassements = {g: {k: {nom: round(mes[g][k] / s["valeur"], 3) for nom, s in SOUS_INDICATEURS[k]["seuils"].items()}
                        for k in SOUS_INDICATEURS if k in mes[g]} for g in UE27}

    # Grille principale : même fonction d'agrégation aux deux étages (scénario conjoint).
    resultats, bruts = [], []
    seuils_irnr = list(SOUS_INDICATEURS[CLE_IRNR]["seuils"].items())
    for (nn, fn), (na, rho), (np_, w), (ns, s) in itertools.product(
            NORMALISATIONS.items(), AGREGATIONS.items(), POIDS.items(), seuils_irnr):
        for ibd in VALEURS_IBD:
            ied = {g: ied_pays(mes, g, fn, rho, rho, w, s["valeur"], ibd, iee_ids) for g in complets}
            bruts.append(ied)
            resultats.append({"normalisation": nn, "agregation": na, "agregation_iee": na, "agregation_ied": na,
                              "poids": np_, "seuil_irnr": ns, "ibd": ibd, "ied": {g: round(v, 4) for g, v in ied.items()},
                              "ied_brut": dict(ied)})

    i_ref = next(i for i, r in enumerate(resultats) if all(r[k] == REFERENCE[k] for k in REFERENCE))
    ref_brut = bruts[i_ref]
    for r, b in zip(resultats, bruts):
        sp = spearman(ref_brut, b) if len(complets) > 2 else None
        r["spearman_vs_reference"] = round(sp, 6) if sp is not None else None
        r["inversions_vs_reference"] = [f"{g}/{h}" for g, h in inversions(ref_brut, b)] if sp is not None else None
    distincts = len({tuple(round(b[g], 9) for g in complets) for b in bruts})

    # Agrégation séparée : un étage varie, l'autre reste en moyenne géométrique (référence).
    fn_ref = NORMALISATIONS[REFERENCE["normalisation"]]
    w_ref = POIDS[REFERENCE["poids"]]
    t_ref = SOUS_INDICATEURS[CLE_IRNR]["seuils"][REFERENCE["seuil_irnr"]]["valeur"]
    rho_ref = AGREGATIONS[REFERENCE["agregation"]]
    separee = []
    for etage in ("iee", "ied"):
        for na, rho in AGREGATIONS.items():
            ri, re = (rho, rho_ref) if etage == "iee" else (rho_ref, rho)
            ied = {g: ied_pays(mes, g, fn_ref, ri, re, w_ref, t_ref, REFERENCE["ibd"], iee_ids) for g in complets}
            sp = spearman(ref_brut, ied)
            separee.append({"etage_varie": etage, "agregation": na, "ied": {g: round(v, 4) for g, v in ied.items()},
                            "spearman_vs_reference": round(sp, 6) if sp is not None else None,
                            "inversions_vs_reference": [f"{g}/{h}" for g, h in inversions(ref_brut, ied)]})

    # IBD propre à un pays (scénario hypothétique, non une observation).
    rang_ref = rangs_moyens(ref_brut)
    heterogene = []
    for c in complets:
        ied = {g: ied_pays(mes, g, fn_ref, rho_ref, rho_ref, w_ref, t_ref,
                           IBD_HETEROGENE if g == c else REFERENCE["ibd"], iee_ids) for g in complets}
        rg = rangs_moyens(ied)
        sp = spearman(ref_brut, ied)
        heterogene.append({"pays": c, "ibd_pays": IBD_HETEROGENE, "ibd_autres": REFERENCE["ibd"],
                           "ied_pays": round(ied[c], 4), "ied_pays_reference": round(ref_brut[c], 4),
                           "rang_reference": rang_ref[c], "rang": rg[c],
                           "spearman_vs_reference": round(sp, 6) if sp is not None else None})

    # Variante de périmètre IRNR : part non renouvelable (MF2–MF4), rapportée aux mêmes repères.
    perimetre = None
    complets_variante = sorted(g for g, m in mes.items() if all(k in m for k in iee_ids + [CLE_IRNR_VARIANTE]))
    if complets_variante:
        perimetre = {"sous_indicateur": CLE_IRNR_VARIANTE, "pays_complets": complets_variante, "seuils": {},
                     "reference": {}}
        for ns, s in seuils_irnr:
            ied = {g: ied_pays(mes, g, fn_ref, rho_ref, rho_ref, w_ref, s["valeur"], REFERENCE["ibd"], iee_ids,
                               cle_irnr=CLE_IRNR_VARIANTE) for g in complets_variante}
            perimetre["seuils"][ns] = {g: round(v, 4) for g, v in ied.items()}
            perimetre["reference"][ns] = {g: round(ied_pays(mes, g, fn_ref, rho_ref, rho_ref, w_ref, s["valeur"],
                                                            REFERENCE["ibd"], iee_ids), 4)
                                          for g in complets_variante if g in complets}

    statuts = [{"pays": g, "sous_indicateur": k, "terme": n, "annee": c["annee"], "code": c["statut"],
                "signification": signification(c["statut"]),
                "comparabilite_limitee": any(x in COMPARABILITE for x in c["statut"])}
               for g in UE27 for k, t in trace[g].items() for n, c in t["termes"].items() if c["statut"]]

    def plage(ensemble):
        return {g: {"min": round(min(b[g] for b in ensemble), 4), "max": round(max(b[g] for b in ensemble), 4)}
                for g in complets}

    return {
        "annee": annee,
        "sources": SOURCES,
        "natures_des_reperes": NATURES,
        "sous_indicateurs": copy.deepcopy(SOUS_INDICATEURS),
        "sans_seuil": dict(SANS_SEUIL),
        "regles": {"recul_max": RECUL_MAX,
                   "meme_annee": "une somme et un ratio sont formés à partir de termes de la même année",
                   "statuts": "valeurs marquées retenues et signalées ; b et d signalés comme limitant la comparabilité"},
        "mesures": {g: {k: round(v, 3) for k, v in m.items()} for g, m in mes.items()},
        "mesures_brutes": mes,
        "trace": trace,
        "statuts_utilises": statuts,
        "rapport_au_seuil": depassements,
        "pays_complets": complets,
        "pays_complets_sans_recul": complets_sans_recul,
        "configuration_reference": dict(REFERENCE),
        "configurations": len(resultats),
        "vecteurs_distincts": distincts,
        "resultats": resultats,
        "ied_reference_brut": dict(ref_brut),
        "composantes": composantes(mes, iee_ids),
        "agregation_separee": separee,
        "ibd_heterogene": heterogene,
        "cle_irnr": CLE_IRNR,
        "variante_irnr_abiotique": perimetre,
        "plages": plage(bruts),
        "plages_ibd_reference": plage([b for r, b in zip(resultats, bruts) if r["ibd"] == REFERENCE["ibd"]]),
    }


# ----------------------------------------------------------------------------------------------- rapport

def fr(x, d=2):
    return f"{x:.{d}f}".replace(".", ",")


LIBELLES_COURTS = {"irnr_rmc_abiotique": "RMC MF2–MF4", "iee_co2_empreinte": "CO2", "iee_azote": "Azote",
                   "iee_phosphore": "Phosphore", "irnr_rmc_totale": "RMC totale"}


def rapport(a):
    L = []
    complets, ann = a["pays_complets"], a["annee"]
    ref = a["configuration_reference"]
    L.append(f"# Sensibilité de l'IED aux choix de construction — {ann}\n")
    L.append("*Économie Homéostatique, WP V1.0. Résultats sous hypothèses, produits par `analyse/sensibilite_ied.py` "
             "à partir des séries Eurostat du dossier `calibration/`. Chaque valeur dépend d'un jeu de choix explicite ; "
             "l'IBD est une valeur supposée. Les minima et maxima sont une enveloppe de scénarios.*\n")

    L.append("## Portée : justesse de représentation et échelle géographique\n")
    L.append("L'enjeu de recherche premier des indicateurs de l'EH est leur justesse à représenter la réalité "
             "biophysique : la performativité du dispositif (axiome A4) en dépend.\n")
    L.append("Les résultats sont calculés par État membre, échelle de publication des statistiques. Deux principes "
             "distincts relient un pays au reste du monde. L'empreinte (RMC, CO2) attribue à la demande finale d'un "
             "pays des pressions exercées ailleurs : c'est une règle de responsabilité. La continuité des milieux "
             "(bassins versants, mers et façades maritimes, aires de répartition des espèces) relie des territoires par "
             "leurs interactions biophysiques : c'est l'objet des zones tampons de l'EH. Aucune des séries nationales "
             "retenues ne représente cette continuité. Les zones tampons demandent une géométrie, des données "
             "spatialisées et une règle de partage de l'état d'une zone tampon entre les zones qu'elle relie ; elles "
             "sont à définir au cours de la construction des indicateurs.\n")

    L.append("## Statut des fonctions de normalisation\n")
    L.append("Le WP fixe l'échelle [0, 2], la valeur 1 comme référence de la normalisation et le sens de la "
             "transformation : décroissante pour une pression (IRNR, IEE), croissante pour un état (IBD). Il laisse "
             "à définir, pour chaque indicateur, la traduction des repères 0, 1 et 2 et la forme de la fonction "
             "(§6.2). Trois formes candidates, construites pour cette analyse, sont testées (x ≥ 0, T > 0) :\n")
    L.append("- **linéaire** 2 − x/T : vaut 2 sans pression, 0 à deux fois le repère, puis reste à 0 ;")
    L.append("- **ratio** T/x : vaut 2 jusqu'à la moitié du repère, puis décroît sans atteindre 0 ;")
    L.append("- **hyperbolique** 2/(1 + x/T) : vaut 2 sans pression et décroît sans atteindre 0.\n")
    L.append("Les trois valent 1 au repère. Le placement des valeurs 0 et 2 qu'impose chaque forme est un choix "
             "numérique, au même titre que la forme. La forme hyperbolique sert de configuration de référence pour la "
             "présentation, parce qu'elle est définie sans troncature sur tout le domaine ; ce choix est un choix de "
             "présentation. Les fonctions vérifient leur domaine (valeurs finies, x ≥ 0, T > 0) et s'arrêtent sur "
             "une erreur hors de celui-ci.\n")

    L.append("## 1. Repères retenus pour la valeur 1 de la normalisation\n")
    L.append("Les valeurs retenues sont des repères normatifs publiés : cibles, budgets ou limites globales, répartis "
             "à parts égales par habitant. Chacune est employée comme scénario de référence, avec sa nature et son "
             "périmètre.\n")
    L.append("| Composante | Sous-indicateur | Valeur 1 | Nature du repère | Périmètre du repère | Source |\n"
             "|---|---|---|---|---|---|")
    for k, s in a["sous_indicateurs"].items():
        for n, t in s["seuils"].items():
            L.append(f"| {s['composante']} | {s['libelle']} ({s['unite']}) | {n} | {a['natures_des_reperes'][t['nature']]} "
                     f"| {t['perimetre']} | {t['source']} |")
    L.append("")
    for k, s in a["sous_indicateurs"].items():
        L.append(f"- **{s['libelle']}** : {s['note']}")
    L.append("- **Population de référence.** Les valeurs d'O'Neill et al. (2018) répartissent des grandeurs globales "
             "pour une population mondiale d'environ 7 milliards. À grandeur globale fixée, une population de 8 "
             "milliards réduit la part par habitant de 12,5 %. L'égalité par habitant est une règle distributive ; "
             "responsabilités historiques et besoins différenciés appellent d'autres règles, à comparer.")
    L.append("\n**Sans repère retenu**\n")
    for k, v in a["sans_seuil"].items():
        L.append(f"- **{k}** : {v}")
    L.append("\n**Sources**\n")
    for k, v in a["sources"].items():
        L.append(f"- `{k}` : {v}")

    L.append(f"\n## 2. Mesures, millésimes et rapport au repère par pays ({ann})\n")
    L.append(f"Valeur observée divisée par le repère : 1 signifie « au repère », 3 « trois fois le repère ». Quand une "
             f"série n'est pas publiée pour {ann}, la valeur la plus récente des {RECUL_MAX} années précédentes est "
             "utilisée ; l'année figure alors entre parenthèses. Une somme et un ratio sont formés à partir de termes "
             "de la même année, population comprise. « – » : série absente dans la fenêtre.\n")
    cols = [(CLE_IRNR, "7,2 t (O'Neill)", "RMC totale / 7,2 t"),
            (CLE_IRNR, "5 t (Bringezu)", "RMC totale / 5 t"),
            (CLE_IRNR_VARIANTE, "7,2 t (O'Neill)", "RMC MF2–MF4 / 7,2 t"),
            ("iee_co2_empreinte", None, "CO2"), ("iee_azote", None, "Azote"), ("iee_phosphore", None, "Phosphore")]
    L.append("| Pays | " + " | ".join(c[2] for c in cols) + " | Complet |\n|---|" + "---|" * (len(cols) + 1))
    for g in UE27:
        d, tr = a["rapport_au_seuil"][g], a["trace"][g]
        cel = []
        for k, sn, _ in cols:
            v = d.get(k, {})
            x = v.get(sn) if sn else (next(iter(v.values())) if v else None)
            an = f" ({tr[k]['annee']})" if k in tr and tr[k]["recul"] else ""
            cel.append(fr(x) + an if x is not None else "–")
        L.append(f"| {g} | " + " | ".join(cel) + f" | {'oui' if g in complets else 'non'} |")
    manque = {g: [LIBELLES_COURTS[k] for k in (CLE_IRNR, "iee_azote", "iee_phosphore", "iee_co2_empreinte")
                  if k not in a["mesures"][g]] for g in UE27 if g not in complets}
    par_cause = {}
    for g, m in manque.items():
        par_cause.setdefault(", ".join(m), []).append(g)
    L.append(f"\n**Couverture.** {len(complets)} pays disposent de toutes les séries ({', '.join(complets)}). "
             "Séries absentes pour les autres :\n")
    for cause, gs in sorted(par_cause.items(), key=lambda x: (-len(x[1]), x[0])):
        L.append(f"- {cause} : {', '.join(gs)}")
    L.append("\nLa RMC totale, mesure retenue pour l'IRNR, est publiée par Eurostat pour l'ensemble des États membres ; "
             "sa ventilation par catégorie de matières (MF2–MF4, variante) est partielle. Sans recul temporel, "
             f"{len(a['pays_complets_sans_recul'])} pays sont complets "
             f"({', '.join(sorted(set(complets) - set(a['pays_complets_sans_recul']))) or 'aucun écart'} "
             "sortant du groupe). Ce groupe est un sous-ensemble de disponibilité : ses moyennes et ses rangs "
             "décrivent ces pays seulement.")

    st = a["statuts_utilises"]
    st_c = [s for s in st if s["pays"] in complets]
    L.append("\n**Statuts statistiques des valeurs utilisées.** "
             f"{len(st)} terme(s) portent un code Eurostat, dont {len(st_c)} pour les pays complets :\n")
    if st_c:
        L.append("| Pays | Sous-indicateur | Terme | Année | Code | Comparabilité limitée |\n|---|---|---|---|---|---|")
        for s in st_c:
            L.append(f"| {s['pays']} | {LIBELLES_COURTS.get(s['sous_indicateur'], s['sous_indicateur'])} | "
                     f"{s['terme']} | {s['annee']} | {s['code']} ({', '.join(s['signification'])}) | "
                     f"{'oui' if s['comparabilite_limitee'] else 'non'} |")
    L.append("\nRègle : les valeurs marquées sont retenues et signalées ; les codes b et d sont signalés comme limitant "
             "la comparabilité. L'absence de code n'équivaut pas à l'absence d'incertitude.")

    r0 = next(r for r in a["resultats"] if all(r[k] == ref[k] for k in ref))
    L.append(f"\n## 3. IED sous la configuration de référence\n")
    L.append(f"Normalisation {ref['normalisation']} ; agrégation {ref['agregation']} aux deux étages ; poids "
             f"{ref['poids']} ; repère IRNR {ref['seuil_irnr']} ; **IBD supposé égal à {fr(ref['ibd'], 1)}**.\n")
    L.append("| Pays | IED (référence) | Min (IBD = 1) | Max (IBD = 1) | Min (enveloppe) | Max (enveloppe) |\n"
             "|---|---|---|---|---|---|")
    for g in sorted(complets, key=lambda g: -r0["ied"][g]):
        p, q = a["plages_ibd_reference"][g], a["plages"][g]
        L.append(f"| {g} | {fr(r0['ied'][g])} | {fr(p['min'])} | {fr(p['max'])} | {fr(q['min'])} | {fr(q['max'])} |")
    L.append(f"\nL'enveloppe porte sur les {a['configurations']} configurations de la grille ({len(NORMALISATIONS)} "
             f"normalisations × {len(AGREGATIONS)} agrégations × {len(POIDS)} pondérations × 2 repères IRNR × "
             f"{len(VALEURS_IBD)} valeurs de l'IBD), qui donnent {a['vecteurs_distincts']} vecteurs de scores "
             "distincts : le minimum ignore les poids, et la saturation comme le zéro absorbant produisent des "
             "répétitions. Le nombre de configurations n'est ni un nombre de réplications ni une probabilité.")

    L.append("\n## 4. Effet de chaque choix\n")
    L.append("Pour chaque choix, ce seul paramètre varie à partir de la référence. La corrélation de rang (Spearman, "
             "rangs moyens en cas d'ex æquo, calculée sur les scores non arrondis) vaut 1 quand le classement est "
             "identique ; elle est sans objet (–) quand l'IED est identique pour tous les pays. La dernière colonne "
             "donne les paires de pays dont l'ordre s'inverse.\n")
    titres = {"normalisation": "Normalisation", "agregation": "Agrégation, appliquée aux deux étages (scénario conjoint)",
              "poids": "Pondérations (IBD, IEE, IRNR)", "seuil_irnr": "Repère IRNR", "ibd": "Valeur supposée de l'IBD, commune à tous les pays"}
    for param, options in (("normalisation", NORMALISATIONS), ("agregation", AGREGATIONS), ("poids", POIDS),
                           ("seuil_irnr", SOUS_INDICATEURS[CLE_IRNR]["seuils"]),
                           ("ibd", {v: 0 for v in VALEURS_IBD})):
        L.append(f"**{titres[param]}**\n")
        L.append("| Option | IED moyen | IED min | IED max | Spearman | Inversions |\n|---|---|---|---|---|---|")
        for o in options:
            r = next(x for x in a["resultats"] if x[param] == o and all(x[k] == ref[k] for k in ref if k != param))
            L.append(_ligne(fr(o, 1) if isinstance(o, float) else o, r))
        L.append("")
    L.append("Avec la moyenne géométrique, un IBD commun b multiplie chaque score par b à la puissance du poids relatif "
             "de l'IBD : le classement est invariant par construction. Cette ligne mesure l'effet d'une biodiversité "
             "commune sur le niveau ; l'effet d'une biodiversité propre à chaque pays est donné plus bas.\n")
    for etage, titre in (("iee", "Agrégation entre les sous-indicateurs de l'IEE seule (IED en moyenne géométrique)"),
                         ("ied", "Agrégation entre les composantes de l'IED seule (IEE en moyenne géométrique)")):
        L.append(f"**{titre}**\n")
        L.append("| Option | IED moyen | IED min | IED max | Spearman | Inversions |\n|---|---|---|---|---|---|")
        for r in a["agregation_separee"]:
            if r["etage_varie"] == etage:
                L.append(_ligne(r["agregation"], r))
        L.append("")
    L.append(f"**IBD propre à un pays (scénario hypothétique : IBD = {fr(IBD_HETEROGENE, 1)} pour ce pays, 1 pour les "
             "autres)**\n")
    L.append("| Pays | IED de référence | IED du scénario | Rang de référence | Rang du scénario | Spearman |\n"
             "|---|---|---|---|---|---|")
    for h in a["ibd_heterogene"]:
        L.append(f"| {h['pays']} | {fr(h['ied_pays_reference'])} | {fr(h['ied_pays'])} | {_rang(h['rang_reference'])} | "
                 f"{_rang(h['rang'])} | {fr(h['spearman_vs_reference'], 3) if h['spearman_vs_reference'] is not None else '–'} |")
    L.append("\nCes valeurs explorent des hypothèses ; aucune n'est une observation de la biodiversité.\n")

    p = a.get("variante_irnr_abiotique")
    if p:
        L.append("**Variante de périmètre : IRNR calculé sur la part non renouvelable de l'empreinte (MF2–MF4)**\n")
        L.append("La référence rapporte la RMC totale aux repères, qui portent sur ce même périmètre. Cette variante "
                 "rapporte aux mêmes repères la seule part non renouvelable (minerais métalliques, minéraux non "
                 f"métalliques, matières fossiles), pour les {len(p['pays_complets'])} pays qui disposent de sa "
                 "ventilation et d'un IEE complet ; son rapport au repère est inférieur ou égal à celui de l'empreinte "
                 "totale.\n")
        noms = list(p["seuils"])
        L.append("| Pays | " + " | ".join(f"IED variante, {n} | IED référence, {n}" for n in noms) + " |\n|---|"
                 + "---|" * (2 * len(noms)))
        for g in sorted(p["pays_complets"], key=lambda g: -p["seuils"][noms[0]][g]):
            L.append(f"| {g} | " + " | ".join(f"{fr(p['seuils'][n][g])} | "
                                               f"{fr(p['reference'][n][g]) if g in p['reference'][n] else '–'}"
                                               for n in noms) + " |")
        L.append("")

    nuls = [r for r in a["resultats"] if all(v == 0 for v in r["ied"].values())]
    par_norm = {n: sum(1 for r in nuls if r["normalisation"] == n) for n in NORMALISATIONS}
    par_ibd0 = sum(1 for r in nuls if r["ibd"] == 0 and not r["normalisation"].startswith("linéaire"))
    max_inf1 = max(v for r in a["resultats"] if r["ibd"] <= 1 for v in r["ied"].values())
    max_tout = max(v for r in a["resultats"] for v in r["ied"].values())
    co2 = [a["rapport_au_seuil"][g]["iee_co2_empreinte"]["1,61 t (O'Neill)"] for g in complets]
    L.append("## 5. Constats\n")
    L.append(f"- **Annulation de l'IED.** {len(nuls)} configurations sur {a['configurations']} donnent un IED nul pour "
             f"tous les pays : {par_norm['linéaire : 2 − x/T']} avec la normalisation linéaire, et {par_ibd0} autres "
             "avec un IBD supposé nul. L'empreinte CO2 dépasse son repère d'un facteur "
             f"{fr(min(co2), 1)} à {fr(max(co2), 1)} ; au-delà de deux fois le repère la normalisation linéaire donne 0, "
             "et pour ρ ≤ 0 un zéro est transmis à l'IED (§6.2). Dans l'échantillon, la normalisation linéaire supprime "
             "tout pouvoir de discrimination, quelle que soit la pondération.")
    L.append(f"- **Niveau 1.** Avec un IBD supposé au plus égal à 1, l'IED ne dépasse pas {fr(max_inf1, 3)} ; la grille "
             f"atteint {fr(max_tout, 3)} avec un IBD supposé de 2. Le franchissement du niveau 1 dépend donc de la "
             "valeur supposée de l'IBD.")
    sous = sorted(((a["rapport_au_seuil"][g][k][n], g, k) for g in complets for k in a["rapport_au_seuil"][g]
                   if k.startswith("iee_") for n in a["rapport_au_seuil"][g][k]
                   if a["rapport_au_seuil"][g][k][n] < 1))
    lib = {k: s["libelle"].split(" (")[0].lower() for k, s in a["sous_indicateurs"].items()}
    if sous:
        x, g, k = sous[0]
        L.append(f"- **Compensation à l'intérieur de l'IEE.** Sous-indicateurs de l'IEE sous leur repère "
                 f"dans l'échantillon : {len(sous)}, par exemple {lib[k]} en {g} ({fr(x)} fois le repère). Avec une moyenne, une telle "
                 "valeur compense en partie le dépassement des autres sous-indicateurs, ici l'empreinte CO2 ; c'est une "
                 "propriété de l'agrégation, sans portée sur une compensation écologique réelle.")
    deplace = []
    for param in ("normalisation", "agregation", "poids", "seuil_irnr"):
        for r in a["resultats"]:
            if all(r[k] == ref[k] for k in ref if k != param) and r[param] != ref[param]:
                if r["spearman_vs_reference"] is not None and r["inversions_vs_reference"]:
                    deplace.append(f"{r[param]} : {fr(r['spearman_vs_reference'], 3)} "
                                   f"({', '.join(r['inversions_vs_reference'])})")
    for r in a["agregation_separee"]:
        if r["agregation"] != ref["agregation"] and r["spearman_vs_reference"] is not None and r["inversions_vs_reference"]:
            deplace.append(f"{r['agregation']}, étage {r['etage_varie'].upper()} seul : "
                           f"{fr(r['spearman_vs_reference'], 3)} ({', '.join(r['inversions_vs_reference'])})")
    L.append("- **Ce qui déplace le classement**, à partir de la référence (Spearman, puis paires inversées) :"
             + ("".join(f"\n  - {d}" for d in deplace) if deplace else " aucun des choix testés."))
    het = sorted((h for h in a["ibd_heterogene"] if h["rang"] != h["rang_reference"]),
                 key=lambda h: h["rang_reference"] - h["rang"])
    if het:
        L.append(f"- **Biodiversité propre à un pays.** Un IBD de {fr(IBD_HETEROGENE, 1)} pour un seul pays, les autres "
                 f"à 1, modifie son rang dans {len(het)} cas sur {len(a['ibd_heterogene'])} (par exemple "
                 f"{het[0]['pays']} : rang {_rang(het[0]['rang_reference'])} → {_rang(het[0]['rang'])}). La "
                 "conservation du classement sous un IBD commun ne renseigne donc pas sur sa robustesse à une "
                 "biodiversité différente selon les pays.")
    return "\n".join(L) + "\n"


def _rang(x):
    return str(int(x)) if x == int(x) else fr(x, 1)


def _ligne(option, r):
    v = list(r["ied"].values())
    sp = r["spearman_vs_reference"]
    inv = r.get("inversions_vs_reference")
    return (f"| {option} | {fr(sum(v) / len(v))} | {fr(min(v))} | {fr(max(v))} | "
            f"{fr(sp, 3) if sp is not None else '–'} | {', '.join(inv) if inv else '–'} |")


if __name__ == "__main__":
    annee = int(sys.argv[1]) if len(sys.argv) > 1 else ANNEE
    a = analyser(annee)
    (CAL / "sensibilite_ied.json").write_text(json.dumps(a, ensure_ascii=False, indent=1))
    (CAL / "SENSIBILITE_IED.md").write_text(rapport(a))
    print(f"{annee} : {len(a['pays_complets'])} pays complets, {a['configurations']} configurations, "
          f"{a['vecteurs_distincts']} vecteurs distincts")
