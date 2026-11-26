"""The game-concept → real-data mapping, in one place, and the economic profile of any place built from Eurostat.

Each yield is defined once here and exported to the browser, so the UI and the Almanac always describe exactly what
was computed. Gold is GDP; the other yields count jobs by branch where the work is done (Eurostat regional accounts,
NUTS 3, employment in persons, NACE A*10, self-employed included).

Places are built from NUTS 3 regions: a city (functional urban area) takes each of its regions' totals in proportion
to the share of the region's population living in the city (local units, census 2021); rates published for NUTS 2
regions (unemployment, degrees, income, poverty, life expectancy) are population-weighted means of its regions'.
"""

from __future__ import annotations

from ..core.store import load_interim

# Industry keys keep usaciv's ids (the art has an icon per key). Values: NACE A*10 branches, French label.
INDUSTRIES = {
    "agriculture": (["A"], "Agriculture, forestry and fishing"),
    "manufacturing": (["C"], "Manufacturing"),
    "utilities": (["B-E", "-C"], "Mining, energy, water and waste"),
    "construction": (["F"], "Construction"),
    "retail": (["G-I"], "Trade, transport, accommodation and food services"),
    "information": (["J"], "Information and communication"),
    "finance": (["K"], "Finance and insurance"),
    "real_estate": (["L"], "Real estate"),
    "professional": (["M_N"], "Professional, scientific, technical and support services"),
    "public_admin": (["O-Q"], "Public administration, education, health and social work"),
    "arts": (["R-U"], "Arts, entertainment and other services"),
}
BRANCHES = ["A", "B-E", "C", "F", "G-I", "J", "K", "L", "M_N", "O-Q", "R-U"]

# Value added by branch (NACE A*10) under usaciv's GDP keys.
GDP_LINES = {
    "agriculture": "A", "manufacturing": "B-E", "construction": "F", "retail": "G-I", "information": "J",
    "finance": "K", "real_estate": "L", "professional": "M_N", "government": "O-Q", "arts": "R-U",
}
GDP_INDUSTRIES = {
    "agriculture": "Agriculture, forestry and fishing",
    "manufacturing": "Industry (incl. energy, water and mining)",
    "construction": "Construction",
    "retail": "Trade, transport, accommodation and food services",
    "information": "Information and communication",
    "finance": "Finance and insurance",
    "real_estate": "Real estate",
    "professional": "Professional, scientific, technical and support services",
    "government": "Public administration, education, health and social work",
    "arts": "Arts, entertainment and other services",
}

WHERE = "counted where people work, self-employed included (Eurostat regional accounts, employment by NUTS 3 region)"
YIELDS = [
    {"key": "food", "icon": "y-food", "label": "Food", "color": "#7fbf3f", "unit": "workers",
     "industries": ["agriculture"],
     "description": f"Jobs in agriculture, forestry and fishing, {WHERE}."},
    {"key": "production", "icon": "y-production", "label": "Production", "color": "#d9823b", "unit": "workers",
     "industries": ["manufacturing", "utilities", "construction"],
     "description": f"Jobs in industry (manufacturing, mining, energy, water) and construction, {WHERE}."},
    {"key": "gold", "icon": "y-gold", "label": "Gold", "color": "#f2c94c", "unit": "usd", "industries": [],
     "description": "Annual gross domestic product in current euros (Eurostat, GDP of NUTS 3 regions). A city's GDP is "
     "the sum, over its regions, of the regional GDP times the share of the region's population living in the urban "
     "area (local administrative units, 2021 census)."},
    {"key": "science", "icon": "y-science", "label": "Science", "color": "#4fa3e0", "unit": "workers",
     "industries": ["professional", "information"],
     "description": f"Jobs in professional, scientific and technical activities (research and development, "
     f"engineering, consulting, support services) and in information and communication, {WHERE}."},
    {"key": "culture", "icon": "y-culture", "label": "Culture", "color": "#b07ce0", "unit": "workers",
     "industries": ["arts"],
     "description": f"Jobs in arts, entertainment, recreation and other services (Eurostat does not split them for "
     f"regions), {WHERE}."},
]


# regional table → (national table, the only regional series it fills: the one holding this code, or None for every
# branch series, matched by branch)
NATIONAL = {"pop3": ("pop0", "TOTAL"), "gdp3": ("gdp0", "MIO_EUR"), "emp3": ("emp0", None), "gva3": ("gva0", None)}


class Stats:
    """Eurostat tables (sources/eurostat.py) with the lookups the builders need.

    Regional tables have holes: a country that publishes nothing for its regions (Bosnia and Herzegovina, Kosovo),
    regions newer than the data (Norway's 2024 NUTS), branches published only for larger regions (Germany and Spain
    give information-communication, professional services and arts only for NUTS 2 or 1). `value()` fills a region's
    hole from its nearest ancestor that has the figure (falling back to the national accounts): what the ancestor's
    total leaves over after its known regions, shared out among the missing ones by their employment (branches) or
    population. Such values are flagged as estimates."""

    def __init__(self, counties: list[str] | None = None, weights: dict | None = None):
        self.t = load_interim("eurostat")["tables"]
        self.counties = counties or []
        self.weights = weights or {}  # population of each region (local units), to share out filled values
        self._filled: dict = {}
        self.estimated: set = set()  # (table, codes, region) filled
        # National accounts stand in for a country's missing NUTS 0 row.
        for table, (national, code) in NATIONAL.items():
            for key, series in self.t[table]["series"].items():
                parts = key.split("|")
                if code:
                    if code not in parts:
                        continue
                    src = self.series(national)
                else:
                    src = self.series(national, *[p for p in parts if p in BRANCHES + ["TOTAL"]])
                for geo, row in src.items():
                    if len(geo) == 2:
                        mine = series.setdefault(geo, {})
                        for y, v in row.items():
                            mine.setdefault(y, v)
        pop = self.series("pop3", "TOTAL")
        years = sorted({y for row in pop.values() for y in row})
        n3 = [g for g in pop if len(g) == 5]
        self.pop_year = max(y for y in years if sum(1 for g in n3 if y in pop[g]) >= 0.9 * len(n3))
        self.growth_from = str(int(self.pop_year) - 5)
        gdp = self.series("gdp3", "MIO_EUR")
        g3 = [g for g in gdp if len(g) == 5]
        self.gdp_year = max(y for y in {y for r in gdp.values() for y in r}
                            if sum(1 for g in g3 if y in gdp[g]) >= 0.8 * len(g3))

    def series(self, table: str, *codes: str) -> dict:
        """{geo: {year: value}} of the table's series whose key holds all `codes`."""
        want = set(codes)
        for key, s in self.t[table]["series"].items():
            if want <= set(key.split("|")):
                return s
        return {}

    def _raw(self, table, codes, year, fallback=1):
        out = {}
        for geo, row in self.series(table, *codes).items():
            for k in range(fallback + 1):
                v = row.get(str(int(year) - k))
                if v is not None:
                    out[geo] = v
                    break
        return out

    def value(self, table: str, codes, geo: str, year: str):
        """The figure for a map region (filled from its ancestors when missing) or any other geography (raw)."""
        codes = (codes,) if isinstance(codes, str) else tuple(codes)
        key = (table, codes, year)
        if key not in self._filled:
            self._filled[key] = self._fill(table, codes, year)
        return self._filled[key].get(geo)

    def _fill(self, table, codes, year):
        raw = self._raw(table, codes, year)
        out = dict(raw)
        if not self.counties:
            return out
        total = None
        if "TOTAL" not in codes and table in ("emp3", "gva3"):
            total = {g: self.value(table, [c for c in codes if c not in BRANCHES] + ["TOTAL"], g, year)
                     for g in self.counties}
        missing = [g for g in self.counties if g not in raw]
        by_anc: dict = {}
        for g in missing:
            for n in range(len(g) - 1, 1, -1):
                a = g[:n]
                if a in raw:
                    by_anc.setdefault(a, []).append(g)
                    break
        for a, gs in by_anc.items():
            kids = [g for g in self.counties if g.startswith(a)]
            left = max(0.0, raw[a] - sum(raw[g] for g in kids if g in raw))
            w = {g: (total.get(g) if total else None) or self.weights.get(g) or 0.0 for g in gs}
            tw = sum(w.values())
            for g in gs:
                out[g] = left * w[g] / tw if tw else left / len(gs)
                self.estimated.add((table, codes, g))
        return out

    def at(self, table: str, codes, geo: str, year: str | None = None, fallback: int = 3):
        """Raw value of a series for `geo` in `year` (or the latest year), else up to `fallback` years earlier."""
        row = self.series(table, *([codes] if isinstance(codes, str) else codes)).get(geo)
        if not row:
            return None
        if year is None:
            return row[max(row)]
        y = int(year)
        for k in range(fallback + 1):
            v = row.get(str(y - k))
            if v is not None:
                return v
        return None

    def latest(self, table: str, codes, geo: str):
        row = self.series(table, *([codes] if isinstance(codes, str) else codes)).get(geo)
        if not row:
            return None, None
        y = max(row)
        return int(y), row[y]


def region_profile(s: Stats, geo: str) -> dict:
    """Additive totals of one map region (or a country, unfilled): population, GDP, value added and jobs by branch."""
    out = {"population": s.value("pop3", "TOTAL", geo, s.pop_year),
           "pop_start": s.value("pop3", "TOTAL", geo, s.growth_from),
           "y_lt15": s.value("pop3", "Y_LT15", geo, s.pop_year),
           "y_ge65": s.value("pop3", "Y_GE65", geo, s.pop_year),
           "gdp": s.value("gdp3", "MIO_EUR", geo, s.gdp_year),
           "jobs_total": s.value("emp3", "TOTAL", geo, s.gdp_year)}
    for b in BRANCHES:
        out["gva_" + b] = s.value("gva3", b, geo, s.gdp_year)
        out["emp_" + b] = s.value("emp3", b, geo, s.gdp_year)
    out["gva_total"] = s.value("gva3", "TOTAL", geo, s.gdp_year)
    row = s.series("pop3", "TOTAL").get(geo) or {}
    out["series"] = dict(row)
    out["estimated"] = sorted({t for t, c, g in s.estimated if g == geo})
    return out


def nuts2_rates(s: Stats, geo2: str) -> dict:
    """Rates published for NUTS 2 regions (falling back to the NUTS 1 and country values)."""
    def get(table, codes):
        for g in (geo2, geo2[:3], geo2[:2]):
            v = s.latest(table, codes, g)[1]
            if v is not None:
                return v
        return None
    return {
        "unemployment": get("unemp2", "PC"),
        "employment_rate": get("emprate2", "PC"),
        "tertiary": get("tertiary2", "ED5-8"),
        "income_pps": get("income2", "PPS_EU27_2020_HAB"),
        "income_eur": get("income2", "EUR_HAB"),
        "life_expectancy": get("lifeexp2", "YR"),
        "arope": get("arope2", "PC"),
        "median_age": None,
    }


def combine(parts: list[tuple[float, dict]]) -> dict:
    """Weighted sum of additive profiles: [(share of the region in the place, region profile)]. A total is null when
    any part lacks it."""
    out: dict = {}
    keys = set().union(*(p.keys() for _, p in parts)) - {"series", "estimated"}
    for k in keys:
        vals = [(w, p.get(k)) for w, p in parts if w > 0]
        out[k] = None if not vals or any(v is None for _, v in vals) else sum(w * v for w, v in vals)
    sets = [set(p["series"]) for w, p in parts if w > 0]
    years = set.intersection(*sets) if sets else set()
    out["series"] = {y: round(sum(w * p["series"][y] for w, p in parts if w > 0)) for y in sorted(years)}
    out["estimated"] = sorted({t for w, p in parts if w > 0 for t in p.get("estimated", [])})
    return out


def mean_rates(parts: list[tuple[float, dict]]) -> dict:
    """Population-weighted mean of rate dicts: [(population, rates)]; a rate is null if no part has it."""
    out = {}
    keys = set().union(*(r.keys() for _, r in parts)) if parts else set()
    for k in keys:
        vals = [(w, r[k]) for w, r in parts if r.get(k) is not None and w]
        tot = sum(w for w, _ in vals)
        out[k] = sum(w * v for w, v in vals) / tot if tot else None
    return out


def _r(v, nd=4):
    return round(v, nd) if v is not None else None


def economy(p: dict, rates: dict, s: Stats, population=None, median_age=None) -> dict:
    """The city / country / region record from an additive profile `p` and NUTS 2 `rates` (percentages)."""
    jobs = {}
    for key, (codes, _) in INDUSTRIES.items():
        if codes == ["B-E", "-C"]:
            a, b = p.get("emp_B-E"), p.get("emp_C")
            jobs[key] = round((a - b) * 1000) if a is not None and b is not None else None
        else:
            v = p.get("emp_" + codes[0])
            jobs[key] = round(v * 1000) if v is not None else None
    yields = {}
    for y in YIELDS:
        if y["key"] == "gold":
            yields["gold"] = round(p["gdp"] * 1e6) if p.get("gdp") is not None else None
        else:
            vals = [jobs[k] for k in y["industries"]]
            yields[y["key"]] = None if any(v is None for v in vals) else sum(vals)
    by = None
    if p.get("gdp") is not None and p.get("gva_total"):
        by = {}
        for key, b in GDP_LINES.items():
            v = p.get("gva_" + b)
            by[key] = round(v / p["gva_total"] * p["gdp"] * 1e6) if v is not None else None
    pop = population if population is not None else p.get("population")
    tot = p.get("population")
    pct = lambda v: round(v / 100, 4) if v is not None else None  # noqa: E731
    return {
        "population": round(pop) if pop is not None else None,
        "yields": yields,
        "jobs": jobs,
        "employed": round(p["jobs_total"] * 1000) if p.get("jobs_total") is not None else None,
        "workplace_jobs": round(p["jobs_total"] * 1000) if p.get("jobs_total") is not None else None,
        # Disposable household income per inhabitant in purchasing power standards (euros at EU-average prices), so
        # it compares across countries like the lens and counties.json; the plain-euro figure beside it.
        "median_income": round(rates["income_pps"]) if rates.get("income_pps") is not None else None,
        "income_eur": round(rates["income_eur"]) if rates.get("income_eur") is not None else None,
        "median_rent": None,
        "home_value": None,
        "unemployment": pct(rates.get("unemployment")),
        "employment_rate": pct(rates.get("employment_rate")),
        "rent_burden": None,
        "poverty": pct(rates.get("arope")),
        "bachelors": pct(rates.get("tertiary")),
        "life_expectancy": _r(rates.get("life_expectancy"), 1),
        "median_age": _r(median_age, 1),
        "owners": None,
        "second_homes": None,
        "seniors": _r(p["y_ge65"] / tot) if p.get("y_ge65") is not None and tot else None,
        "youth": _r(p["y_lt15"] / tot) if p.get("y_lt15") is not None and tot else None,
        "gdp": round(p["gdp"] * 1e6) if p.get("gdp") is not None else None,
        "gdp_year": int(s.gdp_year),
        "gdp_per_capita": round(p["gdp"] * 1e6 / pop) if p.get("gdp") is not None and pop else None,
        "gdp_by_industry": by,
        "gdp_undisclosed": None,
        "gdp_estimated": None,
    }


def growth_of(p: dict, s: Stats):
    a, b = p.get("pop_start"), p.get("population")
    g = round(b / a - 1, 4) if a and b else None
    # Beyond ±15% in five years is a break in the series (a census revision: Albania 2023), not growth.
    return (g if g is None or abs(g) <= 0.15 else None), [int(s.growth_from), int(s.pop_year)]


def lenient_sum(parts: list[dict]) -> tuple[dict, dict]:
    """Sum of additive profiles skipping the parts that lack a figure: (totals, {key: [indices of parts left out]})."""
    out, missing = {}, {}
    keys = set().union(*(p.keys() for p in parts)) - {"series", "estimated"}
    for k in keys:
        vals = [p.get(k) for p in parts]
        have = [v for v in vals if v is not None]
        out[k] = sum(have) if have else None
        missing[k] = [i for i, v in enumerate(vals) if v is None]
    return out, missing
