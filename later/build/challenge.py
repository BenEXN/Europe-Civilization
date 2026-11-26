"""defi.json (server only): the pool of communes for the daily challenge ("Où est cette commune ?").

Communes of metropolitan France whose name is not already written on the map (no aire d'attraction carries it),
in three tiers by population, with their town hall in map units. The site does not publish this file: server/api.py
reads it and draws each day's communes from it with a secret key (see docs/DATA_CONTRACTS.md).
"""

from __future__ import annotations

import json
import random
import re
import unicodedata

from ..core.geo import SCALE, MapProjection
from ..core.hexgrid import HexGrid
from ..core.paths import WEB_DATA
from ..core.store import load_interim, write_web

REQUIRES = ["_world", "fr_boundaries", "insee_comparateur", "cities.json"]
PRODUCES = ["defi.json"]

START = "2026-11-26"
PATTERN = ["facile", "facile", "moyen", "moyen", "difficile"]
TIERS = {"facile": (20_000, None), "moyen": (5_000, 20_000), "difficile": (1_500, 5_000)}
SEED = 1789
COLUMNS = ["code", "name", "dep", "pop", "x", "y"]


def norm(s: str) -> str:
    s = unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def build() -> None:
    world = load_interim("_world")
    bounds = load_interim("fr_boundaries")
    com = load_interim("insee_comparateur")["levels"]["COM"]
    cities = json.loads((WEB_DATA / "cities.json").read_text())
    on_map = set()
    for c in cities:
        for part in re.split(r"\s+-\s+|/", c["name"]):
            on_map.add(norm(part))
    proj = MapProjection(**world["projection"])
    owner = world["owner"]
    grid = HexGrid(**world["grid"])
    tiers = {t: [] for t in TIERS}
    for c in sorted(bounds["communes"], key=lambda c: c["code"]):
        pop, pt = com.get(c["code"], {}).get("POP_2023"), bounds["mairies"].get(c["code"])
        if not pop or not pt or norm(c["name"]) in on_map or c["dep"].startswith("97"):
            continue  # overseas communes sit in insets drawn at other scales: distances there mean nothing
        x, y = proj(*pt)
        k = grid.cell_at(x, y)
        if k < 0 or owner[k] < 0:  # town hall off the French land hexes (islands, coast): skip, it would look wrong
            continue
        for t, (lo, hi) in TIERS.items():
            if pop >= lo and (hi is None or pop < hi):
                tiers[t].append([c["code"], c["name"], c["dep"], pop, round(x), round(y)])
    rng = random.Random(SEED)
    for rows in tiers.values():
        rng.shuffle(rows)
    print("    " + ", ".join(f"{t} {len(r)}" for t, r in tiers.items()) + f"; {len(on_map)} names already on the map")
    write_web("defi.json", {"version": 1, "start": START, "pattern": PATTERN, "columns": COLUMNS,
                            "km_per_unit": round(1 / SCALE, 6), "tiers": tiers})
