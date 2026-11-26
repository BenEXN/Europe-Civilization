"""Cities = Insee aires d'attraction des villes (AAV 2020) of metropolitan France, placed at their commune-centre.

Each city keeps its true position (x, y: the town hall of its commune-centre) and gets one land cell for its
banner: the cell under it, snapped to the nearest French land cell when that is water or foreign, and nudged up
to 2 rings away when a bigger city already holds it. GDP (Gold) shares each département's GDP (Eurostat) out to
the area by its jobs (census 2023). Growth is the population change between the 2017 and 2023 censuses.
For the City view each city also gets its intercommunalités, a hex footprint (cells where most commune samples are
member communes), its census population series since 1968, ranks among all cities and its 5 nearest peers by
population (see docs/DATA_CONTRACTS.md).
"""

from __future__ import annotations

import math
from collections import Counter

from ..core.geo import MapProjection
from ..core.hexgrid import HexGrid
from ..core.store import load_interim, load_interim_payload, write_web
from .yields import GDP_INDUSTRIES, INDUSTRIES, TABLE_SOURCES, YIELDS, GdpShare, economy, growth, load_tables, pop_series

REQUIRES = ["_world", "fr_boundaries", "insee_aav", "eurostat_gdp"] + TABLE_SOURCES
PRODUCES = ["cities.json", "nation.json"]

CAPITAL_AAV = "001"  # Paris
GDP_YEAR = "2024"
VOWELS = "AEIOUYÉÈÊÂÎÔ"


def full_name(name: str) -> str:
    """'Le Havre' → "Aire d'attraction du Havre"; 'Annecy' → "Aire d'attraction d'Annecy"."""
    if name.startswith("Le "):
        return f"Aire d'attraction du {name[3:]}"
    if name.startswith("Les "):
        return f"Aire d'attraction des {name[4:]}"
    if name[:1].upper() in VOWELS or name.startswith("H"):
        return f"Aire d'attraction d'{name}"
    return f"Aire d'attraction de {name}"


def ring_search(grid: HexGrid, start: int, max_rings: int):
    """Yield (ring, cell) for every cell within `max_rings` steps of `start`, nearest rings first."""
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


def nearest_land(grid: HexGrid, owner: list[int], cell: int, x: float, y: float, state: int, max_rings=8):
    """Nearest French land cell to (x, y), preferring `state`: the first ring with land, plus one more."""
    found_ring = None
    best = None
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


def free_cell(grid: HexGrid, owner, taken: set, cell: int, x: float, y: float, state: int, max_rings=2):
    """Nearest untaken land cell within `max_rings`, preferring `state`; None if there is none."""
    best = None
    for ring, c in ring_search(grid, cell, max_rings):
        if owner[c] < 0 or c in taken:
            continue
        cx, cy = grid.center(*grid.col_row(c))
        score = (owner[c] != state, math.hypot(cx - x, cy - y))
        if best is None or score < best[0]:
            best = (score, c)
    return best[1] if best else None


FOOTPRINT_MAJORITY = 4  # of a cell's 7 commune samples
PEERS = 5
RANK_KEYS = ["population", "gdp", "gdp_per_capita", "growth"] + [y["key"] for y in YIELDS]


def footprints(world: dict, aav_of_commune: dict[str, str]) -> dict[str, set[int]]:
    """AAV code → French land cells where at least FOOTPRINT_MAJORITY of the 7 commune samples are in the area."""
    by_index = [aav_of_commune.get(code) for code in world["communes"]]
    out: dict[str, set[int]] = {}
    for cell, s in enumerate(world["commune_samples"]):
        if not s or world["owner"][cell] < 0:
            continue
        votes = Counter(by_index[k] for k in s if k >= 0 and by_index[k])
        for code, n in votes.items():
            if n >= FOOTPRINT_MAJORITY:
                out.setdefault(code, set()).add(cell)
    return out


def add_ranks(cities: list[dict]) -> None:
    """ranks: 1 = highest among all cities, null where the value is null (cities are sorted by population,
    so ties keep population order). peers: the PEERS cities closest in population (by ratio)."""
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
        have.sort(key=lambda c: -value(c, key))  # stable: ties stay in population order
        for r, c in enumerate(have, 1):
            c["ranks"][key] = r
        for c in cities:
            c["ranks"].setdefault(key, None)
    for i, c in enumerate(cities):
        lp = math.log(c["population"])
        near = sorted((abs(math.log(o["population"]) - lp), j) for j, o in enumerate(cities) if j != i)
        c["peers"] = [cities[j]["id"] for _, j in near[:PEERS]]


def gdp_share() -> GdpShare:
    bounds = load_interim("fr_boundaries")
    gdp_src = load_interim("eurostat_gdp")
    jobs_com = load_interim("insee_emploi")["levels"]["COM"]
    commune_dep = {c["code"]: c["dep"] for c in bounds["communes"]}
    # Communes missing from the boundaries (merged since the census geography) keep their département prefix.
    for com in jobs_com:
        if com not in commune_dep and not com.startswith("97"):
            commune_dep[com] = com[:3] if com.startswith("97") else com[:2]
    return GdpShare(gdp_src, jobs_com, commune_dep, {d["code"]: d["name"] for d in bounds["departements"]}, GDP_YEAR)


def build() -> None:
    world = load_interim("_world")
    bounds = load_interim("fr_boundaries")
    aav_payload = load_interim_payload("insee_aav")
    aav = aav_payload["data"]
    t = load_tables()
    proj = MapProjection(**world["projection"])
    grid = HexGrid(**world["grid"])
    owner = world["owner"]

    state_index = {code: i for i, code in enumerate(world["states"])}
    mairies = bounds["mairies"]
    commune_pop = {code: r.get("POP_2023") or 0 for code, r in t["comparateur"]["COM"].items()}
    commune_epci = {c["code"]: c["epci"] for c in bounds["communes"]}
    epci_pop: Counter = Counter()
    for com, e in commune_epci.items():
        if e:
            epci_pop[e] += commune_pop.get(com, 0)
    shares = gdp_share()

    members: dict[str, list[dict]] = {}
    for c in aav["communes"]:
        if c["aav"] != "000" and c["dep"] in state_index:
            members.setdefault(c["aav"], []).append(c)
    aav_of_commune = {c["code"]: code for code, cs in members.items() for c in cs}

    cities = []
    no_mairie, no_gdp = [], []
    for code, cs in members.items():
        area = aav["areas"][code]
        if not t["comparateur"]["AAV2020"].get(code, {}).get("POP_2023"):
            continue
        centre = next((c for c in cs if c["cat"] == "11"), None)
        # Cross-border areas (Genève, Bâle, Luxembourg, Monaco, Sarrebruck…) have their commune-centre abroad: the
        # banner goes on the most populous French commune and carries its name.
        abroad = centre is None
        if abroad:
            centre = max(cs, key=lambda c: commune_pop.get(c["code"], 0))
        if centre["code"] in mairies:
            lon, lat = mairies[centre["code"]]
        else:
            no_mairie.append(area["name"])
            continue
        x, y = proj(lon, lat)
        deps = Counter()
        for c in cs:
            deps[c["dep"]] += commune_pop.get(c["code"], 0)
        epci_in: Counter = Counter()
        for c in cs:
            if commune_epci.get(c["code"]):
                epci_in[commune_epci[c["code"]]] += commune_pop.get(c["code"], 0)
        epcis = sorted(e for e, p in epci_in.items() if epci_pop[e] and p / epci_pop[e] >= 0.5)
        gdp = shares.communes_profile([c["code"] for c in cs])
        if gdp["total"] is None:
            no_gdp.append(area["name"])
        g, years = growth("AAV2020", code, t)
        name = centre["name"] if abroad else area["name"].replace(" (partie française)", "").split(" - ")[0]
        cities.append(
            {
                "id": code,
                "name": name,
                "full": full_name(area["name"]),
                "states": [d for d, _ in deps.most_common()],
                "metro": area["band"] >= "2",
                "capital": code == CAPITAL_AAV,
                "centre": centre["name"],
                # The commune itself (what "Poitiers" means to most people), beside the aire d'attraction's total.
                "commune_population": t["comparateur"]["COM"].get(centre["code"], {}).get("POP_2023"),
                "cross_border": "(partie française)" in area["name"],
                "centre_code": centre["code"],
                "band": aav["bands"].get(area["band"]),
                "x": round(x, 1),
                "y": round(y, 1),
                "cell": grid.cell_at(x, y),
                **economy("AAV2020", code, t, gdp),
                "growth": g,
                "growth_years": years,
                "counties": epcis,
                "communes": len(cs),
                "pop_series": pop_series("AAV2020", code, t),
            }
        )
    cities.sort(key=lambda c: -c["population"])

    # Banner cells: on French land, one city per cell where possible (bigger cities choose first).
    taken: set[int] = set()
    snapped, pulled, moved, shared = [], [], [], []
    for c in cities:
        state = state_index.get(c["states"][0], -1)
        own = {state_index.get(d, -1) for d in c["states"]}
        cell = c["cell"]
        if cell < 0 or owner[cell] < 0:
            cell = nearest_land(grid, owner, max(cell, 0), c["x"], c["y"], state)
            snapped.append(c["name"])
        elif owner[cell] not in own:
            alt = free_cell(grid, owner, taken, cell, c["x"], c["y"], state)
            if alt is not None and owner[alt] == state:
                cell = alt
                pulled.append(c["name"])
        if cell in taken:
            alt = free_cell(grid, owner, taken, cell, c["x"], c["y"], state)
            if alt is None:
                shared.append(c["name"])
            else:
                cell = alt
                moved.append(c["name"])
        taken.add(cell)
        c["cell"] = cell

    feet = footprints(world, aav_of_commune)
    own_only = []
    for c in cities:
        cells = feet.get(c["id"], set())
        if c["cell"] not in cells:
            if not cells:
                own_only.append(c["name"])
            cells = cells | {c["cell"]}
        c["footprint"] = sorted(cells)
    add_ranks(cities)

    print(f"    {len(cities)} cities ({sum(c['metro'] for c in cities)} of 50,000+)")
    for label, items in (
        ("without a town hall point", no_mairie),
        ("snapped off water/foreign cells", snapped),
        ("pulled back across a département line", pulled),
        ("moved to a free neighbouring cell", moved),
        ("still sharing a cell", shared),
        ("without GDP", no_gdp),
        ("with a one-hex footprint", own_only),
    ):
        if items:
            print(f"    {len(items)} {label}: {', '.join(items[:8])}{' …' if len(items) > 8 else ''}")

    deps = [d["code"] for d in bounds["departements"]]
    nat_gdp = shares._profile({d: 1.0 for d in deps}, {d: {b: 1.0 for b in shares.dep_gva[d]} for d in deps})
    # France entière: metropolitan France and the five overseas départements (Mayotte from its 2017 census).
    nation = economy("FRANCE", "F", t, nat_gdp)
    nation["growth"], nation["growth_years"] = growth("FRANCE", "F", t)
    nation["pop_series"] = pop_series("FRANCE", "F", t)
    # Filosofi (standard of living, poverty) is published for metropolitan France only: the national reference there.
    metro = economy("FRANCE", "FM", t, nat_gdp)
    for k in ("median_income", "poverty"):
        if nation.get(k) is None:
            nation[k] = metro.get(k)
    write_web("cities.json", cities)
    write_web(
        "nation.json",
        {
            "vintage": "Recensement 2023",
            "year": 2023,
            "gdp_vintage": f"Eurostat, PIB par département, {GDP_YEAR}",
            "nation": nation,
            "yields": YIELDS,
            "industries": {k: label for k, (_, label) in INDUSTRIES.items()},
            "gdp_industries": GDP_INDUSTRIES,
        },
    )
