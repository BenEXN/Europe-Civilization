"""defi.json (server only): the pool of places for the daily challenge ("Where is this place?").

GeoNames towns of the map's countries (their international names, in Latin letters; whole towns, not city districts)
whose name is not already written on the map (no city banner carries it), outside the insets (drawn at other scales,
where distances mean nothing), in three tiers by population, with their position in map units. The site does not publish this file: server/api.py reads it and draws each day's
places from it with a secret key (see docs/DATA_CONTRACTS.md).
"""

from __future__ import annotations

import json
import random
import re
import unicodedata

from ..core.geo import SCALE, MapProjection
from ..core.paths import WEB_DATA
from ..core.store import load_interim, write_web

REQUIRES = ["_world", "geonames", "cities.json"]
TOWN_CODES = {"PPL", "PPLA", "PPLA2", "PPLA3", "PPLA4", "PPLC", "PPLS", "PPLF", "PPLG"}
PRODUCES = ["defi.json"]

START = "2026-11-26"
PATTERN = ["facile", "facile", "moyen", "moyen", "difficile"]  # tier keys are part of the API: easy, medium, hard
TIERS = {"facile": (60_000, None), "moyen": (20_000, 60_000), "difficile": (8_000, 20_000)}
SEED = 1957
COLUMNS = ["code", "name", "dep", "pop", "x", "y"]


def norm(s: str) -> str:
    s = unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def build() -> None:
    world = load_interim("_world")
    towns = load_interim("geonames")["places"]
    grid_owner = world["owner"]
    cities = json.loads((WEB_DATA / "cities.json").read_text())
    on_map = set()
    for c in cities:
        for name in (c["name"], c.get("local_name") or ""):
            for part in [name] + re.split(r"\s+-\s+|/", name):
                if part:
                    on_map.add(norm(part))
    proj = MapProjection(**world["projection"])
    tiers = {t: [] for t in TIERS}
    from ..core.hexgrid import HexGrid
    grid = HexGrid(**world["grid"])
    states = world["states"]
    for t in towns:
        if t["code"] not in TOWN_CODES or norm(t["name"]) in on_map or re.search(r"\d", t["name"]):
            continue
        x, y = proj(t["lon"], t["lat"])
        cell = grid.cell_at(x, y)
        if proj.frame_of(x, y) is not None or cell < 0 or grid_owner[cell] < 0 or states[grid_owner[cell]] != t["country"]:
            continue  # off its own country's hexes (islands, coasts, border towns): it would look wrong
        for tier, (lo, hi) in TIERS.items():
            if t["pop"] >= lo and (hi is None or t["pop"] < hi):
                tiers[tier].append([f"GN{t['id']}", t["name"], t["country"], t["pop"], round(x), round(y)])
    rng = random.Random(SEED)
    for rows in tiers.values():
        rows.sort()
        rng.shuffle(rows)
    print("    " + ", ".join(f"{t} {len(r)}" for t, r in tiers.items()) + f"; {len(on_map)} names already on the map")
    write_web("defi.json", {"version": 1, "start": START, "pattern": PATTERN, "columns": COLUMNS,
                            "km_per_unit": round(1 / SCALE, 6), "tiers": tiers})
