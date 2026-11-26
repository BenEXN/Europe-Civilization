"""citizens.json: each city's citizen mix for the City View's person icons (docs/DATA_CONTRACTS.md).

From the 2023 census (Insee), for each aire d'attraction: employed residents by socio-professional group (PCS) and
sector, residents by age, workers by main mode of transport to work, non-students aged 15+ by highest diploma, and
residents by immigration status (the census publishes no birthplace by département, so "origins" is immigrant or
not). Figures use largest-remainder rounding.
"""

from __future__ import annotations

import json

from ..core.paths import WEB_DATA
from ..core.store import load_interim, write_web

REQUIRES = ["insee_pcs", "insee_population", "insee_diplomes", "insee_navettes", "insee_immigration", "cities.json"]
PRODUCES = ["citizens.json"]

FIGURES = {"workforce": 20, "age": 10, "commute": 10}
P = "AGE=Y_GE15|EMPSTA_ENQ=1|PCS={pcs}|{act}RP_MEASURE=POP"


def _pcs(rec: dict, pcs: str, act: str | None = None) -> float | None:
    return rec.get(P.format(pcs=pcs, act=f"EMP_ACTIVITY={act}|" if act else ""))


WORKFORCE = [  # key (the art's figure), label, how to count it
    ("executive", "Artisans, commerçants et chefs d'entreprise", lambda r: _pcs(r, "2")),
    ("engineer", "Cadres et professions intellectuelles supérieures", lambda r: _pcs(r, "3")),
    ("clerk", "Professions intermédiaires", lambda r: _pcs(r, "4")),
    ("service", "Employés", lambda r: _pcs(r, "5")),
    ("farmer", "Agriculteurs exploitants et ouvriers agricoles", lambda r: _sum(_pcs(r, "1"), _pcs(r, "6", "AZ"))),
    ("builder", "Ouvriers du bâtiment", lambda r: _pcs(r, "6", "FZ")),
    ("maker", "Ouvriers de l'industrie, du transport et des services",
     lambda r: _sum(_pcs(r, "6", "BE"), _pcs(r, "6", "GU"), _pcs(r, "6", "OQ"))),
]
AGE = [("child", "Moins de 15 ans", ["Y_LT15"]), ("young", "15 à 39 ans", ["Y15T24", "Y25T39"]),
       ("midlife", "40 à 64 ans", ["Y40T54", "Y55T64"]), ("elder", "65 ans ou plus", ["Y_GE65"])]
T = "TRANS={m}|AGE=Y_GE15|EMPSTA_ENQ=1|RP_MEASURE=POP"
COMMUTE = [("drove_alone", "Voiture, camion ou fourgonnette", ["5"]), ("transit", "Transports en commun", ["6"]),
           ("walk", "Marche à pied", ["2"]), ("other", "Vélo ou deux-roues motorisé", ["3", "4"]),
           ("home", "Pas de transport (travail à domicile)", ["1"])]
NATIVITY = [("born_in_state", "Non immigrés", "IMMI=0|RP_MEASURE=POP"),
            ("foreign_born", "Immigrés (nés étrangers à l'étranger)", "IMMI=1|RP_MEASURE=POP")]
EDUCATION = [("less_than_hs", "Aucun diplôme, certificat d'études ou brevet", ["001T100_RP", "200_RP"]),
             ("high_school", "CAP, BEP ou baccalauréat", ["300_RP", "350T351_RP"]),
             ("some_college", "Bac +2", ["500_RP"]), ("bachelors", "Bac +3 ou +4", ["600_RP"]),
             ("graduate", "Bac +5 ou plus", ["700_RP"])]
RULE = {"specialist_high": 1.5, "specialist_low": 0.67, "min_share": 0.01, "max_high": 4, "max_low": 2,
        "text": "Une catégorie est mise en avant quand sa part dépasse 1,5 fois (ou tombe sous 0,67 fois) la part "
                "nationale ; les catégories de moins de 1 % sont ignorées."}


def _sum(*vals):
    return None if any(v is None for v in vals) else sum(vals)


def largest_remainder(counts: dict, n: int) -> dict:
    tot = sum(counts.values())
    if not tot:
        return {k: 0 for k in counts}
    raw = {k: v / tot * n for k, v in counts.items()}
    out = {k: int(v) for k, v in raw.items()}
    for k in sorted(raw, key=lambda k: -(raw[k] - out[k]))[: n - sum(out.values())]:
        out[k] += 1
    return out


def row(counts: dict | None, figures: int | None) -> dict | None:
    if counts is None or any(v is None for v in counts.values()):
        return None
    counts = {k: round(v) for k, v in counts.items()}
    tot = sum(counts.values())
    if not tot:
        return None
    out = {"total": tot, "counts": counts, "shares": {k: round(v / tot, 3) for k, v in counts.items()}}
    if figures:
        out["figures"] = largest_remainder(counts, figures)
    return out


def profile(pcs: dict, ages: dict, dipl: dict, nav: dict | None = None, immi: dict | None = None) -> dict:
    wf = row({k: f(pcs) for k, _, f in WORKFORCE}, FIGURES["workforce"]) if pcs else None
    age = row({k: sum(ages.get(b, 0) for b in bands) for k, _, bands in AGE}, FIGURES["age"]) if ages else None
    if age:
        from .lenses import median_age
        m = median_age(ages)
        age["median"] = round(m, 1) if m is not None else None
    edu = row({k: sum(dipl.get(c, 0) for c in codes) for k, _, codes in EDUCATION}, None) if dipl else None
    if edu:
        edu["bachelors_plus"] = round(edu["shares"]["bachelors"] + edu["shares"]["graduate"], 3)
    com = row({k: sum(nav.get(T.format(m=m), 0) for m in modes) for k, _, modes in COMMUTE}, FIGURES["commute"]) if nav else None
    nat = row({k: immi.get(key) for k, _, key in NATIVITY}, None) if immi else None
    if nat:
        nat["foreign_born"] = nat["shares"]["foreign_born"]
        nat["born_in_state"] = None
    return {"workforce": wf, "age": age, "commute": com, "education": edu, "nativity": nat}


def specialists(r: dict, nat: dict) -> list[dict]:
    hi, lo = [], []
    for key in ("workforce", "age", "commute", "education", "nativity"):
        a, b = r.get(key), nat.get(key)
        if not a or not b:
            continue
        for k, s in a["shares"].items():
            ns = b["shares"].get(k) or 0
            if not ns or (s < RULE["min_share"] and ns < RULE["min_share"]):
                continue
            ratio = s / ns
            item = {"row": key, "key": k, "share": s, "national": ns, "ratio": round(ratio, 2)}
            if ratio >= RULE["specialist_high"]:
                hi.append(item)
            elif ratio <= RULE["specialist_low"]:
                lo.append(item)
    hi.sort(key=lambda x: -x["ratio"])
    lo.sort(key=lambda x: x["ratio"])
    return hi[: RULE["max_high"]] + lo[: RULE["max_low"]]


def build() -> None:
    pcs = load_interim("insee_pcs")["levels"]
    nav = load_interim("insee_navettes")["levels"]
    immi = load_interim("insee_immigration")["levels"]
    ages = load_interim("insee_population")["levels"]
    dipl = load_interim("insee_diplomes")["levels"]
    cities = json.loads((WEB_DATA / "cities.json").read_text())
    nat = profile(pcs["FRANCE"]["FM"], ages["FRANCE"]["FM"], dipl["FRANCE"]["FM"], nav["FRANCE"]["FM"], immi["FRANCE"]["FM"])
    nat["specialists"] = []
    out = {}
    for c in cities:
        i = c["id"]
        p = profile(pcs["AAV2020"].get(i), ages["AAV2020"].get(i), dipl["AAV2020"].get(i), nav["AAV2020"].get(i),
                    immi["AAV2020"].get(i))
        if not any(p.values()):
            out[i] = None
            continue
        p["specialists"] = specialists(p, nat)
        p["reliable"] = True
        out[i] = p
    groups = {
        "workforce": [{"key": k, "label": l, "icon": f"c-{k}", "lines": "PCS × A5"} for k, l, _ in WORKFORCE],
        "age": [{"key": k, "label": l, "icon": f"c-{k}", "lines": "+".join(b)} for k, l, b in AGE],
        "commute": [{"key": k, "label": l, "icon": f"c-{k}", "lines": "TRANS " + "+".join(m)} for k, l, m in COMMUTE],
        "education": [{"key": k, "label": l, "icon": f"c-{k}", "lines": "+".join(c)} for k, l, c in EDUCATION],
        "nativity": [{"key": k, "label": l, "icon": f"c-{k}", "lines": key} for k, l, key in NATIVITY],
    }
    print(f"    {sum(1 for v in out.values() if v)} cities with citizens")
    write_web("citizens.json", {
        "version": 1, "vintage": "Recensement 2023", "year": 2023,
        "sources": ["insee_pcs", "insee_population", "insee_diplomes", "insee_navettes", "insee_immigration"],
        "figures": FIGURES,
        "rows": {"workforce": "Actifs occupés de 15 ans ou plus par catégorie socioprofessionnelle",
                 "age": "Habitants par âge", "commute": "Actifs occupés par mode de transport principal pour aller travailler",
                 "education": "Non-scolarisés de 15 ans ou plus par diplôme le plus élevé",
                 "nativity": "Habitants selon la situation quant à l'immigration"},
        "groups": groups, "rule": RULE, "national": nat, "cities": out,
    })
