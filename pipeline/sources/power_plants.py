"""Power plants of the map's countries: the powerplantmatching dataset (PyPSA), which merges the JRC Open Power Plants
Database, ENTSO-E, the Global Energy Monitor trackers, Open Power System Data, national registers and the WRI Global
Power Plant Database into one list with commissioning and retirement years; the WRI database itself only for the map
countries powerplantmatching does not cover (Iceland, Cyprus)."""

from __future__ import annotations

import csv
import io
import re
from collections import Counter, defaultdict

from ..core.europe import COUNTRIES
from ..core.source import Source, SourceInfo

PPM_VERSION = "v0.9.1"  # release of 7 October 2026 (the CSV is regenerated for each release)
PPM_URL = f"https://raw.githubusercontent.com/PyPSA/powerplantmatching/{PPM_VERSION}/powerplants.csv"
PPM_FILE = f"powerplants_{PPM_VERSION}.csv"
WRI_URL = ("https://raw.githubusercontent.com/wri/global-power-plant-database/master/output_database/"
           "global_power_plant_database.csv")
WRI_FILE = "global_power_plant_database_v1.3.csv"
YEAR = 2026  # in service: commissioned by this year and not retired before it (a plant due to close this year stays,
# with its closing year: the dataset's retirement years for the current year are mostly announced closures)
MIN_MW = 1.0  # smaller rows (rooftop solar, single small turbines) are left out
NAMED_MW = 20.0  # names are kept for rows at least this big (smaller ones only add to wind/solar clusters)
BATTERY_SINCE = 2012  # battery rows need a commissioning year from this one on: the storage database behind them
# also lists projects without a date, and a few older rows are other plants filed as batteries (Portoscuso, 1973)

NAME_TO_CODE = {name: code for code, (name, _, _) in COUNTRIES.items()}
WRI_ISO3 = {"ISL": "IS", "CYP": "CY", "MLT": "MT", "LIE": "LI"}
PLACEHOLDER_NAMES = 5  # this many differently named plants at one exact position: a stand-in position, dropped
# Units the dataset still lists as running that have been shut down (Belgian nuclear phase-out, law of 2003 as amended).
RETIRED = {"Doel 1": 2025, "Doel 2": 2025, "Tihange 1": 2025}


def ppm_kind(fuel: str, tech: str, name: str) -> str | None:
    """powerplantmatching Fueltype/Technology → resource kind ('offshore' = offshore wind), or None (not mapped)."""
    if "Tidal" in name:
        return "tidal"  # La Rance is filed as pumped storage
    if fuel == "Hydro":
        return "pumped_storage" if tech == "Pumped Storage" else "hydro"
    if fuel == "Wind":
        return "offshore" if tech == "Offshore" else "wind"
    return {"Nuclear": "nuclear", "Hard Coal": "coal_plant", "Lignite": "coal_plant", "Natural Gas": "gas_plant",
            "Solar": "solar", "Battery": "battery", "Geothermal": "geothermal"}.get(fuel)


WRI_KIND = {"Nuclear": "nuclear", "Hydro": "hydro", "Coal": "coal_plant", "Gas": "gas_plant", "Wind": "wind",
            "Solar": "solar", "Geothermal": "geothermal", "Storage": "battery", "Wave and Tidal": "tidal"}


def _year(v: str) -> int | None:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


class PowerPlants(Source):
    info = SourceInfo(
        id="power_plants",
        title="Power plants of Europe (powerplantmatching, with the WRI Global Power Plant Database)",
        publisher="PyPSA powerplantmatching (Karlsruhe Institute of Technology, TU Berlin and contributors); "
        "World Resources Institute",
        homepage="https://github.com/PyPSA/powerplantmatching",
        license="CC BY 4.0",
        description=f"Every power plant and storage site of powerplantmatching {PPM_VERSION}, a merge of the JRC Open "
        "Power Plants Database (JRC-PPDB-OPEN), ENTSO-E, the Global Energy Monitor trackers, Open Power System Data, "
        "national registers (such as Germany's Marktstammdatenregister) and the WRI Global Power Plant Database: fuel, "
        "technology, capacity, position, commissioning and retirement years. Iceland and Cyprus, which it does not "
        "cover, come from the WRI Global Power Plant Database 1.3 (2021). Only plants in service in "
        f"{YEAR} of at least {MIN_MW:g} MW are read, and batteries only with a commissioning year from "
        f"{BATTERY_SINCE} (the storage database behind them also lists undated projects).",
        used_for=["Nuclear, hydro, coal, gas and geothermal plants", "Wind, solar and battery clusters"],
    )

    def fetch(self, force=False):
        self.download(PPM_URL, PPM_FILE, force=force)
        self.download(WRI_URL, WRI_FILE, force=force)

    def process(self):
        cols = ["name", "country", "kind", "mw", "lon", "lat", "since", "until", "source"]
        rows, seen = [], set()
        skipped = Counter()
        with open(self.raw_dir / PPM_FILE, encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                code = NAME_TO_CODE.get(r["Country"])
                kind = ppm_kind(r["Fueltype"], r["Technology"], r["Name"])
                if not code or not kind:
                    continue
                seen.add(code)
                mw = float(r["Capacity"] or 0)
                since, until = _year(r["DateIn"]), RETIRED.get(r["Name"]) or _year(r["DateOut"])
                if until is not None and until < YEAR:
                    skipped["retired"] += 1
                    continue
                if since is not None and since > YEAR:
                    skipped["planned"] += 1
                    continue
                if kind == "battery" and (since is None or since < BATTERY_SINCE):
                    skipped["undated battery"] += 1
                    continue
                if mw < MIN_MW or not r["lat"] or not r["lon"]:
                    skipped["small or unplaced"] += 1
                    continue
                rows.append([r["Name"].strip() if mw >= NAMED_MW or kind not in ("wind", "solar", "battery") else None,
                             code, kind, round(mw, 2), round(float(r["lon"]), 5), round(float(r["lat"]), 5), since,
                             until if until == YEAR else None, "ppm"])
        # A position shared by many differently named plants is a stand-in (the centre of Romania or Italy given
        # for wind farms whose site is unknown), not where they stand.
        # (Units of one plant share a position too: names are compared without their unit numbers.)
        names_at: dict[tuple, set] = defaultdict(set)
        for r in rows:
            if r[0]:
                names_at[(r[4], r[5])].add(re.sub(r"(\s+(\d+[a-z]?|[IVX]+))+$", "", r[0], flags=re.I).lower())
        stand_ins = {k for k, v in names_at.items() if len(v) >= PLACEHOLDER_NAMES}
        if stand_ins:
            before = len(rows)
            rows = [r for r in rows if (r[4], r[5]) not in stand_ins]
            skipped["at a stand-in position"] += before - len(rows)
        missing = sorted(set(COUNTRIES) - seen)
        wri = 0
        text = (self.raw_dir / WRI_FILE).read_text(encoding="utf-8")
        for r in csv.DictReader(io.StringIO(text)):
            code = WRI_ISO3.get(r["country"])
            kind = WRI_KIND.get(r["primary_fuel"])
            if code not in missing or not kind:
                continue
            mw = float(r["capacity_mw"] or 0)
            if mw < MIN_MW:
                continue
            rows.append([r["name"].strip(), code, kind, round(mw, 2), round(float(r["longitude"]), 5),
                         round(float(r["latitude"]), 5), _year(r["commissioning_year"]), None, "wri"])
            wri += 1
        print(f"    {len(rows)} plants in service of {MIN_MW:g} MW or more ({wri} from WRI for {', '.join(missing)}); "
              f"left out: {dict(skipped)}")
        return {"vintage": f"powerplantmatching {PPM_VERSION}; WRI Global Power Plant Database 1.3",
                "_files": [PPM_FILE, WRI_FILE], "year": YEAR, "ppm_version": PPM_VERSION,
                "wri_countries": missing, "columns": cols, "rows": rows}
