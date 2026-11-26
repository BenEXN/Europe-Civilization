"""Tile improvements: motorways, main roads and railroads rasterised onto hex links, plus ports and airports.

Lines are never shipped as polylines. Each Natural Earth 1:10m line is sampled every SAMPLE_KM along its length,
each sample is mapped to its hex, repeats in a row are dropped, a cell whose neighbours on the line already touch is
dropped (the line only clipped its corner), and every step between two cells becomes a link between neighbouring
cells. The browser draws a link as a road or rail segment from hex centre to hex centre.
Roads: every motorway (Natural Earth "Major Highway" marked as an expressway, and beltways) as class 0; other
roads at scale rank <= MAJOR_MAX_SCALERANK as class 1. Rail at scale rank <= RAIL_MAX_SCALERANK. Links into a
neighbouring country are dropped. Ports: Natural Earth ports. Airports: every French airport Eurostat reports, by
passengers. A site's `cell` is the French land cell at its point, or the nearest one up to SITE_RINGS hexes away.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

from ..core.geo import MapProjection, Shape, ShapeIndex
from ..core.hexgrid import HexGrid
from ..core.paths import WEB_DATA
from ..core.store import load_interim, load_interim_payload, write_web

REQUIRES = ["_world", "natural_earth_roads", "natural_earth", "airports", "ports", "insee_aav", "fr_boundaries", "cities.json"]
PRODUCES = ["infrastructure.json"]

SAMPLE_KM = 4.0
MAJOR_MAX_SCALERANK = 7
MAJOR_TYPES = {"Major Highway", "Beltway"}
RAIL_MAX_SCALERANK = 7
RAIL_MAIN_SCALERANK = 5
SITE_RINGS = 2
ROAD_CLASSES = [{"id": "interstate", "name": "Autoroute"}, {"id": "major", "name": "Route principale"}]
RAIL_TIERS = [{"id": "main", "name": "Grande ligne"}, {"id": "secondary", "name": "Ligne secondaire"}]
HUBS = {"L": "Grand aéroport (10 M de passagers ou plus)", "M": "Aéroport moyen (2 à 10 M)",
        "S": "Petit aéroport (500 000 à 2 M)", "N": "Aéroport régional (moins de 500 000)"}
HUB_MIN = [("L", 10_000_000), ("M", 2_000_000), ("S", 500_000), ("N", 0)]
AIRPORT_MIN = 20_000  # passengers a year

RULES = {
    "roads": "Routes Natural Earth 1:10m en France, échantillonnées tous les 4 km de carte et accrochées aux liaisons "
             "entre centres d'hexagones. Classe 0 : toutes les autoroutes (voies express « Major Highway » et "
             "rocades). Classe 1 : les autres routes de rang d'échelle Natural Earth "
             f"{MAJOR_MAX_SCALERANK} ou moins, là où aucune autoroute ne relie déjà les deux mêmes hexagones.",
    "rail": "Voies ferrées Natural Earth 1:10m de rang d'échelle 7 ou moins, accrochées aux liaisons entre hexagones ; "
            f"grande ligne au rang {RAIL_MAIN_SCALERANK} ou moins. Les tronçons dans les pays voisins sont coupés. "
            "Natural Earth ne porte ni gestionnaire ni trafic.",
    "ports": "Les ports de France métropolitaine déclarés à Eurostat, classés par poids brut des marchandises "
             "traitées (débarquées et embarquées) sur la dernière année complète. Chaque port est placé à la mairie de "
             "sa commune ; Le Havre et Rouen ne sont publiés qu'ensemble (HAROPA), placés au Havre.",
    "airports": f"Chaque aéroport français déclaré à Eurostat avec au moins {AIRPORT_MIN:,} passagers dans l'année "
                "(arrivées et départs), placé par son code OACI avec OurAirports.".replace(",", " "),
}


# ------------------------------------------------------------------ hex helpers


def _axial(grid: HexGrid, cell: int) -> tuple[int, int]:
    col, row = grid.col_row(cell)
    return col - (row - (row & 1)) // 2, row


def _from_axial(grid: HexGrid, q: int, r: int) -> int:
    col = q + (r - (r & 1)) // 2
    if 0 <= col < grid.cols and 0 <= r < grid.rows:
        return grid.index(col, r)
    return -1


def hex_distance(grid: HexGrid, a: int, b: int) -> int:
    (q1, r1), (q2, r2) = _axial(grid, a), _axial(grid, b)
    return (abs(q1 - q2) + abs(r1 - r2) + abs((q1 + r1) - (q2 + r2))) // 2


def hex_walk(grid: HexGrid, a: int, b: int) -> list[int]:
    """Cells on the hex line from a to b, both included (cube lerp with a tiny nudge to break ties)."""
    n = hex_distance(grid, a, b)
    if n <= 1:
        return [a, b] if a != b else [a]
    (q1, r1), (q2, r2) = _axial(grid, a), _axial(grid, b)
    out = []
    for i in range(n + 1):
        t = i / n
        x = q1 + (q2 - q1) * t + 1e-6
        z = r1 + (r2 - r1) * t + 1e-6
        y = -x - z
        rx, ry, rz = round(x), round(y), round(z)
        dx, dy, dz = abs(rx - x), abs(ry - y), abs(rz - z)
        if dx > dy and dx > dz:
            rx = -ry - rz
        elif dy <= dz:
            rz = -rx - ry
        c = _from_axial(grid, rx, rz)
        if c >= 0 and (not out or out[-1] != c):
            out.append(c)
    return out


def sample_cells(grid: HexGrid, pts: list[tuple[float, float]], keep=None) -> list[list[int]]:
    """Runs of distinct consecutive cells along a projected line, sampled every SAMPLE_KM. `keep(x, y)` False
    breaks the run (the sample is dropped)."""
    runs, run = [], []

    def add(x, y):
        nonlocal run
        if keep is not None and not keep(x, y):
            if len(run) > 1:
                runs.append(run)
            run = []
            return
        c = grid.cell_at(x, y)
        if c < 0:
            return
        if not run or run[-1] != c:
            run.append(c)

    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        steps = max(1, math.ceil(math.hypot(x1 - x0, y1 - y0) / SAMPLE_KM))
        for i in range(steps):
            t = i / steps
            add(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t)
    if pts:
        add(*pts[-1])
    if len(run) > 1:
        runs.append(run)
    return runs


def straighten(grid: HexGrid, run: list[int]) -> list[int]:
    """Drop detour cells: where the cells before and after a cell are neighbours themselves, the line only clipped
    that cell's corner. Without this, a road running along a row boundary zigzags between two rows."""
    out = []
    for c in run:
        while len(out) >= 2 and c in grid.neighbours(out[-2]):
            out.pop()
        if not out or out[-1] != c:
            out.append(c)
    return out


def links_of(grid: HexGrid, run: list[int]) -> list[tuple[int, int]]:
    out = []
    run = straighten(grid, [c for path in ([run[0]], *(hex_walk(grid, a, b)[1:] for a, b in zip(run, run[1:])))
                            for c in path])
    for a, b in zip(run, run[1:]):
        path = hex_walk(grid, a, b)
        for u, v in zip(path, path[1:]):
            if u != v:
                out.append((u, v) if u < v else (v, u))
    return out


# ------------------------------------------------------------------ roads and rail


def _route_name(f: dict) -> str | None:
    """'A6' (the national number) when Natural Earth has one, else the European route ('E15')."""
    if f.get("label2"):
        return f["label2"].strip()
    name = (f.get("name") or "").strip()
    return f"E{name}" if name.isdigit() else (name or None)


def _route_key(name: str) -> tuple:
    digits = "".join(ch for ch in name if ch.isdigit())
    return (len(digits) or 9, int(digits) if digits else 999, name)


def build_roads(grid, proj, owner, ne):
    cls_of = defaultdict(lambda: 9)
    names = defaultdict(Counter)
    for f in ne["roads"]:
        inter = bool(f["expressway"]) and f["type"] in MAJOR_TYPES
        sr = f["scalerank"] if f["scalerank"] is not None else 99
        major = sr <= MAJOR_MAX_SCALERANK and f["type"] in ("Major Highway", "Secondary Highway", "Beltway", "Bypass")
        if not (inter or major):
            continue
        cls = 0 if inter else 1
        name = _route_name(f)
        for line in f["lines"]:
            pts = [proj(lon, lat) for lon, lat in line]
            for run in sample_cells(grid, pts):
                for a, b in links_of(grid, run):
                    if owner[a] < 0 and owner[b] < 0:
                        continue
                    if owner[a] == -2 or owner[b] == -2:
                        continue  # into a neighbouring country
                    if cls < cls_of[(a, b)]:
                        cls_of[(a, b)] = cls
                        names[(a, b)].clear()
                    if cls == cls_of[(a, b)] and name:
                        names[(a, b)][name] += 1
    roads = []
    for (a, b), cls in sorted(cls_of.items()):
        nm = min(names[(a, b)], key=_route_key) if names[(a, b)] else None
        roads.append([a, b, cls, nm])
    return roads


def build_rail(grid, proj, owner, ne, foreign_idx):
    tier_of = {}

    def keep(x, y):
        return foreign_idx.locate(x, y) < 0

    for f in ne["rail"]:
        sr = f["scalerank"] if f["scalerank"] is not None else 99
        if sr > RAIL_MAX_SCALERANK:
            continue
        tier = 0 if sr <= RAIL_MAIN_SCALERANK else 1
        for line in f["lines"]:
            pts = [proj(lon, lat) for lon, lat in line]
            for run in sample_cells(grid, pts, keep):
                for a, b in links_of(grid, run):
                    if owner[a] == -2 or owner[b] == -2 or (owner[a] < 0 and owner[b] < 0):
                        continue
                    tier_of[(a, b)] = min(tier, tier_of.get((a, b), 9))
    return [[a, b, t] for (a, b), t in sorted(tier_of.items())]


# ------------------------------------------------------------------ sites


class Locator:
    def __init__(self, world, grid, proj):
        self.grid, self.proj, self.world = grid, proj, world
        self.owner, self.county, self.geoids = world["owner"], world["county"], world["counties"]
        self.states = world["states"]
        city_ids = {c["id"] for c in json.loads((WEB_DATA / "cities.json").read_text())}
        aav_of = {c["code"]: c["aav"] for c in load_interim("insee_aav")["communes"]}
        self.aav_of = {code: a for code, a in aav_of.items() if a in city_ids}
        self.communes = world["communes"]
        self.samples = world["commune_samples"]

    def land_cell(self, x, y, rings=SITE_RINGS) -> int:
        grid, owner = self.grid, self.owner
        cell = grid.cell_at(x, y)
        if cell < 0:
            return -1
        if owner[cell] >= 0:
            return cell
        seen, frontier = {cell}, [cell]
        for _ in range(rings):
            ring = [n for c in frontier for n in grid.neighbours(c) if n not in seen]
            ring = list(dict.fromkeys(ring))
            seen.update(ring)
            land = [n for n in ring if owner[n] >= 0]
            if land:
                return min(land, key=lambda n: math.dist(grid.center(*grid.col_row(n)), (x, y)))
            frontier = ring
        return -1

    def place(self, lon, lat) -> dict | None:
        if lon is None or lat is None:
            return None
        x, y = self.proj(lon, lat)
        cell = self.land_cell(x, y)
        if cell < 0:
            return None
        ci = self.county[cell]
        smp = self.samples[cell]
        commune = self.communes[smp[0]] if smp and smp[0] >= 0 else None
        return {"x": round(x, 1), "y": round(y, 1), "cell": cell, "county": self.geoids[ci] if ci >= 0 else None,
                "cbsa": self.aav_of.get(commune), "state": self.states[self.owner[cell]]}


# Eurostat port name → (commune whose town hall places it, display name). Names not listed are looked up as is.
PORT_PLACE = {
    "HAROPA (Le Havre and Rouen)": ("Le Havre", "Le Havre – Rouen (HAROPA)"),
    "Nantes Saint-Nazaire": ("Saint-Nazaire", "Nantes – Saint-Nazaire"),
    "Caen": ("Ouistreham", "Caen-Ouistreham"),
    "Cherbourg": ("Cherbourg-en-Cotentin", "Cherbourg"),
    "Les Sables d'Olonne": ("Les Sables-d'Olonne", "Les Sables-d'Olonne"),
    "St Malo": ("Saint-Malo", "Saint-Malo"),
    "St Raphaël": ("Saint-Raphaël", "Saint-Raphaël"),
    "St Valéry-sur-Somme": ("Saint-Valery-sur-Somme", "Saint-Valery-sur-Somme"),
    "Le Legue (St Brieuc)": ("Saint-Brieuc", "Le Légué (Saint-Brieuc)"),
    "Le Légué": ("Saint-Brieuc", "Le Légué (Saint-Brieuc)"),
    "Port Vendres": ("Port-Vendres", "Port-Vendres"),
    "Porto Vecchio": ("Porto-Vecchio", "Porto-Vecchio"),
    "L´Île Rousse": ("L'Île-Rousse", "L'Île-Rousse"),
    "Tonnay Charente": ("Tonnay-Charente", "Tonnay-Charente"),
    "Port-Joinville (Île d´Yeu)": ("L'Île-d'Yeu", "Port-Joinville (L'Île-d'Yeu)"),
    "Le Fret (Crozon)": ("Crozon", "Le Fret (Crozon)"),
    "Le Guildo (Crehen)": ("Créhen", "Le Guildo (Créhen)"),
    "Camaret": ("Camaret-sur-Mer", "Camaret-sur-Mer"),
    "Carteret": ("Barneville-Carteret", "Carteret"),
}
AGGREGATE_PORTS = {"FR_1FR888"}  # "other ports" rows are not places


def _norm(name: str) -> str:
    import unicodedata

    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "", s)


def build_ports(loc: Locator, src: dict, bounds: dict) -> list[dict]:
    """Eurostat ports by tonnage, placed at their commune's town hall; Natural Earth points if Eurostat is missing."""
    if not src.get("tonnage"):
        out = []
        ranked = sorted(src["ports"], key=lambda p: (p["rank"] if p["rank"] is not None else 99, p["name"] or ""))
        for k, p in enumerate(ranked, 1):
            at = loc.place(p["lon"], p["lat"])
            if at is None or not p["name"]:
                continue
            out.append({"id": f"port-{k}", "name": p["name"], "type": "coastal", "rank": len(out) + 1, "tons": None,
                        "domestic": None, "foreign": None, "imports": None, "exports": None, "year": None, **at})
        return out
    # Communes of the coast: their département owns a hex next to the sea (to pick Rochefort, Charente-Maritime,
    # over Rochefort, Savoie).
    world = loc.world
    grid, owner, water = loc.grid, world["owner"], world["water"]
    coastal = {loc.states[owner[c]] for c in range(grid.size) if owner[c] >= 0
               and any(water[n] in (1, 2) for n in grid.neighbours(c))}
    by_name: dict[str, list[dict]] = {}
    for c in bounds["communes"]:
        by_name.setdefault(_norm(c["name"]), []).append(c)
    out, missing = [], []
    for p in src["tonnage"]:
        if p["code"] in AGGREGATE_PORTS:
            continue
        commune_name, display = PORT_PLACE.get(p["name"], (p["name"], p["name"]))
        cands = by_name.get(_norm(commune_name), [])
        cands = [c for c in cands if c["dep"] in coastal] or cands
        pt = bounds["mairies"].get(cands[0]["code"]) if cands else None
        at = loc.place(*pt) if pt else None
        if at is None:
            missing.append(p["name"])
            continue
        out.append({"id": p["code"], "name": display, "type": "coastal", "rank": len(out) + 1, "tons": p["tons"],
                    "domestic": None, "foreign": None, "imports": p["in"], "exports": p["out"], "year": p["year"],
                    **at})
    if missing:
        print(f"    ports not placed: {', '.join(missing)}")
    return out


def build_airports(loc: Locator, src: dict) -> list[dict]:
    out = []
    for icao, t in src["traffic"].items():
        years = sorted(t["pax"])
        year = years[-1]
        if year == "2025" and "2024" in t["pax"]:
            year = "2024"  # the last full year everywhere
        pax = t["pax"].get(year)
        pos = src["positions"].get(icao)
        if not pos or not pax or pax < AIRPORT_MIN:
            continue
        at = loc.place(pos["lon"], pos["lat"])
        if at is None:
            continue
        prev = t["pax"].get(str(int(year) - 1))
        hub = next(h for h, m in HUB_MIN if pax >= m)
        out.append({"id": pos.get("iata") or icao, "icao": icao, "name": pos["name"], "city": pos["city"], "hub": hub,
                    "enplanements": _int(pax), "enplanements_prev": _int(prev), "cargo_lbs": None,
                    "year": int(year), **at})
    out.sort(key=lambda a: -(a["enplanements"] or 0))
    return out


def _int(v):
    return None if v is None else int(round(v))


# ------------------------------------------------------------------ build


def build() -> None:
    world = load_interim("_world")
    grid, proj, owner = HexGrid(**world["grid"]), MapProjection(**world["projection"]), world["owner"]
    ne = load_interim("natural_earth_roads")
    foreign = load_interim("natural_earth")["countries"]
    foreign_idx = ShapeIndex([Shape([[proj(lon, lat) for lon, lat in r] for r in c["rings"]]) for c in foreign],
                             cell_km=100)
    roads = build_roads(grid, proj, owner, ne)
    rail = build_rail(grid, proj, owner, ne, foreign_idx)

    loc = Locator(world, grid, proj)
    usace = load_interim_payload("ports")
    faa = load_interim_payload("airports")
    ports = build_ports(loc, usace["data"], load_interim("fr_boundaries"))
    airports = build_airports(loc, faa["data"])

    ne_vintage = load_interim_payload("natural_earth_roads")["vintage"]
    doc = {
        "version": 1,
        "vintage": {"roads": ne_vintage, "rail": ne_vintage, "ports": usace["vintage"], "airports": faa["vintage"]},
        "sources": ["natural_earth_roads", "ports", "airports"],
        "rules": RULES,
        "road_classes": ROAD_CLASSES,
        "rail_tiers": RAIL_TIERS,
        "hubs": HUBS,
        "roads": roads,
        "rail": rail,
        "ports": ports,
        "airports": airports,
    }
    write_web("infrastructure.json", doc)
    road_cells = {c for a, b, *_ in roads for c in (a, b) if owner[c] >= 0}
    rail_cells = {c for a, b, _ in rail for c in (a, b) if owner[c] >= 0}
    land = sum(1 for o in owner if o >= 0)
    n0 = sum(1 for r in roads if r[2] == 0)
    print(f"    roads: {n0} motorway + {len(roads) - n0} main-road links on {len(road_cells)} of {land} land hexes; "
          f"rail: {len(rail)} links on {len(rail_cells)} hexes; {len(ports)} ports, {len(airports)} airports")


# ------------------------------------------------------------------ check


def _neighbours(grid_doc):
    return HexGrid(grid_doc["radius"], grid_doc["cols"], grid_doc["rows"])


def check(web_dir: Path) -> list[tuple[str, str]]:
    path = Path(web_dir) / "infrastructure.json"
    if not path.exists():
        return [("NOTE", "infrastructure.json not built (optional; run: build infrastructure --deps)")]
    out = []
    doc = json.loads(path.read_text())
    for k in ("version", "vintage", "sources", "road_classes", "roads", "rail", "ports", "airports"):
        if k not in doc:
            out.append(("FAIL", f"infrastructure.json lacks '{k}'"))
    if any(lv == "FAIL" for lv, _ in out):
        return out
    if doc["version"] != 1:
        out.append(("FAIL", f"infrastructure.json version {doc['version']!r} (expected 1)"))
    wpath = Path(web_dir) / "world.json"
    world = json.loads(wpath.read_text()) if wpath.exists() else None
    if not world or "grid" not in world:
        return out + [("NOTE", "infrastructure.json: world.json unavailable, cell checks skipped")]
    grid = _neighbours(world["grid"])
    owner = world.get("owner") or []
    n = grid.size
    county_ids = {c["geoid"] for c in world.get("counties", [])}
    cpath = Path(web_dir) / "cities.json"
    city_ids = {c["id"] for c in json.loads(cpath.read_text())} if cpath.exists() else None
    spath = Path(web_dir) / "sources.json"
    if spath.exists():
        src = json.loads(spath.read_text())
        ids = {s["id"] for s in (src.get("sources", src) if isinstance(src, dict) else src) if isinstance(s, dict)}
        miss = [s for s in doc["sources"] if s not in ids]
        if ids and miss:
            out.append(("WARN", f"infrastructure.json cites sources missing from sources.json: {miss}"))

    def bad_link(link, ncls):
        if not isinstance(link, list) or len(link) < 3:
            return "shape"
        a, b, c = link[:3]
        if not all(isinstance(v, int) for v in (a, b, c)):
            return "types"
        if not (0 <= a < b < n):
            return "order/range"
        if b not in grid.neighbours(a):
            return "not neighbours"
        if len(owner) == n and owner[a] < 0 and owner[b] < 0:
            return "no French land end"
        if not 0 <= c < ncls:
            return "class"
        return None

    for key, ncls in (("roads", len(doc["road_classes"])), ("rail", len(doc.get("rail_tiers") or [0, 1]))):
        links = doc[key]
        bad = [(l, why) for l in links if (why := bad_link(l, ncls))]
        pairs = [tuple(l[:2]) for l in links if isinstance(l, list)]
        dup = len(pairs) - len(set(pairs))
        if bad or dup:
            out.append(("FAIL", f"infrastructure.json {key}: {len(bad)} bad links (e.g. {bad[:2]}), {dup} duplicates"))
        else:
            cells = {c for l in links for c in l[:2]}
            out.append(("PASS", f"infrastructure.json {key}: {len(links)} neighbour links on {len(cells)} hexes"))
    if any(not (r[3] is None or isinstance(r[3], str)) for r in doc["roads"] if len(r) > 3):
        out.append(("FAIL", "infrastructure.json roads: route name must be a string or null"))

    def check_sites(key, num_keys):
        probs = []
        for s in doc[key]:
            c = s.get("cell")
            if not isinstance(c, int) or not 0 <= c < n or (len(owner) == n and owner[c] < 0):
                probs.append(f"{s.get('id')}: cell {c!r} is not French land")
                continue
            if any(s.get(k) is not None and not isinstance(s.get(k), (int, float)) for k in num_keys):
                probs.append(f"{s.get('id')}: non-numeric value")
            cx, cy = grid.center(*grid.col_row(c))
            if not all(isinstance(s.get(k), (int, float)) for k in ("x", "y")) or \
                    math.dist((cx, cy), (s["x"], s["y"])) > (SITE_RINGS + 1) * world["grid"]["radius"] * 2:
                probs.append(f"{s.get('id')}: x/y far from its cell")
            if s.get("county") is not None and county_ids and s["county"] not in county_ids:
                probs.append(f"{s.get('id')}: unknown county {s['county']}")
            if s.get("cbsa") is not None and city_ids is not None and s["cbsa"] not in city_ids:
                probs.append(f"{s.get('id')}: unknown cbsa {s['cbsa']}")
        ids = [s.get("id") for s in doc[key]]
        if len(ids) != len(set(ids)):
            probs.append("duplicate ids")
        return probs

    for key, nums in (("ports", ("tons", "domestic", "foreign", "imports", "exports", "rank")),
                      ("airports", ("enplanements", "enplanements_prev", "cargo_lbs"))):
        probs = check_sites(key, nums)
        if probs:
            out.append(("FAIL", f"infrastructure.json {key}: {len(probs)} problems, e.g. {probs[:3]}"))
        else:
            metro = sum(1 for s in doc[key] if s.get("cbsa"))
            out.append(("PASS", f"infrastructure.json {key}: {len(doc[key])} sites, {metro} in a mapped metro"))
    hubs = Counter(a.get("hub") for a in doc["airports"])
    out.append(("NOTE", "infrastructure.json airports by hub: " + ", ".join(f"{k or 'cargo-only'} {v}" for k, v in
                                                                         sorted(hubs.items(), key=lambda kv: str(kv[0])))))
    size = path.stat().st_size
    if size > 300_000:
        out.append(("WARN", f"infrastructure.json is {size / 1e3:.0f} kB (eager files should stay under ~300 kB)"))
    return out
