"""citizens.json: the citizen mix of each urban area, for the City View's rows of person icons.

Five rows per city (docs/DATA_CONTRACTS.md, "citizens.json (lazy)"):

* workforce – jobs by branch of activity where people work (cities.json `jobs`: Eurostat regional accounts, NUTS 3
  employment apportioned to the urban area). Eurostat publishes no occupation split for cities, so the occupation
  keys the browser draws stand for branches (finance and real estate → executive, …; see GROUPS).
* age (under 15, 15-34, 35-64, 65+: the 10-year groups every country publishes split at 35, not 40), education
  (ISCED 0-2, 3-4, 5-8: Eurostat gives no finer split for cities), nativity (country of birth; citizenship where birth
  is not published) and commute (shares of journeys to work by car, public transport, foot, bicycle or motorcycle) –
  Eurostat city statistics (Urban Audit, sources/urban_audit.py).

Each Urban Audit row takes the functional urban area's figures ("…F" codes) when Eurostat publishes them, else the
core city's ("…C", cities.json `centre_code`), from the latest year in which every category of the row is published;
the row records which (`geo`, `level`, `year`). A row Eurostat does not publish for a city is null, never zeros, and
GeoNames towns (ids "GN…") have no Urban Audit data at all (null). Figures are rounded with the largest-remainder
method, so each row's figures add up exactly. `national` is Europe: the sum of the cities that have the row.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path

from ..core.store import load_interim, write_web
from ..core.paths import WEB_DATA

REQUIRES = ["urban_audit", "cities.json", "nation.json"]
PRODUCES = ["citizens.json"]

ROW_IDS = ["workforce", "age", "commute", "education", "nativity"]
FIGURES = {"workforce": 20, "age": 10, "commute": 10}  # education and nativity: the browser rounds to 10
RULE = {"specialist_high": 1.5, "specialist_low": 0.67, "min_share": 0.01, "max_high": 4, "max_low": 2}
COMMUTE_SUM = (85.0, 110.0)  # a year whose mode shares (in %) add up outside this range is a data error: skipped
AGE_TOTAL_TOLERANCE = 0.03  # the age groups must add up to the published total within 3 %

# Branch (cities.json jobs key) → workforce key. The keys are the browser's occupation keys (it has icons for them).
BRANCH_KEY = {
    "finance": "executive", "real_estate": "executive",
    "information": "engineer", "professional": "engineer",
    "arts": "scholar",
    "public_admin": "healer",
    "retail": "clerk",
    "agriculture": "farmer",
    "construction": "builder",
    "manufacturing": "maker", "utilities": "maker",
}


def _g(key, label, lines):
    return {"key": key, "label": label, "icon": f"c-{key}", "lines": lines}


GROUPS = {
    "workforce": [
        _g("executive", "Finance, insurance and real estate", "cities.json jobs: finance + real_estate (NACE K, L)"),
        _g("engineer", "Information, professional, scientific, technical and support services",
           "cities.json jobs: information + professional (NACE J, M, N)"),
        _g("scholar", "Arts, entertainment and other services", "cities.json jobs: arts (NACE R-U)"),
        _g("healer", "Public administration, education, health and social work",
           "cities.json jobs: public_admin (NACE O-Q)"),
        _g("clerk", "Trade, transport, hotels and restaurants", "cities.json jobs: retail (NACE G-I)"),
        _g("farmer", "Agriculture, forestry and fishing", "cities.json jobs: agriculture (NACE A)"),
        _g("builder", "Construction", "cities.json jobs: construction (NACE F)"),
        _g("maker", "Industry: manufacturing, mining, energy, water and waste",
           "cities.json jobs: manufacturing + utilities (NACE B-E)"),
    ],
    "age": [
        _g("child", "Under 15", "DE1040V + DE1074V + DE1077V (0-4, 5-9, 10-14)"),
        _g("young", "15 to 34", "DE1046V + DE1049V + DE1058V (15-19, 20-24, 25-34; 25-34 = DE1101V + DE1104V where "
                                "only 5-year groups are published)"),
        _g("midlife", "35 to 64", "DE1061V + DE1064V + DE1025V (35-44, 45-54, 55-64; or their 5-year groups "
                                  "DE1107V + DE1110V, DE1113V + DE1116V, DE1119V + DE1122V)"),
        _g("elder", "65 and over", "DE1028V + DE1055V (65-74, 75+; or DE1125V + DE1128V, DE1131V + DE1134V + "
                                   "DE1137V)"),
    ],
    "commute": [
        _g("drove_alone", "Car", "TT1003V (share of journeys to work by car)"),
        _g("transit", "Public transport (rail, metro, bus, tram)", "TT1010V"),
        _g("walk", "On foot", "TT1008V"),
        _g("other", "Bicycle or motorcycle", "TT1007V + TT1006V (motorcycle = TT1012V − TT1003V where TT1006V is "
                                             "not published)"),
    ],
    "education": [
        _g("less_than_hs", "At most lower secondary (ISCED 0-2)", "TE2025V (aged 25-64)"),
        _g("high_school", "Upper secondary or post-secondary non-tertiary (ISCED 3-4)", "TE2028V (aged 25-64)"),
        _g("bachelors", "Tertiary: short-cycle, bachelor's, master's or doctorate (ISCED 5-8)", "TE2031V (aged 25-64)"),
    ],
    "nativity": [
        _g("born_in_state", "Born in the country", "DE2008V native-born (citizenship basis: DE2001V nationals)"),
        _g("other_state", "Born in another EU country",
           "DE2010V foreign-born in an EU country (citizenship basis: DE2002V EU foreigners)"),
        _g("foreign_born", "Born outside the EU",
           "DE2011V foreign-born in a non-EU country, or DE2009V − DE2010V (citizenship basis: DE2003V non-EU "
           "foreigners, or DE2012V − DE2002V)"),
    ],
}
KEYS = {r: [g["key"] for g in gs] for r, gs in GROUPS.items()}

# Short row names (the advisors quote them as "share of <row>") and the long notes on how each row is made.
ROWS_TEXT = {
    "workforce": "Jobs by branch of activity",
    "age": "Residents by age group",
    "commute": "Journeys to work by main mode",
    "education": "Residents aged 25-64 by highest level of education",
    "nativity": "Residents by country of birth (or citizenship)",
}
NOTES = {
    "all": "Urban Audit rows take the functional urban area's figures (geo …F, level \"fua\") when Eurostat publishes "
           "them, else the core city's (…C, level \"city\"), from the latest year in which every category of the row "
           "is published (year). A row Eurostat does not publish for the area is null, never zeros. Europe = the sum "
           "of the urban areas that have the row (years differ between cities).",
    "workforce": "Jobs by branch of activity, counted where people work (Eurostat regional accounts, NUTS 3 "
                 "employment by branch apportioned to the urban area by population: cities.json jobs). Eurostat "
                 "publishes no occupation split for cities, so each category is a branch, drawn with the nearest "
                 "occupation's figure.",
    "age": "Residents on 1 January by age group (Urban Audit urb_lpop1 for functional urban areas, urb_cpop1 for core "
           "cities), latest year with every group. Median age: interpolated within the 5-year age groups (a 10-year "
           "group published only as a whole is split evenly), the same way for every city and for Europe; the "
           "statistical office's own median (DE1073V, urb_lpopstr / urb_cpopstr) is kept as median_published.",
    "commute": "Journeys to work by main mode (Urban Audit urb_ltran / urb_ctran, shares in %), rescaled to the four "
               "modes published, times the area's employed residents (active − unemployed, EC1001V − EC1010V; else "
               "employed aged 20-64, EC1177V; else jobs, EC2020V; else cities.json employed). Carpooling and working "
               "from home are not published.",
    "education": "Residents aged 25-64 by highest level of education completed, ISCED 2011 (Urban Audit urb_leduc / "
                 "urb_ceduc).",
    "nativity": "Residents by country of birth: this country, another EU country, outside the EU (Urban Audit "
                "urb_lpopcb / urb_cpopcb). Where country of birth is not published, by citizenship: nationals, "
                "other EU citizens, non-EU citizens (the row's basis says which).",
}

# Age bands used for the categories and the interpolated medians: (low, high, [indicator alternatives]).
AGE_BANDS = [
    (0, 5, [["DE1040V"]]), (5, 10, [["DE1074V"]]), (10, 15, [["DE1077V"]]),
    (15, 20, [["DE1046V"]]), (20, 25, [["DE1049V"]]),
    (25, 35, [["DE1058V"], ["DE1101V", "DE1104V"]]),
    (35, 45, [["DE1061V"], ["DE1107V", "DE1110V"]]),
    (45, 55, [["DE1064V"], ["DE1113V", "DE1116V"]]),
    (55, 65, [["DE1025V"], ["DE1119V", "DE1122V"]]),
    (65, 75, [["DE1028V"], ["DE1125V", "DE1128V"]]),
    (75, None, [["DE1055V"], ["DE1131V", "DE1134V", "DE1137V"]]),
]
AGE_CAT = {"child": (0, 15), "young": (15, 35), "midlife": (35, 65), "elder": (65, 999)}
# The 5-year groups of each wider band (its second alternative), for the medians. A band published only as a whole is
# split evenly between its 5-year groups.
AGE_FINE = {25: [(25, 30), (30, 35)], 35: [(35, 40), (40, 45)], 45: [(45, 50), (50, 55)], 55: [(55, 60), (60, 65)],
            65: [(65, 70), (70, 75)], 75: [(75, 80), (80, 85), (85, None)]}

# Nativity bases: (basis, {key: [indicator alternatives; "A-B" = A minus B]}).
NATIVITY = [
    ("birthplace", {"born_in_state": [["DE2008V"]], "other_state": [["DE2010V"]],
                    "foreign_born": [["DE2011V"], ["DE2009V", "-DE2010V"]]}),
    ("citizenship", {"born_in_state": [["DE2001V"]], "other_state": [["DE2002V"]],
                     "foreign_born": [["DE2003V"], ["DE2012V", "-DE2002V"]]}),
]


# ------------------------------------------------------------------ helpers


def largest_remainder(values: dict, keys: list[str], n: int) -> dict | None:
    """Split n into whole parts proportional to values (the browser's method: ties go to the earlier key)."""
    tot = sum(values.get(k) or 0 for k in keys)
    if not tot > 0:
        return None
    raw = [(values.get(k) or 0) / tot * n for k in keys]
    out = [math.floor(v) for v in raw]
    left = n - sum(out)
    order = sorted(range(len(keys)), key=lambda j: (-(raw[j] - math.floor(raw[j])), j))
    for j in order[:left]:
        out[j] += 1
    return dict(zip(keys, out))


def _years_desc(series: dict, indicators, geo: str) -> list[str]:
    ys = set()
    for i in indicators:
        ys |= set(series.get(i, {}).get(geo, {}))
    return sorted(ys, reverse=True)


def _value(series: dict, alternatives, geo: str, year: str):
    """First alternative whose indicators are all published (a "-X" term is subtracted)."""
    for alt in alternatives:
        vals = []
        for ind in alt:
            sign = -1 if ind.startswith("-") else 1
            v = series.get(ind.lstrip("-"), {}).get(geo, {}).get(year)
            if v is None:
                break
            vals.append(sign * v)
        else:
            return sum(vals)
    return None


def interpolated_median(bands: list[tuple]) -> float | None:
    """Median from (low, high, count) bands, linear within the band (an open last band counts 10 years)."""
    tot = sum(c for _, _, c in bands)
    if not tot > 0:
        return None
    half, cum = tot / 2, 0.0
    for lo, hi, c in bands:
        if c > 0 and cum + c >= half:
            return round(lo + (half - cum) / c * ((hi if hi is not None else lo + 10) - lo), 1)
        cum += c
    return None


def fine_bands(series: dict, geo: str, year: str, bands: list[tuple]) -> list[tuple]:
    """(low, high, count) 5-year groups for the median: published ones where they are, else even splits."""
    out = []
    for (lo, hi, c), (_, _, alts) in zip(bands, AGE_BANDS):
        parts = AGE_FINE.get(lo)
        if not parts:
            out.append((lo, hi, c))
            continue
        vals = [series.get(i, {}).get(geo, {}).get(year) for i in alts[1]]
        if all(v is not None and v >= 0 for v in vals) and sum(vals) > 0:
            k = c / sum(vals)  # scaled to the band's own total
            out += [(a, b, v * k) for (a, b), v in zip(parts, vals)]
        elif hi is not None:
            out += [(a, b, c / len(parts)) for a, b in parts]
        else:
            out.append((lo, hi, c))  # an open band left whole (no median falls there)
    return out


def _row(counts: dict, keys: list[str], n_figures: int | None) -> dict:
    """{total, counts, shares, figures?} with whole counts summing to the total."""
    raw_total = sum(counts[k] for k in keys)
    whole = largest_remainder(counts, keys, round(raw_total)) or {k: 0 for k in keys}
    total = sum(whole.values())
    row = {"total": total, "counts": whole,
           "shares": {k: round(whole[k] / total, 3) if total else 0 for k in keys}}
    if n_figures:
        row["figures"] = largest_remainder(whole, keys, n_figures)
    return row


def _levels(city: dict):
    yield "fua", city["id"]
    core = city.get("centre_code")
    if core:
        yield "city", core


# ------------------------------------------------------------------ rows


def age_row(t: dict, city: dict, stats: Counter):
    for level, geo in _levels(city):
        s = t[f"age_{level}"]["series"]
        for y in _years_desc(s, [i for _, _, alts in AGE_BANDS for alt in alts for i in alt], geo):
            bands = [(lo, hi, _value(s, alts, geo, y)) for lo, hi, alts in AGE_BANDS]
            if any(c is None or c < 0 for _, _, c in bands):
                continue
            counts = {k: sum(c for lo, _, c in bands if a <= lo < b) for k, (a, b) in AGE_CAT.items()}
            total = s.get("DE1001V", {}).get(geo, {}).get(y)
            if total and abs(sum(counts.values()) / total - 1) > AGE_TOTAL_TOLERANCE:
                stats["age: groups off the total, year skipped"] += 1
                continue
            row = _row(counts, KEYS["age"], FIGURES["age"])
            fine = fine_bands(s, geo, y, bands)
            # One method for every city and for Europe: the national institutes' own medians (DE1073V) differ in
            # method (Italy's are whole years), so they are kept alongside, not shown as the median.
            row["median"] = interpolated_median(fine)
            med_s = t[f"median_{level}"]["series"].get("DE1073V", {}).get(geo, {})
            near = sorted((abs(int(yy) - int(y)), -int(yy)) for yy in med_s if abs(int(yy) - int(y)) <= 2)
            if near:
                my = str(-near[0][1])
                row["median_published"], row["median_published_year"] = round(med_s[my], 1), int(my)
            row.update({"geo": geo, "level": level, "year": int(y)})
            return row, fine
    return None, None


def commute_row(t: dict, city: dict, stats: Counter):
    need = ["TT1003V", "TT1010V", "TT1007V", "TT1008V"]
    for level, geo in _levels(city):
        s = t[f"commute_{level}"]["series"]
        for y in _years_desc(s, need, geo):
            v = {i: s.get(i, {}).get(geo, {}).get(y) for i in need + ["TT1006V", "TT1012V"]}
            if any(v[i] is None for i in need):
                continue
            moto = v["TT1006V"]
            if moto is None and v["TT1012V"] is not None:
                moto = max(0.0, v["TT1012V"] - v["TT1003V"])
            if moto is None:
                continue
            pct = {"drove_alone": v["TT1003V"], "transit": v["TT1010V"], "walk": v["TT1008V"],
                   "other": v["TT1007V"] + moto}
            tot = sum(pct.values())
            if not COMMUTE_SUM[0] <= tot <= COMMUTE_SUM[1]:
                stats["commute: mode shares do not add up, year skipped"] += 1
                continue
            workers, wsrc, wyear = _workers(t, level, geo, city)
            if not workers:
                stats["commute: no worker total"] += 1
                continue
            row = _row({k: p / tot * workers for k, p in pct.items()}, KEYS["commute"], FIGURES["commute"])
            row.update({"geo": geo, "level": level, "year": int(y), "total_source": wsrc, "total_year": wyear,
                        "published_sum": round(tot, 1)})
            return row
    return None


def _workers(t: dict, level: str, geo: str, city: dict):
    """Employed residents of the area (latest year), or the nearest stand-in; (value, source, year)."""
    s = t[f"labour_{level}"]["series"]
    for name, alt in (("EC1001V − EC1010V", ["EC1001V", "-EC1010V"]), ("EC1177V", ["EC1177V"]),
                      ("EC2020V", ["EC2020V"])):
        for y in _years_desc(s, [a.lstrip("-") for a in alt], geo):
            v = _value(s, [alt], geo, y)
            if v and v > 0:
                return v, name, int(y)
    if level == "fua" and city.get("employed"):
        return city["employed"], "cities.json employed", None
    return None, None, None


def education_row(t: dict, city: dict):
    inds = {"less_than_hs": "TE2025V", "high_school": "TE2028V", "bachelors": "TE2031V"}
    for level, geo in _levels(city):
        s = t[f"education_{level}"]["series"]
        for y in _years_desc(s, inds.values(), geo):
            v = {k: s.get(i, {}).get(geo, {}).get(y) for k, i in inds.items()}
            if any(x is None or x < 0 for x in v.values()) or not sum(v.values()) > 0:
                continue
            row = _row(v, KEYS["education"], None)
            row["bachelors_plus"] = row["shares"]["bachelors"]
            row.update({"geo": geo, "level": level, "year": int(y)})
            return row
    return None


def origin_row(t: dict, city: dict, basis: str):
    """Residents by origin on one basis ("birthplace" or "citizenship"): the area's latest complete year."""
    spec = dict(NATIVITY)[basis]
    inds = [a.lstrip("-") for alts in spec.values() for alt in alts for a in alt]
    for level, geo in _levels(city):
        s = t[f"origin_{level}"]["series"]
        for y in _years_desc(s, inds, geo):
            v = {k: _value(s, alts, geo, y) for k, alts in spec.items()}
            if any(x is None or x < 0 for x in v.values()) or not sum(v.values()) > 0:
                continue
            row = _row(v, KEYS["nativity"], None)
            row["foreign_born"] = row["shares"]["foreign_born"]
            row["born_in_state"] = row["shares"]["born_in_state"]
            row.update({"basis": basis, "geo": geo, "level": level, "year": int(y)})
            return row
    return None


def nativity_row(t: dict, city: dict):
    """Country of birth (functional urban area, else core city); citizenship where birth is not published."""
    return origin_row(t, city, "birthplace") or origin_row(t, city, "citizenship")


def workforce_row(city: dict, year: int | None):
    jobs = city.get("jobs") or {}
    if not jobs or any(jobs.get(b) is None for b in BRANCH_KEY):
        return None
    counts = {k: 0 for k in KEYS["workforce"]}
    for branch, key in BRANCH_KEY.items():
        counts[key] += jobs[branch]
    if not sum(counts.values()) > 0:
        return None
    row = _row(counts, KEYS["workforce"], FIGURES["workforce"])
    row.update({"basis": "branch", "geo": city["id"], "level": "fua", "year": year})
    return row


# ------------------------------------------------------------------ Europe and specialists


def national_row(rid: str, rows: list[dict], age_bands: list | None = None) -> dict | None:
    if not rows:
        return None
    keys = KEYS[rid]
    counts = {k: sum(r["counts"][k] for r in rows) for k in keys}
    out = _row(counts, keys, FIGURES.get(rid))
    years = [r["year"] for r in rows if r.get("year") is not None]
    out["cities"] = len(rows)
    out["years"] = [min(years), max(years)] if years else None
    if rid == "age":
        agg: dict = {}
        for bands in age_bands:  # 5-year groups up to 75, then one open group (the cities differ above 75)
            for lo, hi, c in bands:
                key = (lo, hi) if lo < 75 else (75, None)
                agg[key] = agg.get(key, 0) + c
        agg = [(lo, hi, c) for (lo, hi), c in sorted(agg.items())]
        out["median"] = interpolated_median(agg)
    if rid == "education":
        out["bachelors_plus"] = out["shares"]["bachelors"]
    if rid == "nativity":
        out["foreign_born"] = out["shares"]["foreign_born"]
        out["born_in_state"] = out["shares"]["born_in_state"]
        out["basis"] = rows[0].get("basis")
    return out


def _unrounded(row: dict) -> dict:
    tot = row["total"]
    return {k: (v / tot if tot else 0) for k, v in row["counts"].items()}


def specialists(city_row: dict, national: dict) -> list[dict]:
    high, low = [], []
    for rid in ROW_IDS:
        row = city_row.get(rid)
        nat = national.get(rid)
        if rid == "nativity" and row and row.get("basis") == "citizenship":
            nat = national.get("_nativity_citizenship")
        if not row or not nat:
            continue
        mine, theirs = _unrounded(row), _unrounded(nat)
        for k in KEYS[rid]:
            s, n = mine[k], theirs[k]
            if n <= 0 or (s < RULE["min_share"] and n < RULE["min_share"]):
                continue
            r = s / n
            item = {"row": rid, "key": k, "share": round(s, 3), "national": round(n, 3), "ratio": round(r, 2)}
            if r >= RULE["specialist_high"]:
                high.append((r, item))
            elif r <= RULE["specialist_low"]:
                low.append((r, item))
    high.sort(key=lambda t: -t[0])
    low.sort(key=lambda t: t[0])
    return [i for _, i in high[:RULE["max_high"]]] + [i for _, i in low[:RULE["max_low"]]]


# ------------------------------------------------------------------ build


def _jobs_year() -> int | None:
    p = WEB_DATA / "nation.json"
    if not p.exists():
        return None
    m = re.search(r"jobs (\d{4})", json.loads(p.read_text()).get("vintage") or "")
    return int(m.group(1)) if m else None


def build() -> None:
    ua = load_interim("urban_audit")
    t = ua["tables"]
    cities = json.loads((WEB_DATA / "cities.json").read_text())
    jobs_year = _jobs_year()
    stats: Counter = Counter()

    rows: dict[str, dict | None] = {}
    age_bands: dict[str, list] = {}
    for c in cities:
        cid = c["id"]
        if cid.startswith("GN"):
            rows[cid] = None  # GeoNames towns: no Urban Audit data
            continue
        age, bands = age_row(t, c, stats)
        r = {"workforce": workforce_row(c, jobs_year), "age": age, "commute": commute_row(t, c, stats),
             "education": education_row(t, c), "nativity": nativity_row(t, c)}
        if bands:
            age_bands[cid] = bands
        rows[cid] = r if any(r.values()) else None

    present = {rid: [r[rid] for r in rows.values() if r and r.get(rid)] for rid in ROW_IDS}
    national = {}
    for rid in ROW_IDS:
        rs = present[rid]
        if rid == "nativity":
            rs = [r for r in rs if r["basis"] == "birthplace"]
        national[rid] = national_row(rid, rs, list(age_bands.values()) if rid == "age" else None)
    # Europe by citizenship: the yardstick of the cities whose origins are by citizenship.
    by_citizenship = [origin_row(t, c, "citizenship") for c in cities if rows.get(c["id"])]
    national["_nativity_citizenship"] = national_row("nativity", [r for r in by_citizenship if r])

    out_cities = {}
    for c in cities:
        r = rows[c["id"]]
        if r is None:
            out_cities[c["id"]] = None
            continue
        r["specialists"] = specialists(r, national)
        r["reliable"] = True
        out_cities[c["id"]] = r

    nat_cit = national.pop("_nativity_citizenship")
    national["specialists"] = []
    national["nativity_citizenship"] = nat_cit  # Europe by citizenship: the yardstick of citizenship-basis rows

    years = {rid: national[rid]["years"] for rid in ROW_IDS if national.get(rid)}
    all_years = [y for ys in years.values() if ys for y in ys]
    for rid in ROW_IDS:
        lv = Counter(r.get("level") for r in present[rid])
        print(f"    {rid:10s} {len(present[rid]):4d} cities (fua {lv.get('fua', 0)}, core city {lv.get('city', 0)}), "
              f"years {years.get(rid)}")
    for k, v in stats.items():
        print(f"    note: {k}: {v}")
    n_null = sum(1 for v in out_cities.values() if v is None)
    print(f"    {len(out_cities) - n_null} cities with a row, {n_null} null "
          f"({sum(1 for c in cities if c['id'].startswith('GN'))} GeoNames towns)")

    rule_text = (f"A category is a specialty when its share is at least {RULE['specialist_high']}× the European share "
                 f"(up to {RULE['max_high']}, strongest first) or at most {RULE['specialist_low']}× (up to "
                 f"{RULE['max_low']}); categories under {RULE['min_share']:.0%} both here and across Europe are "
                 "skipped. Europe = the sum of the urban areas that have the row (citizenship-basis origins are "
                 "compared with Europe by citizenship).")
    write_web("citizens.json", {
        "version": 1,
        "vintage": "Eurostat Urban Audit, latest year per city",
        "year": max(all_years) if all_years else None,
        "years": years,
        "sources": ["urban_audit", "eurostat"],
        "figures": FIGURES,
        "rows": ROWS_TEXT,
        "notes": NOTES,
        "groups": GROUPS,
        "rule": {**RULE, "text": rule_text},
        "national": national,
        "cities": out_cities,
    })


# ------------------------------------------------------------------ check


def check(web_dir: Path) -> list[tuple[str, str]]:
    path = Path(web_dir) / "citizens.json"
    if not path.exists():
        return [("NOTE", "citizens.json not built (optional; run: build citizens)")]
    doc = json.loads(path.read_text())
    out: list[tuple[str, str]] = []
    missing = [k for k in ("version", "vintage", "figures", "rows", "groups", "rule", "national", "cities") if k not in doc]
    if missing:
        return [("FAIL", f"citizens.json lacks {missing}")]
    groups = doc["groups"]
    bad = [r for r in ROW_IDS if not isinstance(groups.get(r), list) or not groups[r]
           or any(not {"key", "label", "icon", "lines"} <= g.keys() for g in groups[r])]
    if bad:
        out.append(("FAIL", f"citizens.json groups malformed: {bad}"))
        return out
    keys = {r: [g["key"] for g in groups[r]] for r in ROW_IDS}
    figs = doc["figures"]
    probs: Counter = Counter()

    def check_row(rid, row, where):
        if row is None:
            return
        if not isinstance(row, dict) or not {"total", "counts", "shares"} <= row.keys():
            probs[f"{rid}: missing total/counts/shares"] += 1
            return
        if set(row["counts"]) != set(keys[rid]) or set(row["shares"]) != set(keys[rid]):
            probs[f"{rid}: categories differ from groups"] += 1
            return
        if any(not isinstance(v, int) or v < 0 for v in row["counts"].values()):
            probs[f"{rid}: counts not whole non-negative numbers"] += 1
        if not isinstance(row["total"], int) or row["total"] <= 0 or sum(row["counts"].values()) != row["total"]:
            probs[f"{rid}: counts do not add up to total"] += 1
        if abs(sum(row["shares"].values()) - 1) > 0.01:
            probs[f"{rid}: shares do not sum to 1"] += 1
        if rid in figs:
            f = row.get("figures")
            if not isinstance(f, dict) or set(f) != set(keys[rid]) or sum(f.values()) != figs[rid]:
                probs[f"{rid}: figures do not add up to {figs[rid]}"] += 1

    for rid in ROW_IDS:
        if doc["national"].get(rid) is None:
            out.append(("FAIL", f"citizens.json national.{rid} is null"))
        check_row(rid, doc["national"].get(rid), "national")
    cpath = Path(web_dir) / "cities.json"
    ids = [c["id"] for c in json.loads(cpath.read_text())] if cpath.exists() else None
    if ids is not None:
        absent = [i for i in ids if i not in doc["cities"]]
        if absent:
            out.append(("FAIL", f"citizens.json lacks {len(absent)} cities.json ids ({', '.join(absent[:5])})"))
        extra = [i for i in doc["cities"] if i not in set(ids)]
        if extra:
            out.append(("WARN", f"citizens.json has {len(extra)} ids not in cities.json ({', '.join(extra[:5])})"))
    have = Counter()
    for cid, row in doc["cities"].items():
        if row is None:
            continue
        for rid in ROW_IDS:
            if row.get(rid) is not None:
                have[rid] += 1
            check_row(rid, row.get(rid), cid)
        for s in row.get("specialists", []):
            if not {"row", "key", "share", "national", "ratio"} <= s.keys() or s["key"] not in keys.get(s["row"], []):
                probs["specialists malformed"] += 1
    if probs:
        out.append(("FAIL", f"citizens.json rows: {dict(probs)}"))
    if not out:
        n = sum(1 for r in doc["cities"].values() if r)
        out.append(("PASS", f"citizens.json: {n} of {len(doc['cities'])} cities with a row ("
                            + ", ".join(f"{r} {have[r]}" for r in ROW_IDS) + ")"))
    size = path.stat().st_size
    if size > 1_500_000:
        out.append(("WARN", f"citizens.json is {size / 1e3:.0f} kB (lazy file; keep it near ~1 MB)"))
    return out
