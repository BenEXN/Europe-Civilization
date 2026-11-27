"""Économie Homéostatique — analyse de sensibilité de l'IED (WP EH V1.0, §5.5 et §6.2 ; problèmes T3, E4, I5).

L'IED agrège IBD, IEE et IRNR, normalisés sur [0, 2], la valeur 1 servant de référence de la normalisation. Ce script
retient pour la valeur 1 des seuils biophysiques absolus, tirés des limites planétaires ramenées par habitant, et
fait varier les autres choix de construction :

* la fonction de normalisation (trois formes, toutes décroissantes pour une pression, égales à 1 au seuil) ;
* la fonction d'agrégation (moyenne géométrique, moyennes de puissance à faible substituabilité, minimum) ;
* les pondérations entre composantes ;
* le seuil retenu quand la littérature en propose plusieurs.

Aucune série nationale publique ne permet aujourd'hui de rapporter l'état de la biodiversité à un seuil absolu :
l'IBD est donc traité comme une inconnue, et l'IED est donné pour plusieurs valeurs de l'IBD.

Entrées : calibration/irnr_series.json, calibration/iee_series.json (workflow « Calibration EH »).
Sorties : calibration/sensibilite_ied.json et calibration/SENSIBILITE_IED.md.

Usage : python3 analyse/sensibilite_ied.py [année]"""

from __future__ import annotations

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

# ----------------------------------------------------------------------------------------------- seuils

SOURCES = {
    "oneill2018": "O'Neill, D. W., Fanning, A. L., Lamb, W. F., & Steinberger, J. K. (2018). A good life for all within "
                  "planetary boundaries. Nature Sustainability, 1, 88–95. https://doi.org/10.1038/s41893-018-0021-4 "
                  "(tableau 1 ; population mondiale de 7 milliards, 2011)",
    "bringezu2015": "Bringezu, S. (2015). Possible target corridor for sustainable use of global material resources. "
                    "Resources, 4(1), 25–54. https://doi.org/10.3390/resources4010025 (§5.2, cible 2050)",
    "eea_wei": "Agence européenne pour l'environnement : seuil conventionnel de stress hydrique de l'indice "
               "d'exploitation de l'eau, 20 % (stress), 40 % (stress sévère)",
}

# Pour chaque sous-indicateur : seuils candidats {nom: (valeur, source, statut)}.
# statut : « planétaire » (limite planétaire ramenée par habitant), « régional » (seuil d'usage, non planétaire).
SOUS_INDICATEURS = {
    "irnr_rmc_abiotique": {
        "composante": "IRNR",
        "libelle": "Empreinte matière non renouvelable (RMC, minerais métalliques + minéraux non métalliques + fossiles)",
        "unite": "t/hab",
        "seuils": {
            "7,2 t (O'Neill)": (7.2, "oneill2018", "planétaire"),
            "5 t (Bringezu)": (5.0, "bringezu2015", "planétaire"),
        },
        "note": "Les deux seuils portent sur l'empreinte matière totale, biomasse comprise ; appliqués à la seule part "
                "non renouvelable, ils sont indulgents. Aucun seuil propre aux matières non renouvelables n'a été "
                "identifié, et la logique de déplétion des stocks du WP (§6.2) n'a pas d'équivalent publié.",
    },
    "iee_co2_empreinte": {
        "composante": "IEE",
        "libelle": "Empreinte CO2 de la consommation",
        "unite": "t CO2/hab",
        "seuils": {"1,61 t (O'Neill)": (1.61, "oneill2018", "planétaire")},
        "note": "Budget de 1 000 Gt CO2 sur 2011–2100 (2 °C, probabilité 66 %) réparti uniformément ; le budget restant "
                "s'est réduit depuis, le seuil est donc indulgent.",
    },
    "iee_azote": {
        "composante": "IEE",
        "libelle": "Azote fixé (engrais minéraux + fixation biologique agricole)",
        "unite": "kg N/hab",
        "seuils": {"8,9 kg (O'Neill)": (8.9, "oneill2018", "planétaire")},
        "note": "Limite de 62 Tg N/an de fixation industrielle et biologique intentionnelle. Mesure territoriale "
                "(production), non empreinte de consommation.",
    },
    "iee_phosphore": {
        "composante": "IEE",
        "libelle": "Phosphore minéral appliqué aux sols agricoles",
        "unite": "kg P/hab",
        "seuils": {"0,89 kg (O'Neill)": (0.89, "oneill2018", "planétaire")},
        "note": "Limite régionale de 6,2 Tg P/an extraits et appliqués aux sols érodables. Mesure territoriale.",
    },
    "iee_eau": {
        "composante": "IEE",
        "libelle": "Indice d'exploitation de l'eau (WEI+)",
        "unite": "%",
        "seuils": {"20 % (AEE)": (20.0, "eea_wei", "régional")},
        "note": "Seuil de stress hydrique d'usage courant, non dérivé d'une limite planétaire. La limite planétaire de "
                "l'eau douce (574 m³/hab chez O'Neill 2018) suppose une série de prélèvements par habitant non "
                "rassemblée ici.",
    },
}

SANS_SEUIL = {
    "IEE — artificialisation (LUCAS) et imperméabilisation": "La limite planétaire du changement d'usage des sols porte "
        "sur le couvert forestier ; aucune limite biophysique de l'artificialisation par habitant n'a été identifiée.",
    "IEE — gaz à effet de serre autres que le CO2": "Le seuil d'O'Neill (2018) porte sur le seul CO2.",
    "IBD — toutes séries": "Les limites de l'intégrité de la biosphère (extinctions par million d'espèces-années, part "
        "de la production primaire appropriée) n'ont pas de traduction nationale ; l'indice des oiseaux communs n'a "
        "pas de seuil absolu.",
}

# ----------------------------------------------------------------------------------------------- normalisation

def norm_lineaire(x, t):
    return min(2.0, max(0.0, 2.0 - x / t))


def norm_ratio(x, t):
    return 2.0 if x <= t / 2 else t / x


def norm_hyperbolique(x, t):
    return 2.0 / (1.0 + x / t)


NORMALISATIONS = {
    "linéaire : 2 − x/T": norm_lineaire,
    "ratio : T/x": norm_ratio,
    "hyperbolique : 2/(1 + x/T)": norm_hyperbolique,
}

# ----------------------------------------------------------------------------------------------- agrégation

def moyenne_puissance(valeurs, poids, rho):
    """M_ρ = (Σ w_i v_i^ρ)^(1/ρ) ; ρ = 0 : moyenne géométrique ; ρ = −∞ : minimum."""
    total = sum(poids)
    w = [p / total for p in poids]
    if rho == -math.inf:
        return min(valeurs)
    if any(v == 0 for v in valeurs):
        return 0.0 if rho <= 0 else sum(wi * v ** rho for wi, v in zip(w, valeurs)) ** (1 / rho)
    if rho == 0:
        return math.exp(sum(wi * math.log(v) for wi, v in zip(w, valeurs)))
    return sum(wi * v ** rho for wi, v in zip(w, valeurs)) ** (1 / rho)


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

VALEURS_IBD = (0.5, 1.0, 1.5)

# ----------------------------------------------------------------------------------------------- données

def charger(nom):
    return json.loads((CAL / nom).read_text())["data"]


RECUL_MAX = 3  # années de recul admises quand une série n'est pas encore publiée pour l'année étudiée
RECULS: dict = {}


def valeur(rows, geo, annee, nom=None):
    """Valeur de l'année demandée, ou de la plus récente des RECUL_MAX années précédentes (recul noté dans RECULS)."""
    for a in range(annee, annee - RECUL_MAX - 1, -1):
        v = rows.get(geo, {}).get(str(a))
        if v is not None:
            if a != annee and nom:
                RECULS.setdefault(geo, {})[nom] = a
            return v[0]
    return None


def serie(series, cle_contient):
    trouve = [k for k in series if all(c in k.split("|") for c in cle_contient)]
    if len(trouve) != 1:
        raise KeyError(f"{cle_contient}: {trouve}")
    return series[trouve[0]]


def mesures(annee):
    irnr, iee = charger("irnr_series.json"), charger("iee_series.json")
    pop = serie(iee["series"]["population"], ["unit=THS_PER"])
    co2 = serie(iee["series"]["ges_empreinte"], ["airpol=CO2", "indic_env=AEMIS_CONS_FP", "unit=KG_HAB"])
    az = iee["series"]["azote"]
    n_min, n_bio = serie(az, ["nutrient=N", "indic_ag=I_FRT_MIN"]), serie(az, ["nutrient=N", "indic_ag=I_OTH_BIO"])
    p_min = serie(az, ["nutrient=P", "indic_ag=I_FRT_MIN"])
    eau = serie(iee["series"]["eau"], ["statinfo=VAL_A"])
    rmc = irnr["series"]["rmc"]
    out = {}
    for g in UE27:
        m = {}
        h = valeur(pop, g, annee)
        r = [valeur(rmc.get(c, {}), g, annee, "irnr_rmc_abiotique") for c in ("MF2", "MF3", "MF4")]
        if None not in r:
            m["irnr_rmc_abiotique"] = sum(r)
        v = valeur(co2, g, annee, "iee_co2_empreinte")
        if v is not None:
            m["iee_co2_empreinte"] = v / 1000
        a, b = valeur(n_min, g, annee, "iee_azote"), valeur(n_bio, g, annee, "iee_azote")
        if None not in (a, b, h):
            m["iee_azote"] = (a + b) * 1000 / (h * 1000)
        p = valeur(p_min, g, annee, "iee_phosphore")
        if None not in (p, h):
            m["iee_phosphore"] = p * 1000 / (h * 1000)
        w = valeur(eau, g, annee, "iee_eau")
        if w is not None:
            m["iee_eau"] = w
        out[g] = m
    return out


# ----------------------------------------------------------------------------------------------- calcul

def rangs(d):
    ordre = sorted(d, key=d.get, reverse=True)
    return {g: i + 1 for i, g in enumerate(ordre)}


def spearman(a, b):
    ra, rb = rangs(a), rangs(b)
    n = len(ra)
    return 1 - 6 * sum((ra[g] - rb[g]) ** 2 for g in ra) / (n * (n * n - 1)) if n > 2 else None


def analyser(annee=ANNEE):
    mes = mesures(annee)
    iee_ids = [k for k, s in SOUS_INDICATEURS.items() if s["composante"] == "IEE"]
    complets = sorted(g for g, m in mes.items() if all(k in m for k in iee_ids + ["irnr_rmc_abiotique"]))

    # Rapport au seuil (x/T) pour chaque sous-indicateur et chaque seuil candidat
    depassements = {g: {k: {nom: round(mes[g][k] / t, 3) for nom, (t, _, _) in s["seuils"].items()}
                        for k, s in SOUS_INDICATEURS.items() if k in mes[g]} for g in UE27}

    resultats = []
    seuil_irnr = list(SOUS_INDICATEURS["irnr_rmc_abiotique"]["seuils"].items())
    for (nn, fn), (na, rho), (np_, w), (ns, (t_irnr, _, _)) in itertools.product(
            NORMALISATIONS.items(), AGREGATIONS.items(), POIDS.items(), seuil_irnr):
        for ibd in VALEURS_IBD:
            ied = {}
            for g in complets:
                s_iee = [fn(mes[g][k], next(iter(SOUS_INDICATEURS[k]["seuils"].values()))[0]) for k in iee_ids]
                iee = moyenne_puissance(s_iee, [1] * len(s_iee), rho)
                irnr = fn(mes[g]["irnr_rmc_abiotique"], t_irnr)
                ied[g] = moyenne_puissance([ibd, iee, irnr], w, rho)
            resultats.append({"normalisation": nn, "agregation": na, "poids": np_, "seuil_irnr": ns, "ibd": ibd,
                              "ied": {g: round(v, 4) for g, v in ied.items()}})

    reference = next(r for r in resultats if r["normalisation"].startswith("hyperbolique")
                     and r["agregation"].startswith("moyenne géo") and r["poids"].startswith("égaux")
                     and r["seuil_irnr"].startswith("7,2") and r["ibd"] == 1.0)
    for r in resultats:
        r["spearman_vs_reference"] = round(spearman(reference["ied"], r["ied"]), 3) if len(complets) > 2 else None

    plages = {g: {"min": min(r["ied"][g] for r in resultats), "max": max(r["ied"][g] for r in resultats)}
              for g in complets}
    return {
        "annee": annee,
        "sources": SOURCES,
        "sous_indicateurs": {k: {**s, "seuils": {n: {"valeur": t, "source": src, "statut": st}
                                                  for n, (t, src, st) in s["seuils"].items()}}
                             for k, s in SOUS_INDICATEURS.items()},
        "sans_seuil": SANS_SEUIL,
        "mesures": {g: {k: round(v, 3) for k, v in m.items()} for g, m in mes.items()},
        "annees_anterieures": RECULS,
        "rapport_au_seuil": depassements,
        "pays_complets": complets,
        "configuration_reference": {k: reference[k] for k in ("normalisation", "agregation", "poids", "seuil_irnr", "ibd")},
        "resultats": resultats,
        "plages": plages,
    }


# ----------------------------------------------------------------------------------------------- rapport

def fr(x, d=2):
    return f"{x:.{d}f}".replace(".", ",")


def rapport(a):
    L = []
    complets, ann = a["pays_complets"], a["annee"]
    ref = a["configuration_reference"]
    L.append(f"# Sensibilité de l'IED aux choix de construction — {ann}\n")
    L.append("*Économie Homéostatique, WP V1.0. Résultats sous hypothèses, produits par `analyse/sensibilite_ied.py` "
             "à partir des séries Eurostat du dossier `calibration/`. Aucune valeur ci-dessous n'est une mesure de "
             "l'IED : chacune dépend d'un jeu de choix explicite, et l'IBD n'a pas de mesure absolue disponible.*\n")

    L.append("## 1. Seuils retenus pour la valeur 1 de la normalisation\n")
    L.append("| Composante | Sous-indicateur | Seuil | Statut | Source |\n|---|---|---|---|---|")
    for k, s in a["sous_indicateurs"].items():
        for n, t in s["seuils"].items():
            L.append(f"| {s['composante']} | {s['libelle']} ({s['unite']}) | {n} | {t['statut']} | {t['source']} |")
    L.append("")
    for k, s in a["sous_indicateurs"].items():
        L.append(f"- **{s['libelle']}** : {s['note']}")
    L.append("\n**Sans seuil absolu identifié**\n")
    for k, v in a["sans_seuil"].items():
        L.append(f"- **{k}** : {v}")
    L.append("\n**Sources**\n")
    for k, v in a["sources"].items():
        L.append(f"- `{k}` : {v}")

    L.append(f"\n## 2. Rapport au seuil par pays ({ann})\n")
    L.append("Valeur observée divisée par le seuil : 1 signifie « au seuil », 3 signifie « trois fois le seuil ». "
             f"Quand une série n'est pas publiée pour {ann}, la valeur la plus récente des {RECUL_MAX} années "
             "précédentes est utilisée (astérisque).\n")
    cols = [("irnr_rmc_abiotique", "7,2 t (O'Neill)", "IRNR / 7,2 t"), ("irnr_rmc_abiotique", "5 t (Bringezu)", "IRNR / 5 t"),
            ("iee_co2_empreinte", None, "CO2"), ("iee_azote", None, "Azote"), ("iee_phosphore", None, "Phosphore"),
            ("iee_eau", None, "Eau (WEI+)")]
    L.append("| Pays | " + " | ".join(c[2] for c in cols) + " |\n|---|" + "---|" * len(cols))
    for g in UE27:
        d = a["rapport_au_seuil"][g]
        cel = []
        for k, sn, _ in cols:
            v = d.get(k, {})
            x = v.get(sn) if sn else (next(iter(v.values())) if v else None)
            etoile = "*" if k in a["annees_anterieures"].get(g, {}) else ""
            cel.append(fr(x) + etoile if x is not None else "–")
        L.append(f"| {g} | " + " | ".join(cel) + " |")

    L.append(f"\n## 3. IED sous la configuration de référence\n")
    L.append(f"Normalisation {ref['normalisation']} ; agrégation {ref['agregation']} ; poids {ref['poids']} ; "
             f"seuil IRNR {ref['seuil_irnr']} ; **IBD fixé à {fr(ref['ibd'], 1)} faute de mesure**. "
             f"Pays disposant de toutes les séries : {len(complets)}.\n")
    r0 = next(r for r in a["resultats"] if all(r[k] == ref[k] for k in ref))
    L.append("| Pays | IED (référence) | IED min | IED max | Écart |\n|---|---|---|---|---|")
    for g in sorted(complets, key=lambda g: -r0["ied"][g]):
        p = a["plages"][g]
        L.append(f"| {g} | {fr(r0['ied'][g])} | {fr(p['min'])} | {fr(p['max'])} | {fr(p['max'] - p['min'])} |")
    L.append(f"\nMin et max portent sur les {len(a['resultats'])} configurations testées "
             f"({len(NORMALISATIONS)} normalisations × {len(AGREGATIONS)} agrégations × {len(POIDS)} pondérations × "
             f"2 seuils IRNR × {len(VALEURS_IBD)} valeurs de l'IBD).")

    L.append("\n## 4. Effet de chaque choix\n")
    L.append("Pour chaque choix, on fait varier ce seul paramètre à partir de la référence. La corrélation de rang "
             "(Spearman) mesure si le classement des pays est conservé (1 = classement identique).\n")
    for param, options in (("normalisation", NORMALISATIONS), ("agregation", AGREGATIONS), ("poids", POIDS),
                           ("seuil_irnr", {n: 0 for n in SOUS_INDICATEURS["irnr_rmc_abiotique"]["seuils"]}),
                           ("ibd", {v: 0 for v in VALEURS_IBD})):
        L.append(f"**{ {'agregation': 'Agrégation', 'normalisation': 'Normalisation', 'poids': 'Pondérations', 'seuil_irnr': 'Seuil IRNR', 'ibd': 'Valeur supposée de l’IBD'}[param] }**\n")
        L.append("| Option | IED moyen | IED min | IED max | Spearman |\n|---|---|---|---|---|")
        for o in options:
            r = next(x for x in a["resultats"] if x[param] == o and all(x[k] == ref[k] for k in ref if k != param))
            v = list(r["ied"].values())
            sp = r["spearman_vs_reference"]
            L.append(f"| {fr(o, 1) if isinstance(o, float) else o} | {fr(sum(v) / len(v))} | {fr(min(v))} | "
                     f"{fr(max(v))} | {fr(sp) if sp is not None else '–'} |")
        L.append("")
    # Lecture : constats calculés
    nuls = [r for r in a["resultats"] if all(v == 0 for v in r["ied"].values())]
    par_norm = {n: sum(1 for r in nuls if r["normalisation"] == n) for n in NORMALISATIONS}
    max_ied = max(v for r in a["resultats"] for v in r["ied"].values())
    max_sans = max(v for r in a["resultats"] if r["ibd"] <= 1 for v in r["ied"].values())
    co2 = [a["rapport_au_seuil"][g]["iee_co2_empreinte"]["1,61 t (O'Neill)"] for g in complets]
    L.append("## 5. Constats\n")
    L.append(f"- **Annulation de l'IED.** {len(nuls)} configurations sur {len(a['resultats'])} donnent un IED nul pour "
             f"tous les pays, dont {par_norm['linéaire : 2 − x/T']} avec la normalisation linéaire. L'empreinte CO2 "
             f"dépasse le seuil d'un facteur {fr(min(co2), 1)} à {fr(max(co2), 1)} ; au-delà de deux fois le seuil, "
             "la normalisation linéaire donne 0, et la moyenne géométrique comme le minimum transmettent ce 0 à l'IED "
             "(§6.2 : si une composante tend vers zéro, l'IED tend vers zéro).")
    L.append(f"- **Aucun pays n'atteint la valeur de référence.** Avec un IBD supposé au plus égal à 1, l'IED ne "
             f"dépasse pas {fr(max_sans)} ; il n'atteint {fr(max_ied)} qu'en supposant un IBD de 1,5, c'est-à-dire "
             "une biodiversité en meilleur état que la référence.")
    L.append("- **Compensation à l'intérieur de l'IEE.** Avec une moyenne, un indice d'exploitation de l'eau très "
             "inférieur à son seuil (note proche de 2) compense en partie un dépassement important de l'empreinte CO2. "
             "Le choix de la fonction d'agrégation se pose donc deux fois : entre les sous-indicateurs d'une "
             "composante, et entre les composantes (T3).")
    L.append("- **Ce qui déplace le classement.** Les normalisations ratio et hyperbolique conservent le classement ; "
             "les agrégations à faible substituabilité (CES ρ = −5, minimum) et les pondérations le modifient "
             "(corrélations de rang de la section 4).")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    annee = int(sys.argv[1]) if len(sys.argv) > 1 else ANNEE
    a = analyser(annee)
    (CAL / "sensibilite_ied.json").write_text(json.dumps(a, ensure_ascii=False, indent=1))
    (CAL / "SENSIBILITE_IED.md").write_text(rapport(a))
    print(f"{annee} : {len(a['pays_complets'])} pays complets, {len(a['resultats'])} configurations")
