"""districts.json: each city's real industry specialisation as strategy-game districts (docs/DATA_CONTRACTS.md).

Jobs come from the census (Insee, EMP2: jobs where the work is done, self-employed included) in 38 industries
(NAF A38), directly for each aire d'attraction and intercommunalité. LQ (indice de spécificité) = (the area's jobs
in the district's industries ÷ its total jobs) ÷ (the same ratio for metropolitan France).
"""

from __future__ import annotations

import json

from ..core.hexgrid import HexGrid
from ..core.paths import WEB_DATA
from ..core.store import load_interim, write_web

REQUIRES = ["_world", "insee_emploi", "cities.json", "world.json"]
PRODUCES = ["districts.json"]

MIN_LQ, MIN_JOBS, MIN_SHARE = 1.25, 1000, 0.01
SPECIALTY_LQ, SPECIALTY_JOBS = 3.0, 1000
MAX_PER_CITY = 5
BADGE_LQ, BADGE_SHARE = 6.0, 0.03
TOP_MIN_JOBS, TOP_N = 1000, 8

A38 = {
    "AZ": "Agriculture, sylviculture et pêche", "BZ": "Industries extractives",
    "CA": "Industries agroalimentaires", "CB": "Textile, habillement, cuir", "CC": "Bois, papier, imprimerie",
    "CD": "Cokéfaction et raffinage", "CE": "Industrie chimique", "CF": "Industrie pharmaceutique",
    "CG": "Caoutchouc, plastique, minéraux", "CH": "Métallurgie et produits métalliques",
    "CI": "Informatique, électronique, optique (fabrication)", "CJ": "Équipements électriques",
    "CK": "Machines et équipements", "CL": "Matériels de transport (automobile, aéronautique, navires)",
    "CM": "Autres industries, réparation", "DZ": "Électricité et gaz", "EZ": "Eau, assainissement, déchets",
    "FZ": "Construction", "GZ": "Commerce", "HZ": "Transports et entreposage", "IZ": "Hébergement et restauration",
    "JA": "Édition, audiovisuel, diffusion", "JB": "Télécommunications", "JC": "Informatique et services d'information",
    "KZ": "Finance et assurance", "LZ": "Immobilier", "MA": "Juridique, comptabilité, ingénierie, études",
    "MB": "Recherche-développement", "MC": "Autres activités scientifiques et techniques",
    "NZ": "Services administratifs et de soutien", "OZ": "Administration publique", "PZ": "Enseignement",
    "QA": "Santé", "QB": "Hébergement médico-social et action sociale", "RZ": "Arts, spectacles, loisirs",
    "SZ": "Autres services", "TZ": "Ménages employeurs", "UZ": "Organisations extraterritoriales",
}


def _d(id, name, icon, color, codes, sub, badge, labels, description, caveat=None):
    return {"id": id, "name": name, "icon": icon, "color": color, "naics": codes, "own": [],
            "sub": sub, "badge": {"id": badge, "label": labels.pop("_"), "labels": labels},
            "description": description, "caveat": caveat}


CATALOG = [
    _d("campus", "Campus", "d-campus", "#4a7bd0", ["MB", "PZ", "JC", "JB", "MA"],
       {"MB": "Recherche", "PZ": "Universités et écoles", "JC": "Informatique", "JB": "Télécoms", "MA": "Ingénierie et études"},
       "scientific", {"_": "Ville du savoir", "MB": "Ville de la recherche", "PZ": "Ville étudiante", "JC": "Ville numérique",
                      "JB": "Ville des télécoms", "MA": "Ville d'ingénieurs"},
       "Recherche, enseignement, informatique, télécoms, ingénierie."),
    _d("commercial_hub", "Centre d'affaires", "d-commercial_hub", "#d9a93a", ["KZ"], {"KZ": "Finance et assurance"},
       "commercial", {"_": "Place financière", "KZ": "Place financière"}, "Banques et assurances."),
    _d("industrial_zone", "Zone industrielle", "d-industrial_zone", "#b0603a",
       ["BZ", "CA", "CB", "CC", "CD", "CE", "CF", "CG", "CH", "CI", "CJ", "CK", "CL", "CM"],
       {"CL": "Automobile, aéronautique, navires", "CI": "Électronique", "CF": "Pharmacie", "CD": "Raffinage",
        "CE": "Chimie", "CH": "Métallurgie", "CA": "Agroalimentaire", "CB": "Textile", "BZ": "Extraction"},
       "industrial", {"_": "Ville industrielle", "CL": "Ville de l'automobile et de l'aéronautique", "CI": "Ville de l'électronique",
                      "CF": "Ville de la pharmacie", "CD": "Ville du pétrole", "CE": "Ville de la chimie",
                      "CH": "Ville de la métallurgie", "CA": "Ville de l'agroalimentaire", "CB": "Ville du textile",
                      "BZ": "Ville minière"},
       "Industrie manufacturière et extractive."),
    _d("harbor", "Port", "d-harbor", "#3f7fb5", ["HZ"], {"HZ": "Transports et logistique"},
       "maritime", {"_": "Ville portuaire et logistique", "HZ": "Ville portuaire et logistique"},
       "Transports et entreposage.", "Le recensement ne sépare pas le maritime des autres transports."),
    _d("theater_square", "Quartier des théâtres", "d-theater_square", "#b07ce0", ["RZ", "JA"],
       {"RZ": "Arts et spectacles", "JA": "Édition et audiovisuel"}, "cultural",
       {"_": "Ville des arts", "RZ": "Ville des arts", "JA": "Ville des médias"}, "Arts, spectacles, édition, audiovisuel."),
    _d("entertainment_complex", "Complexe de loisirs", "d-entertainment_complex", "#e0708a", ["IZ"],
       {"IZ": "Hôtels et restaurants"}, "entertainment", {"_": "Ville touristique", "IZ": "Ville touristique"},
       "Hébergement et restauration."),
    _d("government_plaza", "Quartier administratif", "d-government_plaza", "#7a8aa8", ["OZ"],
       {"OZ": "Administration publique"}, "governmental", {"_": "Ville administrative", "OZ": "Ville administrative"},
       "Administration publique (État, collectivités, défense)."),
    _d("aqueduct", "Aqueduc et barrage", "d-aqueduct", "#3fa7a0", ["DZ", "EZ"],
       {"DZ": "Électricité et gaz", "EZ": "Eau et déchets"}, "utility",
       {"_": "Ville de l'énergie", "DZ": "Ville de l'énergie", "EZ": "Ville de l'eau"}, "Énergie, eau, déchets."),
]
RULE_TEXT = (f"Un quartier apparaît quand ses secteurs pèsent au moins {MIN_LQ} fois leur part nationale des emplois "
             f"(indice de spécificité) avec au moins {MIN_JOBS} emplois ou {round(MIN_SHARE * 100)} % des emplois de "
             f"l'aire, ou quand l'une de ses spécialités pèse au moins {SPECIALTY_LQ:g} fois la part nationale avec "
             f"{SPECIALTY_JOBS} emplois. Les quartiers sont classés par emplois au-delà de la norme nationale, cinq au "
             f"plus. Le Port demande un hexagone au bord de l'eau ou traversé par un fleuve. Le type de ville est celui "
             f"du quartier le plus fort, sauf si un quartier pèse {BADGE_LQ:g} fois la norme et {round(BADGE_SHARE * 100)} % "
             f"des emplois. Emplois du recensement 2023 au lieu de travail, non-salariés compris.")


def lq(jobs: dict, codes, nat: dict) -> tuple[float, float]:
    emp = sum(jobs.get(c, 0.0) for c in codes)
    tot = jobs.get("_T") or 0.0
    nat_share = sum(nat.get(c, 0.0) for c in codes) / nat["_T"]
    return emp, (emp / tot / nat_share) if tot and nat_share else 0.0


def districts_of(jobs: dict, nat: dict, wet: bool | None = None) -> list[dict]:
    tot = jobs.get("_T") or 0.0
    out = []
    for c in CATALOG:
        if c["id"] == "harbor" and wet is False:
            continue
        emp, q = lq(jobs, c["naics"], nat)
        best = None
        for code in c["sub"]:
            se, sq = lq(jobs, [code], nat)
            if se >= 1000 and sq > 1 and (best is None or sq > best[1]):
                best = (code, sq, se)
        broad = q >= MIN_LQ and (emp >= MIN_JOBS or emp >= MIN_SHARE * tot)
        spec = best is not None and best[1] >= SPECIALTY_LQ and best[2] >= SPECIALTY_JOBS
        if not (broad or spec):
            continue
        strength = max(emp - emp / q if q else 0.0, (best[2] - best[2] / best[1]) if best else 0.0)
        out.append({"id": c["id"], "lq": round(q, 2), "emp": round(emp), "share": round(emp / tot, 4) if tot else None,
                    "avg_pay": None, "sub": best[0] if best else None, "sub_lq": round(best[1], 2) if best else None,
                    "sub_emp": round(best[2]) if best else None, "sub_lower_bound": False,
                    "via": "broad" if broad else "specialty", "strength": round(strength), "suppressed": 0,
                    "lower_bound": False})
    out.sort(key=lambda d: -d["strength"])
    return out[:MAX_PER_CITY]


def badge_of(ds: list[dict], capital: bool) -> dict | None:
    if not ds:
        return None
    strong = [d for d in ds if d["lq"] >= BADGE_LQ and (d["share"] or 0) >= BADGE_SHARE]
    d = strong[0] if strong else ds[0]
    c = next(c for c in CATALOG if c["id"] == d["id"])
    if d["id"] == "government_plaza" and capital:
        label = "Capitale"
    else:
        label = c["badge"]["labels"].get(d["sub"]) if d["sub"] and (d["sub_lq"] or 0) >= SPECIALTY_LQ else c["badge"]["label"]
    what = c["sub"].get(d["sub"]) if d["sub"] else c["name"]
    q = d["sub_lq"] if d["sub"] and (d["sub_lq"] or 0) >= SPECIALTY_LQ else d["lq"]
    return {"id": c["badge"]["id"], "label": label, "district": d["id"], "basis": "census",
            "text": f"{what} : {str(round(q, 1)).replace('.', ',')} fois la part nationale des emplois"}


def build() -> None:
    world = load_interim("_world")
    jobs = load_interim("insee_emploi")["levels"]
    cities = json.loads((WEB_DATA / "cities.json").read_text())
    wjson = json.loads((WEB_DATA / "world.json").read_text())
    grid = HexGrid(**world["grid"])
    nat = jobs["FRANCE"]["FM"]
    water = wjson["water"]
    river_cells = {grid.cell_at(r["pts"][k], r["pts"][k + 1]) for r in wjson["rivers"] for k in range(0, len(r["pts"]), 2)}

    out_c = {}
    for c in cities:
        j = jobs["AAV2020"].get(c["id"])
        if not j:
            out_c[c["id"]] = None
            continue
        wet = any(water[n] for f in c["footprint"] for n in grid.neighbours(f)) or bool(set(c["footprint"]) & river_cells)
        ds = districts_of(j, nat, wet)
        top = []
        for code, title in A38.items():
            e, q = lq(j, [code], nat)
            if e >= TOP_MIN_JOBS and q > 1:
                top.append({"naics": code, "emp": round(e), "lq": round(q, 2), "avg_pay": None, "oty_pct": None,
                            "suppressed": 0, "lower_bound": False})
        top.sort(key=lambda t: -t["lq"])
        out_c[c["id"]] = {"emp": round(j["_T"]), "avg_pay": None, "counties": [1, 1], "top": top[:TOP_N],
                          "districts": ds, "badge": badge_of(ds, c.get("capital"))}
    out_e = {}
    for geoid in world["counties"]:
        j = jobs["EPCI"].get(geoid)
        if j:
            out_e[geoid] = {"emp": round(j["_T"]), "districts": [[d["id"], d["lq"], d["emp"]] for d in districts_of(j, nat)]}
    badges = sum(1 for v in out_c.values() if v and v["badge"])
    print(f"    {len(out_c)} cities, {badges} with a badge; {len(out_e)} intercommunalités")
    write_web("districts.json", {
        "version": 1, "vintage": "Recensement 2023 (EMP2), emplois au lieu de travail", "year": 2023,
        "sources": ["insee_emploi"],
        "rule": {"min_lq": MIN_LQ, "min_jobs": MIN_JOBS, "min_share": MIN_SHARE, "specialty_lq": SPECIALTY_LQ,
                 "specialty_jobs": SPECIALTY_JOBS, "max_per_city": MAX_PER_CITY, "harbor_needs_water": True,
                 "badge_lq": BADGE_LQ, "badge_share": BADGE_SHARE, "text": RULE_TEXT,
                 "county_note": "Même règle par intercommunalité, sans le test de l'eau pour le Port."},
        "catalog": CATALOG,
        "industries": {code: {"title": title, "us_emp": round(nat.get(code, 0))} for code, title in A38.items()},
        "national": {"emp": round(nat["_T"]), "avg_pay": None},
        "cities": out_c,
        "counties": out_e,
    })
