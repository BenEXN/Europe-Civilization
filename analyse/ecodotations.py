"""Économie Homéostatique — ordre de grandeur des canaux de l'écodotation rapportés au PIB (WP EH V1.0, §4.2).

Formules du WP : DETA = IED × β_pub × c ; la dotation totale des citoyens d'un État est égale à sa dotation publique
(DTCIT = DTETA) ; DENT = IED × 𝒴 ; dotation globale DG = DTETA + DTCIT + DTENT. Dans la formalisation, la création
primaire effective est e = u · e_base, avec u = Φ(IED) ; u = 1 est le régime neutre, où la création est égale au flux
de référence e_base.

Ce script calcule, par pays et pour l'agrégat UE-27, chaque canal et DG rapportés au PIB de la même année :

* au flux de référence (u = 1), qui ne dépend que des paramètres institutionnels (β_pub, c, 𝒴) ;
* à u = IED de la configuration de référence de l'analyse de sensibilité, à l'échelle nationale, pour les pays qui en
  disposent (Φ₀(z) = z ; IBD supposé égal à 1).

Il calcule aussi l'IED de zone pour chacune des configurations de la grille. La zone est l'ensemble des pays qui
disposent de toutes les séries (sous-ensemble de disponibilité, non l'UE-27). Ses grandeurs physiques par habitant
sont agrégées d'abord — moyenne des valeurs nationales par habitant pondérée par la population de l'année étudiée —
puis normalisées et agrégées comme celles d'un pays. C'est un proxy, indiqué comme tel : une valeur nationale reprise
d'une année antérieure (recul de l'analyse de sensibilité) est pondérée par la population de l'année étudiée.

Choix de mesure, à lire avec les résultats :

* β_pub est le β_pub de référence (euros constants 2017), converti en euros courants de l'année étudiée par le même
  déflateur du PIB de l'UE-27 que le calcul de β_pub, pour être rapporté à un PIB en euros courants ;
* Σ𝒴 suit la formule du WP : charges d'exploitation brutes des entreprises, lissées sur les trois dernières années.
  Chaque millésime est exprimé à la valeur monétaire de l'année étudiée par le même déflateur que β_pub, puis la
  moyenne est formée (même convention de valeur constante que β_pub) ; la moyenne des montants courants est conservée
  pour comparaison. Il est approché par les comptes nationaux par secteur
  (pipeline/sources/eh_entreprises.py) : consommations intermédiaires, rémunération des salariés et consommation de
  capital fixe (proche des dotations aux amortissements) des sociétés non financières et financières. Les charges
  financières, les impôts et les distributions de bénéfices n'y entrent pas. Deux variantes sont calculées : sans la
  consommation de capital fixe ; sociétés non financières seules.
* Les consommations intermédiaires des comptes nationaux sont comptées chez chaque producteur, sans consolidation
  entre entreprises, comme dans une somme des 𝒴. Elles comprennent les services d'assurance et les services
  d'intermédiation financière indirectement mesurés, que les comptes par secteur ne permettent pas de retirer.

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
    "reference": (("S11", "S12"), ("P2", "D1", "P51C")),
    "sans_amortissements": (("S11", "S12"), ("P2", "D1")),
    "societes_non_financieres": (("S11",), ("P2", "D1", "P51C")),
}
LIBELLES = {
    "reference": "charges d'exploitation brutes (WP §4.2) : consommations intermédiaires, rémunération des salariés et "
                 "consommation de capital fixe, sociétés non financières et financières",
    "sans_amortissements": "idem, sans la consommation de capital fixe",
    "societes_non_financieres": "idem référence, sociétés non financières seules",
}


def lire(nom):
    return json.loads((CAL / nom).read_text())["data"] if nom != "sensibilite_ied.json" \
        else json.loads((CAL / nom).read_text())


def valeur(rows: dict, geo: str, annee: int):
    """(valeur, statut) ou None."""
    v = rows.get(geo, {}).get(str(annee))
    return (v[0], v[1]) if v and v[0] is not None else None


def rapports_prix(beta: dict, annee: int) -> dict:
    """{année a : D(annee) / D(a)} pour les années du lissage, D étant le déflateur du PIB de l'UE-27 qui sert à β_pub.

    Multiplier un montant courant de l'année a par ce rapport l'exprime à la valeur monétaire de l'année étudiée, selon
    la même convention de valeur constante que β_pub. Le déflateur brut est employé quand il est publié dans
    beta_pub.json, sinon le facteur de déflation arrondi."""
    par = beta["par_annee"]
    out = {}
    for a in range(annee - LISSAGE + 1, annee + 1):
        if str(a) not in par or str(annee) not in par:
            raise ValueError(f"déflateur absent pour {a} ou {annee} : lissage à valeur constante impossible")
        da, dn = par[str(a)].get("deflateur_ue27"), par[str(annee)].get("deflateur_ue27")
        out[a] = dn / da if da and dn else par[str(a)]["facteur_deflation"] / par[str(annee)]["facteur_deflation"]
    return out


def assiette(secteurs: dict, geo: str, annee: int, cle: str, prix: dict | None = None):
    """Σ𝒴 lissé (millions d'euros, valeur de l'année étudiée), avec le détail des termes ; None si un terme manque.

    Chaque millésime est d'abord exprimé à la valeur monétaire de l'année étudiée (rapports `prix`, même déflateur
    que β_pub), puis la moyenne est formée. Sans `prix`, la moyenne porte sur les montants courants ; elle est aussi
    conservée (mio_eur_nominal) pour comparaison."""
    secs, ops = ASSIETTES[cle]
    termes, par_annee = [], []
    annees = list(range(annee - LISSAGE + 1, annee + 1))
    for a in annees:
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
    nominal = sum(par_annee) / LISSAGE
    homogene = sum(x * prix[a] for a, x in zip(annees, par_annee)) / LISSAGE if prix else nominal
    return {"mio_eur": homogene, "mio_eur_nominal": nominal,
            "par_annee": dict(zip(annees, [round(x, 1) for x in par_annee])), "codes": termes}


def ied_reference(sens: dict) -> dict:
    """IED national de la configuration de référence, non arrondi quand l'analyse le publie."""
    if "ied_reference_brut" in sens:
        return sens["ied_reference_brut"]
    ref = sens["configuration_reference"]
    for r in sens["resultats"]:
        if all(r.get(k) == v for k, v in ref.items()):
            return r["ied"]
    raise ValueError("configuration de référence absente des résultats de l'analyse de sensibilité")


def _sensibilite():
    import importlib.util
    spec = importlib.util.spec_from_file_location("sensibilite_ied", Path(__file__).resolve().parent / "sensibilite_ied.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def ied_zone(ent: dict, sens: dict, annee: int = ANNEE) -> dict:
    """IED de la zone formée des pays complets, pour chaque configuration de la grille (mêmes libellés d'options)."""
    si = _sensibilite()
    zone = sens["pays_complets"]
    pop = {g: valeur(ent["population"], g, annee) for g in zone}
    if any(p is None for p in pop.values()):
        raise ValueError(f"population {annee} absente pour un pays de la zone : {pop}")
    iee_ids = [k for k, v in si.SOUS_INDICATEURS.items() if v["composante"] == "IEE"]
    cles = iee_ids + [si.CLE_IRNR]
    total = sum(p[0] for p in pop.values())
    mesures = sens.get("mesures_brutes", sens["mesures"])  # valeurs non arrondies quand l'analyse les publie
    mes = {"ZONE": {k: sum(mesures[g][k] * pop[g][0] for g in zone) / total for k in cles}}
    grille = []
    seuils = si.SOUS_INDICATEURS[si.CLE_IRNR]["seuils"]
    for nn, fn in si.NORMALISATIONS.items():
        for na, rho in si.AGREGATIONS.items():
            for np_, w in si.POIDS.items():
                for ns, t in seuils.items():
                    for ibd in si.VALEURS_IBD:
                        v = si.ied_pays(mes, "ZONE", fn, rho, rho, w, t["valeur"], ibd, iee_ids)
                        grille.append({"normalisation": nn, "agregation": na, "poids": np_, "seuil_irnr": ns,
                                       "ibd": ibd, "ied": round(v, 4), "ied_brut": v})
    return {"pays": zone, "population_milliers": round(total, 1),
            "mesures_par_habitant": {k: round(v, 4) for k, v in mes["ZONE"].items()},
            "methode": "grandeurs physiques par habitant agrégées (pondération par la population), puis normalisées",
            "grille": grille}


def calculer(ent: dict, beta: dict, sens: dict, annee: int = ANNEE) -> dict:
    facteur = beta["par_annee"][str(annee)]["facteur_deflation"]  # déflateur 2017 / déflateur de l'année
    beta_const = beta["beta_pub_reference"]["beta_pub_eur_constants"]
    beta_courant = beta_const / facteur
    ied = ied_reference(sens) if sens.get("annee") == annee else {}
    prix = rapports_prix(beta, annee)
    # Variante en standards de pouvoir d'achat : un même pouvoir d'achat par citoyen, converti dans chaque pays par son
    # indice de niveau des prix du PIB de l'année étudiée.
    spa = (beta.get("beta_pub_reference") or {}).get("variante_spa")
    beta_spa_courant = spa["beta_pub_spa_constants"] / facteur if spa else None
    pli = beta.get("niveau_prix", {})
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
        niveau = (pli.get(geo) or {}).get(str(annee))
        if beta_spa_courant and niveau and niveau[0]:
            deta_spa = beta_spa_courant * niveau[0] / 100 * habitants
            r["variante_spa"] = {"niveau_prix": niveau[0], "code_niveau_prix": niveau[1],
                                 "dteta_pib": deta_spa / pib_eur, "dtcit_pib": deta_spa / pib_eur}
        for cle in ASSIETTES:
            y = assiette(ent["secteurs"], geo, annee, cle, prix)
            if y is None:
                continue
            r["assiettes"][cle] = {"y_mio_eur": round(y["mio_eur"], 1), "y_mio_eur_nominal": round(y["mio_eur_nominal"], 1),
                                   "dtent_pib_u1_nominal": y["mio_eur_nominal"] * 1e6 / pib_eur,
                                   "y_par_annee": y["par_annee"],
                                   "codes": y["codes"], "dtent_pib_u1": y["mio_eur"] * 1e6 / pib_eur,
                                   "dg_pib_u1": (2 * deta + y["mio_eur"] * 1e6) / pib_eur}
            if "variante_spa" in r and cle == "reference":
                r["variante_spa"]["dg_pib_u1"] = (2 * r["variante_spa"]["dteta_pib"] * pib_eur + y["mio_eur"] * 1e6) / pib_eur
        if geo in ied:
            u = ied[geo]
            r["u_ied"] = {"u": u, **{k: u * v for k, v in r["u1"].items()},
                          **{f"dtent_pib_{c}": u * a["dtent_pib_u1"] for c, a in r["assiettes"].items()},
                          **{f"dg_pib_{c}": u * a["dg_pib_u1"] for c, a in r["assiettes"].items()}}
        pays[geo] = r
    return {
        "annee": annee,
        "lissage_y": LISSAGE,
        "lissage_methode": "chaque millésime de 𝒴 est exprimé à la valeur monétaire de l'année étudiée par le déflateur "
                           "du PIB de l'UE-27 qui sert à β_pub, puis la moyenne des trois millésimes est formée ; la "
                           "moyenne des montants courants est conservée (y_mio_eur_nominal)",
        "rapports_prix": {str(a): v for a, v in prix.items()},
        "beta_pub_eur_constants_2017": beta_const,
        "beta_pub_eur_courants": round(beta_courant, 2),
        "facteur_deflation": facteur,
        "variante_spa": None if not spa else {
            "beta_pub_spa_constants_2017": spa["beta_pub_spa_constants"],
            "beta_pub_spa_courants": round(beta_spa_courant, 2),
            "pays": [p["geo"] for p in spa["pays"]],
            "methode": "dépense publique par habitant divisée par l'indice de niveau des prix du PIB (UE-27 = 100), "
                       "moyenne des dix pays les plus élevés en 2017 ; montant reconverti pour chaque pays par son "
                       "indice de l'année étudiée",
        },
        "assiettes": {c: {"secteurs": list(s), "operations": list(o), "libelle": LIBELLES[c]}
                      for c, (s, o) in ASSIETTES.items()},
        "u_ied": "IED de la configuration de référence (échelle nationale, Φ₀(z) = z, IBD supposé égal à 1)",
        "statut": "ordres de grandeur sous hypothèses ; aucun montant n'est une prévision ni une proposition budgétaire",
        "pays": pays,
        "zone": ied_zone(ent, sens, annee) if sens.get("annee") == annee else None,
    }


def resume(res: dict) -> str:
    L = [f"  année {res['annee']}, β_pub = {res['beta_pub_eur_courants']:.0f} € courants "
         f"({res['beta_pub_eur_constants_2017']:.0f} €2017) ; rapports au PIB, u = 1"]
    L.append(f"  {'pays':6s} {'DTETA':>7s} {'DTCIT':>7s} {'DTENT':>7s} {'s.amort.':>8s} {'S11':>7s} {'DG':>7s}"
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
                 f"{pc(a.get('sans_amortissements', {}).get('dtent_pib_u1')):>8s} "
                 f"{pc(a.get('societes_non_financieres', {}).get('dtent_pib_u1'))} {pc(ref.get('dg_pib_u1'))}")
        if "u_ied" in r:
            ligne += f" {r['u_ied']['u']:6.2f} {pc(r['u_ied'].get('dg_pib_reference'))}"
        L.append(ligne)
    return "\n".join(L)


if __name__ == "__main__":
    annee = int(sys.argv[1]) if len(sys.argv) > 1 else ANNEE
    res = calculer(lire("entreprises_series.json"), lire("beta_pub.json"), lire("sensibilite_ied.json"), annee)
    (CAL / "ecodotations.json").write_text(json.dumps(res, ensure_ascii=False, indent=1) + "\n")
    print(resume(res))
