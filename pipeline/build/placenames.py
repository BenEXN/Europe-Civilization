"""placenames/: the names the map's Places layer writes, cut so a phone never loads the 126,000 rows at once.

* placenames/top.json: every place of TOP_MIN people or more (all the map needs until it is zoomed in close), with
  the list of tiles below.
* placenames/t<col>_<row>.json: the smaller places, by square tile of TILE map units; the layer loads a tile only
  when it is zoomed in far enough to name them and the tile is on screen.

Columns: code (communes.json `code`, for the place card), name, dep (country), pop, x, y (map units). Rows are
sorted by population, largest first.
"""

from __future__ import annotations

import json
import math

from ..core.paths import WEB_DATA
from ..core.store import write_web

REQUIRES = ["communes.json"]
PRODUCES = ["placenames/top.json"]

TOP_MIN = 4000  # people
TILE = 500  # map units (200 km)
COLUMNS = ["code", "name", "dep", "pop", "x", "y"]


def build() -> None:
    d = json.loads((WEB_DATA / "communes.json").read_text())
    col = {c: k for k, c in enumerate(d["columns"])}
    top, tiles = [], {}
    for r in d["rows"]:
        x, y = r[col["x"]], r[col["y"]]
        if x is None or y is None:
            continue
        row = [r[col["code"]], r[col["name"]], r[col["dep"]], r[col["pop"]] or 0, x, y]
        if row[3] >= TOP_MIN:
            top.append(row)
        else:
            tiles.setdefault(f"{math.floor(x / TILE)}_{math.floor(y / TILE)}", []).append(row)
    out = WEB_DATA / "placenames"
    out.mkdir(parents=True, exist_ok=True)
    keep = {"top.json"} | {f"t{k}.json" for k in tiles}
    for old in out.glob("*.json"):
        if old.name not in keep:
            old.unlink()
    for k, rows in sorted(tiles.items()):
        rows.sort(key=lambda r: -r[3])
        text = json.dumps({"columns": COLUMNS, "rows": rows}, separators=(",", ":"), ensure_ascii=False)
        (out / f"t{k}.json").write_text(text, encoding="utf-8")
    top.sort(key=lambda r: -r[3])
    write_web("placenames/top.json", {"version": 1, "columns": COLUMNS, "top_min": TOP_MIN, "tile": TILE,
                                      "tiles": sorted(tiles), "rows": top})
    sizes = sorted(len(v) for v in tiles.values())
    print(f"    {len(top)} places of {TOP_MIN}+ in top.json; {sum(sizes)} smaller ones in {len(tiles)} tiles "
          f"(largest {sizes[-1] if sizes else 0} rows)")
