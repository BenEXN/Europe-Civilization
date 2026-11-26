"""The map itself: hex grid, land/water, relief, land cover, countries, NUTS 3 regions, rivers.

The map's "states" are the countries (EU, EFTA and Western Balkans, core/europe.py) and its "counties" are the NUTS 3
regions. Also saves interim "_world" (grid + projection + per-cell country/region/urban area/water/cover) so the other
builders can drop their data onto the same hexes.
"""

from __future__ import annotations

import math
from collections import Counter

from ..core.europe import COUNTRIES, GEO_LABELS, INSETS, inset_of_nuts
from ..core.geo import SCALE, Laea3035, MapProjection, Shape, ShapeIndex
from ..core.hexgrid import SQRT3, HexGrid
from ..core.paths import INTERIM
from ..core.store import load_interim, save_interim, write_web

REQUIRES = ["gisco", "natural_earth", "etopo", "corine_eu", "clc_dom"]
PRODUCES = ["_world", "world.json"]

HEX_RADIUS_KM = 25.0  # map units (1 / SCALE real km each: 10 km)
MARGIN_KM = 400.0  # map units (160 km of sea and neighbouring land around the map's countries)

# Cell owner codes (besides state index >= 0)
WATER, FOREIGN = -1, -2

# --- tables (written to world.json so the frontend and Almanac read one definition) ---------

LAND, OCEAN, COAST, LAKE = range(4)
TIDAL_SEA_SHARE = 0.5  # share of ETOPO samples below 0 m that keeps a sea-centred hex as water
COAST_DEPTH_M = -200
WATER_TABLE = [
    {"id": LAND, "name": "Land", "rule": "At least 4 of the hex's 7 sample points (centre + 6) fall in a NUTS 3 region or a neighbouring country (GISCO outlines), unless the centre is sea and the ETOPO1 mean is at or below sea level, or at least half its ETOPO1 samples are (bays and estuaries stay water)."},
    {"id": OCEAN, "name": "Ocean", "color": "#1b4266", "rule": "Sea deeper than 200 m and not next to land."},
    {"id": COAST, "name": "Coast", "color": "#2d6d97", "rule": "Sea next to a land hex, or shallower than 200 m (ETOPO1 mean)."},
    {"id": LAKE, "name": "Lake", "color": "#3a80b0", "rule": "Water hex (most of its 7 sample points off land) with Natural Earth 1:10m lake points that outnumber sea points, or above sea level."},
]

WATER_NOTE = (
    "GISCO's 1:3 million outlines and ETOPO1 do not meet exactly. A sea hex whose ETOPO1 mean is above sea level (and "
    "with fewer than half its samples below) becomes land when at least 4 of its 6 neighbours are land, or when it "
    "touches both a map country and a neighbouring country; it takes its neighbours' majority owner. Reservoirs "
    "narrower than half a hex stay land and their river crosses them. A sea hex's elevation is the mean of its ETOPO1 "
    "samples below sea level (its depth)."
)

FLAT, HILLS, MOUNTAINS, PEAKS = range(4)
LAND_MIN_ALT_M = -100  # ETOPO samples below this inside a land hex are treated as sea floor
# Hexes are 10 km in radius here (25 km in usaciv), so the roughness thresholds are lower for the same terrain.
HILLS_STD, MOUNTAINS_STD, MOUNTAINS_MEAN, PEAKS_MEAN = 55, 190, 1500, 2100
RELIEF_TABLE = [
    {"id": FLAT, "name": "Flat", "rule": f"Elevation standard deviation inside the hex under {HILLS_STD} m."},
    {"id": HILLS, "name": "Hills", "rule": f"Elevation standard deviation ≥ {HILLS_STD} m."},
    {"id": MOUNTAINS, "name": "Mountains", "rule": f"Elevation standard deviation ≥ {MOUNTAINS_STD} m, or mean elevation ≥ {MOUNTAINS_MEAN:,} m."},
    {"id": PEAKS, "name": "Peaks", "rule": f"Mean elevation ≥ {PEAKS_MEAN:,} m (alpine)."},
]
RELIEF_NOTE = (
    "From ETOPO1 points (one every two arc-minutes, about 3.7 km, some thirty per hex) at or above -100 m, so bays "
    "and sea floor do not count; all points are used if none qualifies. Water hexes are always flat."
)

URBAN_MIN_PCT = 30
# id, key, name, colour, NLCD-like codes (see sources/corine_eu.py), rule. Ids are fixed by docs/DATA_CONTRACTS.md.
COVER = [
    (1, "forest_deciduous", "Broadleaf forest", "#4f7a35", [41], "Forest (311+312+313) dominates and broadleaf (311) is its largest part."),
    (2, "forest_evergreen", "Coniferous forest", "#2f5a3a", [42], "Forest dominates and conifers (312) are its largest part."),
    (3, "forest_mixed", "Mixed forest", "#43703f", [43], "Forest dominates and mixed forest (313) is its largest part."),
    (4, "scrub", "Heath and scrub", "#c9b07a", [52], "Moors, heathland, maquis, garrigue and transitional woodland (322, 323, 324, 334) dominate."),
    (5, "grassland", "Grassland", "#a9b35a", [71, 21], "Natural grassland, sparse vegetation (321, 333) and green urban areas (141, 142) dominate."),
    (6, "pasture", "Pasture and mixed farming", "#8fb04e", [81], "Pastures (231), complex cultivation patterns, farmland with natural areas and agro-forestry (242, 243, 244) dominate."),
    (7, "cropland", "Cropland", "#c2b84e", [82], "Arable land, rice fields, vineyards, orchards, olive groves and associated annual crops (211-223, 241) dominate."),
    (8, "wetland", "Wetland", "#4f8a6e", [95], "Marshes, peat bogs, salines and intertidal flats (411-423) dominate."),
    (9, "urban", "Urban", "#8a8378", [22, 23, 24], f"Built-up land (111-133) covers at least {URBAN_MIN_PCT}% of the hex's land, whatever else there is."),
    (10, "barren", "Rock and sand", "#bfae95", [31], "Bare rock, beaches and dunes, mineral extraction (331, 332, 131) dominate."),
    (11, "ice", "Glaciers and snow", "#e8eef2", [12], "Glaciers and perpetual snow (335) dominate."),
]
COVER_NOTE = (
    "From OpenGeoHub's 2018 land-cover map in the CORINE nomenclature (its ~480 m overview), sampled on a ~800 m "
    "lattice in every hex of the map's countries (about 400 points), and CORINE Land Cover 2018 for the French "
    "overseas regions. Water (511-523) and no-data pixels are ignored; shares are of the remaining land points, "
    "rounded to the percent, and the urban threshold applies to the rounded built-up share. Neighbouring countries "
    "(Turkey, Ukraine…) have no land cover (0)."
)
# Groups competing for the dominant cover (urban is decided by its threshold first).
GROUPS = {
    "forest": (41, 42, 43), "scrub": (52,), "grassland": (71, 21), "pasture": (81,), "cropland": (82,),
    "wetland": (90, 95), "barren": (31,), "ice": (12,),
}
FOREST_ID = {41: 1, 42: 2, 43: 3}
GROUP_ID = {"scrub": 4, "grassland": 5, "pasture": 6, "cropland": 7, "wetland": 8, "barren": 10, "ice": 11}
URBAN_ID = 9
PCT = {
    "forest": (41, 42, 43), "crop": (82,), "pasture": (81,), "grass": (71, 21), "shrub": (52,),
    "wetland": (90, 95), "developed": (22, 23, 24),
}
RIVER_MAX_RANK = 12  # Natural Earth scalerank
FOREIGN_RIVER_MAX_RANK = 6  # rivers drawn across neighbouring countries
RIVER_NAMES = {"Rhne": "Rhône", "Sane": "Saône", "Rhein": "Rhine", "Donau": "Danube", "Wisla": "Vistula",
               "Odra": "Oder", "Tevere": "Tiber", "Tajo": "Tagus", "Tejo": "Tagus", "Duero": "Douro"}
NLCD_STEP_KM = 2.0  # map units between land-cover sample points (about 800 m)
def classify_relief(mean: float, std: float) -> int:
    if mean >= PEAKS_MEAN:
        return PEAKS
    if std >= MOUNTAINS_STD or mean >= MOUNTAINS_MEAN:
        return MOUNTAINS
    if std >= HILLS_STD:
        return HILLS
    return FLAT


def is_valley_floor(samples: list) -> bool:
    """True when the lower 60% of a hex's land samples is flat lowland (within 60 m, under 400 m): the hex is mostly
    valley floor even if a range at its edge makes the whole hex's spread look hilly or mountainous."""
    if len(samples) < 6:
        return False
    v = sorted(samples)
    lo = v[: max(3, int(len(v) * 0.6))]
    return lo[-1] < 400 and lo[-1] - lo[0] < 60


def dominant_cover(counts: Counter, land: int) -> int:
    """Cover id for a hex from its NLCD class counts (land = points that are not water or no-data)."""
    if not land:
        return 0
    if round(100 * sum(counts[c] for c in (22, 23, 24)) / land) >= URBAN_MIN_PCT:  # same rounding as pct.developed
        return URBAN_ID
    best, best_n = None, 0
    for g, codes in GROUPS.items():  # dict order breaks ties
        n = sum(counts[c] for c in codes)
        if n > best_n:
            best, best_n = g, n
    if best is None:
        return 0  # only developed land below the urban threshold
    if best == "forest":
        return FOREST_ID[max((41, 42, 43), key=lambda c: counts[c])]
    return GROUP_ID[best]


def simplify(points: list[tuple[float, float]], min_km: float) -> list[tuple[float, float]]:
    out = [points[0]]
    for p in points[1:-1]:
        if math.dist(p, out[-1]) >= min_km:
            out.append(p)
    out.append(points[-1])
    return out


def clip_segment(p, q, w, h):
    """Liang–Barsky: the part of segment p→q inside [0,w]×[0,h], or None."""
    (x0, y0), (x1, y1) = p, q
    dx, dy = x1 - x0, y1 - y0
    t0, t1 = 0.0, 1.0
    for pk, qk in ((-dx, x0), (dx, w - x0), (-dy, y0), (dy, h - y0)):
        if pk == 0:
            if qk < 0:
                return None
            continue
        t = qk / pk
        if pk < 0:
            t0 = max(t0, t)
        else:
            t1 = min(t1, t)
        if t0 > t1:
            return None
    return (x0 + t0 * dx, y0 + t0 * dy), (x0 + t1 * dx, y0 + t1 * dy)


def clip_polyline(pts, w, h) -> list[list[tuple[float, float]]]:
    """Split a polyline into the pieces that lie inside the map rectangle."""
    pieces, cur = [], []
    for p, q in zip(pts, pts[1:]):
        seg = clip_segment(p, q, w, h)
        if seg is None:
            if len(cur) >= 2:
                pieces.append(cur)
            cur = []
            continue
        a, b = seg
        if cur and math.dist(cur[-1], a) < 1e-9:
            cur.append(b)
        else:
            if len(cur) >= 2:
                pieces.append(cur)
            cur = [a, b]
        if b != q:  # left the map inside this segment
            pieces.append(cur)
            cur = []
    if len(cur) >= 2:
        pieces.append(cur)
    return pieces


def land_runs(pts, is_land, step: float = 2.0) -> list[list[tuple[float, float]]]:
    """Split a projected polyline (densified every `step` km) into the runs whose points satisfy is_land."""
    runs, cur = [], []
    for k, (p, q) in enumerate(zip(pts, pts[1:])):
        n = max(1, math.ceil(math.dist(p, q) / step))
        for j in range(0 if k == 0 else 1, n + 1):
            t = j / n
            pt = (p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1]))
            if is_land(pt):
                cur.append(pt)
            else:
                if len(cur) >= 2:
                    runs.append(cur)
                cur = []
    if len(cur) >= 2:
        runs.append(cur)
    return runs


def join_lines(lines: list[list[tuple[float, float]]], tol: float = 0.5) -> list[list[tuple[float, float]]]:
    """Greedily join polylines whose ends meet (within `tol` km), reversing pieces as needed."""
    lines = [list(l) for l in lines]
    joined = True
    while joined:
        joined = False
        for a in range(len(lines)):
            for b in range(len(lines)):
                if a == b or not lines[a] or not lines[b]:
                    continue
                la, lb = lines[a], lines[b]
                for la2, lb2 in ((la, lb), (la, lb[::-1]), (la[::-1], lb), (la[::-1], lb[::-1])):
                    if math.dist(la2[-1], lb2[0]) <= tol:
                        lines[a] = la2 + lb2[1:]
                        lines[b] = []
                        joined = True
                        break
        lines = [l for l in lines if l]
    return lines


def chain_lines(lines: list[list[tuple]]) -> list[list[tuple]]:
    """Join segments that share an end point into the longest chains, using end-point lookups (fast on thousands of
    segments, where join_lines' pairwise search is not)."""
    pool = {k: list(l) for k, l in enumerate(lines) if len(l) >= 2}
    starts: dict = {}
    ends: dict = {}
    for k, l in pool.items():
        starts.setdefault(l[0], set()).add(k)
        ends.setdefault(l[-1], set()).add(k)

    def take(k):
        l = pool.pop(k)
        starts[l[0]].discard(k)
        ends[l[-1]].discard(k)
        return l

    out = []
    while pool:
        cur = take(next(iter(pool)))
        grew = True
        while grew:
            grew = False
            tail, head = cur[-1], cur[0]
            if starts.get(tail):
                cur += take(next(iter(starts[tail])))[1:]
                grew = True
            elif ends.get(tail):
                cur += take(next(iter(ends[tail])))[::-1][1:]
                grew = True
            elif ends.get(head):
                cur = take(next(iter(ends[head]))) + cur[1:]
                grew = True
            elif starts.get(head):
                cur = take(next(iter(starts[head])))[::-1] + cur[1:]
                grew = True
        out.append(cur)
    return out


def river_rank(wide: bool, km: float) -> int | None:
    """Drawing rank of a French river (1 = widest) from its length within the map's 15 m+ network (BD CARTO); the
    widest rank needs a river that also reaches 50 m. None: too short to draw."""
    if km >= 450 and wide:
        return 2
    return 3 if km >= 250 else 4 if km >= 120 else 5 if km >= 60 else 6 if km >= 30 else None


def hex_lattice(radius: float, step: float) -> list[tuple[float, float]]:
    """Offsets of a square lattice (spacing `step`) that fall inside a pointy-top hex."""
    half_w = SQRT3 / 2 * radius
    n = int(radius // step) + 1
    out = []
    for iy in range(-n, n + 1):
        for ix in range(-n, n + 1):
            x, y = (ix + 0.5) * step, (iy + 0.5) * step
            if abs(x) <= half_w and abs(y) <= radius - abs(x) / SQRT3:
                out.append((x, y))
    return out


def majority(values: list, centre) -> object:
    """Most common value; ties go to `centre` if it is among the tied, else to the first seen."""
    counts = Counter(values)
    top = max(counts.values())
    tied = [v for v in counts if counts[v] == top]
    return centre if centre in tied else tied[0]


def build() -> None:
    gisco = load_interim("gisco")
    ne = load_interim("natural_earth")
    etopo = load_interim("etopo")
    clc = load_interim("corine_eu")
    dom = load_interim("clc_dom")

    codes = sorted(COUNTRIES, key=lambda c: COUNTRIES[c][0])  # states in alphabetical order of their English names
    states = [{"fips": c, "abbr": c, "name": COUNTRIES[c][0], "region": COUNTRIES[c][2]} for c in codes]
    state_k = {c: k for k, c in enumerate(codes)}
    counties = sorted((n for n in gisco["nuts"] if n.get("county")), key=lambda n: n["code"])
    counties = [{"geoid": n["code"], "name": n["name"], "state_fips": n["country"], "rings": n["rings"]} for n in counties]
    county_state_k = [state_k[c["state_fips"]] for c in counties]

    # Projection: fit the main map (every region outside the insets) with a margin.
    probe = MapProjection(0, 0, 0)
    xs, ys = [], []
    for c in counties:
        if inset_of_nuts(c["geoid"]):
            continue
        for ring in c["rings"]:
            for lon, lat in ring:
                x, y = probe._albers(lon, lat)
                xs.append(x)
                ys.append(y)
    proj = MapProjection(min(xs), max(ys), MARGIN_KM, insets=INSETS)
    width = (max(xs) - min(xs)) * SCALE + 2 * MARGIN_KM
    height = (max(ys) - min(ys)) * SCALE + 2 * MARGIN_KM
    grid = HexGrid.covering(width, height, HEX_RADIUS_KM)
    print(f"    LAEA x {min(xs):.0f}..{max(xs):.0f} km, y {min(ys):.0f}..{max(ys):.0f} km; map {width:.0f}×{height:.0f} units; "
          f"grid {grid.cols}×{grid.rows} = {grid.size} hexes of {HEX_RADIUS_KM:g} units")

    def shape(rings):
        return Shape([[proj(lon, lat) for lon, lat in r] for r in rings])

    county_idx = ShapeIndex([shape(c["rings"]) for c in counties], cell_km=60)
    foreign_rings = [f["rings"] for f in gisco["foreign"]] + [c["rings"] for c in ne["countries"]]
    foreign_idx = ShapeIndex([shape(r) for r in foreign_rings], cell_km=120)
    lake_idx = ShapeIndex([shape(l["rings"]) for l in ne["lakes"]])
    fuas = sorted(gisco["fuas"], key=lambda f: f["code"])
    fua_idx = ShapeIndex([shape(f["rings"]) for f in fuas], cell_km=60)

    # --- elevation statistics per hex (land samples and all samples) -----------------------------
    stats_all = [[0, 0.0, 0.0] for _ in range(grid.size)]
    stats_land = [[0, 0.0, 0.0] for _ in range(grid.size)]
    samples_land = [[] for _ in range(grid.size)]  # land altitudes, for the peak height and the valley-floor test
    below_sea = [0] * grid.size
    below_sum = [0.0] * grid.size
    for lat, lon, alt in zip(etopo["lat"], etopo["lon"], etopo["alt"]):
        x, y = proj(lon, lat)
        if proj.inset_of(lon, lat) is None and proj.frame_of(x, y) is not None:
            continue  # sea floor under an inset's frame
        i = grid.cell_at(x, y)
        if i < 0:
            continue
        if alt < 0:
            below_sea[i] += 1
            below_sum[i] += alt
        for st in (stats_all[i], stats_land[i]) if alt >= LAND_MIN_ALT_M else (stats_all[i],):
            st[0] += 1
            st[1] += alt
            st[2] += alt * alt
        if alt >= LAND_MIN_ALT_M:
            samples_land[i].append(alt)

    def sea_share(i):
        return below_sea[i] / stats_all[i][0] if stats_all[i][0] else 0.0

    def mean_std(st):
        n, s1, s2 = st
        if not n:
            return None, None
        m = s1 / n
        return m, math.sqrt(max(0.0, s2 / n - m * m))

    # --- ownership: majority of 7 sample points --------------------------------------------------
    # The centre plus six points 60% of the way to each corner. Each point is lake, a NUTS 3 region (hence a
    # country), foreign land or other water; the majority decides (the centre breaks ties). The seven region samples
    # also give an area-weighted region mix for lenses.
    offsets = [(0.0, 0.0)] + [
        (0.6 * HEX_RADIUS_KM * math.cos(math.radians(60 * k - 30)), 0.6 * HEX_RADIUS_KM * math.sin(math.radians(60 * k - 30)))
        for k in range(6)
    ]
    owner = [WATER] * grid.size
    water = [OCEAN] * grid.size
    county_samples: list[list[int]] = [[] for _ in range(grid.size)]
    for i in range(grid.size):
        cx, cy = grid.center(*grid.col_row(i))
        kinds, regions = [], []
        for dx, dy in offsets:
            x, y = cx + dx, cy + dy
            if lake_idx.locate(x, y) >= 0:
                kinds.append("lake")
                regions.append(-1)
            elif (r := county_idx.locate(x, y)) >= 0:
                kinds.append(county_state_k[r])
                regions.append(r)
            elif foreign_idx.locate(x, y) >= 0:
                kinds.append(FOREIGN)
                regions.append(-1)
            else:
                kinds.append("sea")
                regions.append(-1)
        land = [k for k in kinds if not isinstance(k, str)]
        m_all, _ = mean_std(stats_all[i])
        tidal = kinds[0] == "sea" and m_all is not None and (m_all <= 0 or sea_share(i) >= TIDAL_SEA_SHARE)
        if len(land) * 2 > len(kinds) and not tidal:
            mine = [k for k in land if k >= 0]
            n_foreign = len(land) - len(mine)
            if len(mine) > n_foreign or (len(mine) == n_foreign and kinds[0] != FOREIGN):
                owner[i] = majority(mine, kinds[0])
                county_samples[i] = regions
            else:
                owner[i] = FOREIGN
            water[i] = LAND
        else:
            wet = [k for k in kinds if isinstance(k, str)]
            above_sea = m_all is not None and m_all > 0
            lakeish = "lake" in wet and (above_sea or majority(wet, kinds[0] if kinds[0] in wet else "lake") == "lake")
            water[i] = LAKE if lakeish else OCEAN

    # Sliver fix: a non-lake water hex whose ETOPO mean is above sea level becomes land if at least 4 of its
    # neighbours are land, or if it touches both a map country and foreign land; it takes its land neighbours'
    # majority owner.
    slivers = []
    for i in range(grid.size):
        if water[i] != OCEAN:
            continue
        m, _ = mean_std(stats_all[i])
        land_nb = [owner[j] for j in grid.neighbours(i) if water[j] == LAND]
        border = FOREIGN in land_nb and any(o >= 0 for o in land_nb)
        if m is not None and m > 0 and sea_share(i) < TIDAL_SEA_SHARE and (len(land_nb) >= 4 or border):
            slivers.append((i, Counter(land_nb).most_common(1)[0][0]))
    for i, o in slivers:
        owner[i], water[i] = o, LAND
    print(f"    {len(slivers)} sliver water hexes turned into land")

    # Every city centre stands on its own hex: a coastal or island centre whose hex came out as water or as the
    # next country's gets that hex as land of its own country, so the city is drawn where it is. Smaller urban
    # areas first, so when two centres share a hex the bigger one keeps it (sizes: the FUA's outline area).
    fua_area = {f["code"]: sum(abs(sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(r, r[1:] + r[:1]))) for r in f["rings"])
                for f in fuas}
    anchored = []
    centres = [c for c in gisco["cities"] if c["country"] in state_k and c["fua"]]
    for c in sorted(centres, key=lambda c: fua_area.get(c["fua"], 0)):
        k, dk = grid.cell_at(*proj(c["lon"], c["lat"])), state_k[c["country"]]
        if k < 0 or (water[k] == LAND and owner[k] == dk):
            continue
        anchored.append((c["name"], "water" if water[k] != LAND else "abroad" if owner[k] < 0 else codes[owner[k]]))
        owner[k], water[k] = dk, LAND
        r = county_idx.locate(*proj(c["lon"], c["lat"]))
        if r >= 0 and county_state_k[r] == dk:
            county_samples[k] = [r] * 7 if not county_samples[k] else [r] + county_samples[k][1:]
    print(f"    {len(anchored)} city-centre hexes given to their country: {anchored[:12]}{' …' if len(anchored) > 12 else ''}")

    # A country smaller than a hex (Liechtenstein, Malta at worst) would own none: give it the land hex under its
    # largest region's centre.
    owned = Counter(o for o in owner if o >= 0)
    for k, code in enumerate(codes):
        if owned[k]:
            continue
        mine = [j for j, c in enumerate(counties) if c["state_fips"] == code]
        ring = max((r for j in mine for r in counties[j]["rings"]), key=len)
        lon = sum(p[0] for p in ring) / len(ring)
        lat = sum(p[1] for p in ring) / len(ring)
        c = grid.cell_at(*proj(lon, lat))
        if c >= 0:
            owner[c], water[c] = k, LAND
            county_samples[c] = [mine[0]] * 7
            print(f"    {states[k]['name']} owns no hex by majority: given hex {c} under its centre")

    # --- regions (NUTS 3) per cell ----------------------------------------------------------------
    county = [-1] * grid.size
    borrowed = 0
    for i in range(grid.size):
        if owner[i] < 0:
            county_samples[i] = []
            continue
        smp = county_samples[i]
        if not smp or max(smp) < 0:
            nb = [k for j in grid.neighbours(i) if owner[j] == owner[i] for k in county_samples[j] if k >= 0]
            if nb:
                county_samples[i] = smp = ([Counter(nb).most_common(1)[0][0]] + (smp[1:] if smp else [-1] * 6))
                borrowed += 1
    # The hex's region must lie in its owner country: the centre if it does, else the most common in-country sample,
    # else any sample.
    off_state = 0
    for i, smp in enumerate(county_samples):
        valid = [k for k in smp if k >= 0]
        if not valid:
            continue
        same = [k for k in valid if county_state_k[k] == owner[i]]
        pool = same or valid
        county[i] = smp[0] if smp[0] in pool else Counter(pool).most_common(1)[0][0]
        off_state += not same
    print(f"    {borrowed} hexes borrowed a neighbour's region; {off_state} have no region in their own country")

    # Functional urban areas under the seven sample points.
    fua_samples: list[list[int]] = [[] for _ in range(grid.size)]
    for i in range(grid.size):
        if owner[i] >= 0:
            cx, cy = grid.center(*grid.col_row(i))
            fua_samples[i] = [fua_idx.locate(cx + dx, cy + dy) for dx, dy in offsets]

    # --- elevation, water depth classes and relief -------------------------------------------------
    elev = [0] * grid.size
    relief = [FLAT] * grid.size
    elev_max = [0] * grid.size
    valley_floor = no_elev = 0
    for i in range(grid.size):
        if water[i] == LAND:
            m, sd = mean_std(stats_land[i])
            if m is None:
                m, sd = mean_std(stats_all[i])
                m = None if m is None else max(m, 0.0)
            if m is None:
                no_elev += 1
                continue
            elev[i] = round(m)
            relief[i] = classify_relief(max(m, 0.0), sd)
            if relief[i] in (HILLS, MOUNTAINS) and is_valley_floor(samples_land[i]):
                relief[i] -= 1
                valley_floor += 1
            if samples_land[i]:
                elev_max[i] = max(0, round(max(samples_land[i])))
        else:
            m, _ = mean_std(stats_all[i])
            if m is None:
                no_elev += 1
                elev[i] = -4000
            elif water[i] != LAKE and below_sea[i]:
                elev[i] = round(below_sum[i] / below_sea[i])
            else:
                elev[i] = min(round(m), 0)
            if water[i] == OCEAN:
                near_land = any(water[j] == LAND for j in grid.neighbours(i))
                water[i] = COAST if near_land or elev[i] > COAST_DEPTH_M else OCEAN
    print(f"    {no_elev} hexes without elevation samples; {valley_floor} valley-floor hexes eased one relief class")

    # --- land cover ----------------------------------------------------------------------------------
    raster = (INTERIM / clc["raster"]).read_bytes()
    rw, rh, px = clc["width"], clc["height"], clc["pixel"]
    rx0, ry0 = clc["x0"], clc["y0"]
    code_of = {int(v): c for v, c in clc["values"].items()}
    to_nlcd = {int(k): v for k, v in clc["nlcd"].items()}
    laea = Laea3035()
    dom_raster = {r["dep"]: r for r in dom["rasters"]}
    clc_hex: list[dict] = [None] * grid.size
    lattice = hex_lattice(HEX_RADIUS_KM, NLCD_STEP_KM)
    cover = [0] * grid.size
    pct = {k: [0] * grid.size for k in PCT}
    no_cover = 0
    for i in range(grid.size):
        if owner[i] < 0:
            continue
        cx, cy = grid.center(*grid.col_row(i))
        codes_here: Counter = Counter()
        ins = proj.frame_of(cx, cy)
        rs = dom_raster.get(ins.d["dep"]) if ins is not None else None
        for ox, oy in lattice:
            lon, lat = proj.inverse(cx + ox, cy + oy)
            if rs is not None:
                c, r = round((lon - rs["x0"]) / rs["dx"]), round((lat - rs["y0"]) / rs["dy"])
                if 0 <= r < len(rs["rows"]) and 0 <= c < rs["cols"]:
                    code = rs["rows"][r][c]
                    if code:
                        codes_here[code] += 1
                continue
            X, Y = laea(lon, lat)
            c, r = int((X - rx0) / px), int((ry0 - Y) / px)
            if 0 <= c < rw and 0 <= r < rh:
                code = code_of.get(raster[r * rw + c])
                if code:
                    codes_here[code] += 1
        clc_hex[i] = dict(codes_here)
        counts: Counter = Counter()
        for code, n in codes_here.items():
            counts[to_nlcd.get(code, 0)] += n
        land = sum(n for code, n in counts.items() if code not in (0, 11))
        cover[i] = dominant_cover(counts, land)
        if not land and codes[owner[i]] == "FR" and ins is not None and ins.d["dep"] == "FRY3":
            cover[i] = 1  # CORINE maps only Guyane's coastal strip; the interior is Amazon rainforest
            pct["forest"][i] = 100
            continue
        if not land:
            no_cover += 1
            continue
        for k, grp in PCT.items():
            pct[k][i] = round(100 * sum(counts[c] for c in grp) / land)
    print(f"    {len(lattice)} land-cover points per hex; {no_cover} map hexes without land-cover samples")

    # --- rivers (Natural Earth, with its European supplement) ------------------------------------------
    def on_land(pt):
        c = grid.cell_at(*pt)
        return c >= 0 and water[c] == LAND

    def abroad(pt):
        c = grid.cell_at(*pt)
        return c >= 0 and owner[c] == FOREIGN

    by_river: dict[tuple, list] = {}
    for r in ne["rivers"]:
        if r["rank"] > RIVER_MAX_RANK:
            continue
        line = [proj(lon, lat) for lon, lat in r["line"]]
        if (r.get("featurecla") or "").startswith("Lake Centerline"):
            parts = [run for p in clip_polyline(line, width, height) for run in land_runs(p, on_land)]
        else:
            parts = clip_polyline(line, width, height)
        if r["rank"] > FOREIGN_RIVER_MAX_RANK:  # abroad, only the big rivers: the haze stays calm
            parts = [run for p in parts for run in land_runs(p, lambda pt: not abroad(pt))]
        name = RIVER_NAMES.get(r["name"], r["name"])
        by_river.setdefault((name, r["rank"]), []).extend(parts)
    rivers = []
    for (name, rank), parts in by_river.items():
        for piece in (join_lines(parts) if len(parts) < 300 else chain_lines([[tuple(p) for p in q] for q in parts])):
            if sum(math.dist(a, b) for a, b in zip(piece, piece[1:])) < 1.0:
                continue
            pts = simplify(piece, 4.0)
            if len(pts) >= 2:
                rivers.append({"name": name or "", "rank": int(rank), "pts": [round(v, 1) for p in pts for v in p]})
    print(f"    rivers: {len(rivers)} pieces")

    cover_table = [{"id": 0, "key": "none", "name": "None", "rule": "Water, a neighbouring country, or no land pixel."}] + [
        {"id": cid, "key": key, "name": name, "color": color, "nlcd": cs, "rule": rule}
        for cid, key, name, color, cs, rule in COVER
    ]
    tables = {"water": WATER_TABLE, "relief": RELIEF_TABLE, "cover": cover_table,
              "notes": {"water": WATER_NOTE, "relief": RELIEF_NOTE, "cover": COVER_NOTE}}
    n_land = sum(1 for o in owner if o >= 0)
    print(f"    {n_land} hexes in the map's countries, {sum(1 for o in owner if o == FOREIGN)} foreign land")
    write_web(
        "world.json",
        {
            "version": 2,
            "grid": grid.to_dict(),
            "width": round(width, 1),
            "height": round(height, 1),
            "margin": MARGIN_KM,
            "km_per_unit": round(1 / SCALE, 6),
            "insets": proj.insets_dict(),
            "owner": owner,
            "county": county,
            "elev": elev,
            "elev_max": elev_max,
            "water": water,
            "relief": relief,
            "cover": cover,
            "pct": pct,
            "tables": tables,
            "states": states,
            "counties": [{"geoid": c["geoid"], "name": c["name"]} for c in counties],
            "rivers": rivers,
            # names of seas and mountain ranges: map units, font height in map units, angle in degrees clockwise
            "features": [{"name": n, "kind": k, "x": round(proj(lon, lat)[0], 1), "y": round(proj(lon, lat)[1], 1),
                          "size": round(km * SCALE, 1), "angle": a} for n, k, lon, lat, km, a in GEO_LABELS],
        },
    )
    save_interim(
        "_world",
        {
            "grid": grid.to_dict(),
            "projection": proj.to_dict(),
            "owner": owner,
            "county": county,
            "county_samples": county_samples,
            "states": codes,
            "counties": [c["geoid"] for c in counties],
            "county_state": [c["state_fips"] for c in counties],
            "fuas": [f["code"] for f in fuas],
            "fua_samples": fua_samples,
            "clc": clc_hex,
            "water": water,
            "cover": cover,
            "pct": pct,
        },
    )
