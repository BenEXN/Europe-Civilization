"""counties.json: one row per intercommunalité (EPCI, the map's "counties"), column-oriented (docs/DATA_CONTRACTS.md).

Metrics use exactly the lens formulas (lenses.py), at the EPCI level. Land shares are the mean of the hex shares
over the EPCI's sample points. `cbsa` is the aire d'attraction (cities.json id) holding most of the EPCI's people.
"""

from __future__ import annotations

import json
import math
from collections import Counter

from ..core.geo import MapProjection
from ..core.hexgrid import HexGrid
from ..core.paths import WEB_DATA
from ..core.store import load_interim, write_web
from .cities import nearest_land
from .lenses import LENSES, add_civic, epci_value
from .yields import TABLE_SOURCES, load_tables

REQUIRES = ["_world", "fr_boundaries", "insee_aav", "cities.json", "catnat", "presidentielle_2022"] + TABLE_SOURCES
PRODUCES = ["counties.json"]

METRICS = {  # output key → lens id
    "income": "income", "poverty": "poverty", "unemployment": "unemployment", "median_age": "age",
    "seniors": "seniors", "bachelors": "bachelors", "homeownership": "homeownership",
    "second_homes": "second_homes", "vacancy": "vacancy", "growth": "growth", "immigrants": "immigrants",
    "car": "car", "transit": "transit", "vote_macron": "vote_macron", "abstention": "abstention",
    "disasters": "disasters",
}
LAND = {
    "forest": ("forest", "Forêt", "Part des terres de l'EPCI couvertes de forêt (CORINE 311-313)"),
    "crop": ("crop", "Cultures", "Part des terres de l'EPCI en cultures, vignes et vergers (CORINE 211-223, 241)"),
    "pasture": ("pasture", "Prairies et bocage", "Part des terres de l'EPCI en prairies et bocage (CORINE 231, 242-244)"),
    "developed": ("developed", "Bâti", "Part des terres de l'EPCI bâties (CORINE 111-133)"),
}
LAND_NOTE = ", moyenne sur les points d'échantillonnage des hexagones qui tombent dans l'EPCI."


def _field(key, label, fmt, unit, higher_is, source, description):
    return {"key": key, "label": label, "format": fmt, "unit": unit, "higher_is": higher_is,
            "source": source, "description": description}


def fields() -> list[dict]:
    out = [
        _field("geoid", "SIREN", "text", None, "neutral", "fr_boundaries", "Numéro SIREN de l'intercommunalité."),
        _field("name", "Intercommunalité", "text", None, "neutral", "fr_boundaries",
               "Nom de l'EPCI à fiscalité propre (métropole, communauté urbaine, d'agglomération ou de communes)."),
        _field("state", "Département", "text", None, "neutral", "fr_boundaries",
               "Département qui compte le plus de communes de l'EPCI."),
        _field("population", "Population", "int", "habitants", "neutral", "insee_comparateur",
               "Population municipale 2023 (recensement)."),
        _field("land_km2", "Superficie", "km2", "km²", "neutral", "insee_comparateur", "Superficie (Insee)."),
        _field("density", "Densité", "float", "habitants / km²", "neutral", "insee_comparateur",
               "Habitants par km² : population 2023 ÷ superficie."),
    ]
    sources = {"income": "insee_comparateur", "poverty": "insee_comparateur", "unemployment": "insee_activite",
               "median_age": "insee_population", "seniors": "insee_population", "bachelors": "insee_diplomes",
               "immigrants": "insee_immigration", "car": "insee_navettes", "transit": "insee_navettes",
               "vote_macron": "presidentielle_2022", "abstention": "presidentielle_2022", "disasters": "catnat"}
    for key, lid in METRICS.items():
        meta = LENSES[lid][1]
        out.append(_field(key, meta["name"], meta["format"], meta["unit"], meta["higher_is"],
                          sources.get(key, "insee_comparateur"), meta["description"]))
    for key, (_, label, desc) in LAND.items():
        out.append(_field(key, label, "pct", "part des terres", "neutral", "clc", desc + LAND_NOTE))
    out.append(_field("cbsa", "Aire d'attraction", "text", None, "neutral", "insee_aav",
                      "Identifiant (cities.json) de l'aire d'attraction qui réunit le plus d'habitants de l'EPCI ; "
                      "nul si la plupart vivent hors des aires."))
    out.append(_field("cell", "Hexagone", "int", None, "neutral", "fr_boundaries",
                      "Un hexagone représentatif : celui de la mairie de la commune la plus peuplée de l'EPCI."))
    return out


def _round(v, fmt):
    if v is None:
        return None
    if fmt == "pct":
        return round(v, 4)
    return round(v, 1) if abs(v) < 1000 else round(v)


def build() -> None:
    world = load_interim("_world")
    bounds = load_interim("fr_boundaries")
    aav = load_interim("insee_aav")
    t = load_tables()
    add_civic(t, bounds)
    proj = MapProjection(**world["projection"])
    grid = HexGrid(**world["grid"])
    owner = world["owner"]
    city_ids = {c["id"] for c in json.loads((WEB_DATA / "cities.json").read_text())}
    aav_of = {c["code"]: c["aav"] for c in aav["communes"]}
    com_pop = {code: r.get("POP_2023") or 0 for code, r in t["comparateur"]["COM"].items()}
    by_epci: dict[str, list[str]] = {}
    for c in bounds["communes"]:
        if c["epci"]:
            by_epci.setdefault(c["epci"], []).append(c["code"])
    names = {e["code"]: e["name"] for e in bounds["epci"]}
    state_index = {code: i for i, code in enumerate(world["states"])}

    # Land shares: mean of hex pct over the EPCI's sample points (a hex counts once per sample in the EPCI).
    land_acc = {k: Counter() for k in LAND}
    hits: Counter = Counter()
    for i, s in enumerate(world["county_samples"]):
        if not s or not world["cover"][i]:
            continue
        for k in s:
            if k < 0:
                continue
            hits[k] += 1
            for key, (pk, _, _) in LAND.items():
                land_acc[key][k] += world["pct"][pk][i]

    flds = fields()
    rows = []
    for idx, geoid in enumerate(world["counties"]):
        comp = t["comparateur"]["EPCI"].get(geoid, {})
        coms = by_epci.get(geoid, [])
        pop = comp.get("POP_2023")
        area = comp.get("SUP_2023")
        votes = Counter()
        for c in coms:
            votes[aav_of.get(c, "000")] += com_pop.get(c, 0)
        top = votes.most_common(1)[0][0] if votes else None
        biggest = max(coms, key=lambda c: com_pop.get(c, 0)) if coms else None
        cell = None
        if biggest and biggest in bounds["mairies"]:
            x, y = proj(*bounds["mairies"][biggest])
            c = grid.cell_at(x, y)
            st = state_index.get(world["county_state"][idx], -1)
            if c >= 0 and owner[c] >= 0:
                cell = c
            else:
                cell = nearest_land(grid, owner, max(c, 0), x, y, st)
                cell = cell if cell >= 0 else None
        row = {
            "geoid": geoid, "name": names.get(geoid, geoid), "state": world["county_state"][idx],
            "population": pop, "land_km2": round(area, 1) if area else None,
            "density": round(pop / area, 1) if pop and area else None,
        }
        for key, lid in METRICS.items():
            fmt = LENSES[lid][1]["format"]
            row[key] = _round(epci_value(lid, geoid, t), fmt)
        for key in LAND:
            row[key] = round(land_acc[key][idx] / hits[idx] / 100, 3) if hits[idx] else None
        row["cbsa"] = top if top in city_ids else None
        row["cell"] = cell
        rows.append([row[f["key"]] for f in flds])
    missing_cell = sum(1 for r in rows if r[-1] is None)
    print(f"    {len(rows)} intercommunalités; {missing_cell} without a representative hex")
    write_web("counties.json", {
        "vintage": "Recensement 2023, Filosofi 2023",
        "fields": flds,
        "columns": [f["key"] for f in flds],
        "rows": rows,
    })
