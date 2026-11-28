"""Évolution de l'IED et de ses composantes, 2015–2023 — Économie Homéostatique, WP V1.0.

Prolonge dans le temps l'analyse de sensibilité (analyse/sensibilite_ied.py), avec les mêmes sous-indicateurs, les mêmes
repères et les mêmes fonctions. Chaque année est mesurée sans recul : une série absente pour une année n'est pas
remplacée par une année voisine, pour que la série temporelle ne répète pas de valeur. Les repères restent fixes ; les
populations sont celles de chaque année.

Produits :
  - IED, IEE, IRNR et rapports aux repères par pays et par année, en configuration de référence (IBD supposé égal à 1) ;
  - sur le panel des pays complets chaque année : variation 2015–2023, pente annuelle (moindres carrés), et
    décomposition de la variation de ln IED entre l'IEE et l'IRNR (exacte pour la moyenne géométrique à poids égaux,
    l'IBD supposé constant) ;
  - robustesse du sens de la variation : pour chaque pays, part des configurations de la grille (IBD = 1) où l'IED
    augmente, diminue ou ne varie pas ;
  - codes Eurostat des termes, par année : une rupture de série (b) ou une définition différente (d) limite la
    lecture d'une tendance.

Les données décrivent l'évolution passée des pressions mesurées. Elles permettent de borner des tendances ; elles ne
renseignent pas la réponse de S au coefficient de régulation u, ni la dynamique F.

Entrées : calibration/irnr_series.json, calibration/iee_series.json.
Sorties : calibration/evolution_ied.json, calibration/EVOLUTION_IED.md.
"""

import itertools
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sensibilite_ied as si  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CAL = ROOT / "calibration"
ANNEES = tuple(range(2015, 2024))
IBD_REFERENCE = 1.0
TOLERANCE = 1e-9  # variation considérée nulle


def iee_ids():
    return [k for k, s in si.SOUS_INDICATEURS.items() if s["composante"] == "IEE"]


def scores(mes, g, fn, rho, w, t_irnr, ids):
    """(IED, IEE, IRNR) d'un pays pour une configuration, IBD supposé égal à 1."""
    iee = si.iee_pays(mes, g, fn, rho, ids)
    irnr = fn(mes[g][si.CLE_IRNR], t_irnr)
    return si.moyenne_puissance([IBD_REFERENCE, iee, irnr], w, rho), iee, irnr


def pente(xs, ys):
    """Pente des moindres carrés de ys sur xs."""
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    den = sum((x - mx) ** 2 for x in xs)
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den


def analyser(irnr=None, iee=None, annees=ANNEES):
    irnr = irnr if irnr is not None else si.charger("irnr_series.json")
    iee = iee if iee is not None else si.charger("iee_series.json")
    ids = iee_ids()
    requis = ids + [si.CLE_IRNR]
    ref = si.REFERENCE
    fn0, rho0 = si.NORMALISATIONS[ref["normalisation"]], si.AGREGATIONS[ref["agregation"]]
    w0 = si.POIDS[ref["poids"]]
    t0 = si.SOUS_INDICATEURS[si.CLE_IRNR]["seuils"][ref["seuil_irnr"]]["valeur"]

    par_annee, mesures, codes = {}, {}, {}
    for a in annees:
        mes, trace = si.mesures(a, recul=0, irnr=irnr, iee=iee)
        complets = sorted(g for g, m in mes.items() if all(k in m for k in requis))
        mesures[a] = mes
        ligne = {}
        for g in complets:
            ied, e, r = scores(mes, g, fn0, rho0, w0, t0, ids)
            ligne[g] = {"ied": ied, "iee": e, "irnr": r,
                        "rapports": {k: mes[g][k] / next(iter(si.SOUS_INDICATEURS[k]["seuils"].values()))["valeur"]
                                     for k in requis}}
        par_annee[a] = {"complets": complets, "pays": ligne}
        for g in complets:
            for k in requis:
                for terme, c in trace[g][k]["termes"].items():
                    for s in c["statut"]:
                        codes.setdefault(g, []).append({"annee": a, "sous_indicateur": k, "terme": terme, "code": s})

    panel = sorted(set.intersection(*(set(par_annee[a]["complets"]) for a in annees)))
    a0, a1 = annees[0], annees[-1]

    tendances = {}
    for g in panel:
        serie = [par_annee[a]["pays"][g] for a in annees]
        d_ln = math.log(serie[-1]["ied"]) - math.log(serie[0]["ied"])
        w = [x / sum(w0) for x in w0]
        tendances[g] = {
            "ied_debut": serie[0]["ied"], "ied_fin": serie[-1]["ied"],
            "variation": serie[-1]["ied"] - serie[0]["ied"],
            "variation_relative": serie[-1]["ied"] / serie[0]["ied"] - 1,
            "pente_annuelle": pente(list(annees), [s["ied"] for s in serie]),
            # ln IED = w_IBD ln IBD + w_IEE ln IEE + w_IRNR ln IRNR (moyenne géométrique), IBD constant.
            "contribution_iee": w[1] * (math.log(serie[-1]["iee"]) - math.log(serie[0]["iee"])),
            "contribution_irnr": w[2] * (math.log(serie[-1]["irnr"]) - math.log(serie[0]["irnr"])),
            "variation_ln": d_ln,
            "rapports_variation": {k: serie[-1]["rapports"][k] / serie[0]["rapports"][k] - 1 for k in requis},
            "codes_rupture": sorted({f"{c['annee']} {c['terme']} : {c['code']}" for c in codes.get(g, [])
                                     if c["code"] in si.COMPARABILITE}),
        }

    # Robustesse du sens de la variation sur la grille (IBD = 1).
    configs = list(itertools.product(si.NORMALISATIONS.items(), si.AGREGATIONS.items(), si.POIDS.items(),
                                     si.SOUS_INDICATEURS[si.CLE_IRNR]["seuils"].items()))
    robustesse = {g: {"hausse": 0, "baisse": 0, "stable": 0} for g in panel}
    for (nn, fn), (na, rho), (np_, w), (ns, s) in configs:
        for g in panel:
            v0 = scores(mesures[a0], g, fn, rho, w, s["valeur"], ids)[0]
            v1 = scores(mesures[a1], g, fn, rho, w, s["valeur"], ids)[0]
            cle = "hausse" if v1 - v0 > TOLERANCE else "baisse" if v0 - v1 > TOLERANCE else "stable"
            robustesse[g][cle] += 1

    moyenne_panel = {a: sum(par_annee[a]["pays"][g]["ied"] for g in panel) / len(panel) for a in annees} if panel else {}
    return {
        "annees": list(annees),
        "configuration_reference": ref,
        "ibd_suppose": IBD_REFERENCE,
        "mesure_sans_recul": True,
        "par_annee": {str(a): v for a, v in par_annee.items()},
        "panel": panel,
        "moyenne_panel": {str(a): v for a, v in moyenne_panel.items()},
        "tendances": tendances,
        "robustesse": {"configurations": len(configs), "pays": robustesse},
        "codes": codes,
    }


# ----------------------------------------------------------------------------------------------- rapport

def fr(x, d=2):
    return f"{x:.{d}f}".replace(".", ",").replace("-", "−")


def pc(x, d=1):
    return f"{'+' if x > 0 else ''}{fr(100 * x, d)} %"


COURTS = {"iee_co2_empreinte": "CO2", "iee_azote": "Azote", "iee_phosphore": "Phosphore",
          "irnr_rmc_totale": "Matière totale"}


def rapport(e):
    a0, a1 = e["annees"][0], e["annees"][-1]
    panel = e["panel"]
    L = [f"# Évolution de l'IED et de ses composantes — {a0}–{a1}\n",
         "*Économie Homéostatique, WP V1.0. Résultats sous hypothèses, produits par `analyse/evolution_ied.py` à partir "
         "des séries Eurostat du dossier `calibration/`, avec les sous-indicateurs, les repères et les fonctions de "
         "`SENSIBILITE_IED.md`. Configuration de référence, IBD supposé égal à 1 et constant. Chaque année est mesurée "
         "sans recul ; les repères sont fixes.*\n",
         "Ces séries décrivent l'évolution passée des pressions mesurées. Elles permettent de borner des tendances ; "
         "elles ne renseignent ni la réponse de S au coefficient de régulation u, ni la dynamique F.\n",
         "## 1. Couverture\n",
         "| Année | Pays complets | IED moyen du panel |\n|---|---|---|"]
    for a in e["annees"]:
        pa = e["par_annee"][str(a)]
        L.append(f"| {a} | {len(pa['complets'])} | {fr(e['moyenne_panel'][str(a)]) if panel else '–'} |")
    L.append(f"\nPanel : {len(panel)} pays complets chaque année de {a0} à {a1} ({', '.join(panel)}). Les moyennes et "
             "les tendances décrivent ces pays seulement.\n")

    L.append(f"## 2. IED de référence par année\n")
    L.append("| Pays | " + " | ".join(str(a) for a in e["annees"]) + " |\n|---|" + "---|" * len(e["annees"]))
    for g in sorted(panel, key=lambda g: -e["par_annee"][str(a1)]["pays"][g]["ied"]):
        L.append(f"| {g} | " + " | ".join(fr(e["par_annee"][str(a)]["pays"][g]["ied"]) for a in e["annees"]) + " |")

    L.append(f"\n## 3. Variation {a0}–{a1} et décomposition\n")
    L.append("La variation de ln IED se répartit exactement entre l'IEE et l'IRNR (moyenne géométrique à poids égaux, "
             "IBD constant) : contribution = ⅓ × variation du logarithme de la composante. Les colonnes des "
             "sous-indicateurs donnent la variation de la grandeur mesurée par habitant (une baisse est une pression "
             "plus faible).\n")
    ks = list(COURTS)
    L.append("| Pays | IED " + str(a0) + " | IED " + str(a1) + " | Variation | Pente / an | Contribution IEE | "
             "Contribution IRNR | " + " | ".join(COURTS[k] for k in ks) + " |\n|---|" + "---|" * (6 + len(ks)))
    for g in sorted(panel, key=lambda g: -e["tendances"][g]["variation_relative"]):
        t = e["tendances"][g]
        L.append(f"| {g} | {fr(t['ied_debut'])} | {fr(t['ied_fin'])} | {pc(t['variation_relative'])} | "
                 f"{fr(t['pente_annuelle'], 4)} | {fr(t['contribution_iee'], 3)} | {fr(t['contribution_irnr'], 3)} | "
                 + " | ".join(pc(t["rapports_variation"][k], 0) for k in ks) + " |")

    r = e["robustesse"]
    L.append(f"\n## 4. Robustesse du sens de la variation\n")
    L.append(f"Pour chaque pays, nombre des {r['configurations']} configurations de la grille (normalisation, "
             "agrégation, pondérations, repère IRNR ; IBD = 1) où l'IED augmente, diminue ou ne varie pas entre "
             f"{a0} et {a1}. « Stable » regroupe surtout les configurations où l'IED est nul les deux années "
             "(normalisation linéaire).\n")
    L.append("| Pays | Hausse | Baisse | Stable | Sens en référence |\n|---|---|---|---|---|")
    for g in panel:
        p = r["pays"][g]
        sens = "hausse" if e["tendances"][g]["variation"] > TOLERANCE else "baisse" \
            if e["tendances"][g]["variation"] < -TOLERANCE else "stable"
        L.append(f"| {g} | {p['hausse']} | {p['baisse']} | {p['stable']} | {sens} |")

    ruptures = {g: e["tendances"][g]["codes_rupture"] for g in panel if e["tendances"][g]["codes_rupture"]}
    L.append("\n## 5. Codes limitant la lecture des tendances\n")
    if ruptures:
        L.append("Termes portant un code de rupture de série (b) ou de définition différente (d) sur la période ; la "
                 "variation correspondante mêle évolution mesurée et changement de méthode.\n")
        for g, cs in ruptures.items():
            L.append(f"- **{g}** : {' ; '.join(cs)}")
    else:
        L.append("Aucun terme des pays du panel ne porte de code b ou d sur la période.")

    L.append("\n## 6. Lecture\n")
    hausses = [g for g in panel if e["tendances"][g]["variation"] > TOLERANCE]
    unanimes = [g for g in panel if r["pays"][g]["baisse"] == 0 and r["pays"][g]["hausse"] > 0]
    L.append(f"- En configuration de référence, l'IED augmente entre {a0} et {a1} pour {len(hausses)} des {len(panel)} "
             f"pays du panel ; pour {len(unanimes)} d'entre eux, aucune configuration de la grille ne donne de baisse.")
    L.append("- Une hausse de l'IED signale une baisse des pressions mesurées par habitant rapportées à des repères "
             "fixes ; elle ne dit pas que le niveau 1 est approché, ni que l'état biophysique s'améliore (l'IBD n'est "
             "pas mesuré).")
    L.append("- Les données sont publiées avec un délai de un à deux ans et révisées ; une série temporelle de l'IED "
             "dépend du millésime de téléchargement.")
    return "\n".join(L) + "\n"


def main():
    e = analyser()
    (CAL / "evolution_ied.json").write_text(json.dumps(e, ensure_ascii=False, indent=1) + "\n")
    (CAL / "EVOLUTION_IED.md").write_text(rapport(e))
    print(f"{e['annees'][0]}–{e['annees'][-1]} : panel de {len(e['panel'])} pays, "
          f"{e['robustesse']['configurations']} configurations testées")


if __name__ == "__main__":
    main()
