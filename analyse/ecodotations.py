"""Économie Homéostatique — ordre de grandeur des canaux de l'écodotation rapportés au PIB (WP EH V1.0, §4.2).

Formules du WP : DETA = IED × β_pub × c ; la dotation totale des citoyens d'un État est égale à sa dotation publique
(DTCIT = DTETA) ; DENT = IED × 𝒴 ; dotation globale DG = DTETA + DTCIT + DTENT. Dans la formalisation, la création
primaire effective est e = u · e_base, avec u = Φ(IED) ; u = 1 est le régime neutre, où la création est égale au flux
de référence e_base.

Ce script calcule, par pays et pour l'agrégat UE-27, chaque canal et DG rapportés au PIB de la même année :

* au flux de référence (u = 1), qui ne dépend que des paramètres institutionnels (β_pub, c, 𝒴) ;
* à u = IED de la configuration de référence de l'analyse de sensibilité, à l'échelle nationale, pour les pays qui en
  disposent (Φ₀(z) = z ; IBD supposé égal à 1).

Choix de mesure, à lire avec les résultats :

* β_pub est le β_pub de référence (euros constants 2017), converti en euros courants de l'année étudiée par le même
  déflateur du PIB de l'UE-27 que le calcul de β_pub, pour être rapporté à un PIB en euros courants ;
* Σ𝒴 est approché par les comptes nationaux par secteur (pipeline/sources/eh_entreprises.py), lissé sur les trois
  dernières années comme le prévoit le WP (moyenne des montants courants). Trois assiettes sont calculées :
  consommations intermédiaires et rémunération des salariés des sociétés non financières (référence) ; la même
  augmentée de la consommation de capital fixe (amortissements) ; la même étendue aux sociétés financières. Les
  impôts, assurances, produits financiers et distributions de bénéfices n'y entrent pas.
* Les consommations intermédiaires sont comptées chez chaque producteur, sans consolidation entre entreprises.

Ce sont des ordres de grandeur sous hypothèses : aucun montant n'est une prévision ni une proposition budgétaire.

Entrées : calibration/entreprises_series.json, calibration/beta_pub.json, calibration/sensibilite_ied.json.
Sortie : calibration/ecodotations.json.

Usage : python3 analyse/ecodotations.py [année]"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CAL = ROOT / "calibration"
ANNEE = 2023
LISSAGE = 3  # années de lissage de 𝒴 (WP §4.2)
UE27 = ("AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE", "EL", "ES", "FI", "FR", "HR", "HU", "IE", "IT", "LT", "LU",
        "LV", "MT", "NL", "PL", "PT", "RO", "SE", "SI", "SK")
ZONE = "EU27_2020"

# assiette → (secteurs, opérations)
ASSIETTES = {
    "reference": (("S11",), ("P2", "D1")),
    "avec_amortissements": (("S11",), ("P2", "D1", "P51C")),
    "avec_societes_financieres": (("S11", "S12"), ("P2", "D1")),
}
LIBELLES = {
    "reference": "sociétés non financières : consommations intermédiaires + rémunération des salariés",
    "avec_amortissements": "idem + consommation de capital fixe",
    "avec_societes_financieres": "idem référence, sociétés non financières et financières",
}


def lire(nom):
    return json.loads((CAL / nom).read_text())["data"] if nom != "sensibilite_ied.json" \
        else json.loads((CAL / nom).read_text())


def valeur(rows: dict, geo: str, annee: int):
    """(valeur, statut) ou None."""
    v = rows.get(geo, {}).get(str(annee))
    return (v[0], v[1]) if v and v[0] is not None else None


def assiette(secteurs: dict, geo: str, annee: int, cle: str):
    """Σ𝒴 lissé (millions d'euros courants), avec le détail des termes ; None si un terme manque."""
    secs, ops = ASSIETTES[cle]
    termes, par_annee = [], []
    for a in range(annee - LISSAGE + 1, annee + 1):
        total = 0.0
        for s in secs:
            for op in ops:
                v = valeur(secteurs[s][op], geo, a)
                if v is None:
                    return None
                total += v[0]
                if v[1]:
                    termes.append({"annee": a, "terme": f"{s} {op}", "code": v[1]})
        par_annee.append(total)
    return {"mio_eur": sum(par_annee) / LISSAGE, "par_annee": dict(zip(range(annee - LISSAGE + 1, annee + 1),
                                                                     [round(x, 1) for x in par_annee])),
            "codes": termes}


def ied_reference(sens: dict) -> dict:
    ref = sens["configuration_reference"]
    for r in sens["resultats"]:
        if all(r.get(k) == v for k, v in ref.items()):
            return r["ied"]
    raise ValueError("configuration de référence absente des résultats de l'analyse de sensibilité")


def calculer(ent: dict, beta: dict, sens: dict, annee: int = ANNEE) -> dict:
    facteur = beta["par_annee"][str(annee)]["facteur_deflation"]  # déflateur 2017 / déflateur de l'année
    beta_const = beta["beta_pub_reference"]["beta_pub_eur_constants"]
    beta_courant = beta_const / facteur
    ied = ied_reference(sens) if sens.get("annee") == annee else {}
    pays = {}
    for geo in UE27 + (ZONE,):
        pib, pop = valeur(ent["pib"], geo, annee), valeur(ent["population"], geo, annee)
        if pib is None or pop is None:
            pays[geo] = {"disponible": False}
            continue
        pib_eur, habitants = pib[0] * 1e6, pop[0] * 1e3
        deta = beta_courant * habitants
        r = {"disponible": True, "pib_mio_eur": pib[0], "population_milliers": pop[0],
             "codes": [f"{n} : {c}" for n, (_, c) in (("PIB", pib), ("population", pop)) if c],
             "u1": {"dteta_pib": deta / pib_eur, "dtcit_pib": deta / pib_eur}, "assiettes": {}}
        for cle in ASSIETTES:
            y = assiette(ent["secteurs"], geo, annee, cle)
            if y is None:
                continue
            r["assiettes"][cle] = {"y_mio_eur": round(y["mio_eur"], 1), "y_par_annee": y["par_annee"],
                                   "codes": y["codes"], "dtent_pib_u1": y["mio_eur"] * 1e6 / pib_eur,
                                   "dg_pib_u1": (2 * deta + y["mio_eur"] * 1e6) / pib_eur}
        if geo in ied:
            u = ied[geo]
            r["u_ied"] = {"u": u, **{k: u * v for k, v in r["u1"].items()},
                          **{f"dtent_pib_{c}": u * a["dtent_pib_u1"] for c, a in r["assiettes"].items()},
                          **{f"dg_pib_{c}": u * a["dg_pib_u1"] for c, a in r["assiettes"].items()}}
        pays[geo] = r
    return {
        "annee": annee,
        "lissage_y": LISSAGE,
        "beta_pub_eur_constants_2017": beta_const,
        "beta_pub_eur_courants": round(beta_courant, 2),
        "facteur_deflation": facteur,
        "assiettes": {c: {"secteurs": list(s), "operations": list(o), "libelle": LIBELLES[c]}
                      for c, (s, o) in ASSIETTES.items()},
        "u_ied": "IED de la configuration de référence (échelle nationale, Φ₀(z) = z, IBD supposé égal à 1)",
        "statut": "ordres de grandeur sous hypothèses ; aucun montant n'est une prévision ni une proposition budgétaire",
        "pays": pays,
    }


def resume(res: dict) -> str:
    L = [f"  année {res['annee']}, β_pub = {res['beta_pub_eur_courants']:.0f} € courants "
         f"({res['beta_pub_eur_constants_2017']:.0f} €2017) ; rapports au PIB, u = 1"]
    L.append(f"  {'pays':6s} {'DTETA':>7s} {'DTCIT':>7s} {'DTENT':>7s} {'+amort.':>8s} {'+S12':>7s} {'DG':>7s}"
             f" {'u=IED':>6s} {'DG(u)':>7s}")
    for geo, r in res["pays"].items():
        if not r.get("disponible"):
            L.append(f"  {geo:6s} indisponible")
            continue
        a = r["assiettes"]

        def pc(x):
            return f"{100 * x:6.1f}%" if x is not None else "      –"
        ref = a.get("reference", {})
        ligne = (f"  {geo:6s} {pc(r['u1']['dteta_pib'])} {pc(r['u1']['dtcit_pib'])} {pc(ref.get('dtent_pib_u1'))} "
                 f"{pc(a.get('avec_amortissements', {}).get('dtent_pib_u1')):>8s} "
                 f"{pc(a.get('avec_societes_financieres', {}).get('dtent_pib_u1'))} {pc(ref.get('dg_pib_u1'))}")
        if "u_ied" in r:
            ligne += f" {r['u_ied']['u']:6.2f} {pc(r['u_ied'].get('dg_pib_reference'))}"
        L.append(ligne)
    return "\n".join(L)


if __name__ == "__main__":
    annee = int(sys.argv[1]) if len(sys.argv) > 1 else ANNEE
    res = calculer(lire("entreprises_series.json"), lire("beta_pub.json"), lire("sensibilite_ied.json"), annee)
    (CAL / "ecodotations.json").write_text(json.dumps(res, ensure_ascii=False, indent=1) + "\n")
    print(resume(res))
