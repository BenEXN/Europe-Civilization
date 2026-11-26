"""Tile resources: the big power plants of the map's countries, placed on the hex map.

Like strategic resources on a Civ tile, but only meaningful sites: each type has a size threshold (stated in its
description). Plants come from powerplantmatching (sources/power_plants.py), placed at their own coordinates: a plant
whose point falls in the sea or across a border is moved to the nearest hex of its own country. Plants of one kind
in the same hex make one site (the units of a nuclear plant, a cascade of hydro stations). Wind, solar and batteries
are counted as clusters: every installation of the hex is summed (German wind turbines are filed one by one), and
offshore wind farms are summed on the coastal hex they are moved to. `types` is listed in rank order (rarest/most
significant first).

Vineyards come from the hexes' land-cover samples (CORINE class 221; `_world.clc`, a nearest-neighbour sample of the
30 m land-cover map since the file's averaged overviews mixed classes up).
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

from ..core.europe import COUNTRIES
from ..core.geo import MapProjection
from ..core.hexgrid import HexGrid
from ..core.paths import WEB_DATA
from ..core.store import load_interim, load_interim_payload, write_web
from .cities import nearest_land

REQUIRES = ["_world", "_places", "power_plants", "cities.json"]
PRODUCES = ["resources.json"]

SITE_MIN = {"nuclear": 0, "pumped_storage": 300, "tidal": 100, "hydro": 300, "coal_plant": 300, "gas_plant": 500,
            "geothermal": 50}  # MW per hex
CLUSTER_MIN = {"wind": 250, "offshore": 200, "solar": 250, "battery": 100}  # MW summed per hex
SNAP_RINGS = {"offshore": 10}  # how far a point may be moved to reach its country's land (default 3 hexes, ~50 km)
DUP_KM = 30  # two sites of one kind and name, filed in two countries this close with capacities within
# DUP_SHARE, are one plant filed twice
DUP_SHARE = 0.03
VINEYARDS = True
VINE_MIN = 0.12  # share of the hex's land in vineyards (17 km hexes dilute a wine district more than France's 12 km)
SRC = "power_plants"
IN_SERVICE = "Only plants in service in 2026 count (those due to close in 2026 say so)."
HEX = "Plants of the same kind in one hex count as one site."
CLUSTER = "Every installation in the hex is added up (wind turbines are often filed one by one)."


def _t(id, name, category, color, unit, description, source=SRC):
    return {"id": id, "name": name, "category": category, "icon": f"r-{id}", "color": color,
            "unit": unit, "description": description, "source": source}


TYPES = [
    _t("nuclear", "Nuclear plant", "energy", "#e8d44d", "MW",
       f"Every nuclear power plant in service; the value is the capacity of its reactors. {IN_SERVICE}"),
    _t("pumped_storage", "Pumped-storage plant", "energy", "#2f7fb8", "MW",
       f"Pumped-storage hydro of at least {SITE_MIN['pumped_storage']} MW per hex: two reservoirs that work as the "
       f"grid's battery. {HEX} {IN_SERVICE}"),
    _t("tidal", "Tidal power station", "energy", "#3f8fd6", "MW",
       f"Tidal power stations of at least {SITE_MIN['tidal']} MW: La Rance, in Brittany, is Europe's only large one."),
    _t("hydro", "Hydroelectric plant", "energy", "#3fa7d6", "MW",
       f"Hydroelectric plants (reservoir and run-of-river) of at least {SITE_MIN['hydro']} MW per hex. {HEX} "
       f"{IN_SERVICE}"),
    _t("coal_plant", "Coal plant", "energy", "#5a5a5a", "MW",
       f"Hard-coal and lignite plants of at least {SITE_MIN['coal_plant']} MW per hex. {HEX} {IN_SERVICE}"),
    _t("gas_plant", "Gas plant", "energy", "#f08a24", "MW",
       f"Natural-gas plants (combined cycles, gas turbines, cogeneration) of at least {SITE_MIN['gas_plant']} MW per "
       f"hex. {HEX} {IN_SERVICE}"),
    _t("geothermal", "Geothermal plant", "energy", "#c0504d", "MW",
       f"Geothermal power plants of at least {SITE_MIN['geothermal']} MW per hex (Tuscany's Larderello field, "
       f"Iceland). {HEX} {IN_SERVICE}"),
    _t("wind", "Wind farms", "energy", "#9fd8cb", "MW",
       f"Onshore wind where a hex adds up to at least {CLUSTER_MIN['wind']} MW, and offshore wind farms (moved to the "
       f"nearest coast of their country) where they add up to at least {CLUSTER_MIN['offshore']} MW on one coastal "
       f"hex. {CLUSTER} {IN_SERVICE}"),
    _t("solar", "Solar parks", "energy", "#ffc93c", "MW",
       f"Ground-mounted solar where a hex adds up to at least {CLUSTER_MIN['solar']} MW (rooftops and installations "
       f"under 1 MW are not counted). {CLUSTER} {IN_SERVICE}"),
    _t("battery", "Battery storage", "energy", "#7bc96f", "MW",
       f"Grid batteries where a hex adds up to at least {CLUSTER_MIN['battery']} MW, counting only installations "
       f"with a commissioning year (from 2012). {CLUSTER}"),
]
WINE = _t("wine", "Vineyards", "agri", "#8e2c55", "% of the land in vines",
          f"Hexes where at least {round(VINE_MIN * 100)}% of the land is vineyards (CORINE class 221), thinned to "
          "about one hex in four on a regular lattice; the value is the vineyard share of the hex's land, in percent.", "corine_eu")
if VINEYARDS:
    TYPES.append(WINE)
RANK = {t["id"]: i for i, t in enumerate(TYPES)}
CLUSTER_LABEL = {"wind": "Wind farms around {}", "offshore": "Offshore wind off {}", "solar": "Solar parks around {}",
                 "battery": "Battery storage at {}"}

_PREFIX = re.compile(r"^(Psw|Pss|Kw|Hkw|Gkw|Rhe|He|Hc|Hpp|Te|Tpp)\s+", re.I)  # plant-type abbreviations
_SUFFIX = re.compile(r"\s+(Phase|Chp|Pss|Ms|Geothermal|Power Plant|Power Station|Solar Farm|Solar Park|"
                     r"Offshore Wind Farm|Offshore Wind Park|Offshore Wind|Wind Farm|Wind Park|Bess)$", re.I)
_UNIT = re.compile(r"\s+(\d+[A-Za-z]?|[IVX]+|[A-D])$")


def clean_name(name: str | None) -> str | None:
    """'Gravelines 1' → 'Gravelines'; 'Belchatow Phase' → 'Belchatow'; 'Rance Tidal Rance Tidal' → 'Rance Tidal';
    'Psw Goldisthal Pss' → 'Goldisthal'; 'Fljótsdalsvirkjun (Kárahnjúkar )' → 'Fljótsdalsvirkjun (Kárahnjúkar)'."""
    if not name:
        return None
    n = re.sub(r"\s+", " ", name).replace("( ", "(").replace(" )", ")").strip()
    m = re.fullmatch(r"(.+?) \1", n)
    if m:
        n = m.group(1)
    n = _PREFIX.sub("", n)
    for _ in range(3):
        n2 = _UNIT.sub("", _SUFFIX.sub("", n)).strip()
        if n2 == n or not n2:
            break
        n = n2
    return n or None


def words(name: str) -> set[str]:
    return {w for w in re.findall(r"\w{4,}", name.lower())}


def site_detail(kind: str, rows: list[dict]) -> str:
    years = sorted(r["since"] for r in rows if r["since"])
    n = len(rows)
    closing = sum(1 for r in rows if r.get("until"))
    if kind == "nuclear":
        text = f"{n} reactor{'s' if n > 1 else ''}" + (f", in service since {years[0]}" if years else "")
    elif n == 1:
        text = f"In service since {years[0]}" if years else "Commissioning year not published"
    else:
        text = f"{n} units in the hex" + (f", the first in service in {years[0]}" if years else "")
    if closing:
        year = next(r["until"] for r in rows if r.get("until"))
        text += f"; due to close in {year}" if closing == n else f"; {closing} of the {n} due to close in {year}"
    return text


def cluster_detail(kind: str, rows: list[dict]) -> str:
    by_name: dict[str, float] = defaultdict(float)
    for r in rows:
        nm = clean_name(r["name"])
        if nm:
            by_name[nm] += r["mw"]
    top = sorted(by_name, key=by_name.get, reverse=True)
    n = len(rows)
    what = "offshore installations" if kind == "offshore" else "installations"
    text = f"{n} {what} in the hex" if n > 1 else f"1 {what[:-1]} in the hex"
    if top:
        named = ", ".join(f"{t} ({round(by_name[t]):,} MW)" for t in top[:2])
        more = f" and {len(top) - 2} more" if len(top) > 2 else ""
        text += f"; the largest: {named}{more}"
    return text


def build() -> None:
    world = load_interim("_world")
    places = load_interim("_places")
    pp_payload = load_interim_payload("power_plants")
    pp = pp_payload["data"]
    cities = json.loads((WEB_DATA / "cities.json").read_text())
    proj = MapProjection(**world["projection"])
    grid = HexGrid(**world["grid"])
    owner, states = world["owner"], world["states"]
    state_index = {code: i for i, code in enumerate(states)}

    city_of: dict[int, str] = {}  # cell → the most populous city whose footprint holds it
    for c in sorted(cities, key=lambda c: -(c.get("population") or 0)):
        for cell in c.get("footprint") or [c["cell"]]:
            city_of.setdefault(cell, c["id"])
    pcol = {k: i for i, k in enumerate(places["columns"])}
    place_of: dict[int, tuple[float, str]] = {}  # cell → (population, name) of its most populous local unit
    for r in places["rows"]:
        cell, pop = r[pcol["cell"]], r[pcol["pop"]] or 0
        if cell is not None and cell >= 0 and (cell not in place_of or pop > place_of[cell][0]):
            place_of[cell] = (pop, r[pcol["name"]])

    def place_name(cell: int) -> str | None:
        """The most populous local unit of the hex, else of its neighbours (a coastal hex can hold none)."""
        for ring in ([cell], grid.neighbours(cell)):
            best = max((n for n in ring if n in place_of), key=lambda n: place_of[n][0], default=None)
            if best is not None:
                return place_of[best][1]
        return None

    cols = pp["columns"]
    lost = Counter()
    groups: dict[tuple, list] = defaultdict(list)
    for raw in pp["rows"]:
        r = dict(zip(cols, raw))
        si = state_index.get(r["country"])
        if si is None:
            continue
        x, y = proj(r["lon"], r["lat"])
        cell = grid.cell_at(x, y)
        if cell >= 0 and owner[cell] != si:
            cell = nearest_land(grid, owner, cell, x, y, si, SNAP_RINGS.get(r["kind"], 3))
        if cell < 0:
            lost[r["kind"]] += 1
            continue
        r["x"], r["y"] = x, y
        groups[(r["kind"], cell)].append(r)
    if lost:
        print(f"    {sum(lost.values())} plants off the map or too far from their country's land: {dict(lost)}")

    def item(type_, name, x, y, cell, value, detail, state):
        return {"type": type_, "name": name, "x": round(x, 1), "y": round(y, 1), "cell": cell,
                "value": round(value) if type_ != "wine" else value, "detail": detail, "state": state,
                "cbsa": city_of.get(cell)}

    items = []
    sites = []
    for (kind, cell), rows in groups.items():
        mw = sum(r["mw"] for r in rows)
        if kind in SITE_MIN:
            if mw < SITE_MIN[kind] or mw <= 0:
                continue
            rows.sort(key=lambda r: -r["mw"])
            top = rows[0]
            state = Counter({r["country"]: 0 for r in rows})
            for r in rows:
                state[r["country"]] += r["mw"]
            name = clean_name(top["name"]) or place_name(cell) or "Power plant"
            sites.append(item(kind, name, top["x"], top["y"], cell, mw, site_detail(kind, rows),
                              state.most_common(1)[0][0]))
        elif kind in CLUSTER_MIN:
            if mw < CLUSTER_MIN[kind]:
                continue
            state = Counter()
            for r in rows:
                state[r["country"]] += r["mw"]
            x, y = grid.center(*grid.col_row(cell))
            where = place_name(cell) or COUNTRIES[state.most_common(1)[0][0]][0]
            items.append(item("wind" if kind == "offshore" else kind, CLUSTER_LABEL[kind].format(where), x, y, cell,
                              mw, cluster_detail(kind, rows), state.most_common(1)[0][0]))
    # One plant filed twice (Vianden, in the Luxembourg and the German registers): same kind and name word, two
    # countries, nearly the same capacity, a few km apart. Keep the copy whose country owns its hex.
    sites.sort(key=lambda s: -s["value"])
    merged = []
    kept: list[dict] = []
    for s in sites:
        twin = next((k for k in kept if k["type"] == s["type"] and k["state"] != s["state"]
                     and abs(k["value"] - s["value"]) <= DUP_SHARE * k["value"] and words(k["name"]) & words(s["name"])
                     and math.dist((k["x"], k["y"]), (s["x"], s["y"])) <= DUP_KM * proj.scale), None)
        if twin is None:
            kept.append(s)
            continue
        merged.append(f"{s['name']} ({s['state']}) = {twin['name']} ({twin['state']})")
        if states[owner[s["cell"]]] == s["state"] and states[owner[twin["cell"]]] != twin["state"]:
            kept[kept.index(twin)] = s
    if merged:
        print(f"    {len(merged)} plant(s) filed twice merged: {'; '.join(merged)}")
    items += kept

    if VINEYARDS:
        # On a lattice (axial q and r both even) so a wine region shows as a field of icons, not a wall; named after
        # the NUTS 3 region.
        wj = WEB_DATA / "world.json"
        names = {c["geoid"]: c["name"] for c in json.loads(wj.read_text())["counties"]} if wj.exists() else {}
        for i, counts in enumerate(world["clc"]):
            if owner[i] < 0 or not counts:
                continue
            land = sum(n for code, n in counts.items() if not str(code).startswith("5"))
            share = counts.get("221", 0) / land if land else 0
            col, row = grid.col_row(i)
            q = col - (row - (row & 1)) // 2
            if share < VINE_MIN or q % 2 or row % 2:
                continue
            x, y = grid.center(col, row)
            region = world["counties"][world["county"][i]] if world["county"][i] >= 0 else None
            items.append(item("wine", f"Vineyards ({names.get(region) or region or states[owner[i]]})", x, y, i,
                              round(share * 100), f"{round(share * 100)}% of the land in vines", states[owner[i]]))

    items.sort(key=lambda it: (RANK[it["type"]], -it["value"]))
    national = {t["id"]: {"count": 0, "value": 0, "unit": t["unit"]} for t in TYPES}
    by_state: dict[str, dict] = defaultdict(dict)
    for it in items:
        n = national[it["type"]]
        n["count"] += 1
        n["value"] += it["value"]
        s = by_state[it["state"]].setdefault(it["type"], {"count": 0, "value": 0, "unit": n["unit"]})
        s["count"] += 1
        s["value"] += it["value"]
    if "wine" in national:
        national["wine"]["value"] = None
        for s in by_state.values():
            if "wine" in s:
                s["wine"]["value"] = None
    print(f"    {len(items)} resources: " + ", ".join(f"{t} {national[t]['count']}" for t in national))
    write_web("resources.json", {
        "types": TYPES,
        "items": items,
        "summary": {
            "note": "Totals of the mapped sites only (each type has its own threshold): not the total installed "
                    "capacity of a country.",
            "national": national,
            "states": dict(sorted(by_state.items())),
        },
    })


# ------------------------------------------------------------------ check


def check(web_dir: Path) -> list[tuple[str, str]]:
    path = Path(web_dir) / "resources.json"
    if not path.exists():
        return [("NOTE", "resources.json not built (optional; run: build resources)")]
    doc = json.loads(path.read_text())
    out: list[tuple[str, str]] = []
    for k in ("types", "items", "summary"):
        if k not in doc:
            out.append(("FAIL", f"resources.json lacks '{k}'"))
    if out:
        return out
    types = {t.get("id"): t for t in doc["types"]}
    bad_types = [t.get("id") for t in doc["types"]
                 if not {"id", "name", "category", "icon", "color", "unit", "description", "source"} <= t.keys()
                 or t["icon"] != f"r-{t['id']}"]
    if bad_types:
        out.append(("FAIL", f"resources.json types malformed (keys or icon r-<id>): {bad_types}"))
    wpath = Path(web_dir) / "world.json"
    world = json.loads(wpath.read_text()) if wpath.exists() else None
    owner = (world or {}).get("owner") or []
    abbrs = {s.get("abbr") for s in (world or {}).get("states", [])}
    cpath = Path(web_dir) / "cities.json"
    city_ids = {c.get("id") for c in json.loads(cpath.read_text())} if cpath.exists() else None
    keys = {"type", "name", "x", "y", "cell", "value", "detail", "state", "cbsa"}
    probs = Counter()
    for it in doc["items"]:
        if not isinstance(it, dict) or not keys <= it.keys():
            probs["missing keys"] += 1
            continue
        if it["type"] not in types:
            probs["unknown type"] += 1
        if not isinstance(it["cell"], int) or (owner and not (0 <= it["cell"] < len(owner) and owner[it["cell"]] >= 0)):
            probs["cell not a map-country land hex"] += 1
        if abbrs and it["state"] not in abbrs:
            probs["state not a world.json country"] += 1
        if it["cbsa"] is not None and city_ids is not None and it["cbsa"] not in city_ids:
            probs["cbsa not a cities.json id"] += 1
        if not (isinstance(it["value"], (int, float)) or (it["value"] is None)):
            probs["value not a number"] += 1
        if not isinstance(it["name"], str) or not it["name"]:
            probs["no name"] += 1
    if probs:
        out.append(("FAIL", f"resources.json items: {dict(probs)}"))
    per_type = Counter(it.get("type") for it in doc["items"])
    nat = doc["summary"].get("national", {})
    wrong = [t for t in types if nat.get(t, {}).get("count") != per_type.get(t, 0)]
    if set(nat) != set(types) or wrong:
        out.append(("FAIL", f"resources.json summary.national does not match the items ({wrong or 'type set'})"))
    if not out:
        countries = len({it["state"] for it in doc["items"]})
        mw = sum(it["value"] or 0 for it in doc["items"] if types.get(it["type"], {}).get("unit") == "MW")
        out.append(("PASS", f"resources.json: {len(doc['items'])} sites in {countries} countries, "
                            f"{round(mw / 1000)} GW mapped ({', '.join(f'{t} {n}' for t, n in per_type.most_common())})"))
    size = path.stat().st_size
    if size > 300_000:
        out.append(("WARN", f"resources.json is {size / 1e3:.0f} kB (keep it under ~300 kB)"))
    return out
