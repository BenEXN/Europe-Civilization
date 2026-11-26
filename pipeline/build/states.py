"""Countries (the map's "states"): the same economic profile as a city (Eurostat), ranks, and a label anchor.

Also land-cover shares over the country's hexes and the MW of the power plants mapped in resources.json (only the
sites above each type's threshold, so not the country's total capacity).

Ranks are among the 37 countries of the map (1 = largest). The label anchor is the country's "pole of
inaccessibility" on the hex map (the hex farthest from the border, by hex steps, or one nearly as deep that fits a
bigger name), turned along the country's long axis when that helps, and sized to fit the run of its own hexes through
the anchor. `size` assumes ~0.6 em per character.
"""

from __future__ import annotations

import json
import math
from collections import deque

from ..core.europe import COUNTRIES, EFTA, EU
from ..core.hexgrid import HexGrid
from ..core.paths import WEB_DATA
from ..core.store import load_interim, write_web
from .yields import YIELDS, Stats, economy, growth_of, nuts2_rates, region_profile

REQUIRES = ["_world", "_places", "eurostat"]
PRODUCES = ["states.json"]

MIN_LABEL_KM, MAX_LABEL_KM = 14.0, 240.0  # suggested font height range, map units


def label_anchor(grid: HexGrid, owner: list[int], s: int, name: str) -> dict | None:
    """{x, y, angle, size} for state index `s`, or None if it owns no hex (e.g. DC).

    angle: degrees, clockwise on screen (y down), in (-90, 90]. size: suggested font height in map km.
    """
    cells = [i for i, o in enumerate(owner) if o == s]
    if not cells:
        return None
    # Multi-source BFS from the border hexes inward.
    dist = {}
    queue = deque()
    for c in cells:
        nb = grid.neighbours(c)
        if len(nb) < 6 or any(owner[n] != s for n in nb):
            dist[c] = 0
            queue.append(c)
    while queue:
        c = queue.popleft()
        for n in grid.neighbours(c):
            if owner[n] == s and n not in dist:
                dist[n] = dist[c] + 1
                queue.append(n)
    pts = {c: grid.center(*grid.col_row(c)) for c in cells}
    mx = sum(p[0] for p in pts.values()) / len(cells)
    my = sum(p[1] for p in pts.values()) / len(cells)

    # Principal axis of the hex centres. Labels stay horizontal unless tilting them
    # along a clearly elongated state (at most 45°) allows a much bigger name.
    sxx = sum((p[0] - mx) ** 2 for p in pts.values())
    syy = sum((p[1] - my) ** 2 for p in pts.values())
    sxy = sum((p[0] - mx) * (p[1] - my) for p in pts.values())
    theta = 0.5 * math.atan2(2 * sxy, sxx - syy)  # (-90°, 90°], clockwise on screen
    angles = [0.0] + ([theta] if 1 <= abs(math.degrees(theta)) <= 45 else [])
    step = grid.radius / 4

    def reach(x: float, y: float, ux: float, uy: float) -> float:
        """Distance (km) from (x, y) along (ux, uy) before leaving the state's hexes."""
        t = 0.0
        while True:
            c = grid.cell_at(x + (t + step) * ux, y + (t + step) * uy)
            if c < 0 or owner[c] != s:
                return t + step / 2
            t += step

    def fit(c: int, t: float) -> float:
        """Font height (km) for a label centred on hex c at angle t: ~0.6 em per character
        over 90% of the local run through c, and no taller than 80% of the local breadth.
        The run is then re-measured along the label's top and bottom edges (twice), so the
        whole box, not just its centre line, stays inside the state."""
        (x, y), ux, uy = pts[c], math.cos(t), math.sin(t)
        across = 2 * min(reach(x, y, -uy, ux), reach(x, y, uy, -ux))
        h, offsets = 0.8 * across, [0.0]
        for _ in range(3):
            along = min(
                2 * min(reach(x - o * uy, y + o * ux, ux, uy), reach(x - o * uy, y + o * ux, -ux, -uy))
                for o in offsets
            )
            h = min(h, 0.9 * along / (0.6 * max(len(name), 4)))
            offsets = [0.0, h / 2, -h / 2]
        return h

    # Candidates: the pole of inaccessibility and hexes nearly as deep; pick the one (and angle)
    # that fits the biggest label, a tilted label only if it is 25% bigger than a flat one.
    far = max(dist.values())
    best = None
    for c in cells:
        if dist[c] < far - 1:
            continue
        for t in angles:
            size = fit(c, t) / (1.25 if t else 1.0)
            score = (round(size), -math.hypot(pts[c][0] - mx, pts[c][1] - my))
            if best is None or score > best[0]:
                best = (score, c, t, size * (1.25 if t else 1.0))
    _, pole, angle, size = best
    px, py = pts[pole]
    return {
        "x": round(px, 1),
        "y": round(py, 1),
        "angle": round(math.degrees(angle), 1),
        "size": round(max(MIN_LABEL_KM, min(MAX_LABEL_KM, size)), 1),
    }


PCT_KEYS = ["forest", "crop", "pasture", "grass", "shrub", "wetland", "developed"]
ENERGY_NOTE = ("Only the power plants and wind or solar clusters mapped as resources, each above its type's threshold, "
               "are counted: this is not the country's total installed capacity.")


def land_shares(world: dict, s: int) -> dict | None:
    """Mean world `pct` (0..100) over the state's cells with land-cover samples, as 0..1 fractions."""
    pct, cover, owner = world.get("pct"), world.get("cover"), world["owner"]
    if not pct or not cover:
        return None
    cells = [i for i, o in enumerate(owner) if o == s and cover[i]]
    if not cells:
        return None
    return {k: round(sum(pct[k][i] for i in cells) / len(cells) / 100, 3) for k in PCT_KEYS}


def energy_by_state() -> dict[str, dict] | None:
    """abbr → {unit, total, by_type, sites, note} summed from resources.json items of every MW type
    (states without a mapped site get zeros under "", the default row); None if resources.json is not built."""
    path = WEB_DATA / "resources.json"
    if not path.exists():
        return None
    res = json.loads(path.read_text())
    mw_types = [t["id"] for t in res["types"] if t["unit"] == "MW"]
    mw: dict[str, dict] = {}
    sites: dict[str, dict] = {}
    for it in res["items"]:
        if it["type"] in mw_types and it.get("state"):
            mw.setdefault(it["state"], dict.fromkeys(mw_types, 0))[it["type"]] += it["value"] or 0
            sites.setdefault(it["state"], dict.fromkeys(mw_types, 0))[it["type"]] += 1
    out = {}
    for abbr in ["", *mw]:
        by_type = {k: round(v) for k, v in mw.get(abbr, dict.fromkeys(mw_types, 0)).items()}
        out[abbr] = {"unit": "MW", "total": sum(by_type.values()), "by_type": by_type,
                     "sites": sites.get(abbr, dict.fromkeys(mw_types, 0)), "note": ENERGY_NOTE}
    return out


def build() -> None:
    world = load_interim("_world")
    places = load_interim("_places")
    s = Stats(world["counties"], places["region_pop"])
    grid = HexGrid(**world["grid"])
    owner = world["owner"]
    energy = energy_by_state()
    if energy is None:
        print("    resources.json not built yet: energy left null")
    states = []
    for i, code in enumerate(world["states"]):
        name, capital, region = COUNTRIES[code]
        p = region_profile(s, code)
        rates = nuts2_rates(s, code)
        econ = economy(p, rates, s, median_age=s.latest("medage3", "MEDAGEPOP", code)[1])
        g, years = growth_of(p, s)
        states.append({
            "fips": code,
            "abbr": code,
            "name": name,
            "region": region,
            "capital": capital,
            "membership": "EU" if code in EU else "EFTA" if code in EFTA else "Candidate" if code != "XK" else "Potential candidate",
            **econ,
            "growth": g,
            "growth_years": years if g is not None else None,
            "pop_series": p["series"] or None,
            "ranks": {},
            "label": label_anchor(grid, owner, i, name),
            "land": land_shares(world, i),
            "energy": dict(energy.get(code) or energy[""]) if energy is not None else None,
        })
    for key in [y["key"] for y in YIELDS]:
        ranked = sorted((st for st in states if st["yields"][key] is not None), key=lambda st: -st["yields"][key])
        for r, st in enumerate(ranked, 1):
            st["ranks"][key] = r
        for st in states:
            st["ranks"].setdefault(key, None)
    write_web("states.json", states)
    missing = {k: [st["abbr"] for st in states if st.get(k) is None] for k in ("population", "gdp", "unemployment")}
    print(f"    {len(states)} countries; missing: {missing}")
