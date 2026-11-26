"""Lenses = per-hex map overlays built from commune and intercommunalité (EPCI) data, and land cover.

Each French hex is sampled at 7 points (see world.py). A commune's population is spread over the hexes in
proportion to how many of all its sample points fall in each hex, so every commune's people are counted once.
Small communes that no sample point hits are added in full to the hex holding their town hall (or the nearest
French land hex). Density = people ÷ the hex's land area; every other lens is the mean of the communes in the hex,
weighted by those people, of the commune's own value where Insee publishes one, else its intercommunalité's.
"""

from __future__ import annotations

import math
from collections import Counter

from ..core.geo import MapProjection
from ..core.hexgrid import HexGrid
from ..core.store import load_interim, write_web
from .cities import nearest_land
from .yields import load_tables

REQUIRES = ["_world", "fr_boundaries", "insee_comparateur", "insee_activite", "insee_diplomes", "insee_population",
            "insee_navettes", "insee_immigration", "catnat", "presidentielle_2022", "meteo_sim", "meteo_lsh"]
PRODUCES = ["lenses.json", "_hexpeople"]

GROUPS = [
    {"id": "people", "name": "Population"},
    {"id": "prosperity", "name": "Prospérité"},
    {"id": "knowledge", "name": "Savoir"},
    {"id": "life", "name": "Vie quotidienne"},
    {"id": "civic", "name": "Vie civique"},
    {"id": "climate", "name": "Climat"},
    {"id": "hazards", "name": "Risques"},
    {"id": "land", "name": "Terre"},
]


def nice(v: float, up: bool) -> float:
    """v rounded outward (up or down) to 2 significant digits."""
    if v == 0:
        return 0
    mag = 10 ** (math.floor(math.log10(abs(v))) - 1)
    return round((math.ceil if up else math.floor)(v / mag) * mag, 10)


def percentile_domain(values: list, log: bool) -> list[float] | None:
    """[2nd, 98th] percentile of the non-null hex values, rounded outward; positive values only on a log scale."""
    vals = sorted(v for v in values if v is not None and (v > 0 or not log))
    if not vals:
        return None
    lo, hi = vals[int(0.02 * (len(vals) - 1))], vals[int(0.98 * (len(vals) - 1))]
    lo, hi = nice(lo, False), nice(hi, True)
    return [lo, hi] if hi > lo else [lo, nice(vals[-1], True)]


DOMAIN_NOTE = " Les couleurs couvrent du 2e au 98e centile des hexagones ; au-delà, les valeurs prennent la couleur extrême."
AGE_BANDS = [("Y_LT15", 0, 15), ("Y15T24", 15, 25), ("Y25T39", 25, 40), ("Y40T54", 40, 55), ("Y55T64", 55, 65),
             ("Y65T79", 65, 80), ("Y_GE80", 80, 95)]


def ratio(num, den):
    return num / den if num is not None and den else None


def median_age(ages: dict) -> float | None:
    """Median age interpolated linearly inside the census age bands (the 80+ band is taken as 80-95)."""
    if not ages or any(b not in ages for b, _, _ in AGE_BANDS):
        return None
    total = sum(ages[b] for b, _, _ in AGE_BANDS)
    if not total:
        return None
    acc = 0.0
    for b, lo, hi in AGE_BANDS:
        n = ages[b]
        if acc + n >= total / 2:
            return lo + (hi - lo) * ((total / 2 - acc) / n if n else 0)
        acc += n
    return None


def commune_value(lid: str, com: dict, code: str | None = None, t: dict | None = None) -> float | None:
    if lid == "vote_macron":
        return vote_share(t["pr2022"].get(code)) if t else None
    if lid == "abstention":
        return abstention(t["pr2022"].get(code)) if t else None
    if lid == "disasters":
        return float(t["catnat"].get(code, {}).get("total", 0)) if t and com else None
    """A lens value from a commune (or EPCI) row of the comparator; None if Insee publishes none there."""
    if lid == "income":
        return com.get("MED_SL_2023")
    if lid == "poverty":
        return com["PR_MD60_2023"] / 100 if com.get("PR_MD60_2023") is not None else None
    if lid == "growth":
        g = ratio(com.get("POP_2023"), com.get("POP_2017"))
        return g - 1 if g is not None else None
    if lid == "homeownership":
        return ratio(com.get("RP_PROP_2023"), com.get("RP_2023"))
    if lid == "second_homes":
        return ratio(com.get("RSEC_2023"), com.get("LOG_2023"))
    if lid == "vacancy":
        return ratio(com.get("LVAC_2023"), com.get("LOG_2023"))
    return None


def epci_value(lid: str, code: str, t: dict) -> float | None:
    if lid in ("income", "poverty", "growth", "homeownership", "second_homes", "vacancy"):
        return commune_value(lid, t["comparateur"]["EPCI"].get(code, {}))
    if lid == "unemployment":
        act = t["activite"]["EPCI"].get(code, {})
        return ratio(act.get("EMPSTA_ENQ=2|AGE=Y15T64|RP_MEASURE=POP"), act.get("EMPSTA_ENQ=1T2|AGE=Y15T64|RP_MEASURE=POP"))
    if lid == "bachelors":
        d = t["diplomes"]["EPCI"].get(code, {})
        return ratio(d.get("500T702_RP"), d.get("_T"))
    if lid == "age":
        return median_age(t["population"]["EPCI"].get(code, {}))
    if lid == "seniors":
        a = t["population"]["EPCI"].get(code, {})
        return ratio(a.get("Y_GE65"), a.get("_T"))
    if lid in ("car", "transit"):
        n = t["navettes"]["EPCI"].get(code, {})
        mode = "5" if lid == "car" else "6"
        return ratio(n.get(f"TRANS={mode}|AGE=Y_GE15|EMPSTA_ENQ=1|RP_MEASURE=POP"), n.get("AGE=Y_GE15|EMPSTA_ENQ=1|RP_MEASURE=POP"))
    if lid == "immigrants":
        im = t["immigration"]["EPCI"].get(code, {})
        return ratio(im.get("IMMI=1|RP_MEASURE=POP"), im.get("RP_MEASURE=POP"))
    if lid in ("vote_macron", "abstention", "disasters"):
        return t["epci_agg"].get(lid, {}).get(code)
    return None


def add_civic(t: dict, bounds: dict) -> None:
    """Commune-level CatNat and 2022 election tables, and their intercommunalité totals, into the source tables."""
    t["catnat"] = load_interim("catnat")["communes"]
    t["pr2022"] = load_interim("presidentielle_2022")["communes"]
    pops = {code: r.get("POP_2023") or 0 for code, r in t["comparateur"]["COM"].items()}
    acc: dict[str, dict[str, float]] = {}
    for c in bounds["communes"]:
        e = c["epci"]
        if not e:
            continue
        a = acc.setdefault(e, {"mac": 0, "exp": 0, "abs": 0, "ins": 0, "dis": 0.0, "pop": 0})
        v = t["pr2022"].get(c["code"])
        if v:
            a["mac"] += v["voix"].get("MACRON", 0)
            a["exp"] += v["exprimes"]
            a["abs"] += v["abstentions"]
            a["ins"] += v["inscrits"]
        p = pops.get(c["code"], 0)
        if p:
            a["dis"] += t["catnat"].get(c["code"], {}).get("total", 0) * p
            a["pop"] += p
    t["epci_agg"] = {
        "vote_macron": {e: ratio(a["mac"], a["exp"]) for e, a in acc.items()},
        "abstention": {e: ratio(a["abs"], a["ins"]) for e, a in acc.items()},
        "disasters": {e: (a["dis"] / a["pop"] if a["pop"] else None) for e, a in acc.items()},
    }


def vote_share(v: dict | None) -> float | None:
    return ratio(v["voix"].get("MACRON"), v["exprimes"]) if v else None


def abstention(v: dict | None) -> float | None:
    return ratio(v["abstentions"], v["inscrits"]) if v else None


HAZARDS = [
    {"id": "flood", "name": "Inondations", "color": "#3f7fc4", "description": "Inondations, coulées de boue et remontées de nappe."},
    {"id": "drought", "name": "Sécheresse", "color": "#d9a441", "description": "Sécheresse : mouvements de terrain liés au retrait-gonflement des argiles."},
    {"id": "ground", "name": "Mouvements de terrain", "color": "#9a6a4a", "description": "Glissements, éboulements, effondrements."},
    {"id": "storm", "name": "Tempête, grêle, neige", "color": "#8a8fb8", "description": "Tempêtes, grêle et poids de la neige."},
    {"id": "sea", "name": "Submersion marine", "color": "#3fb0b0", "description": "Chocs des vagues et submersion marine."},
    {"id": "quake", "name": "Séisme", "color": "#c45a5a", "description": "Secousses sismiques."},
    {"id": "avalanche", "name": "Avalanche", "color": "#e8eef2", "description": "Avalanches."},
]


# Lenses: id → (level: "commune" = the commune's own value, else its EPCI's; "epci" = always the EPCI's; metadata).
LENSES = {
    "growth": ("commune", {
        "group": "people", "name": "Croissance", "icon": "l-growth",
        "unit": "évolution de la population, 2017-2023", "format": "pct", "scale": "linear", "higher_is": "neutral",
        "ramp": ["#5b1a2a", "#a8434a", "#e0a08a", "#f2efe6", "#8fc1b5", "#2f7f86", "#123f52"],
        "description": "Évolution de la population entre les recensements de 2017 et de 2023 (populations "
        "municipales), moyenne des communes de l'hexagone pondérée par leur population.",
    }),
    "age": ("epci", {
        "group": "people", "name": "Âge médian", "icon": "l-age",
        "unit": "ans", "format": "years", "scale": "linear", "higher_is": "neutral",
        "ramp": ["#00224e", "#35456c", "#666970", "#948e77", "#c8b866", "#fee838"],
        "description": "Âge médian des habitants de l'intercommunalité, estimé par interpolation linéaire dans les "
        "tranches d'âge du recensement 2023 (moins de 15 ans, 15-24, 25-39, 40-54, 55-64, 65-79, 80 ans ou plus).",
    }),
    "seniors": ("epci", {
        "group": "people", "name": "Seniors", "icon": "l-age",
        "unit": "part des 65 ans ou plus", "format": "pct", "scale": "linear", "higher_is": "neutral",
        "ramp": ["#0b1d3a", "#2d3f73", "#6a5a8e", "#a8738f", "#dc9a83", "#fbd8a5"],
        "description": "Part des habitants de 65 ans ou plus dans l'intercommunalité (recensement 2023).",
    }),
    "income": ("commune", {
        "group": "prosperity", "name": "Niveau de vie", "icon": "l-income",
        "unit": "niveau de vie médian annuel, €", "format": "usd", "scale": "linear", "higher_is": "good",
        "ramp": ["#3a1c0b", "#7a4413", "#b8781f", "#e3b23c", "#f6e27f", "#fffbe0"],
        "description": "Niveau de vie médian (revenu disponible du ménage par unité de consommation, Filosofi 2023) "
        "de la commune, ou de son intercommunalité quand l'Insee ne le publie pas pour une petite commune ; "
        "moyenne de l'hexagone pondérée par la population.",
    }),
    "poverty": ("epci", {
        "group": "prosperity", "name": "Pauvreté", "icon": "l-poverty",
        "unit": "taux de pauvreté à 60 % du niveau de vie médian", "format": "pct", "scale": "linear",
        "higher_is": "bad",
        "ramp": ["#03051a", "#4c1d4b", "#a11a5b", "#e83f3f", "#f69c73", "#faebdd"],
        "description": "Part des habitants dont le niveau de vie est inférieur à 60 % du niveau de vie médian "
        "national (Filosofi 2023), par intercommunalité.",
    }),
    "unemployment": ("epci", {
        "group": "prosperity", "name": "Chômage", "icon": "l-unemployment",
        "unit": "chômeurs parmi les actifs de 15 à 64 ans", "format": "pct", "scale": "linear", "higher_is": "bad",
        "ramp": ["#0d1b2a", "#1b3a4b", "#3e5c76", "#8d6a9f", "#d17a8c", "#f6c5a0"],
        "note": "Chômage au sens du recensement (déclaratif), plus élevé que le taux au sens du BIT.",
        "description": "Part des chômeurs parmi les actifs de 15 à 64 ans de l'intercommunalité, au sens du "
        "recensement 2023 (les personnes se déclarent chômeuses).",
    }),
    "bachelors": ("epci", {
        "group": "knowledge", "name": "Diplômés du supérieur", "icon": "l-degrees",
        "unit": "part des diplômés du supérieur", "format": "pct", "scale": "linear", "higher_is": "good",
        "ramp": ["#08203e", "#0f4c81", "#2a7fc1", "#5fa8e0", "#a6d1f2", "#eaf5ff"],
        "description": "Part des diplômés de l'enseignement supérieur (bac+2 ou plus) parmi la population non "
        "scolarisée de 15 ans ou plus de l'intercommunalité (recensement 2023).",
    }),
    "homeownership": ("commune", {
        "group": "life", "name": "Propriétaires", "icon": "l-homeownership",
        "unit": "résidences principales occupées par leur propriétaire", "format": "pct", "scale": "linear",
        "higher_is": "neutral",
        "ramp": ["#1c1a05", "#45410f", "#76701d", "#a8a033", "#d4ce62", "#f8f6c4"],
        "description": "Part des résidences principales occupées par leur propriétaire (recensement 2023).",
    }),
    "second_homes": ("commune", {
        "group": "life", "name": "Résidences secondaires", "icon": "l-home",
        "unit": "part des logements", "format": "pct", "scale": "linear", "higher_is": "neutral",
        "ramp": ["#0b1d2e", "#123d5c", "#1f6f8b", "#47a3a8", "#9fd3c1", "#f3f7d8"],
        "description": "Part des résidences secondaires et logements occasionnels parmi tous les logements "
        "(recensement 2023) : les côtes et les montagnes touristiques ressortent.",
    }),
    "vacancy": ("commune", {
        "group": "life", "name": "Logements vacants", "icon": "l-home",
        "unit": "part des logements", "format": "pct", "scale": "linear", "higher_is": "bad",
        "ramp": ["#101418", "#2a2f3a", "#4d4a5c", "#80697a", "#b98d87", "#ebc6a6"],
        "description": "Part des logements vacants parmi tous les logements (recensement 2023).",
    }),
    "immigrants": ("epci", {
        "group": "people", "name": "Immigrés", "icon": "l-foreign-born",
        "unit": "part des habitants nés étrangers à l'étranger", "format": "pct", "scale": "linear", "higher_is": "neutral",
        "ramp": ["#0b0405", "#382a54", "#395d9c", "#3497a9", "#60ceac", "#def5e5"],
        "description": "Part des immigrés (personnes nées étrangères à l'étranger, au sens de l'Insee) parmi les "
        "habitants de l'intercommunalité (recensement 2023).",
    }),
    "car": ("epci", {
        "group": "life", "name": "Voiture", "icon": "l-commute",
        "unit": "actifs qui vont travailler en voiture", "format": "pct", "scale": "linear", "higher_is": "neutral",
        "ramp": ["#2b0b1e", "#5e1742", "#93275f", "#c84f7c", "#ea8fa8", "#fbd9e1"],
        "description": "Part des actifs occupés dont la voiture (ou un camion, une fourgonnette) est le mode de "
        "transport principal pour aller travailler (recensement 2023), par intercommunalité.",
    }),
    "transit": ("epci", {
        "group": "life", "name": "Transports en commun", "icon": "l-commute",
        "unit": "actifs qui vont travailler en transports en commun", "format": "pct", "scale": "log", "higher_is": "neutral",
        "ramp": ["#0d1b2a", "#1b3a4b", "#1f6f8b", "#3fa3a8", "#9fd3c1", "#f3f7d8"],
        "description": "Part des actifs occupés dont les transports en commun sont le mode principal pour aller "
        "travailler (recensement 2023), par intercommunalité.",
    }),
    "vote_macron": ("commune", {
        "group": "civic", "name": "Présidentielle 2022", "icon": "l-vote",
        "unit": "part des suffrages exprimés pour E. Macron au 2nd tour", "format": "pct", "scale": "linear",
        "higher_is": "neutral",
        "ramp": ["#2a4d8f", "#5f82bf", "#b9c8e2", "#f1eee6", "#d9bfa6", "#b07a4f", "#6e4a2a"][::-1],
        "note": "Second tour du 24 avril 2022 : E. Macron contre M. Le Pen ; la part de M. Le Pen est le complément à 100 %.",
        "description": "Part des suffrages exprimés pour Emmanuel Macron au second tour de l'élection présidentielle "
        "du 24 avril 2022 (résultats définitifs du ministère de l'Intérieur), commune par commune, moyenne de "
        "l'hexagone pondérée par la population. Les communes fusionnées depuis 2022 n'ont pas de valeur.",
    }),
    "abstention": ("commune", {
        "group": "civic", "name": "Abstention", "icon": "l-abstention",
        "unit": "part des inscrits qui n'ont pas voté (2nd tour 2022)", "format": "pct", "scale": "linear",
        "higher_is": "bad",
        "ramp": ["#0f1a12", "#24402a", "#4a6b3a", "#8a9a4a", "#cfc06a", "#f6eeb0"],
        "description": "Part des inscrits qui ne sont pas allés voter au second tour de la présidentielle 2022.",
    }),
    "disasters": ("commune", {
        "group": "hazards", "name": "Catastrophes naturelles", "icon": "l-disasters",
        "unit": "arrêtés CatNat depuis 2000", "format": "int", "scale": "linear", "higher_is": "bad",
        "ramp": ["#14161f", "#2e2a4a", "#5b3466", "#93405f", "#cf6a4a", "#f4b860"],
        "note": "Un arrêté CatNat est un acte administratif qui ouvre l'indemnisation, pas une mesure des dégâts.",
        "description": "Nombre d'arrêtés de reconnaissance de l'état de catastrophe naturelle (« CatNat ») publiés pour "
        "la commune depuis le 1er janvier 2000 (base GASPAR), chaque arrêté et chaque risque comptés une fois ; "
        "moyenne de l'hexagone pondérée par la population.",
    }),
}
# Land lenses from the world builder's per-hex land-cover shares (CORINE), 0..100 → 0..1.
LAND_LENSES = {
    "forest": (["forest"], {
        "name": "Forêt", "icon": "l-forest",
        "ramp": ["#0b1f0f", "#14401c", "#1f6b2b", "#3a9443", "#7fc07a", "#d5efcd"],
        "description": "Part des terres de l'hexagone couvertes de forêts de feuillus, de conifères ou mélangées "
        "(CORINE Land Cover 2018, postes 311 à 313).",
    }),
    "farmland": (["crop", "pasture"], {
        "name": "Terres agricoles", "icon": "l-farmland",
        "ramp": ["#141d05", "#2f4510", "#557019", "#84a02a", "#b8cf55", "#eef7b8"],
        "description": "Part des terres de l'hexagone en cultures, vignes, vergers, prairies et bocage "
        "(CORINE Land Cover 2018, postes 211 à 244).",
    }),
    "developed": (["developed"], {
        "name": "Bâti", "icon": "l-developed",
        "ramp": ["#121218", "#2c2c3c", "#4b4b66", "#727294", "#a3a3c2", "#e2e2f0"],
        "description": "Part des terres de l'hexagone bâties : tissu urbain, zones industrielles et commerciales, "
        "réseaux, chantiers (CORINE 111 à 133 ; les espaces verts urbains ne comptent pas).",
    }),
}
VINE_CLASSES = {221: "vines", 222: "orchards", 223: "olives"}
HAZARD_INDEX = {h["id"]: k for k, h in enumerate(HAZARDS)}
NO_EPCI_FALLBACK = {"vote_macron", "abstention", "disasters"}  # commune data: a missing commune stays missing


def climate_lenses(world: dict, grid: HexGrid, proj: MapProjection) -> list[dict]:
    """Temperature and rainfall normals from the Safran grid (Météo-France SIM2: a hex takes the mean of its grid
    points, or the nearest one within 12 km), and warming from the homogenised station series (Météo-France LSH:
    inverse-distance-squared mean of the stations within 120 km, at least three). Metropolitan France only: the grid
    does not cover the overseas départements, and no overseas series spans both windows."""
    owner = world["owner"]
    km = 1 / proj.scale
    sim = load_interim("meteo_sim")
    col = {c: k for k, c in enumerate(sim["columns"])}
    by_cell: dict[int, list] = {}
    pts = []
    for p in sim["points"]:
        x, y = proj(p[col["lon"]], p[col["lat"]])
        pts.append((x, y, p))
        k = grid.cell_at(x, y)
        if k >= 0:
            by_cell.setdefault(k, []).append(p)
    def hex_mean(key):
        out = []
        for i in range(grid.size):
            if owner[i] < 0 or proj.frame_of(*grid.center(*grid.col_row(i))) is not None:
                out.append(None)
                continue
            ps = by_cell.get(i)
            if not ps:
                cx, cy = grid.center(*grid.col_row(i))
                d, near = min(((x - cx) ** 2 + (y - cy) ** 2, p) for x, y, p in pts)
                ps = [near] if math.sqrt(d) * km <= 12 else []
            vals = [p[col[key]] for p in ps if p[col[key]] is not None]
            out.append(round(sum(vals) / len(vals), 2) if vals else None)
        return out

    lsh = load_interim("meteo_lsh")
    stations = [(*proj(s["lon"], s["lat"]), s["warming"]) for s in lsh["stations"] if s["zone"] == "metro"]
    warming = []
    for i in range(grid.size):
        cx, cy = grid.center(*grid.col_row(i))
        if owner[i] < 0 or proj.frame_of(cx, cy) is not None:
            warming.append(None)
            continue
        num = den = 0.0
        n = 0
        for x, y, w in stations:
            d = math.hypot(x - cx, y - cy) * km
            if d > 120:
                continue
            wt = 1 / max(d, 5.0) ** 2
            num += wt * w
            den += wt
            n += 1
        warming.append(round(num / den, 2) if n >= 3 else None)

    old, recent = lsh["old"], lsh["recent"]
    note = ("Les départements d'outre-mer ne sont pas couverts (grille Safran métropolitaine, pas de série "
            "homogénéisée sur les deux périodes).")
    return [
        {"id": "temperature", "group": "climate", "name": "Température", "icon": "l-temperature",
         "unit": "°C, moyenne annuelle 1991-2020", "format": "celsius", "scale": "linear", "higher_is": "neutral",
         "ramp": ["#2b3a8c", "#4f7cc2", "#9cc5dd", "#f2e6b6", "#f0a35c", "#c8452c", "#7a1420"],
         "source": "meteo_sim",
         "description": "Température moyenne de l'année, normale 1991-2020 (Météo-France, réanalyse Safran, grille "
         "d'environ 8 km) : le relief domine, puis la latitude et la mer. " + note,
         "values": hex_mean("t_normal")},
        {"id": "warming", "group": "climate", "name": "Réchauffement", "icon": "l-warming",
         "unit": f"°C de plus en {recent[0]}-{recent[1]} qu'en {old[0]}-{old[1]}", "format": "dcelsius",
         "scale": "linear", "higher_is": "bad",
         "ramp": ["#fbe3b0", "#f6b26b", "#e8783f", "#c8452c", "#8e1c24", "#4d0a17"],
         "source": "meteo_lsh",
         "note": "Écart entre deux moyennes de trente ans, sur des séries corrigées des déplacements de stations et "
         "changements d'instruments.",
         "description": f"Hausse de la température moyenne entre {old[0]}-{old[1]} et {recent[0]}-{recent[1]}, mesurée "
         f"aux {len(stations)} stations de Météo-France dont les séries homogénéisées couvrent les deux périodes, puis "
         "interpolée entre stations voisines. Les côtes, tempérées par la mer, se sont moins réchauffées que "
         "l'intérieur et l'est. " + note,
         "values": warming},
        {"id": "rainfall", "group": "climate", "name": "Pluies", "icon": "l-rain",
         "unit": "mm par an, normale 1991-2020", "format": "int", "scale": "linear", "higher_is": "neutral",
         "ramp": ["#f4ecd6", "#cfe0d8", "#8fc1cf", "#4f8fbf", "#2b5ea8", "#1b2f73"],
         "source": "meteo_sim",
         "description": "Cumul annuel des précipitations (pluie et neige), normale 1991-2020 (Météo-France, réanalyse "
         "Safran) : des Cévennes et des Pyrénées très arrosées au pourtour méditerranéen et à la Beauce plus secs. "
         + note,
         "values": hex_mean("rain_normal")},
    ]


def build() -> None:
    world = load_interim("_world")
    bounds = load_interim("fr_boundaries")
    t = load_tables()
    add_civic(t, bounds)
    proj = MapProjection(**world["projection"])
    grid = HexGrid(**world["grid"])
    owner = world["owner"]
    samples = world["commune_samples"]
    km2_per_unit2 = (1 / proj.scale) ** 2
    hex_area = 1.5 * math.sqrt(3) * grid.radius**2 * km2_per_unit2  # real km²
    state_index = {code: i for i, code in enumerate(world["states"])}
    com_rows = t["comparateur"]["COM"]
    communes = world["communes"]
    epci_of = {c["code"]: c["epci"] for c in bounds["communes"]}
    total_hits = Counter(k for s in samples for k in s if k >= 0)

    pop = [com_rows.get(code, {}).get("POP_2023") for code in communes]
    # Unsampled communes go to the hex holding their town hall (moved onto French land if needed).
    small_by_cell: dict[int, list[int]] = {}
    lost = []
    for k, code in enumerate(communes):
        if total_hits[k] or not pop[k]:
            continue
        pt = bounds["mairies"].get(code)
        if not pt:
            lost.append(code)
            continue
        x, y = proj(*pt)
        cell = grid.cell_at(x, y)
        if cell < 0 or not samples[cell]:
            cell = nearest_land(grid, owner, max(cell, 0), x, y, state_index.get(code[:2], -1))
        if cell < 0:
            lost.append(code)
            continue
        small_by_cell.setdefault(cell, []).append(k)

    people = [None] * grid.size
    weights: list[list[tuple[int, float]]] = [[] for _ in range(grid.size)]
    density = [None] * grid.size
    for i, s in enumerate(samples):
        if not s:
            continue
        parts = [(k, pop[k] * hits / total_hits[k]) for k, hits in Counter(x for x in s if x >= 0).items() if pop[k]]
        parts += [(k, pop[k]) for k in small_by_cell.get(i, [])]
        land = sum(1 for x in s if x >= 0) or 1
        weights[i] = parts
        if parts:
            people[i] = sum(p for _, p in parts)
            density[i] = round(people[i] / (hex_area * land / len(s)), 2)
    total_com = sum(p for p in pop if p)
    total_hex = sum(p for p in people if p)
    print(f"    population on hexes {total_hex:,.0f} of {total_com:,.0f} ({total_hex / total_com:.4%}); "
          f"{len(lost)} communes not placed")

    lenses = [{
        "id": "density", "group": "people", "name": "Densité", "icon": "l-people",
        "unit": "habitants / km²", "format": "int", "scale": "log",
        "ramp": ["#1b1035", "#4b2377", "#9a3b8a", "#e0645e", "#f9b24a", "#fff3a8"], "higher_is": "neutral",
        "source": "insee_comparateur",
        "description": "Habitants par km² de terre. La population municipale 2023 de chaque commune est répartie "
        "sur ses hexagones selon la part de la commune que couvre chacun.",
        "values": density,
    }]
    epci_cache: dict[tuple[str, str], float | None] = {}
    for lid, (level, meta) in LENSES.items():
        cvals = []
        for k, code in enumerate(communes):
            v = commune_value(lid, com_rows.get(code, {}), code, t) if level == "commune" else None
            if v is None and epci_of.get(code) and lid not in NO_EPCI_FALLBACK:
                key = (lid, epci_of[code])
                if key not in epci_cache:
                    epci_cache[key] = epci_value(lid, epci_of[code], t)
                v = epci_cache[key]
            cvals.append(v)
        values = [None] * grid.size
        for i, parts in enumerate(weights):
            vals = [(cvals[k], p) for k, p in parts if cvals[k] is not None]
            wsum = sum(p for _, p in vals)
            if wsum:
                v = sum(v * p for v, p in vals) / wsum
                values[i] = round(v, 4) if meta["format"] == "pct" else round(v, 1 if v < 1000 else 0)
        src = {"income": "insee_comparateur", "poverty": "insee_comparateur", "unemployment": "insee_activite",
               "bachelors": "insee_diplomes", "age": "insee_population", "seniors": "insee_population",
               "car": "insee_navettes", "transit": "insee_navettes", "immigrants": "insee_immigration",
               "vote_macron": "presidentielle_2022", "abstention": "presidentielle_2022", "disasters": "catnat"}.get(lid, "insee_comparateur")
        if lid == "disasters":
            values = [None if v is None else int(round(v)) for v in values]
        lenses.append({"id": lid, **meta, "source": src, "values": values})
        if lid == "growth":
            lenses[-1]["domain"] = [-0.08, 0.08]
        if lid == "vote_macron":
            lenses[-1]["domain"] = [0.3, 0.8]
        if lid == "disasters":  # the dominant hazard: decrees of each family, weighted like the counts
            kinds = []
            for i, parts in enumerate(weights):
                tot: dict = {}
                for k, p in parts:
                    by = t["catnat"].get(communes[k], {}).get("by", {})
                    cp = pop[k] or 0
                    for fam, n in by.items():
                        if fam in HAZARD_INDEX and cp:
                            tot[fam] = tot.get(fam, 0) + n * p / cp
                kinds.append(HAZARD_INDEX[max(tot, key=tot.get)] if tot else None)
            hazard_lens = {
                "id": "hazard_kind", "group": "hazards", "name": "Risque dominant", "icon": "l-disasters",
                "unit": "famille de risque la plus souvent reconnue", "format": "category", "scale": "linear",
                "higher_is": "neutral", "categories": HAZARDS, "ramp": [h["color"] for h in HAZARDS],
                "domain": [0, len(HAZARDS) - 1], "source": "catnat", "note": lenses[-1]["note"],
                "description": "La famille de risque qui a donné le plus d'arrêtés CatNat depuis 2000 dans les communes "
                "de l'hexagone (inondations, sécheresse, mouvements de terrain, tempête, submersion, séisme, "
                "avalanche), chaque commune pesant selon la part de sa population dans l'hexagone.",
                "values": kinds,
            }

    lenses.append(hazard_lens)
    pct, cover = world["pct"], world["cover"]
    for lid, (keys, meta) in LAND_LENSES.items():
        values = [round(sum(pct[k][i] for k in keys) / 100, 2) if owner[i] >= 0 and cover[i] else None
                  for i in range(grid.size)]
        lenses.append({"id": lid, "group": "land", **meta, "unit": "part des terres", "format": "pct",
                       "scale": "linear", "higher_is": "neutral", "source": "clc", "values": values})
    vines = []
    for i in range(grid.size):
        counts = world["clc"][i] if owner[i] >= 0 else None
        if not counts:
            vines.append(None)
            continue
        land = sum(n for code, n in counts.items() if not str(code).startswith("5"))
        vines.append(round(counts.get("221", counts.get(221, 0)) / land, 3) if land else None)
    lenses.append({
        "id": "vines", "group": "land", "name": "Vignes", "icon": "l-farmland",
        "unit": "part des terres en vignobles", "format": "pct", "scale": "linear", "higher_is": "neutral",
        "ramp": ["#1a0b14", "#3d1230", "#6b1d4a", "#9c2f5c", "#cf6f7f", "#f6c9c4"], "domain": [0, 0.5],
        "source": "clc",
        "description": "Part des terres de l'hexagone en vignobles (CORINE Land Cover 2018, poste 221) : Bordelais, "
        "Champagne, Bourgogne, vallée du Rhône, Languedoc, Alsace, Loire… Les couleurs s'arrêtent à 50 %.",
        "values": vines,
    })
    lenses.extend(climate_lenses(world, grid, proj))
    for lens in lenses:
        if "domain" in lens:
            continue
        lens["domain"] = percentile_domain(lens["values"], lens["scale"] == "log")
        lens["description"] += DOMAIN_NOTE
    groups = [g for g in GROUPS if any(l["group"] == g["id"] for l in lenses)]
    write_web("lenses.json", {"vintage": "Recensement 2023, Filosofi 2023, CORINE 2018", "groups": groups,
                              "lenses": lenses})
    from ..core.store import save_interim
    save_interim("_hexpeople", {"people": people, "weights": [[(k, round(p, 1)) for k, p in w] for w in weights]})
