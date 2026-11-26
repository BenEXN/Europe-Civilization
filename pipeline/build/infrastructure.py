"""Tile improvements: motorways, major roads and railways rasterised onto hex links, plus seaports and airports.

Lines are never shipped as polylines. Each Natural Earth 1:10m line is sampled every SAMPLE map units (1.6 km) along
its length, each sample is mapped to its hex, repeats in a row are dropped, a cell whose neighbours on the line already
touch is dropped (the line only clipped its corner), and every step between two cells becomes a link between
neighbouring cells. The browser draws a link as a road or rail segment from hex centre to hex centre. Samples on
foreign land (owner -2) break the line, and a line is also cut where it leaves an inset's window (the two sides are
drawn in different places).

Roads: class 0 = every Natural Earth road flagged as an expressway (the motorways); class 1 = the other roads of the
E-road network and the other highways at scale rank <= MAJOR_MAX_SCALERANK. Rail: scale rank <= RAIL_MAX_SCALERANK,
main line at <= RAIL_MAIN_SCALERANK. Ports: Eurostat tonnage (`ports`), airports: Eurostat passengers (`airports`).
A site's `cell` is a land cell of its own country at its point, or the nearest one up to SITE_RINGS hexes away.
"""

from __future__ import annotations

import json
import math
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

from ..core.europe import COUNTRIES
from ..core.geo import MapProjection
from ..core.hexgrid import HexGrid
from ..core.paths import WEB_DATA
from ..core.store import load_interim, load_interim_payload, write_web

REQUIRES = ["_world", "natural_earth_roads", "airports", "ports", "geonames", "cities.json"]
PRODUCES = ["infrastructure.json"]

FOREIGN = -2
SAMPLE = 4.0  # map units between samples along a line (1.6 km; hexes are 25 units in radius)
MAJOR_MAX_SCALERANK = 7
HIGHWAY_TYPES = {"Major Highway", "Secondary Highway", "Beltway", "Bypass"}
RAIL_MAX_SCALERANK = 7
RAIL_MAIN_SCALERANK = 5
SITE_RINGS = 2
FAR_RINGS = 4  # for a site on or next to a neighbour's land (a coastal strip too narrow for its own hexes)
SEA = (1, 2)  # world water codes of the open sea (ocean, coast)
INLAND_RINGS = 4  # a port with no sea hex this close (about 70 km; fjords and estuaries are closer) is a river port
ROAD_CLASSES = [{"id": "interstate", "name": "Motorway"}, {"id": "major", "name": "Major road"}]
RAIL_TIERS = [{"id": "main", "name": "Main line"}, {"id": "secondary", "name": "Secondary line"}]
HUBS = {"L": "Large airport (10 million passengers or more)", "M": "Medium airport (2 to 10 million)",
        "S": "Small airport (500,000 to 2 million)", "N": "Regional airport (under 500,000)"}
HUB_MIN = [("L", 10_000_000), ("M", 2_000_000), ("S", 500_000), ("N", 0)]
AIRPORT_MIN = 50_000  # passengers a year
PORT_MIN_TONS = 500_000  # tonnes a year
YEAR_COMPLETE = 0.8  # share of the year before's airports a year needs to be the reference year

RULES = {
    "roads": "Natural Earth 1:10m roads in the map's countries, sampled every 1.6 km and snapped to links between hex "
             "centres. Class 0 (motorway): every road Natural Earth flags as an expressway. Class 1 (major road): the "
             "other roads of the European E-road network, and the other highways (Natural Earth types Major and "
             f"Secondary Highway, Beltway, Bypass) at scale rank {MAJOR_MAX_SCALERANK} or less, where no motorway "
             "already joins the same two hexes. Route names: the national number (A6, M7) where Natural Earth has "
             "one, else the E-road number (a bare national number shows as \"Route 8\"); where several routes "
             "share a link the lowest number wins. Lines stop at "
             "the borders of neighbouring countries; ferries are left out.",
    "rail": f"Natural Earth 1:10m railways at scale rank {RAIL_MAX_SCALERANK} or less, snapped to links between hex "
            f"centres; main lines are scale rank {RAIL_MAIN_SCALERANK} or less. Lines stop at the borders of "
            "neighbouring countries. Natural Earth carries neither operator nor traffic, and its alignments are "
            "older and sparser than today's network.",
    "ports": f"Every port reporting to Eurostat that handled at least {PORT_MIN_TONS:,} tonnes of goods (gross weight, "
             "unloaded plus loaded) in its country's latest complete year, ranked by tonnage. Each port is placed at "
             "the Wikidata place carrying its UN/LOCODE, else at the UN/LOCODE list's coordinates, else at the "
             "GeoNames town of its name. Ports Eurostat reports as one authority are drawn at their main harbour "
             "(Antwerp-Bruges at Antwerp, HAROPA at Le Havre). Rows that are not one place (\"other ports\", "
             "offshore installations, Estonia's confidential total) are left out, and so are ports on islands too "
             "small for a hex of their own.",
    "airports": f"Every airport reporting to Eurostat with at least {AIRPORT_MIN:,} passengers in the year (arrivals "
                "plus departures, scheduled and charter), placed by its ICAO code with OurAirports. Hub classes "
                "follow passengers: large 10 million or more, medium 2 to 10 million, small 500,000 to 2 million, "
                "regional under 500,000. Airports on islands too small for a hex of their own are left out; Tirana "
                "(Albania) has no figures at Eurostat and is missing.",
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


def project_line(proj: MapProjection, line) -> list[list[tuple[float, float]]]:
    """A lon/lat line in map units, cut where it passes between the main map and an inset window (or two windows)."""
    parts, cur, frame = [], [], None
    for lon, lat in line:
        f = proj.inset_of(lon, lat) if (lon > 40 or lon < -40 or (lon < -12.5 and lat < 40.5)) else None
        if cur and f is not frame:
            if len(cur) > 1:
                parts.append(cur)
            cur = []
        frame = f
        cur.append(proj(lon, lat))
    if len(cur) > 1:
        parts.append(cur)
    return parts


def sample_cells(grid: HexGrid, pts: list[tuple[float, float]], owner: list[int]) -> list[list[int]]:
    """Runs of distinct consecutive cells along a projected line, sampled every SAMPLE units. A sample off the grid or
    on foreign land breaks the run."""
    runs, run = [], []

    def add(x, y):
        nonlocal run
        c = grid.cell_at(x, y)
        if c < 0 or owner[c] == FOREIGN:
            if len(run) > 1:
                runs.append(run)
            run = []
            return
        if not run or run[-1] != c:
            run.append(c)

    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        steps = max(1, math.ceil(math.hypot(x1 - x0, y1 - y0) / SAMPLE))
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


def line_links(grid, proj, owner, lines):
    """Every link (a < b) of a feature's lines with at least one end on a map country and neither end foreign."""
    for line in lines:
        for pts in project_line(proj, line):
            for run in sample_cells(grid, pts, owner):
                for a, b in links_of(grid, run):
                    if owner[a] >= 0 or owner[b] >= 0:
                        yield a, b


# ------------------------------------------------------------------ roads and rail


def road_class(f: dict) -> int | None:
    """0 motorway, 1 major road, None (not drawn)."""
    if f["expressway"]:
        return 0
    sr = f["scalerank"] if f["scalerank"] is not None else 99
    if f.get("level") == "E" or (f["type"] in HIGHWAY_TYPES and sr <= MAJOR_MAX_SCALERANK):
        return 1
    return None


def route_name(f: dict) -> str | None:
    """'A6' (the national number) when Natural Earth has one, else the E-road ('E15'); a bare national number (Poland's
    8, Iceland's 1) is 'Route 8' unless the road is an E-road."""
    label = re.split(r"[\s;,]+", (f.get("label2") or f.get("local") or "").strip())[0].strip("!?.*")
    name = (f.get("name") or "").strip()
    e_road = f"E{name}" if name.isdigit() else None
    if label and not label.isdigit():
        return label
    if e_road:
        return e_road
    if label:
        return f"Route {label}"
    return name or None


def _route_key(name: str) -> tuple:
    digits = "".join(ch for ch in name if ch.isdigit())
    return (len(digits) or 9, int(digits) if digits else 999, name)


def build_roads(grid, proj, owner, ne):
    cls_of: dict[tuple[int, int], int] = {}
    names = defaultdict(Counter)
    for f in ne["roads"]:
        cls = road_class(f)
        if cls is None:
            continue
        name = route_name(f)
        for a, b in line_links(grid, proj, owner, f["lines"]):
            best = cls_of.get((a, b), 9)
            if cls < best:
                cls_of[(a, b)] = cls
                names[(a, b)].clear()
            if cls <= best and name:
                names[(a, b)][name] += 1
    return [[a, b, cls, min(names[(a, b)], key=_route_key) if names[(a, b)] else None]
            for (a, b), cls in sorted(cls_of.items())]


def build_rail(grid, proj, owner, ne):
    tier_of: dict[tuple[int, int], int] = {}
    for f in ne["rail"]:
        sr = f["scalerank"] if f["scalerank"] is not None else 99
        if sr > RAIL_MAX_SCALERANK:
            continue
        tier = 0 if sr <= RAIL_MAIN_SCALERANK else 1
        for a, b in line_links(grid, proj, owner, f["lines"]):
            tier_of[(a, b)] = min(tier, tier_of.get((a, b), 9))
    return [[a, b, t] for (a, b), t in sorted(tier_of.items())]


# ------------------------------------------------------------------ sites


class Locator:
    """Puts a lon/lat site on a land cell of its own country and names its NUTS 3 region and urban area."""

    def __init__(self, world, grid, proj, cities):
        self.grid, self.proj, self.world = grid, proj, world
        self.owner, self.county, self.geoids = world["owner"], world["county"], world["counties"]
        self.states = world["states"]
        self.state_k = {s: k for k, s in enumerate(self.states)}
        self.fuas = world["fuas"]
        self.fua_samples = world["fua_samples"]
        self.city_ids = {c["id"] for c in cities}
        # Cell → the most populous city whose footprint holds it.
        self.foot: dict[int, str] = {}
        for c in sorted(cities, key=lambda c: -(c.get("population") or 0)):
            for cell in c.get("footprint") or [c["cell"]]:
                self.foot.setdefault(cell, c["id"])

    def land_cell(self, x, y, country) -> int:
        """The cell at (x, y) if it is land of `country`, else the nearest such cell up to SITE_RINGS hexes away, or
        up to FAR_RINGS when the point is on or next to another map country's land (Dubrovnik's strip of coast is
        too narrow for Croatian hexes). Small islands without a hex of their own get no cell."""
        grid, owner, want = self.grid, self.owner, self.state_k.get(country)
        cell = grid.cell_at(x, y)
        if cell < 0 or want is None:
            return -1
        if owner[cell] == want:
            return cell
        touches = owner[cell] >= 0
        seen, frontier = {cell}, [cell]
        for k in range(1, FAR_RINGS + 1):
            ring = list(dict.fromkeys(n for c in frontier for n in grid.neighbours(c) if n not in seen))
            seen.update(ring)
            land = [n for n in ring if owner[n] == want]
            if land:
                return min(land, key=lambda n: math.dist(grid.center(*grid.col_row(n)), (x, y)))
            touches = touches or (k == 1 and any(owner[n] >= 0 for n in ring))
            if k >= SITE_RINGS and not touches:
                break
            frontier = ring
        return -1

    def city_of(self, cell) -> str | None:
        if cell in self.foot:
            return self.foot[cell]
        smp = [k for k in self.fua_samples[cell] if k >= 0]
        if smp:
            code = self.fuas[Counter(smp).most_common(1)[0][0]]
            if code in self.city_ids:
                return code
        return None

    def place(self, lon, lat, country) -> dict | None:
        if lon is None or lat is None:
            return None
        x, y = self.proj(lon, lat)
        cell = self.land_cell(x, y, country)
        if cell < 0:
            return None
        ci = self.county[cell]
        return {"x": round(x, 1), "y": round(y, 1), "cell": cell, "county": self.geoids[ci] if ci >= 0 else None,
                "cbsa": self.city_of(cell), "state": self.states[self.owner[cell]]}

    def near_sea(self, cell, rings=INLAND_RINGS) -> bool:
        water, grid = self.world["water"], self.grid
        if water[cell] in SEA:
            return True
        seen, frontier = {cell}, [cell]
        for _ in range(rings):
            ring = [n for c in frontier for n in grid.neighbours(c) if n not in seen]
            if any(water[n] in SEA for n in ring):
                return True
            seen.update(ring)
            frontier = ring
        return False


def _norm(name: str | None) -> str:
    s = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "", s)


def _name_keys(p: dict) -> list[str]:
    """Names to look a port up by in GeoNames: its labels, without '(…)' asides and harbour words, and their parts."""
    out = []
    for n in (p["eurostat_name"], p["name"], p.get("locode_name"), *re.findall(r"\((.*?)\)", p["eurostat_name"])):
        if not n:
            continue
        base = re.sub(r"\(.*?\)", "", n)
        base = re.sub(r"\b(Havn|Havnen|Harbour|Port|Hafen|høfn)\b", "", base, flags=re.I)
        for part in [n, base, *re.split(r"[,/–-]", base)]:
            k = _norm(part)
            if len(k) >= 3 and k not in out:
                out.append(k)
    return out


def build_ports(loc: Locator, src: dict, places: list[dict]) -> tuple[list[dict], list[str], int]:
    """Eurostat ports by tonnage. Returns (ports, names of the ports not placed, ports under PORT_MIN_TONS)."""
    towns: dict[tuple[str, str], dict] = {}
    for pl in sorted(places, key=lambda p: -p["pop"]):
        towns.setdefault((pl["country"], _norm(pl["name"])), pl)
    out, missing, small = [], [], 0
    for p in src["ports"]:
        if p["tons"] < PORT_MIN_TONS:
            small += 1
            continue
        cands = [p["positions"]["wikidata"], p["positions"]["locode"]]
        cands += [(t["lon"], t["lat"]) for k in _name_keys(p) if (t := towns.get((p["country"], k)))]
        at = next((a for c in cands if c and (a := loc.place(c[0], c[1], p["country"]))), None)
        if at is None:
            missing.append(f"{p['name']} ({p['country']})")
            continue
        point = loc.grid.cell_at(at["x"], at["y"])
        inland = (p.get("area") or "").endswith("Inland") or not (
            loc.near_sea(at["cell"]) or (point >= 0 and loc.near_sea(point)))
        out.append({"id": p["code"], "name": p["name"], "type": "inland" if inland else "coastal", "rank": 0,
                    "tons": p["tons"], "domestic": None, "foreign": None, "imports": p["in"], "exports": p["out"],
                    "year": p["year"], **at})
    out.sort(key=lambda s: -s["tons"])
    for k, s in enumerate(out, 1):
        s["rank"] = k
    return out, missing, small


def reference_year(traffic: dict) -> str:
    """The latest year in which at least YEAR_COMPLETE of the airports that reported the year before report too."""
    seen: dict[str, set] = defaultdict(set)
    for icao, t in traffic.items():
        for y, v in t["pax"].items():
            if v:
                seen[y].add(icao)
    for y in sorted(seen, reverse=True):
        prev = seen.get(str(int(y) - 1))
        if not prev or len(seen[y] & prev) >= YEAR_COMPLETE * len(prev):
            return y
    return max(seen)


def build_airports(loc: Locator, src: dict) -> tuple[list[dict], list[str]]:
    """Airports by passengers in the reference year (or the year before, for a country that reports late; an airport
    with neither has closed or stopped reporting)."""
    ref = reference_year(src["traffic"])
    prev_year = str(int(ref) - 1)
    out, missing = [], []
    for icao, t in src["traffic"].items():
        year = ref if t["pax"].get(ref) else prev_year if t["pax"].get(prev_year) else None
        if year is None or t["pax"][year] < AIRPORT_MIN:
            continue
        pax = t["pax"][year]
        pos = src["positions"].get(icao)
        at = loc.place(pos["lon"], pos["lat"], t["country"]) if pos else None
        if at is None:
            missing.append(f"{icao} {t['label']}")
            continue
        hub = next(h for h, m in HUB_MIN if pax >= m)
        city = re.sub(r"\s*\(.*\)$", "", pos["city"] or "") or None  # "Paris (Roissy-en-France, Val-d'Oise)"
        out.append({"id": pos.get("iata") or icao, "icao": icao, "name": pos["name"], "city": city, "hub": hub,
                    "enplanements": _int(pax), "enplanements_prev": _int(t["pax"].get(str(int(year) - 1))),
                    "cargo_lbs": None, "year": int(year), **at})
    out.sort(key=lambda a: -(a["enplanements"] or 0))
    return out, missing


def _int(v):
    return None if v is None else int(round(v))


# ------------------------------------------------------------------ build


def build() -> None:
    world = load_interim("_world")
    grid, proj, owner = HexGrid(**world["grid"]), MapProjection(**world["projection"]), world["owner"]
    ne_payload = load_interim_payload("natural_earth_roads")
    ne = ne_payload["data"]
    roads = build_roads(grid, proj, owner, ne)
    rail = build_rail(grid, proj, owner, ne)

    cities = json.loads((WEB_DATA / "cities.json").read_text())
    loc = Locator(world, grid, proj, cities)
    ports_src, air_src = load_interim_payload("ports"), load_interim_payload("airports")
    ports, ports_missing, ports_small = build_ports(loc, ports_src["data"], load_interim("geonames")["places"])
    airports, air_missing = build_airports(loc, air_src["data"])
    lo, hi = min(a["year"] for a in airports), max(a["year"] for a in airports)

    vintage = ne_payload["vintage"]
    doc = {
        "version": 1,
        "vintage": {"roads": vintage, "rail": vintage, "ports": ports_src["vintage"],
                    "airports": f"Eurostat avia_paoa {lo}" if lo == hi else f"Eurostat avia_paoa {lo}–{hi}"},
        "sources": ["natural_earth_roads", "ports", "airports", "geonames"],
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
    r0 = sum(1 for r in rail if r[2] == 0)
    print(f"    roads: {n0} motorway + {len(roads) - n0} major-road links on {len(road_cells)} of {land} land hexes; "
          f"rail: {r0} main + {len(rail) - r0} secondary links on {len(rail_cells)} hexes")
    print(f"    ports: {len(ports)} placed (>= {PORT_MIN_TONS:,} t), {len(ports_missing)} left out (no position, or "
          f"no hex of their country within reach){': ' + '; '.join(ports_missing) if ports_missing else ''}; "
          f"{ports_small} smaller ports not drawn")
    print(f"    airports: {len(airports)} placed (>= {AIRPORT_MIN:,} passengers), {len(air_missing)} left out (no "
          f"hex of their country within reach: small islands, Svalbard, Saint-Martin)"
          f"{': ' + '; '.join(air_missing) if air_missing else ''}")
    no_air = sorted(set(COUNTRIES) - {a["state"] for a in airports})
    if no_air:
        print(f"    countries without an airport on the map: {', '.join(no_air)}")


# ------------------------------------------------------------------ check


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
    g = world["grid"]
    grid = HexGrid(g["radius"], g["cols"], g["rows"])
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
            return "no end on a map country"
        if len(owner) == n and FOREIGN in (owner[a], owner[b]):
            return "foreign end"
        if not 0 <= c < ncls:
            return "class"
        return None

    for key, ncls in (("roads", len(doc["road_classes"])), ("rail", len(doc.get("rail_tiers") or [0, 1]))):
        links = doc[key]
        bad = [(link, why) for link in links if (why := bad_link(link, ncls))]
        pairs = [tuple(link[:2]) for link in links if isinstance(link, list)]
        dup = len(pairs) - len(set(pairs))
        if bad or dup:
            out.append(("FAIL", f"infrastructure.json {key}: {len(bad)} bad links (e.g. {bad[:2]}), {dup} duplicates"))
        else:
            cells = {c for link in links for c in link[:2]}
            out.append(("PASS", f"infrastructure.json {key}: {len(links)} neighbour links on {len(cells)} hexes"))
    if any(not (r[3] is None or isinstance(r[3], str)) for r in doc["roads"] if len(r) > 3):
        out.append(("FAIL", "infrastructure.json roads: route name must be a string or null"))

    states = world.get("states") or []
    state_codes = [s.get("fips") if isinstance(s, dict) else s for s in states]

    def check_sites(key, num_keys):
        probs = []
        for s in doc[key]:
            c = s.get("cell")
            if not isinstance(c, int) or not 0 <= c < n or (len(owner) == n and owner[c] < 0):
                probs.append(f"{s.get('id')}: cell {c!r} is not on a map country")
                continue
            if any(s.get(k) is not None and not isinstance(s.get(k), (int, float)) for k in num_keys):
                probs.append(f"{s.get('id')}: non-numeric value")
            cx, cy = grid.center(*grid.col_row(c))
            if not all(isinstance(s.get(k), (int, float)) for k in ("x", "y")) or \
                    math.dist((cx, cy), (s["x"], s["y"])) > (FAR_RINGS + 1) * g["radius"] * 2:
                probs.append(f"{s.get('id')}: x/y far from its cell")
            if s.get("state") not in COUNTRIES:
                probs.append(f"{s.get('id')}: unknown country {s.get('state')!r}")
            elif len(owner) == n and len(state_codes) > owner[c] and state_codes[owner[c]] not in (None, s["state"]):
                probs.append(f"{s.get('id')}: cell in {state_codes[owner[c]]}, site in {s['state']}")
            if s.get("county") is not None and county_ids and s["county"] not in county_ids:
                probs.append(f"{s.get('id')}: unknown NUTS 3 region {s['county']}")
            if s.get("cbsa") is not None and city_ids is not None and s["cbsa"] not in city_ids:
                probs.append(f"{s.get('id')}: unknown urban area {s['cbsa']}")
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
            out.append(("PASS", f"infrastructure.json {key}: {len(doc[key])} sites, {metro} in a mapped urban area"))
    hubs = Counter(a.get("hub") for a in doc["airports"])
    out.append(("NOTE", "infrastructure.json airports by hub: " + ", ".join(f"{k or 'cargo-only'} {v}" for k, v in
                                                                         sorted(hubs.items(), key=lambda kv: str(kv[0])))))
    size = path.stat().st_size
    if size > 450_000:  # 38 countries' roads, rails, ports and airports: about 90 kB compressed
        out.append(("WARN", f"infrastructure.json is {size / 1e3:.0f} kB (keep this eager file under ~450 kB)"))
    return out
