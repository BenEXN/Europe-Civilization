"""communes.json: every local administrative unit (LAU 2021: communes, Gemeinden, comuni…) of the map's countries,
plus GeoNames towns where GISCO has no local units, for the search box and its place card (column-oriented).

* `code` GISCO id (country + national LAU code, or GN_<geonameid>), `dep` country code, `region` NUTS 3 code,
  `pop` 2021 census population, `cell` the hex of its centre (or the nearest hex of its country), `aav` the
  cities.json id of its urban area (or null), `density` people per km² (null for GeoNames towns), `x`, `y` its centre
  in map units (the map's Places layer draws every one of them as you zoom in).
"""

from __future__ import annotations

import json

from ..core.paths import WEB_DATA
from ..core.store import load_interim, write_web

REQUIRES = ["_places", "cities.json"]
PRODUCES = ["communes.json"]

COLUMNS = ["code", "name", "dep", "pop", "cell", "aav", "density", "region", "x", "y"]


def build() -> None:
    places = load_interim("_places")
    city_ids = {c["id"] for c in json.loads((WEB_DATA / "cities.json").read_text())}
    rows = []
    for code, name, country, pop, area, x, y, cell, reg, fua in places["rows"]:
        rows.append([code, name, country, round(pop) if pop is not None else None, cell,
                     fua if fua in city_ids else None,
                     round(pop / area) if pop and area else None, reg, round(x), round(y)])
    rows.sort(key=lambda r: (r[2], r[1]))
    write_web("communes.json", {"version": 1, "vintage": "GISCO LAU 2021 (census 2021), GeoNames",
                                "columns": COLUMNS, "rows": rows})
    print(f"    {len(rows)} places; {sum(1 for r in rows if r[5])} in an urban area")
