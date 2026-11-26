"""Cities = the functional urban areas (FUA) of Eurostat's Urban Audit 2021, placed at their core city; in the
countries the Urban Audit does not cover (Western Balkans, Cyprus, Iceland, Liechtenstein), the towns of 50,000+
inhabitants and the capital (GeoNames).

Each city keeps its true position (x, y: its core city's point) and gets one land cell for its banner: the cell under
it, snapped to the nearest land cell of its country when that is water or foreign, and nudged up to 2 rings away when
a bigger city already holds it. Its economy is built from its NUTS 3 regions in proportion to the share of each
region's population that lives in the urban area (yields.py). Also writes nation.json (the 37 countries together).
"""

from __future__ import annotations

import math
import unicodedata
from collections import Counter

from ..core.europe import COUNTRIES, english_name
from ..core.geo import MapProjection
from ..core.hexgrid import HexGrid
from ..core.store import load_interim, write_web
from .yields import (GDP_INDUSTRIES, INDUSTRIES, YIELDS, Stats, combine, economy, growth_of, lenient_sum, mean_rates,
                     nuts2_rates, region_profile)

REQUIRES = ["_world", "_places", "gisco", "geonames", "eurostat"]
PRODUCES = ["cities.json", "nation.json"]

TOWN_MIN = 50000  # GeoNames towns kept as cities where there is no urban area
SUBURB_KM = 15  # a smaller GeoNames town this close to a kept one is its district or suburb
METRO_MIN = 250000
# Countries whose local units are smaller than municipalities (parishes, electoral divisions, local communities): the
# core city's population comes from GeoNames there.
# Local units smaller than a city (parishes, wards): the core city's population is the biggest GeoNames place near it.
SUBMUNICIPAL_LAU = {"PT", "IE", "EL", "CY", "UK"}
FOOTPRINT_MAJORITY = 4  # of a cell's 7 urban-area samples
PEERS = 5
RANK_KEYS = ["population", "gdp", "gdp_per_capita", "growth"] + [y["key"] for y in YIELDS]


def ring_search(grid: HexGrid, start: int, max_rings: int):
    seen = {start}
    frontier = [start]
    yield 0, start
    for ring in range(1, max_rings + 1):
        nxt = []
        for c in frontier:
            for n in grid.neighbours(c):
                if n not in seen:
                    seen.add(n)
                    nxt.append(n)
                    yield ring, n
        frontier = nxt


def nearest_land(grid, owner, cell, x, y, state, max_rings=8):
    found_ring, best = None, None
    for ring, c in ring_search(grid, cell, max_rings):
        if found_ring is not None and ring > found_ring + 1:
            break
        if owner[c] < 0:
            continue
        found_ring = ring if found_ring is None else found_ring
        cx, cy = grid.center(*grid.col_row(c))
        score = (owner[c] != state, math.hypot(cx - x, cy - y))
        if best is None or score < best[0]:
            best = (score, c)
    return best[1] if best else -1


def free_cell(grid, owner, taken, cell, x, y, state, max_rings=2):
    best = None
    for ring, c in ring_search(grid, cell, max_rings):
        if owner[c] < 0 or c in taken:
            continue
        cx, cy = grid.center(*grid.col_row(c))
        score = (owner[c] != state, math.hypot(cx - x, cy - y))
        if best is None or score < best[0]:
            best = (score, c)
    return best[1] if best else None


def norm(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    return "".join(ch for ch in s if ch.isalnum())


def core_unit(units: list, name: str, x: float, y: float):
    """The local unit that is the core city itself: the most populous unit of the urban area whose name starts like
    the city's ('München, Landeshauptstadt'), else the most populous unit within 8 km of its point."""
    key = norm(name)[:8]
    named = [u for u in units if u[3] and norm(u[1]).startswith(key)]
    if named:
        return max(named, key=lambda u: u[3])
    near = [u for u in units if u[3] and math.hypot(u[5] - x, u[6] - y) <= 8 * 2.5]
    return max(near, key=lambda u: u[3]) if near else None


def latest(row: dict | None):
    return row[max(row)] if row else None


def clean_name(name: str) -> str:
    """'Milano (greater city)' → 'Milano'; 'Irun-Hendaye (French Part)' → 'Irun-Hendaye'; 'Greater Valletta' → 'Valletta';
    'Bristol, City of' and 'Glasgow City' (UK council names) → 'Bristol', 'Glasgow'."""
    name = name.replace("\xa0", " ")
    for tail in (" (greater city)", " (French Part)", " (French part)", " (partie française)", " (Greater City)",
                 ", City of", ", County of"):
        name = name.replace(tail, "")
    if name.endswith(" City") and name[:-5] in UK_CITY_COUNCILS:
        name = name[:-5]
    return name.removeprefix("Greater ").strip()


# Scottish councils named "<town> City" (Glasgow City, Dundee City…): the city is the town.
UK_CITY_COUNCILS = {"Glasgow", "Dundee", "Aberdeen", "Edinburgh"}


def add_ranks(cities: list[dict]) -> None:
    def value(c, key):
        if key == "gdp_per_capita":
            return c["gdp"] / c["population"] if c.get("gdp") is not None and c.get("population") else None
        if key in ("population", "gdp", "growth"):
            return c.get(key)
        return c["yields"].get(key)

    for c in cities:
        c["ranks"] = {}
    for key in RANK_KEYS:
        have = [c for c in cities if value(c, key) is not None]
        have.sort(key=lambda c: -value(c, key))
        for r, c in enumerate(have, 1):
            c["ranks"][key] = r
        for c in cities:
            c["ranks"].setdefault(key, None)
    for i, c in enumerate(cities):
        lp = math.log(c["population"])
        near = sorted((abs(math.log(o["population"]) - lp), j) for j, o in enumerate(cities) if j != i)
        c["peers"] = [cities[j]["id"] for _, j in near[:PEERS]]


def region_rates(s: Stats, parts: list[tuple[str, float]]):
    """Population-weighted NUTS 2 rates and NUTS 3 median age over [(NUTS 3 code, population)]."""
    rates = mean_rates([(w, nuts2_rates(s, g[:4])) for g, w in parts])
    ages = [(w, s.latest("medage3", "MEDAGEPOP", g)[1]) for g, w in parts]
    ages = [(w, a) for w, a in ages if a is not None]
    tot = sum(w for w, _ in ages)
    return rates, (sum(w * a for w, a in ages) / tot if tot else None)


def build() -> None:
    world = load_interim("_world")
    places = load_interim("_places")
    gisco = load_interim("gisco")
    s = Stats(world["counties"], places["region_pop"])
    proj = MapProjection(**world["projection"])
    grid = HexGrid(**world["grid"])
    owner = world["owner"]
    state_index = {code: i for i, code in enumerate(world["states"])}
    region_pop = places["region_pop"]
    profiles: dict[str, dict] = {}

    def profile(g):
        if g not in profiles:
            profiles[g] = region_profile(s, g)
        return profiles[g]

    def share_parts(by_region: dict[str, float], census=True):
        """[(share of the region in the place, region profile)] from the place's population per region: against
        the region's local-unit population (both 2021 census), or for GeoNames towns against Eurostat's."""
        out = []
        for g, p in by_region.items():
            den = region_pop.get(g) if census else profile(g).get("population")
            out.append((min(1.0, p / den) if den else 0.0, profile(g)))
        return out

    fua_pop_eu = s.series("fua_pop", "DE1001V")
    city_pop_eu = s.series("city_pop", "DE1001V")
    fua_names = {f["code"]: f["name"] for f in gisco["fuas"]}
    cores: dict[str, list] = {}
    for c in gisco["cities"]:
        fua = places.get("city_fua", {}).get(c["code"], c["fua"])
        if fua and c["country"] in state_index:
            cores.setdefault(fua, []).append(c)

    gn_by_country: dict[str, list] = {}
    for g in load_interim("geonames")["places"]:
        gx, gy = proj(g["lon"], g["lat"])
        gn_by_country.setdefault(g["country"], []).append({"pop": g["pop"], "x": gx, "y": gy})
    units_by_fua: dict[str, list] = {}
    for u in places["rows"]:
        if u[9]:
            units_by_fua.setdefault(u[9], []).append(u)

    cities = []
    for fua, by_region in places["fua_regions"].items():
        cs = cores.get(fua)
        if not cs:
            continue
        # The core city: a city proper (code …C) rather than a "greater city" (…K), the most populous one.
        core = max(cs, key=lambda c: (c["code"].endswith("C"), latest(city_pop_eu.get(c["code"])) or 0, c["capital"]))
        country = core["country"]
        x, y = proj(core["lon"], core["lat"])
        series_eu = fua_pop_eu.get(fua) or {}
        pop_eu = series_eu[max(series_eu)] if series_eu else None
        parts = share_parts(by_region)
        p = combine(parts)
        rates, median_age = region_rates(s, list(by_region.items()))
        population = pop_eu or places["fua_pop"].get(fua)
        name = english_name(clean_name(core["name"]))
        core_lau = core_unit(units_by_fua.get(fua, []), clean_name(core["name"]), x, y)
        core_pop, core_year = (round(core_lau[3]), 2021) if core_lau and core_lau[3] else (None, None)
        if country in SUBMUNICIPAL_LAU or core_pop is None:
            # The biggest GeoNames place within 10 km of the core city's point: the city proper (Lisbon, not one of
            # its parishes nor Greater Lisbon).
            near = [g["pop"] for g in gn_by_country.get(country, [])
                    if math.hypot(g["x"] - x, g["y"] - y) <= 10 * 2.5]
            if near:
                core_pop, core_year = max(near), None
        g, years = growth_of(p, s)
        cities.append({
            "id": fua,
            "name": name,
            "full": f"{name} functional urban area",
            "local_name": clean_name(core["name"]) if name != clean_name(core["name"]) else None,
            "states": [country],
            "metro": (population or 0) >= METRO_MIN,
            "capital": COUNTRIES[country][1] == name or bool(core["capital"]),
            "national_capital": bool(core["capital"]),
            "centre": name,
            "commune_population": core_pop,
            "commune_year": core_year,
            "cross_border": False,
            "centre_code": core["code"],
            "band": None,
            "x": round(x, 1), "y": round(y, 1),
            "cell": grid.cell_at(x, y),
            **economy(p, rates, s, population=population, median_age=median_age),
            "estimated": p.get("estimated") or None,
            "growth": g, "growth_years": years,
            "counties": sorted(r for r, q in by_region.items() if region_pop.get(r) and q / region_pop[r] >= 0.5)
                        or [max(by_region, key=by_region.get)],
            "communes": None,
            "land_km2": places["fua_area"].get(fua),
            "pop_series": p["series"] or None,
            "source": "urban_audit",
        })
    have = {c["states"][0] for c in cities}

    # Towns of the countries without urban areas.
    cols = places["columns"]
    kept: list[tuple[float, float]] = []
    for gn in sorted(load_interim("geonames")["places"], key=lambda g: -g["pop"]):
        country = gn["country"]
        if country in have:
            continue
        gx, gy = proj(gn["lon"], gn["lat"])
        if any(math.hypot(gx - kx, gy - ky) < SUBURB_KM * 2.5 for kx, ky in kept):
            continue  # a district or suburb of a bigger town already kept (Novi Beograd, Zemun by Belgrade)
        cap = COUNTRIES[country][1]
        is_cap = english_name(gn["name"]) == cap or gn["code"] == "PPLC"
        if gn["pop"] < TOWN_MIN and not is_cap:
            continue
        kept.append((gx, gy))
        x, y = gx, gy
        cell = grid.cell_at(x, y)
        reg = world["county"][cell] if cell >= 0 else -1
        g3 = world["counties"][reg] if reg >= 0 and world["county_state"][reg] == country else None
        if g3 is None:
            near = nearest_land(grid, owner, max(cell, 0), x, y, state_index[country])
            reg = world["county"][near] if near >= 0 else -1
            g3 = world["counties"][reg] if reg >= 0 else None
        by_region = {g3: gn["pop"]} if g3 else {}
        p = combine(share_parts(by_region, census=False)) if by_region else {}
        rates, median_age = region_rates(s, list(by_region.items())) if by_region else ({}, None)
        name = english_name(gn["name"])
        g, years = growth_of(p, s) if p else (None, [int(s.growth_from), int(s.pop_year)])
        cities.append({
            "id": f"GN{gn['id']}", "name": name, "full": name, "local_name": gn["name"] if name != gn["name"] else None,
            "states": [country], "metro": gn["pop"] >= METRO_MIN, "capital": is_cap, "national_capital": is_cap,
            "centre": name, "commune_population": gn["pop"], "commune_year": None, "cross_border": False, "centre_code": None,
            "band": None, "estimated": p.get("estimated") or None if p else None,
            "x": round(x, 1), "y": round(y, 1), "cell": cell,
            **economy(p, rates, s, population=gn["pop"], median_age=median_age),
            "growth": g, "growth_years": years, "counties": [g3] if g3 else [], "communes": None, "land_km2": None,
            "pop_series": None, "source": "geonames",
        })
    cities = [c for c in cities if c["population"]]
    cities.sort(key=lambda c: -c["population"])

    # Banner cells: on the city's country's land, one city per cell where possible (bigger cities choose first).
    taken: set[int] = set()
    snapped, moved, shared = [], [], []
    for c in cities:
        state = state_index[c["states"][0]]
        cell = c["cell"]
        if cell < 0 or owner[cell] != state:
            cell = nearest_land(grid, owner, max(cell, 0), c["x"], c["y"], state)
            snapped.append(c["name"])
        if cell in taken:
            alt = free_cell(grid, owner, taken, cell, c["x"], c["y"], state)
            if alt is None:
                shared.append(c["name"])
            else:
                cell = alt
                moved.append(c["name"])
        taken.add(cell)
        c["cell"] = cell

    # Footprints: cells where most of the 7 urban-area samples are in the city's FUA.
    fua_index = {code: k for k, code in enumerate(world["fuas"])}
    feet: dict[int, set] = {}
    for cell, smp in enumerate(world["fua_samples"]):
        if not smp:
            continue
        for k, n in Counter(x for x in smp if x >= 0).items():
            if n >= FOOTPRINT_MAJORITY:
                feet.setdefault(k, set()).add(cell)
    for c in cities:
        cells = feet.get(fua_index.get(c["id"], -1), set()) | {c["cell"]}
        c["footprint"] = sorted(cells)
    add_ranks(cities)

    print(f"    {len(cities)} cities ({sum(c['metro'] for c in cities)} of {METRO_MIN:,}+), "
          f"{sum(c['source'] == 'geonames' for c in cities)} GeoNames towns; "
          f"{sum(1 for c in cities if c['gdp'] is None)} without GDP")
    for label, items in (("snapped onto their country's land", snapped), ("moved to a free cell", moved),
                         ("still sharing a cell", shared)):
        if items:
            print(f"    {len(items)} {label}: {', '.join(items[:8])}{' …' if len(items) > 8 else ''}")

    # Europe: the 37 countries together (country totals from the NUTS 0 rows, rates weighted by population).
    parts, rate_parts = [], []
    for code in world["states"]:
        pr = profile(code)
        parts.append((1.0, pr))
        rate_parts.append((pr.get("population") or 0, nuts2_rates(s, code)))
    p, missing = lenient_sum([q for _, q in parts])
    nat = economy(p, mean_rates(rate_parts), s)
    nat["left_out"] = {k: [world["states"][i] for i in missing[k]] for k in ("population", "gdp", "jobs_total")
                       if missing[k]}
    have = [q for _, q in parts if q.get("pop_start") and q.get("population")]
    nat["growth"] = round(sum(q["population"] for q in have) / sum(q["pop_start"] for q in have) - 1, 4)
    nat["growth_years"] = [int(s.growth_from), int(s.pop_year)]
    years = set.intersection(*[set(q["series"]) for q in have]) if have else set()
    nat["pop_series"] = {y: round(sum(q["series"][y] for q in have)) for y in sorted(years)} or None
    write_web("cities.json", cities)
    write_web("nation.json", {
        "vintage": f"Eurostat regional statistics: population on 1 January {s.pop_year}, GDP and jobs {s.gdp_year}",
        "year": int(s.pop_year),
        "gdp_vintage": f"Eurostat, GDP of NUTS 3 regions, {s.gdp_year}",
        "nation": nat,
        "name": "Europe",
        "countries": len(world["states"]),
        "yields": YIELDS,
        "industries": {k: label for k, (_, label) in INDUSTRIES.items()},
        "gdp_industries": GDP_INDUSTRIES,
    })
