"""communes.json (lazy): every commune of metropolitan France for the search box and its commune card.

Column-oriented like counties.json: code, name, département, population 2023, map hex (the hex of its town hall,
or the nearest French land hex), aire d'attraction (cities.json id or null), intercommunalité, and a few facts
for the card: density, growth 2017-2023, median standard of living, CatNat decrees since 2000, the 2022
presidential second round and abstention. Null means no published figure.
"""

from __future__ import annotations

import json

from ..core.geo import MapProjection
from ..core.hexgrid import HexGrid
from ..core.paths import WEB_DATA
from ..core.store import load_interim, write_web
from .cities import nearest_land
from .lenses import abstention, ratio, vote_share

REQUIRES = ["_world", "fr_boundaries", "insee_aav", "insee_comparateur", "catnat", "presidentielle_2022", "cities.json"]
PRODUCES = ["communes.json"]

COLUMNS = ["code", "name", "dep", "pop", "cell", "aav", "density", "growth", "income", "catnat", "vote_macron",
           "abstention"]


def build() -> None:
    world = load_interim("_world")
    bounds = load_interim("fr_boundaries")
    aav = {c["code"]: c["aav"] for c in load_interim("insee_aav")["communes"]}
    com = load_interim("insee_comparateur")["levels"]["COM"]
    catnat = load_interim("catnat")["communes"]
    pr = load_interim("presidentielle_2022")["communes"]
    city_ids = {c["id"] for c in json.loads((WEB_DATA / "cities.json").read_text())}
    proj = MapProjection(**world["projection"])
    grid = HexGrid(**world["grid"])
    owner = world["owner"]
    state_index = {code: i for i, code in enumerate(world["states"])}
    rows, no_cell = [], 0
    for c in sorted(bounds["communes"], key=lambda c: c["code"]):
        r = com.get(c["code"], {})
        pt = bounds["mairies"].get(c["code"])
        cell = None
        if pt:
            x, y = proj(*pt)
            k = grid.cell_at(x, y)
            cell = k if k >= 0 and owner[k] >= 0 else nearest_land(grid, owner, max(k, 0), x, y, state_index.get(c["dep"], -1))
            cell = cell if cell is not None and cell >= 0 else None
        no_cell += cell is None
        pop, area = r.get("POP_2023"), r.get("SUP_2023")
        g = ratio(r.get("POP_2023"), r.get("POP_2017"))
        a = aav.get(c["code"])
        v = pr.get(c["code"])
        rows.append([
            c["code"], c["name"], c["dep"], pop, cell, a if a in city_ids else None,
            round(pop / area) if pop and area else None,
            round(g - 1, 3) if g is not None else None,
            r.get("MED_SL_2023"),
            catnat.get(c["code"], {}).get("total", 0) if r else None,
            round(vote_share(v), 3) if v and vote_share(v) is not None else None,
            round(abstention(v), 3) if v and abstention(v) is not None else None,
        ])
    print(f"    {len(rows)} communes; {no_cell} without a hex")
    write_web("communes.json", {"version": 1, "vintage": "Recensement 2023, Filosofi 2023, GASPAR, présidentielle 2022",
                                "columns": COLUMNS, "rows": rows})
