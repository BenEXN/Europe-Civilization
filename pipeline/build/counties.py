"""counties.json: one row per NUTS 3 region (the map's "counties"), column-oriented (docs/DATA_CONTRACTS.md).

Metrics are the lens formulas (lenses.py) at the region level. Land shares are the mean of the hex shares over the
region's sample points. `cbsa` is the urban area (cities.json id) holding most of the region's people. `cell` is a
representative hex: the one under the population-weighted centre of the region's local units, on its country's land.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict

from ..core.europe import COUNTRIES
from ..core.hexgrid import HexGrid
from ..core.paths import WEB_DATA
from ..core.store import load_interim, write_web
from .cities import nearest_land
from .yields import Stats

REQUIRES = ["_world", "_places", "_region_values", "gisco", "eurostat", "cities.json"]
PRODUCES = ["counties.json"]

LENS_COLUMNS = {  # column → (lens id, label, format, unit, higher_is)
    "growth": ("growth", "Growth", "pct", "population change", "neutral"),
    "median_age": ("age", "Median age", "years", "years", "neutral"),
    "seniors": ("seniors", "Seniors", "pct", "share aged 65+", "neutral"),
    "youth": ("youth", "Children", "pct", "share under 15", "neutral"),
    "gdp_capita": ("gdp_capita", "GDP per person (PPS)", "usd", "€ PPS per inhabitant", "good"),
    "income": ("income", "Household income (PPS)", "usd", "disposable income per inhabitant, PPS", "good"),
    "poverty": ("poverty", "Poverty", "pct", "at risk of poverty or social exclusion", "bad"),
    "unemployment": ("unemployment", "Unemployment", "pct", "unemployment rate 15-74", "bad"),
    "employment": ("employment", "Employment rate", "pct", "employed among 20-64", "good"),
    "bachelors": ("bachelors", "University degrees", "pct", "25-64 with tertiary education", "good"),
    "life_expectancy": ("life_expectancy", "Life expectancy", "float", "years at birth", "good"),
}
LAND = {
    "forest": ("forest", "Forest", "Share of the region's land covered by forest (CORINE 311-313)"),
    "crop": ("crop", "Cropland", "Share of the region's land in crops, vineyards and orchards (CORINE 211-223, 241)"),
    "pasture": ("pasture", "Pasture", "Share of the region's land in pastures and mixed farming (CORINE 231, 242-244)"),
    "developed": ("developed", "Built-up", "Share of the region's built-up land (CORINE 111-133)"),
}
LAND_NOTE = ", mean over the sample points of the hexes that fall in the region."


def _field(key, label, fmt, unit, higher_is, source, description):
    return {"key": key, "label": label, "format": fmt, "unit": unit, "higher_is": higher_is,
            "source": source, "description": description}


def fields(lenses: dict) -> list[dict]:
    out = [
        _field("geoid", "NUTS code", "text", None, "neutral", "gisco", "NUTS 2024 code of the region."),
        _field("name", "Region", "text", None, "neutral", "gisco", "Name of the NUTS 3 region (Latin script)."),
        _field("state", "Country", "text", None, "neutral", "gisco", "Country code of the region."),
        _field("population", "Population", "int", "people", "neutral", "eurostat",
               "Population on 1 January (Eurostat demo_r_pjanaggr3)."),
        _field("land_km2", "Area", "km2", "km²", "neutral", "gisco",
               "Area of the region: the sum of its local administrative units' areas (GISCO LAU 2021)."),
        _field("density", "Density", "float", "people / km²", "neutral", "eurostat", "Population ÷ area."),
        _field("gdp", "GDP", "usd", "€", "neutral", "eurostat",
               "Gross domestic product at current prices (Eurostat nama_10r_3gdp)."),
        _field("jobs", "Jobs", "int", "people employed", "neutral", "eurostat",
               "Employment at the place of work (Eurostat nama_10r_3empers)."),
    ]
    for key, (lid, label, fmt, unit, hi) in LENS_COLUMNS.items():
        desc = lenses.get(lid, {}).get("description", "")
        out.append(_field(key, label, fmt, unit, hi, "eurostat", desc.split(" Colours span")[0]))
    for key, (_, label, desc) in LAND.items():
        out.append(_field(key, label, "pct", "share of the land", "neutral", "corine_eu", desc + LAND_NOTE))
    out.append(_field("cbsa", "Urban area", "text", None, "neutral", "gisco",
                      "The urban area (cities.json id) holding most of the region's people, if any."))
    out.append(_field("cell", "Hex", "int", None, "neutral", "gisco", "A representative hex of the region."))
    out.append(_field("estimated", "Estimated", "text", None, "neutral", "eurostat",
                      "Figures filled from a larger region because Eurostat does not publish them for this one "
                      "(tables: emp3 = jobs by branch, gva3 = value added by branch, gdp3 = GDP, pop3 = population)."))
    return out


def build() -> None:
    world = load_interim("_world")
    places = load_interim("_places")
    gisco = load_interim("gisco")
    rv = load_interim("_region_values")["values"]
    s = Stats(world["counties"], places["region_pop"])
    grid = HexGrid(**world["grid"])
    owner = world["owner"]
    regions = world["counties"]
    names = {n["code"]: n["name"] for n in gisco["nuts"]}
    state_k = {c: k for k, c in enumerate(world["states"])}
    lenses = {l["id"]: l for l in json.loads((WEB_DATA / "lenses.json").read_text())["lenses"]}
    city_ids = {c["id"] for c in json.loads((WEB_DATA / "cities.json").read_text())}

    # Land shares: hex shares averaged over the region's sample points.
    pct = world["pct"]
    acc = defaultdict(lambda: defaultdict(float))
    hits = Counter()
    for i, smp in enumerate(world["county_samples"]):
        if owner[i] < 0 or not world["cover"][i]:
            continue
        for k in smp:
            if k >= 0:
                hits[k] += 1
                for key in LAND:
                    acc[k][key] += pct[key][i]
    # Areas, centres and urban areas from the local units.
    area = Counter()
    cx, cy, w = Counter(), Counter(), Counter()
    fua_pop = defaultdict(Counter)
    for u in places["rows"]:
        _, _, _, pop, a, x, y, _, reg, fua = u
        if not reg:
            continue
        area[reg] += a or 0
        p = pop or 1
        cx[reg] += x * p
        cy[reg] += y * p
        w[reg] += p
        if fua and fua in city_ids:
            fua_pop[reg][fua] += pop or 0
    rows = []
    for k, g in enumerate(regions):
        country = world["county_state"][k]
        pop = s.value("pop3", "TOTAL", g, s.pop_year)
        gdp = s.value("gdp3", "MIO_EUR", g, s.gdp_year)
        jobs = s.value("emp3", "TOTAL", g, s.gdp_year)
        land_km2 = round(area[g], 1) if area[g] else None
        if w[g]:
            x, y = cx[g] / w[g], cy[g] / w[g]
            cell = grid.cell_at(x, y)
            if cell < 0 or owner[cell] != state_k[country]:
                cell = nearest_land(grid, owner, max(cell, 0), x, y, state_k[country])
        else:
            own = [i for i, c in enumerate(world["county"]) if c == k]
            cell = own[len(own) // 2] if own else None
        est = sorted({t for t, c, gg in s.estimated if gg == g})
        row = [g, names.get(g, g), country,
               round(pop) if pop is not None else None, land_km2,
               round(pop / land_km2, 1) if pop and land_km2 else None,
               round(gdp * 1e6) if gdp is not None else None,
               round(jobs * 1000) if jobs is not None else None]
        for key, (lid, *_rest) in LENS_COLUMNS.items():
            v = rv[lid][k]
            row.append(round(v, 4) if v is not None else None)
        for key in LAND:
            row.append(round(acc[k][key] / hits[k] / 100, 3) if hits[k] else None)
        top = fua_pop[g].most_common(1)
        row += [top[0][0] if top else None, cell if cell is not None and cell >= 0 else None, ",".join(est) or None]
        rows.append(row)
    flds = fields(lenses)
    write_web("counties.json", {"vintage": f"Eurostat {s.pop_year} (GDP {s.gdp_year})",
                                "fields": flds, "columns": [f["key"] for f in flds], "rows": rows})
    print(f"    {len(rows)} regions; without population {sum(1 for r in rows if r[3] is None)}, "
          f"without GDP {sum(1 for r in rows if r[6] is None)}, without a cell {sum(1 for r in rows if r[-2] is None)}; "
          f"{sum(1 for r in rows if r[-1])} with estimated figures; countries {len({r[2] for r in rows})}/{len(COUNTRIES)}")
