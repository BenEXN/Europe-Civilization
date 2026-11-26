"""districts.json: each city's real industry specialisation as strategy-game districts (docs/DATA_CONTRACTS.md,
"districts.json (lazy)").

Two Eurostat sources, each used where it is best:

* Regional accounts (sources/eurostat.py, nama_10r_3empers): jobs by NACE A*10 branch for every NUTS 3 region,
  self-employed included, counted where the work is done. A city takes each of its regions' jobs in proportion to the
  share of the region's population living in the urban area, like cities.json. Districts whose industries are a whole
  branch (finance K, manufacturing C, public administration-education-health O-Q) use these figures directly.
* Structural business statistics (sources/sbs.py, sbs_r_nuts2021): persons employed in local units by NACE division,
  published for NUTS 2 regions only. A division's jobs in a NUTS 3 region are its NUTS 2 region's jobs in that division
  shared out by the NUTS 3 region's jobs in the division's branch (regional accounts): Haute-Garonne gets the share of
  Midi-Pyrénées's aircraft-industry jobs that it has of the region's manufacturing jobs. So within a branch, a city has
  its NUTS 2 region's mix of divisions; the branch's size is the city's own. Figures Eurostat withholds as confidential
  are estimated from what the NUTS 1 or national total leaves over after the published regions, shared out by the size
  of the section; when nothing is left to estimate from, the figure counts as zero and the total is a lower bound.

LQ (location quotient) = (the city's jobs in the district's industries ÷ its total jobs) ÷ (the same ratio for
Europe). Europe is the 37 countries for the regional accounts, and the 31 that publish SBS for the divisions (no SBS
for Switzerland, Liechtenstein, Albania, Bosnia and Herzegovina, Montenegro and Kosovo: their cities get only the
branch-based districts).
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from ..core.hexgrid import HexGrid
from ..core.paths import WEB_DATA
from ..core.store import load_interim, write_web
from .yields import Stats

REQUIRES = ["_world", "_places", "eurostat", "sbs", "gisco", "cities.json", "world.json", "infrastructure.json"]
PRODUCES = ["districts.json"]

MIN_LQ, MIN_JOBS, MIN_SHARE = 1.25, 1000, 0.01
GOV_COUNTRY_LQ = 1.1  # Government plaza also needs this LQ against its own country (except in national capitals)
SPECIALTY_LQ, SPECIALTY_JOBS = 3.0, 1000
MAX_PER_CITY = 5
BADGE_LQ, BADGE_SHARE = 6.0, 0.03
TOP_MIN_JOBS, TOP_N = 1000, 8
SBS_MAX_LAG = 2  # a region's SBS year may be up to this many years older than the latest

# Codes taken whole from the regional accounts (NUTS 3), everything else from SBS (NUTS 2, shared out).
NAMA = {"C", "F", "J", "K", "L", "M_N", "O-Q", "R-U", "G-I", "A"}
# SBS section → the regional-accounts branch its jobs are shared out by ("BDE": B-E without manufacturing).
SECTION_BRANCH = {"B": "BDE", "C": "C", "D": "BDE", "E": "BDE", "F": "F", "G": "G-I", "H": "G-I", "I": "G-I", "J": "J",
                  "K": "K", "L": "L", "M": "M_N", "N": "M_N", "P": "O-Q", "Q": "O-Q", "R": "R-U", "S": "R-U"}

# Short English titles (the top-industries table and the specialities).
TITLES = {
    "B": "Mining and quarrying", "B05": "Coal and lignite mining", "B06": "Oil and gas extraction",
    "B07": "Metal ore mining", "B08": "Quarrying (stone, sand, clay, salt)", "B09": "Mining support services",
    "C": "Manufacturing", "C10": "Food processing", "C11": "Beverages (wine, beer, spirits)", "C12": "Tobacco products",
    "C13": "Textiles", "C14": "Clothing", "C15": "Leather and footwear", "C16": "Wood products", "C17": "Paper and board",
    "C18": "Printing", "C19": "Oil refining and coke", "C20": "Chemicals", "C21": "Pharmaceuticals",
    "C22": "Rubber and plastics (tyres)", "C23": "Glass, ceramics and cement", "C24": "Steel and basic metals",
    "C25": "Metal products", "C26": "Electronics, computers and optics", "C27": "Electrical equipment",
    "C28": "Machinery", "C29": "Cars and car parts", "C30": "Aircraft, ships and trains", "C31": "Furniture",
    "C32": "Medical devices, jewellery, toys and other goods", "C33": "Machinery repair and installation",
    "D": "Power and gas", "D35": "Power and gas supply", "E": "Water, sewage and waste", "E36": "Water supply",
    "E37": "Sewerage", "E38": "Waste and recycling", "E39": "Remediation", "F": "Construction",
    "F41": "Building construction", "F42": "Civil engineering", "F43": "Specialised construction trades",
    "G45": "Car dealers and repair", "G46": "Wholesale trade", "G47": "Retail trade", "H49": "Road and rail transport",
    "H50": "Shipping", "H51": "Airlines", "H52": "Warehousing, port and airport services", "H53": "Post and couriers",
    "I55": "Hotels and holiday lodging", "I56": "Restaurants and bars", "J": "Information and communication",
    "J58": "Publishing (books, press, software)", "J59": "Film, TV and music production", "J60": "Radio and TV broadcasting",
    "J61": "Telecommunications", "J62": "Software and IT services", "J63": "Data processing and web portals",
    "K": "Finance and insurance", "K64": "Banking and financial services", "K65": "Insurance and pension funds",
    "K66": "Fund management, exchanges and brokers", "L": "Real estate", "L68": "Real estate",
    "M69": "Law and accounting", "M70": "Head offices and management consulting",
    "M71": "Engineering, architecture and testing", "M72": "Research and development",
    "M73": "Advertising and market research", "M74": "Design, photography and translation", "M75": "Veterinary",
    "N77": "Rental and leasing", "N78": "Employment agencies", "N79": "Travel agencies and tour operators",
    "N80": "Security services", "N81": "Cleaning and landscaping", "N82": "Office support and call centres",
    "R90": "Performing and creative arts", "R91": "Museums, libraries and heritage", "R92": "Gambling and betting",
    "R93": "Sports, amusement parks and recreation", "O-Q": "Public administration, education and health",
    "R-U": "Arts, recreation, other services and households", "M_N": "Professional and support services",
    "G-I": "Trade, transport, hotels and restaurants", "A": "Agriculture, forestry and fishing",
}
# The top-industries table: divisions of the business economy (P and Q are only their market part in SBS, so they are
# left out; S is personal services).
TOP_CODES = [c for c in TITLES if len(c) == 3 and c[1:].isdigit() and c[0] in "BCDEFGHIJKLMNR"]


def _d(id, name, color, codes, sub, badge, labels, description, caveat=None):
    return {"id": id, "name": name, "icon": f"d-{id}", "color": color, "naics": codes, "own": [],
            "sub": {k: TITLES[k] for k in sub}, "badge": {"id": badge, "label": labels.pop("_"), "labels": labels},
            "description": description, "caveat": caveat}


REGIONAL = ("Specialities are regional: the city has its NUTS 2 region's mix of industries within each branch, "
            "scaled to its own jobs in that branch.")
CATALOG = [
    _d("campus", "Campus", "#4a7bd0", ["J61", "J62", "J63", "M71", "M72"], ["M72", "J62", "J63", "J61", "M71"],
       "scientific", {"_": "Knowledge city", "M72": "Research city", "J62": "Tech city", "J63": "Tech city",
                      "J61": "Telecom city", "M71": "Engineering city"},
       "Research and development, software and IT, telecoms, engineering.",
       "Universities and public research are outside the business statistics Eurostat publishes for regions. " + REGIONAL),
    _d("commercial_hub", "Commercial hub", "#d9a93a", ["K"], ["K64", "K65", "K66"],
       "commercial", {"_": "Finance city", "K64": "Banking city", "K65": "Insurance city", "K66": "Finance city"},
       "Banks, insurers, fund managers and exchanges.", REGIONAL),
    _d("industrial_zone", "Industrial zone", "#b0603a", ["B", "C"],
       ["C29", "C30", "C26", "C21", "C20", "C19", "C24", "C28", "C27", "C22", "C23", "C25", "C10", "C11", "C12", "C13",
        "C14", "C15", "C16", "C17", "C31", "C32", "B05", "B06", "B07", "B08"],
       "industrial", {"_": "Factory town", "C29": "Car city", "C30": "Aerospace city",
                      "C26": "Electronics city", "C21": "Pharma city", "C20": "Chemical city", "C19": "Refinery town",
                      "C24": "Steel town", "C28": "Machine-building town", "C27": "Electrical-goods town",
                      "C22": "Tyre and plastics town", "C23": "Glass and ceramics town", "C25": "Metalworking town",
                      "C10": "Food-processing town", "C11": "Wine and brewing town", "C12": "Tobacco town",
                      "C13": "Textile town", "C14": "Garment town", "C15": "Shoe and leather town",
                      "C16": "Timber town", "C17": "Paper-mill town", "C31": "Furniture town",
                      "C32": "Medtech and jewellery town", "B05": "Coal town", "B06": "Oil town", "B07": "Mining town",
                      "B08": "Quarry town"},
       "Manufacturing, mining and quarrying.",
       "Aircraft, ships and trains name a city 'Shipyard city' when it also has a Harbor district, else "
       "'Aerospace city' (aircraft are most of this industry's jobs in Europe; trains are counted here too). "
       + REGIONAL),
    _d("harbor", "Harbor", "#3f7fb5", ["H50", "H52"], ["H50", "H52"],
       "maritime", {"_": "Port city", "H50": "Port city", "H52": "Port and logistics city"},
       "Shipping, and the warehousing and cargo handling around ports.",
       "Warehousing and transport services also serve airports and inland logistics; the district needs a seaport. "
       + REGIONAL),
    _d("theater_square", "Theater square", "#b07ce0", ["J58", "J59", "J60", "R90", "R91"],
       ["R90", "J59", "J60", "J58", "R91"], "cultural",
       {"_": "Arts city", "R90": "Arts city", "J59": "Film city", "J60": "Broadcasting city", "J58": "Publishing city",
        "R91": "Museum city"},
       "Performing arts, film, TV and music, broadcasting, publishing, museums.",
       "Public theatres and museums run by governments are often outside the business statistics. " + REGIONAL),
    _d("entertainment_complex", "Entertainment complex", "#e0708a", ["I55", "R92", "R93"], ["I55", "R93", "R92"],
       "entertainment", {"_": "Resort city", "I55": "Resort city", "R93": "Leisure city", "R92": "Betting city"},
       "Hotels and holiday lodging, sports and amusement parks, gambling.", REGIONAL),
    _d("aerodrome", "Aerodrome", "#6a9ad8", ["H51"], ["H51"], "aviation", {"_": "Air hub", "H51": "Air hub"},
       "Airlines (passenger and freight air transport).",
       "Airport ground services are counted with warehousing (Harbor). The district needs an airport. " + REGIONAL),
    _d("government_plaza", "Government plaza", "#7a8aa8", ["O-Q"], [], "governmental", {"_": "Government town"},
       "Public administration and defence, education, health and social work.",
       "Eurostat publishes public administration together with education and health for regions, so hospitals, "
       "schools and universities count here too. Their share mostly follows how much of a country's health and "
       "education is public, so outside national capitals this district also needs the share to be "
       f"{GOV_COUNTRY_LQ:g}× the country's own."),
    _d("encampment", "Encampment", "#8a4a3a", [], [], "militaristic", {"_": "Military town"},
       "Armed forces.", "No regional defence employment is published for Europe: this district comes only from "
       "military.json, when that file exists."),
    _d("aqueduct", "Aqueduct", "#3fa7a0", ["D", "E"], ["D", "E"], "utility",
       {"_": "Utility town", "D": "Power town", "E": "Water and waste town"},
       "Power and gas supply, water, sewage, waste and recycling.", REGIONAL),
]
CAT = {c["id"]: c for c in CATALOG}

RULE_TEXT = (
    f"A district appears when its industries' share of the urban area's jobs is at least {MIN_LQ}× their share of "
    f"Europe's jobs (the location quotient), with at least {MIN_JOBS:,} jobs or {round(MIN_SHARE * 100)}% of the "
    f"area's jobs, or when one of its specialities is at least {SPECIALTY_LQ:g}× the European share with "
    f"{SPECIALTY_JOBS:,} jobs. Districts are ranked by jobs above the European norm (jobs − jobs ÷ LQ), five at most. "
    f"Harbor needs a seaport handling 500,000 tonnes a year in or next to the urban area, Aerodrome an airport with "
    f"50,000 passengers (when infrastructure.json is built; otherwise Harbor needs a hex on the water or a river). "
    f"Government plaza (public administration, education and health, which Eurostat publishes together for "
    f"regions) also needs {GOV_COUNTRY_LQ:g}× its country's own share, except in national capitals. "
    f"The city type is its strongest district, unless a district or one of its specialities is {BADGE_LQ:g}× the "
    f"norm with {round(BADGE_SHARE * 100)}% of the area's jobs; it is named after the speciality when that is "
    f"{SPECIALTY_LQ:g}× the norm. Jobs by branch come from Eurostat's regional accounts for the urban area's NUTS 3 "
    f"regions (counted where people work, self-employed included); finance, manufacturing and the public "
    f"administration-education-health group use them directly. The other districts and every speciality use "
    f"Eurostat's business statistics by NACE division, published only for NUTS 2 regions: each division's regional "
    f"jobs are shared out among the NUTS 3 regions by their jobs in its branch, so a city has its NUTS 2 region's mix "
    f"of industries within each branch. Figures withheld as confidential are estimated from what the NUTS 1 or "
    f"national total leaves over; '≥' marks a lower bound where nothing was left to estimate from. Europe is the 37 "
    f"countries for branches and the 31 publishing business statistics for divisions (not Switzerland, "
    f"Liechtenstein, Albania, Bosnia and Herzegovina, Montenegro, Kosovo).")
COUNTY_NOTE = ("Same rule for each NUTS 3 region, its divisions shared out from its NUTS 2 region; Harbor and Aerodrome "
               "need a port or airport in the region itself.")


# ------------------------------------------------------------------------------------------------ the job figures

class Jobs:
    """Jobs by code for map NUTS 3 regions: regional accounts for whole branches, SBS divisions shared out."""

    def __init__(self, s: Stats, sbs: dict, counties: list[str]):
        self.s, self.year = s, s.gdp_year
        self.vals, self.held = sbs["values"], sbs["withheld"]
        latest = max(int(y) for y in sbs["years"])
        # each SBS geography's year: the latest with at least 20 published or withheld cells, not too old
        self.yr = {}
        for g, by in self.vals.items():
            ok = [y for y in by if len(by[y]) + len(self.held.get(g, {}).get(y, [])) >= 20
                  and int(y) >= latest - SBS_MAX_LAG]
            if ok:
                self.yr[g] = max(ok)
        self.counties = counties
        self.unit = {}  # NUTS 3 → the most detailed SBS geography covering it
        for r3 in counties:
            self.unit[r3] = next((g for g in (r3[:4], r3[:3], r3[:2]) if g in self.yr), None)
        self.members: dict = {}
        for r3, u in self.unit.items():
            if u:
                self.members.setdefault(u, []).append(r3)
        self._nama: dict = {}
        self._part: dict = {}
        self._sbs: dict = {}

    # regional accounts, persons
    def nama(self, geo: str, code: str):
        key = (geo, code)
        if key not in self._nama:
            if code == "BDE":
                a, b = self.nama(geo, "B-E"), self.nama(geo, "C")
                v = max(0.0, a - b) if a is not None and b is not None else None
            else:
                v = self.s.value("emp3", code, geo, self.year)
                v = v * 1000 if v is not None else None
            self._nama[key] = v
        return self._nama[key]

    def _branch_jobs(self, geos, branch):
        return sum(self.nama(g, branch) or 0.0 for g in geos)

    def sbs(self, g: str, code: str):
        """(persons, status) for an SBS geography: "ok", "est" (a withheld figure estimated from an ancestor's
        remainder), "held" (withheld, nothing to estimate from: 0) or "none" (not published)."""
        y = self.yr.get(g)
        key = (g, code, y)
        if key in self._sbs:
            return self._sbs[key]
        row = self.vals.get(g, {}).get(y or "", {})
        if code in row:
            out = (row[code], "ok")
        elif code in self.held.get(g, {}).get(y or "", []):
            out = self._estimate(g, code, y)
        else:
            out = (None, "none")
        self._sbs[key] = out
        return out

    def _weight(self, g, code, y):
        if len(code) == 3:
            v = self.vals.get(g, {}).get(y, {}).get(code[0])
            if v:
                return v
        return self._branch_jobs(self.members.get(g) or [c for c in self.counties if c.startswith(g)],
                                 SECTION_BRANCH[code[0]])

    def _estimate(self, g, code, y):
        level = len(g)
        for n in range(level - 1, 1, -1):
            anc = g[:n]
            av = self.vals.get(anc, {}).get(y, {}).get(code)
            if av is None:
                continue
            kids = sorted({u for u in self.unit.values() if u and len(u) == level and u.startswith(anc)
                           and self.yr.get(u) == y} | {g})
            known, held = 0.0, []
            for k in kids:
                kv = self.vals.get(k, {}).get(y, {}).get(code)
                if kv is not None:
                    known += kv
                elif code in self.held.get(k, {}).get(y, []):
                    held.append(k)
            left = max(0.0, av - known)
            w = {k: self._weight(k, code, y) for k in held}
            tw = sum(w.values())
            share = w.get(g, 0.0) / tw if tw else 1.0 / max(1, len(held))
            return (left * share, "est")
        return (0.0, "held")

    def part(self, r3: str, code: str):
        """(persons, status) of a code in one map NUTS 3 region."""
        key = (r3, code)
        if key in self._part:
            return self._part[key]
        if code in NAMA:
            v = self.nama(r3, code)
            out = (v, "ok" if v is not None else "none")
        else:
            u = self.unit.get(r3)
            v, st = self.sbs(u, code) if u else (None, "none")
            if v is None:
                out = (None, "none")
            else:
                branch = SECTION_BRANCH[code[0]]
                mine, tot = self.nama(r3, branch), self._branch_jobs(self.members[u], branch)
                if not mine or not tot:  # no branch figure: by total jobs
                    mine, tot = self.nama(r3, "TOTAL"), self._branch_jobs(self.members[u], "TOTAL")
                out = (v * (mine or 0.0) / tot if tot else 0.0, st)
        self._part[key] = out
        return out

    def europe(self, code: str, states: list[str]):
        """(Europe's jobs in the code, Europe's total jobs over the same countries)."""
        num = den = 0.0
        for cc in states:
            tot = self.nama(cc, "TOTAL")
            if not tot:
                continue
            if code in NAMA or code == "BDE":
                v = self.nama(cc, code)
            else:
                v, st = self.sbs(cc, code) if cc in self.yr else (None, "none")
                if st != "ok":
                    v = None
            if v is None:
                continue
            num += v
            den += tot
        return num, den


def aggregate(jobs: Jobs, parts: list[tuple[float, str]], codes) -> tuple[float | None, int, int]:
    """(jobs, member regions with a withheld or unpublished part, member regions with an estimated part) of a place
    made of [(share, NUTS 3)]. None when no part has any figure."""
    emp, have = 0.0, False
    held, est = set(), set()
    for f, r3 in parts:
        if f <= 0:
            continue
        for code in codes:
            v, st = jobs.part(r3, code)
            if st == "none":
                held.add(r3)
                continue
            have = True
            emp += f * v
            if st == "held":
                held.add(r3)
            elif st == "est":
                est.add(r3)
    return (emp if have else None), (len(held) if have else 0), len(est)


# ------------------------------------------------------------------------------------------------ the rule

class Norm:
    """Europe's share of jobs for each code (and the denominator for LQs)."""

    def __init__(self, jobs: Jobs, states: list[str]):
        self.jobs, self.states = jobs, states
        self._share: dict = {}
        self.emp: dict = {}

    def share(self, code):
        if code not in self._share:
            num, den = self.jobs.europe(code, self.states)
            self._share[code] = num / den if den else None
            self.emp[code] = num
        return self._share[code]

    def country(self, cc, code):
        """The country's own share of jobs in a regional-accounts code."""
        a, b = self.jobs.nama(cc, code), self.jobs.nama(cc, "TOTAL")
        return a / b if a is not None and b else None

    def of(self, codes):
        vals = [self.share(c) for c in codes]
        vals = [v for v in vals if v is not None]
        return sum(vals) if vals else None


def lq(emp, total, share):
    return emp / total / share if emp is not None and total and share else 0.0


def districts_of(jobs: Jobs, norm: Norm, parts, total, wet=None, airport=None, country=None,
                 capital=False) -> list[dict]:
    """The place's districts passing the rule, strongest first (≤ MAX_PER_CITY). wet/airport: None = no test;
    country: the place's country (Government plaza's second test), skipped in a national capital."""
    out = []
    for c in CATALOG:
        if not c["naics"] or (c["id"] == "harbor" and wet is False) or (c["id"] == "aerodrome" and airport is False):
            continue
        emp, sup, est = aggregate(jobs, parts, c["naics"])
        if emp is None:
            continue
        q = lq(emp, total, norm.of(c["naics"]))
        best = None
        for code in c["sub"]:
            se, ssup, _ = aggregate(jobs, parts, [code])
            if se is None or se < SPECIALTY_JOBS:
                continue
            sq = lq(se, total, norm.share(code))
            if sq > 1 and (best is None or sq > best[1]):
                best = (code, sq, se, ssup)
        broad = q >= MIN_LQ and (emp >= MIN_JOBS or emp >= MIN_SHARE * total)
        extra = {}
        if c["id"] == "government_plaza":
            cs = norm.country(country, "O-Q") if country else None
            qc = lq(emp, total, cs) if cs else None
            extra["lq_country"] = round(qc, 2) if qc is not None else None
            broad = broad and (capital or (qc is not None and qc >= GOV_COUNTRY_LQ))
        spec = best is not None and best[1] >= SPECIALTY_LQ and best[2] >= SPECIALTY_JOBS
        if not (broad or spec):
            continue
        strength = max(emp - emp / q if q else 0.0, (best[2] - best[2] / best[1]) if best else 0.0)
        out.append({"id": c["id"], "lq": round(q, 2), "emp": round(emp), "share": round(emp / total, 4),
                    "avg_pay": None, "sub": best[0] if best else None, "sub_lq": round(best[1], 2) if best else None,
                    "sub_emp": round(best[2]) if best else None, "sub_lower_bound": bool(best and best[3]),
                    "via": "broad" if broad else "specialty", "strength": round(strength), "suppressed": sup,
                    "lower_bound": sup > 0, "estimated": est, **extra})
    out.sort(key=lambda d: -d["strength"])
    return out[:MAX_PER_CITY]


def badge_of(ds: list[dict], capital: bool, total: float) -> dict | None:
    if not ds:
        return None
    strong = [d for d in ds if (d["lq"] >= BADGE_LQ and (d["share"] or 0) >= BADGE_SHARE)
              or (d["sub"] and (d["sub_lq"] or 0) >= BADGE_LQ and (d["sub_emp"] or 0) >= BADGE_SHARE * total)]
    d = strong[0] if strong else ds[0]
    c = CAT[d["id"]]
    by_sub = bool(d["sub"]) and (d["sub_lq"] or 0) >= SPECIALTY_LQ
    if d["id"] == "government_plaza" and capital:
        label = "Capital city"
    else:
        label = c["badge"]["labels"].get(d["sub"], c["badge"]["label"]) if by_sub else c["badge"]["label"]
        if by_sub and d["sub"] == "C30" and any(x["id"] == "harbor" for x in ds):
            label = "Shipyard city"
    what = c["sub"][d["sub"]] if by_sub else c["name"]
    q = d["sub_lq"] if by_sub else d["lq"]
    lb = d["sub_lower_bound"] if by_sub else d["lower_bound"]
    return {"id": c["badge"]["id"], "label": label, "district": d["id"], "basis": "eurostat",
            "text": f"{what}: {'≥' if lb else ''}{q:.1f}× the European share of jobs"}


def top_of(jobs: Jobs, norm: Norm, parts, total) -> list[dict]:
    top = []
    for code in TOP_CODES:
        e, sup, _ = aggregate(jobs, parts, [code])
        if e is None or e < TOP_MIN_JOBS:
            continue
        q = lq(e, total, norm.share(code))
        if q > 1:
            top.append({"naics": code, "emp": round(e), "lq": round(q, 2), "avg_pay": None,
                        "oty_pct": None, "suppressed": sup, "lower_bound": sup > 0})
    top.sort(key=lambda t: -t["lq"])
    return top[:TOP_N]


# ------------------------------------------------------------------------------------------------ build

def _infrastructure():
    p = WEB_DATA / "infrastructure.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except ValueError:
        return None


def _sites(items, grid, cities):
    """{city id: name of its biggest site} for sites inside a city's urban area (cbsa) or on/next to its footprint."""
    by_cell: dict = {}
    out: dict = {}
    for it in items:  # sorted biggest first
        if it.get("cbsa"):
            out.setdefault(it["cbsa"], it["name"])
        if it.get("cell") is not None and it["cell"] >= 0:
            by_cell.setdefault(it["cell"], it["name"])
    for c in cities:
        if c["id"] in out:
            continue
        near = set(c["footprint"]) | {n for f in c["footprint"] for n in grid.neighbours(f)}
        hits = [by_cell[k] for k in near if k in by_cell]
        if hits:
            out[c["id"]] = hits[0]
    return out


def build() -> None:
    world = load_interim("_world")
    places = load_interim("_places")
    sbs = load_interim("sbs")
    sbs_vintage = max(sbs["years"])
    cities = json.loads((WEB_DATA / "cities.json").read_text())
    wjson = json.loads((WEB_DATA / "world.json").read_text())
    grid = HexGrid(**world["grid"])
    s = Stats(world["counties"], places["region_pop"])
    jobs = Jobs(s, sbs, world["counties"])
    norm = Norm(jobs, world["states"])
    infra = _infrastructure()
    ports = _sites(infra.get("ports", []), grid, cities) if infra else None
    airports = _sites(infra.get("airports", []), grid, cities) if infra else None
    port_regions = {p["county"] for p in infra.get("ports", []) if p.get("county")} if infra else None
    air_regions = {a["county"] for a in infra.get("airports", []) if a.get("county")} if infra else None
    water = wjson["water"]
    river_cells = {grid.cell_at(r["pts"][k], r["pts"][k + 1]) for r in wjson["rivers"] for k in range(0, len(r["pts"]), 2)}
    region_pop = places["region_pop"]

    out_c: dict = {}
    for c in cities:
        if c["source"] == "urban_audit":
            parts = [(min(1.0, p / region_pop[g]) if region_pop.get(g) else 0.0, g)
                     for g, p in places["fua_regions"].get(c["id"], {}).items()]
        else:
            parts = []
            for g in c["counties"]:
                rp = s.value("pop3", "TOTAL", g, s.pop_year)
                parts.append((min(1.0, c["population"] / rp) if rp else 0.0, g))
        parts = [(f, g) for f, g in parts if f > 0 and g in jobs.unit]
        total = sum(f * (jobs.nama(g, "TOTAL") or 0.0) for f, g in parts)
        if not parts or not total or any(jobs.nama(g, "TOTAL") is None for _, g in parts):
            out_c[c["id"]] = None
            continue
        if ports is not None:
            wet = c["id"] in ports
        else:
            wet = any(water[n] for f in c["footprint"] for n in grid.neighbours(f)) or bool(set(c["footprint"]) & river_cells)
        air = (c["id"] in airports) if airports is not None else None
        capital = bool(c.get("national_capital"))
        ds = districts_of(jobs, norm, parts, total, wet, air, c["states"][0], capital)
        for d in ds:
            if d["id"] == "harbor" and ports:
                d["site"] = ports.get(c["id"])
            if d["id"] == "aerodrome" and airports:
                d["site"] = airports.get(c["id"])
        units = sorted({jobs.unit[g] for _, g in parts if jobs.unit.get(g)})
        n = len(c["counties"]) or len(parts)  # the urban area's regions as cities.json lists them
        out_c[c["id"]] = {"emp": round(total), "avg_pay": None, "counties": [n, n],
                          "regions": units, "top": top_of(jobs, norm, parts, total), "districts": ds,
                          "badge": badge_of(ds, capital, total)}

    out_r: dict = {}
    for g in world["counties"]:
        total = jobs.nama(g, "TOTAL")
        if not total:
            continue
        wet = (g in port_regions) if port_regions is not None else None
        air = (g in air_regions) if air_regions is not None else None
        ds = districts_of(jobs, norm, [(1.0, g)], total, wet, air, g[:2])
        out_r[g] = {"emp": round(total), "districts": [[d["id"], d["lq"], d["emp"]] for d in ds]}

    rows = [v for v in out_c.values() if v]
    badges = Counter(v["badge"]["label"] for v in rows if v["badge"])
    print(f"    {len(out_c)} cities: {len(rows)} with jobs, {sum(1 for v in rows if v['districts'])} with districts, "
          f"{sum(badges.values())} with a badge; {len(out_r)} NUTS 3 regions"
          f"{'' if infra else '; infrastructure.json missing: Harbor uses the water test, Aerodrome untested'}")
    print("    badges: " + ", ".join(f"{k} {n}" for k, n in badges.most_common(12)))
    eu_total = sum(jobs.nama(cc, "TOTAL") or 0.0 for cc in world["states"])
    names = {n["code"]: n["name"] for n in load_interim("gisco")["nuts"] if n.get("level") in (0, 1, 2)}
    used = sorted({u for v in rows for u in v["regions"]})
    industries = {}
    for code in TITLES:
        norm.share(code)
        industries[code] = {"title": TITLES[code], "eu_emp": round(norm.emp.get(code) or 0)}
    write_web("districts.json", {
        "version": 1,
        "vintage": f"Eurostat regional accounts {s.gdp_year} (jobs by branch, NUTS 3) and structural business "
                   f"statistics {sbs_vintage} (jobs by division, NUTS 2)",
        "year": int(sbs_vintage),
        "sources": ["eurostat", "sbs"],
        "rule": {"min_lq": MIN_LQ, "min_jobs": MIN_JOBS, "min_share": MIN_SHARE, "specialty_lq": SPECIALTY_LQ,
                 "specialty_jobs": SPECIALTY_JOBS, "max_per_city": MAX_PER_CITY, "harbor_needs_water": True,
                 "harbor_needs_port": infra is not None, "aerodrome_needs_airport": infra is not None,
                 "badge_lq": BADGE_LQ, "badge_share": BADGE_SHARE, "text": RULE_TEXT, "county_note": COUNTY_NOTE},
        "catalog": CATALOG,
        "industries": industries,
        "national": {"emp": round(eu_total), "avg_pay": None},
        "regions": {u: names.get(u, u) for u in used},  # the SBS regions (NUTS 2, or NUTS 1/0) the cities use
        "cities": out_c,
        "counties": out_r,
    })


# ------------------------------------------------------------------------------------------------ check

def check(web_dir: Path) -> list[tuple[str, str]]:
    path = Path(web_dir) / "districts.json"
    if not path.exists():
        return [("NOTE", "districts.json not built (optional; run: build districts)")]
    doc = json.loads(path.read_text())
    out: list[tuple[str, str]] = []
    missing = [k for k in ("version", "vintage", "year", "rule", "catalog", "industries", "national", "cities", "counties")
               if k not in doc]
    if missing:
        return [("FAIL", f"districts.json lacks {missing}")]
    ids = [c.get("id") for c in doc["catalog"]]
    want = ["campus", "commercial_hub", "industrial_zone", "harbor", "theater_square", "entertainment_complex",
            "aerodrome", "government_plaza", "encampment", "aqueduct"]
    if ids != want:
        out.append(("FAIL", f"districts.json catalog ids {ids} != {want}"))
    cat = {c["id"]: c for c in doc["catalog"]}
    if not isinstance(doc["rule"].get("text"), str) or not doc["rule"]["text"]:
        out.append(("FAIL", "districts.json rule.text missing"))
    cpath = Path(web_dir) / "cities.json"
    cities = {c["id"]: c for c in json.loads(cpath.read_text())} if cpath.exists() else None
    probs: Counter = Counter()
    n_d = n_b = 0
    for cid, row in doc["cities"].items():
        if cities is not None and cid not in cities:
            probs["unknown city id"] += 1
        if row is None:
            continue
        ds = row.get("districts") or []
        n_d += bool(ds)
        if len(ds) > doc["rule"]["max_per_city"]:
            probs["too many districts"] += 1
        if [d["strength"] for d in ds] != sorted((d["strength"] for d in ds), reverse=True):
            probs["districts not sorted by strength"] += 1
        for d in ds:
            if d["id"] not in cat:
                probs["unknown district id"] += 1
            elif d["sub"] is not None and d["sub"] not in cat[d["id"]]["sub"]:
                probs["speciality not in catalog"] += 1
            if not (isinstance(d["lq"], (int, float)) and d["lq"] >= 0 and isinstance(d["emp"], int) and d["emp"] >= 0):
                probs["bad lq/emp"] += 1
            if d["via"] == "broad" and d["lq"] < doc["rule"]["min_lq"]:
                probs["broad district under min_lq"] += 1
        b = row.get("badge")
        if b:
            n_b += 1
            if b.get("district") not in {d["id"] for d in ds}:
                probs["badge district not among districts"] += 1
            if not b.get("label") or not b.get("text"):
                probs["badge without label/text"] += 1
        elif ds:
            probs["districts but no badge"] += 1
        for t in row.get("top") or []:
            if t["naics"] not in doc["industries"]:
                probs["top industry without title"] += 1
        if cities is not None and cid in cities and cities[cid].get("employed"):
            if abs(row["emp"] / cities[cid]["employed"] - 1) > 0.02:
                probs["jobs differ from cities.json employed by > 2%"] += 1
    for k, n in sorted(probs.items()):
        out.append(("FAIL", f"districts.json: {n} cities with {k}"))
    rows = [r for r in doc["cities"].values() if r]
    if cities is not None:
        missing_c = [c for c in cities if c not in doc["cities"]]
        if missing_c:
            out.append(("WARN", f"districts.json: {len(missing_c)} cities.json cities without a row"))
    out.append(("PASS" if not probs else "NOTE",
                f"districts.json: {len(rows)} of {len(doc['cities'])} cities with jobs, {n_d} with districts, "
                f"{n_b} with a badge; {len(doc['counties'])} NUTS 3 regions"))
    return out
