"""Trade routes: the largest freight flows between regions, drawn as caravan routes between their biggest cities.

The ministry's national flow files (`freight` interim) give 2019 freight between NUTS 2 regions (the 22 former
régions of metropolitan France, and neighbouring regions and countries) by road (tonne-km, French-flagged lorries),
rail and inland waterways (tonnes and tonne-km). Here:

* A zone is one of the 22 regions; its départements come from the Eurostat NUTS 3 codes (a département's NUTS 3 code
  starts with its region's NUTS 2 code). Each cities.json city joins the zone of its main département.
* A route is a pair of different zones whose anchors are at least MIN_KM apart, both directions summed; the TOP_N
  largest by tonne-km (road + rail + waterway) are kept. Tonne-km is the measure all three modes publish (the road
  file has no tonnes), so it weighs long hauls more than short ones.
* Rail values under statistical secrecy are not published: they count as nothing here, so rail is understated.

Each zone is anchored on its biggest city's banner cell. Each route has a `path` of neighbouring cells along the road
links in infrastructure.json (motorways preferred): the files say where freight starts and ends, not which way it
went, so the path is a drawing aid, not data.
"""

from __future__ import annotations

import heapq
import json
import math
from collections import defaultdict
from pathlib import Path

from ..core.hexgrid import HexGrid
from ..core.paths import WEB_DATA
from ..core.store import load_interim, load_interim_payload, write_web
from .yields import nuts3_of_dep

REQUIRES = ["_world", "freight", "fr_boundaries", "eurostat_gdp", "cities.json", "infrastructure.json"]
PRODUCES = ["trade.json"]

TOP_N = 30
MIN_KM = 90  # real km between the two anchors (keeps the Seine axis Paris – Rouen)
PARTNERS = 5
MODES = [("truck", "Route"), ("rail", "Rail"), ("water", "Voie d'eau")]
STEP_COST = {"interstate": 1.0, "major": 1.4, "rail": 1.8, "land": 4.0, "water": 10.0}
# The flow files' region names, tidied for display.
NAME_FIX = {"Ile-de-France": "Île-de-France", "Nord-Pas de Calais": "Nord-Pas-de-Calais",
            "Centre - Val de Loire": "Centre-Val de Loire", "Provence-Alpes-Côte d’Azur": "Provence-Alpes-Côte d'Azur"}

RULE = (f"Les {TOP_N} plus grands flux de marchandises de 2019 entre deux des 22 anciennes régions de la France "
        "métropolitaine (régions NUTS 2), en tonnes-kilomètres, route, rail et voie d'eau additionnés, les deux sens "
        f"cumulés, entre régions dont les grandes villes sont à au moins {MIN_KM} km l'une de l'autre. La route ne "
        "compte que les camions sous pavillon français (enquête TRM) ; les flux ferroviaires couverts par le secret "
        "statistique ne sont pas publiés et manquent ici.")
PATH_NOTE = ("Les données disent d'où partent et où arrivent les marchandises, pas par où elles passent : la ligne "
             "tracée entre les deux grandes villes est une aide au dessin, pas l'itinéraire réel.")


def is_metro(code: str) -> bool:
    return code.startswith("FR") and len(code) == 4 and not code.startswith("FRY")


# ------------------------------------------------------------------ paths (as in usaciv)


def road_graph(infra: dict | None) -> dict:
    cost = {}
    if not infra:
        return cost
    classes = [c["id"] for c in infra.get("road_classes", [])]
    for a, b, *_ in infra.get("rail", []):
        cost[(a, b)] = STEP_COST["rail"]
    for a, b, cls, *_ in infra.get("roads", []):
        cost[(a, b)] = min(cost.get((a, b), 99), STEP_COST.get(classes[cls] if cls < len(classes) else "major", 1.4))
    return cost


def shortest_path(grid: HexGrid, owner: list, links: dict, src: int, dst: int) -> list[int]:
    """Cheapest chain of neighbouring cells from src to dst (Dijkstra with an A* bound)."""
    def h(c):
        x0, y0 = grid.center(*grid.col_row(c))
        x1, y1 = grid.center(*grid.col_row(dst))
        return math.hypot(x1 - x0, y1 - y0) / (math.sqrt(3) * grid.radius) * STEP_COST["interstate"]

    best = {src: 0.0}
    prev = {}
    heap = [(h(src), 0.0, src)]
    while heap:
        _, d, c = heapq.heappop(heap)
        if c == dst:
            break
        if d > best.get(c, math.inf):
            continue
        for n in grid.neighbours(c):
            key = (c, n) if c < n else (n, c)
            step = links.get(key)
            if step is None:
                step = STEP_COST["land"] if owner[n] >= 0 else STEP_COST["water"]
            nd = d + step
            if nd < best.get(n, math.inf):
                best[n] = nd
                prev[n] = c
                heapq.heappush(heap, (nd + h(n), nd, n))
    if dst not in best:
        return [src, dst] if src == dst else []
    path = [dst]
    while path[-1] != src:
        path.append(prev[path[-1]])
    return path[::-1]


# ------------------------------------------------------------------ flows


def mode_tkm(f: dict) -> dict:
    """Tonne-km by mode for one directed flow (withheld rail counts as 0)."""
    return {"truck": f.get("road_tkm") or 0.0, "rail": f.get("rail_tkm") or 0.0, "water": f.get("water_tkm") or 0.0}


def aggregate(flows: list[dict]):
    """Pair sums between different metropolitan zones, per-zone partner sums, and per-zone totals (tkm)."""
    pair = defaultdict(lambda: {"tkm": defaultdict(float), "tons": 0.0})
    partner = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))
    totals = defaultdict(lambda: defaultdict(float))
    national = defaultdict(float)
    for f in flows:
        o, d = f["o"], f["d"]
        mt = mode_tkm(f)
        v = sum(mt.values())
        mo, md = is_metro(o), is_metro(d)
        if mo and md:
            national["domestic"] += v
            if o == d:
                totals[o]["within"] += v
                continue
            key = (o, d) if o < d else (d, o)
            for m, x in mt.items():
                pair[key]["tkm"][m] += x
                partner[o][d][m] += x
                partner[d][o][m] += x
            pair[key]["tons"] += (f.get("rail_t") or 0.0) + (f.get("water_t") or 0.0)
            totals[o]["other_zones"] += v
            totals[d]["other_zones"] += v
        elif mo:
            totals[o]["export"] += v
            national["export"] += v
        elif md:
            totals[d]["import"] += v
            national["import"] += v
    return pair, partner, totals, national


# ------------------------------------------------------------------ build


def build() -> None:
    world = load_interim("_world")
    grid, owner = HexGrid(**world["grid"]), world["owner"]
    km_per_unit = 1 / world["projection"].get("scale", 1)
    payload = load_interim_payload("freight")
    fr = payload["data"]
    bounds = load_interim("fr_boundaries")
    dep_names = {d["code"]: d["name"] for d in bounds["departements"]}
    nuts3 = nuts3_of_dep(load_interim("eurostat_gdp")["labels"], dep_names)
    zone_of_dep = {dep: code[:4] for dep, code in nuts3.items()}
    cities = json.loads((WEB_DATA / "cities.json").read_text())
    ipath = WEB_DATA / "infrastructure.json"
    infra = json.loads(ipath.read_text()) if ipath.exists() else None

    # Zones: the metropolitan regions of the flow files, with their départements, cities and EPCI count.
    codes = sorted({c for f in fr["flows"] for c in (f["o"], f["d"]) if is_metro(c)})
    deps_of = defaultdict(list)
    for dep, z in zone_of_dep.items():
        deps_of[z].append(dep)
    epci_count = defaultdict(int)
    for st in world["county_state"]:
        if st in zone_of_dep:
            epci_count[zone_of_dep[st]] += 1
    zones = {}
    for code in codes:
        raw = fr["names"].get(code, code)
        zones[code] = {"id": code, "nuts": [code], "name": NAME_FIX.get(raw, raw), "short": None, "kind": "region",
                       "states": sorted(deps_of.get(code, [])), "cities": [], "counties": epci_count[code],
                       "anchor": None}
    for c in cities:  # population order
        z = zone_of_dep.get((c.get("states") or [None])[0])
        if z in zones:
            zones[z]["cities"].append(c["id"])
    by_id = {c["id"]: c for c in cities}
    for z in zones.values():
        if z["cities"]:
            c = by_id[z["cities"][0]]
            z["anchor"] = {"cell": c["cell"], "x": c["x"], "y": c["y"], "city": c["id"]}
            z["short"] = c["name"]
        else:
            z["short"] = z["name"]

    pair, partner, totals, national = aggregate(fr["flows"])
    mode_ids = [m for m, _ in MODES]
    cands = []
    for (a, b), p in pair.items():
        za, zb = zones.get(a), zones.get(b)
        if not za or not zb or not za["anchor"] or not zb["anchor"]:
            continue
        dist = math.dist((za["anchor"]["x"], za["anchor"]["y"]), (zb["anchor"]["x"], zb["anchor"]["y"])) * km_per_unit
        if dist < MIN_KM:
            continue
        tkm = sum(p["tkm"].values())
        if tkm > 0:
            cands.append((tkm, dist, a, b, p))
    cands.sort(key=lambda t: (-t[0], t[2], t[3]))

    links = road_graph(infra)
    routes = []
    for rank, (tkm, dist, a, b, p) in enumerate(cands[:TOP_N], 1):
        shares = {m: round(p["tkm"].get(m, 0.0) / tkm, 4) for m in mode_ids}
        routes.append({
            "a": a, "b": b, "rank": rank,
            "value_musd": None,
            "tkm_m": round(tkm / 1e6, 1),
            "tons_k": None,
            "rail_water_tons_k": round(p["tons"] / 1e3, 1),
            "modes": shares, "top_mode": max(mode_ids, key=lambda m: shares[m]), "top_commodity": None,
            "dist_km": round(dist),
            "path": shortest_path(grid, owner, links, zones[a]["anchor"]["cell"], zones[b]["anchor"]["cell"]),
        })

    for zid, z in zones.items():
        ps = []
        for other, ms in partner[zid].items():
            v = sum(ms.values())
            if v > 0 and other in zones:
                ps.append([other, round(v / 1e6, 1), max(ms, key=ms.get)])
        ps.sort(key=lambda q: (-q[1], q[0]))
        z["partners"] = ps[:PARTNERS]
        t = totals[zid]
        z["totals_tkm"] = {k: round(t[k] / 1e6, 1) for k in ("within", "other_zones", "import", "export")}

    used = {r["a"] for r in routes} | {r["b"] for r in routes}
    write_web("trade.json", {
        "version": 1,
        "vintage": payload["vintage"],
        "year": fr["year"],
        "sources": ["freight"],
        "rule": RULE,
        "path_note": PATH_NOTE,
        "measure": "tkm_m",
        "units": {"tkm_m": "millions de tonnes-kilomètres", "tons_k": "milliers de tonnes",
                  "rail_water_tons_k": "milliers de tonnes, rail et voie d'eau seulement"},
        "modes": [{"id": m, "name": n} for m, n in MODES],
        "commodities": {},
        "national_tkm": {k: round(national[k] / 1e6, 1) for k in ("domestic", "import", "export")},
        "national_musd": None,
        "zones": sorted(zones.values(), key=lambda z: z["id"]),
        "routes": routes,
    })
    if routes:
        r0 = routes[0]
        print(f"    {len(zones)} zones, {len(cands)} region pairs ≥ {MIN_KM} km, {len(routes)} routes over {len(used)} "
              f"zones; top: {zones[r0['a']]['short']} – {zones[r0['b']]['short']} {r0['tkm_m']:,.0f} Mt·km")
    else:
        print("    no routes")


# ------------------------------------------------------------------ check


def check(web_dir: Path) -> list[tuple[str, str]]:
    path = Path(web_dir) / "trade.json"
    if not path.exists():
        return [("NOTE", "trade.json not built (optional; run: build trade --deps)")]
    out = []
    doc = json.loads(path.read_text())
    for k in ("version", "vintage", "year", "sources", "rule", "modes", "zones", "routes"):
        if k not in doc:
            out.append(("FAIL", f"trade.json lacks '{k}'"))
    if out:
        return out
    wpath = Path(web_dir) / "world.json"
    world = json.loads(wpath.read_text()) if wpath.exists() else None
    grid = HexGrid(world["grid"]["radius"], world["grid"]["cols"], world["grid"]["rows"]) if world else None
    owner = (world or {}).get("owner") or []
    cpath = Path(web_dir) / "cities.json"
    city_ids = {c["id"] for c in json.loads(cpath.read_text())} if cpath.exists() else None
    zones, probs = {}, []
    for z in doc["zones"]:
        zones[z.get("id")] = z
        a = z.get("anchor")
        if a is not None and grid is not None:
            c = a.get("cell")
            if not isinstance(c, int) or not 0 <= c < grid.size or (owner and owner[c] < 0):
                probs.append(f"zone {z.get('id')} anchor cell {c!r} is not French land")
        if city_ids is not None and any(c not in city_ids for c in z.get("cities") or []):
            probs.append(f"zone {z.get('id')} lists unknown cities")
    out.append(("FAIL", f"trade.json zones: {probs[:3]}") if probs else
               ("PASS", f"trade.json zones: {len(zones)} zones, {sum(1 for z in zones.values() if z['anchor'])} anchored"))
    measure = doc.get("measure", "value_musd")
    mode_ids = {m["id"] for m in doc["modes"]}
    probs, vals, pairs = [], [], set()
    for k, r in enumerate(doc["routes"], 1):
        a, b = zones.get(r.get("a")), zones.get(r.get("b"))
        if a is None or b is None:
            probs.append(f"route {k}: unknown zone")
            continue
        if r.get("rank") != k:
            probs.append(f"route {k}: rank {r.get('rank')}")
        v = r.get(measure)
        if not isinstance(v, (int, float)) or v <= 0:
            probs.append(f"route {k}: {measure} {v!r}")
        else:
            vals.append(v)
        pairs.add(tuple(sorted((r["a"], r["b"]))))
        if r.get("top_mode") not in mode_ids or set(r.get("modes", {})) - mode_ids:
            probs.append(f"route {k}: unknown mode")
        shares = list(r.get("modes", {}).values())
        if shares and abs(sum(shares) - 1) > 0.01:
            probs.append(f"route {k}: mode shares sum to {sum(shares):.3f}")
        p = r.get("path")
        if p is not None and grid is not None:
            if not p or p[0] != a["anchor"]["cell"] or p[-1] != b["anchor"]["cell"]:
                probs.append(f"route {k}: path does not join the anchors")
            elif any(v2 not in grid.neighbours(u) for u, v2 in zip(p, p[1:])):
                probs.append(f"route {k}: path steps are not neighbours")
    if vals != sorted(vals, reverse=True):
        probs.append(f"routes are not sorted by {measure}")
    if len(pairs) != len(doc["routes"]):
        probs.append("duplicate zone pairs")
    if probs:
        out.append(("FAIL", f"trade.json routes: {len(probs)} problems, e.g. {probs[:3]}"))
    elif doc["routes"]:
        top = doc["routes"][0]
        out.append(("PASS", f"trade.json routes: {len(doc['routes'])} routes by {measure}; #1 "
                            f"{zones[top['a']]['short']} – {zones[top['b']]['short']} {top[measure]:,.0f}"))
    else:
        out.append(("WARN", "trade.json has no routes"))
    if path.stat().st_size > 300_000:
        out.append(("WARN", f"trade.json is {path.stat().st_size / 1e3:.0f} kB (eager files should stay under ~300 kB)"))
    return out
