"""The United Kingdom, which Eurostat's regional tables and GISCO's 2024 files no longer cover, rebuilt from the UK
statistical offices in the shapes of the `gisco` and `eurostat` interims, so the two can be merged:

* regions: the ITL 2025 levels (International Territorial Levels, the UK's successor to NUTS) recoded TL… → UK…
  (TLC31 → UKC31), with ONS boundaries for the 182 ITL3 regions;
* local units: the December 2022 electoral wards with their census population (2021 England, Wales and Northern
  Ireland; 2022 Scotland);
* functional urban areas and core cities: Eurostat's Urban Audit 2020, the last edition with the UK;
* tables keyed like the Eurostat ones (pop3, gdp3, gva3, emp3, unemp2, income2, lifeexp2, pop0…): ONS/NRS/NISRA
  population, regional accounts, BRES jobs, the Annual Population Survey, life expectancy; pounds become euros at
  Eurostat's yearly average rate and PPS through Eurostat's purchasing power parities. Every approximation is listed in
  the interim's "notes"."""

from __future__ import annotations

import csv
import difflib
import io
import json
import re
import statistics
import time
import unicodedata
import urllib.error
import zipfile
from collections import defaultdict

import urllib.parse

from ..core.europe import english_name
from ..core.fetch import UnexpectedContentError
from ..core.geo import Shape, ShapeIndex, geojson_rings
from ..core.ods import read_rows as ods_rows
from ..core.source import Source, SourceInfo
from ..core.xlsx import read_rows
from .gisco import centroid, thin
from .transport_hubs import LOCODE, LOCODE_TAG, OURAIRPORTS

ARC = "https://services1.arcgis.com/ESMARspQHYMw9BZ9/arcgis/rest/services"
NOMIS = "https://www.nomisweb.co.uk/api/v01/dataset"
ONS = "https://www.ons.gov.uk/file?uri="
GISCO = "https://gisco-services.ec.europa.eu/distribution/v2"
ESTAT = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data"

SINCE = 2014  # first year kept, as in the eurostat source
MID_YEARS = list(range(SINCE - 1, 2026))  # mid-year population estimates 2013-2025, filed as 1 January 2014-2026
APS_YEARS = list(range(SINCE, 2026))  # Annual Population Survey, January-December averages
BRES_YEARS = [2023, 2024]  # Business Register and Employment Survey (September), Great Britain and Northern Ireland
NOMIS_PAGE = 25_000  # rows per Nomis API response without a key
ARC_PAGE = 1000  # features per ArcGIS response (the wards service's maxRecordCount)
ONS_PAUSE = 8.0  # seconds between ons.gov.uk downloads (Cloudflare answers 429 to fast series of requests)
# ons.gov.uk turns away scripted user agents: a browser-like one, for that host only.
ONS_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0 Safari/537.36",
    "Accept": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/octet-stream,*/*",
}

BRANCHES = ["TOTAL", "A", "B-E", "C", "F", "G-I", "J", "K", "L", "M_N", "O-Q", "R-U"]
# NACE section → the A*10 branches it counts in (C is both a branch and part of B-E).
SECTION_BRANCHES = {"A": ["A"], "B": ["B-E"], "C": ["B-E", "C"], "D": ["B-E"], "E": ["B-E"], "F": ["F"],
                    "G": ["G-I"], "H": ["G-I"], "I": ["G-I"], "J": ["J"], "K": ["K"], "L": ["L"], "M": ["M_N"],
                    "N": ["M_N"], "O": ["O-Q"], "P": ["O-Q"], "Q": ["O-Q"], "R": ["R-U"], "S": ["R-U"],
                    "T": ["R-U"], "U": ["R-U"]}
# ONS GVA (SIC07 code before " (") → branches. ITL3 tables publish agriculture and mining together (AB), energy and
# water together (DE); ITL1/ITL2 tables split them, and follow the ITL3 convention (mining in A) so levels add up.
GVA_BRANCHES = {"Total": ["TOTAL"], "AB": ["A"], "A": ["A"], "B": ["A"], "C": ["B-E", "C"], "DE": ["B-E"],
                "D": ["B-E"], "E": ["B-E"], "F": ["F"], "G": ["G-I"],
                "H": ["G-I"], "I": ["G-I"], "J": ["J"], "K": ["K"], "L": ["L"], "M": ["M_N"], "N": ["M_N"],
                "O": ["O-Q"], "P": ["O-Q"], "Q": ["O-Q"], "R": ["R-U"], "S": ["R-U"], "T": ["R-U"]}
# Life expectancy: the published figure of each ITL1 region (English regions, the three other nations).
LE_ITL1 = {"E12000001": "TLC", "E12000002": "TLD", "E12000003": "TLE", "E12000004": "TLF", "E12000005": "TLG",
           "E12000006": "TLH", "E12000007": "TLI", "E12000008": "TLJ", "E12000009": "TLK", "W92000004": "TLL",
           "S92000003": "TLM", "N92000002": "TLN"}
UK_CODE, NI_CODE = "K02000001", "N92000002"
NI_ITL = ("TLN", "TLN0")  # Northern Ireland is a single ITL1 and ITL2 region
# Census figures published only for the whole local authority (their wards are too small): one local unit each.
WHOLE_LA = {"E09000001": "City of London", "E06000053": "Isles of Scilly"}

F_ITL3 = "itl3_2025_buc.geojson"
F_LOOKUP = "lad25_itl25_lookup.json"
F_WARDS = "wards_dec2022_bgc_{:02d}.geojson"
F_CENSUS_EW = "census2021_ts001_wards_ew.csv"
F_CENSUS_SC = "census2022_uv101b_wards_scotland.csv"
F_CENSUS_NI = "census2021_ms_a01_ni.xlsx"
F_POP = "mye_single_age_lad_{:02d}.csv"
F_BRES = "bres_lad_gb_" + "_".join(map(str, BRES_YEARS)) + ".csv"
F_BRES_NI = "bres2024_ni.xlsx"  # districts × sections
F_BRES_NI_2023 = "bres2023_ni.xlsx"  # districts' totals only
F_CAA = "caa_annual_2025_table_10_3_terminal_pax.csv"
F_OURAIRPORTS = "ourairports_airports.csv"
F_LOCODE = f"un-locode-{LOCODE_TAG}/code-list.csv"
F_WIKIDATA = "wikidata_locode_gb.csv"
F_PORT0101 = "dft_port0101.ods"
F_APS = "aps_itl.csv"
F_GDP = "regional_gdp_itl.xlsx"
F_GVA = "regional_gva_industry_itl.xlsx"
F_GDHI = "regional_gdhi_itl.xlsx"
F_LE = "life_expectancy_local_areas.xlsx"
F_FUA = "URAU_RG_100K_2020_4326_FUA.geojson"
F_URAU = "URAU_LB_2020_4326.geojson"
F_NUTS21 = "NUTS_RG_20M_2021_4326_LEVL_3.geojson"
F_ERT = "ert_bil_eur_a_GBP.json"
F_PPP = "prc_ppp_ind_UK.json"

WARDS_URL = (f"{ARC}/Wards_December_2022_Boundaries_UK_BGC/FeatureServer/0/query?where=1%3D1"
             "&outFields=WD22CD,WD22NM,LAD22CD,LAD22NM,Shape__Area&outSR=4326&geometryPrecision=5"
             "&orderByFields=OBJECTID&resultOffset={offset}&resultRecordCount=" + str(ARC_PAGE) + "&f=geojson")
POP_URL = (f"{NOMIS}/NM_2002_1.data.csv?geography=TYPE424&date=" + ",".join(map(str, MID_YEARS))
           + "&gender=0&c_age=101...191&measures=20100&select=date_name,geography_code,c_age,obs_value"
           "&recordoffset={offset}")
FILES = {
    F_ITL3: f"{ARC}/ITL3_JAN_2025_UK_BUC_V2/FeatureServer/2/query?where=1%3D1&outFields=ITL325CD,ITL325NM"
            "&outSR=4326&f=geojson",
    F_LOOKUP: f"{ARC}/ITL125_ITL225_ITL325_LAU125_LAD25_UK_LU/FeatureServer/0/query?where=1%3D1"
              "&outFields=ITL125CD,ITL125NM,ITL225CD,ITL225NM,ITL325CD,ITL325NM,LAU125CD,LAU125NM,LAD25CD,LAD25NM"
              "&f=json",
    F_CENSUS_EW: f"{NOMIS}/NM_2021_1.data.csv?date=latest&geography=TYPE153&c2021_restype_3=0&measures=20100"
                 "&select=geography_code,geography_name,obs_value",
    F_CENSUS_SC: "https://ukds-ckan.s3.eu-west-1.amazonaws.com/2022/NRS/UV101b/"
                 "census_2022_UV101b_sex_and_age_residence_type_Electoral_Ward_2022.csv",
    F_CENSUS_NI: "https://www.nisra.gov.uk/system/files/statistics/census-2021-ms-a01.xlsx",
    F_BRES: f"{NOMIS}/NM_189_1.data.csv?geography=TYPE424&date=" + ",".join(map(str, BRES_YEARS))
            + "&industry=150994945...150994965"
            "&employment_status=4&measure=1&measures=20100&select=date_name,geography_code,industry_name,obs_value",
    F_BRES_NI: "https://www.nisra.gov.uk/system/files/statistics/2026-10/BRES-2024-Publication-Tables1.xlsx",
    F_BRES_NI_2023: "https://www.nisra.gov.uk/system/files/statistics/2025-10/BRES2023-Publication-Tables.xlsx",
    # UK Civil Aviation Authority, UK airport data, annual 2025 release: Table 10.3, terminal passengers 2015-2025
    # (https://www.caa.co.uk/data-and-analysis/uk-aviation-market/airports/uk-airport-data/).
    F_CAA: "https://www.caa.co.uk/Documents/Download/24007/87fb7670-4e10-4aeb-942d-509238aa25a1/17507",
    F_OURAIRPORTS: OURAIRPORTS,
    F_LOCODE: LOCODE,
    # Department for Transport, port freight statistics, PORT0101 (July 2026 release, data to 2025)
    # (https://www.gov.uk/government/statistical-data-sets/port-and-domestic-waterborne-freight-statistics-port).
    F_PORT0101: "https://assets.publishing.service.gov.uk/media/6a62202b2dc18ebe4c3b2b06/port0101.ods",
    F_APS: f"{NOMIS}/NM_17_5.data.csv?geography=2092957697,TYPE419,TYPE420,TYPE499&date="
           + ",".join(f"{y}-12" for y in APS_YEARS)
           + "&variable=45,83,290,1902&measures=20599&select=date_name,geography_code,variable,obs_value",
    F_FUA: f"{GISCO}/urau/geojson/URAU_RG_100K_2020_4326_FUA.geojson",
    F_URAU: f"{GISCO}/urau/geojson/URAU_LB_2020_4326.geojson",
    F_NUTS21: f"{GISCO}/nuts/geojson/NUTS_RG_20M_2021_4326_LEVL_3.geojson",
    F_ERT: f"{ESTAT}/ert_bil_eur_a?format=JSON&lang=en&sinceTimePeriod={SINCE}&currency=GBP&statinfo=AVG&unit=NAC",
    F_PPP: f"{ESTAT}/prc_ppp_ind?format=JSON&lang=en&sinceTimePeriod={SINCE}&geo=UK&na_item=PPP_EU27_2020"
           "&na_item=VI_PPS_EU27_2020_HAB&ppp_cat=GDP&ppp_cat=A01",
}
# Wikidata items with a British UN/LOCODE and a position (the ports source asks for all of Europe's).
WIKIDATA_GB = "https://query.wikidata.org/sparql?" + urllib.parse.urlencode(
    {"query": 'SELECT ?code ?coord WHERE { ?item wdt:P1937 ?code; wdt:P625 ?coord. '
              'FILTER(STRSTARTS(UCASE(?code), "GB")) }'})
# CAA reporting airport → ICAO code. The CAA's "Non UK Reporting Airports" (Jersey, Guernsey, Alderney, Isle of Man:
# Crown Dependencies, not the UK) are left out.
CAA_ICAO = {
    "ABERDEEN": "EGPD", "BARRA": "EGPR", "BELFAST CITY (GEORGE BEST)": "EGAC", "BELFAST INTERNATIONAL": "EGAA",
    "BENBECULA": "EGPL", "BIGGIN HILL": "EGKB", "BIRMINGHAM": "EGBB", "BLACKPOOL": "EGNH", "BOURNEMOUTH": "EGHH",
    "BRISTOL": "EGGD", "CAMBRIDGE": "EGSC", "CAMPBELTOWN": "EGEC", "CARDIFF WALES": "EGFF",
    "CITY OF DERRY (EGLINTON)": "EGAE", "DONCASTER SHEFFIELD": "EGCN", "DUNDEE": "EGPN",
    "EAST MIDLANDS INTERNATIONAL": "EGNX", "EDINBURGH": "EGPH", "EXETER": "EGTE", "FARNBOROUGH": "EGLF",
    "GATWICK": "EGKK", "GLASGOW": "EGPF", "GLOUCESTERSHIRE": "EGBJ", "HEATHROW": "EGLL", "HUMBERSIDE": "EGNJ",
    "INVERNESS": "EGPE", "ISLAY": "EGPI", "ISLES OF SCILLY (ST.MARYS)": "EGHE", "KIRKWALL": "EGPA",
    "LANDS END (ST JUST)": "EGHC", "LEEDS BRADFORD": "EGNM", "LERWICK (TINGWALL)": "EGET",
    "LIVERPOOL (JOHN LENNON)": "EGGP", "LONDON CITY": "EGLC", "LUTON": "EGGW", "LYDD": "EGMD", "MANCHESTER": "EGCC",
    "NEWCASTLE": "EGNT", "NEWQUAY": "EGHQ", "NORWICH": "EGSH", "OXFORD (KIDLINGTON)": "EGTK", "PRESTWICK": "EGPK",
    "SCATSTA": "EGPM", "SHOREHAM": "EGKA", "SOUTHAMPTON": "EGHI", "SOUTHEND": "EGMC", "STANSTED": "EGSS",
    "STORNOWAY": "EGPO", "SUMBURGH": "EGPB", "TEESSIDE INTERNATIONAL AIRPORT": "EGNV", "TIREE": "EGPU",
    "WICK JOHN O GROATS": "EGPC",
}
# Harbour positions (lon, lat) for the major ports that neither Wikidata nor the UN/LOCODE list places, or that the
# UN/LOCODE list misplaces (GBFOR is a Lanarkshire village, GBSHO Shoreham in Kent); DfT's own codes (GB2xx) are not
# UN/LOCODEs.
PORT_POS = {
    "GBCYP": (-4.74, 55.95),  # Clydeport: Greenock
    "GBFOR": (-3.70, 56.03),  # Forth ports: Grangemouth, the largest
    "GBKPS": (-5.80, 54.72),  # Kilroot power station jetty, Belfast Lough
    "GBMED": (0.74, 51.44),  # Medway: Sheerness and Thamesport
    "GBSHO": (-0.24, 50.83),  # Shoreham-by-Sea
    "GBWPT": (-6.25, 54.10),  # Warrenpoint
    "GB203": (-0.73, 53.59),  # River Trent wharves: Keadby
    "GB221": (-0.36, 53.70),  # Rivers Hull and Humber wharves: New Holland
}

ONS_FILES = {
    F_GDP: ONS + "/economy/grossdomesticproductgdp/datasets/regionalgrossdomesticproductallnutslevelregions/1998to2024/"
                 "regionalgrossdomesticproductgdpbyallinternationalterritoriallevelitlregions.xlsx",
    F_GVA: ONS + "/economy/grossvalueaddedgva/datasets/nominalandrealregionalgrossvalueaddedbalancedbyindustry/current/"
                 "re424b1.xlsx",
    F_GDHI: ONS + "/economy/regionalaccounts/grossdisposablehouseholdincome/datasets/"
                  "regionalgrossdisposablehouseholdincomegdhi/1997to2024/regionalgrossdisposablehouseholdincomeallitlregions2024.xlsx",
    F_LE: ONS + "/peoplepopulationandcommunity/healthandsocialcare/healthandlifeexpectancies/datasets/"
                "lifeexpectancyforlocalareasoftheuk/between2001to2003and2022to2024/lifeexpectancylocalareas.xlsx",
}

NOTES = [
    "Regions are the ITL 2025 regions (International Territorial Levels, the UK's successor to NUTS since 2021), "
    "recoded TL… → UK… (TLC31 → UKC31); 182 ITL3 regions, which differ in places from the last UK NUTS (2021).",
    "Population: ONS, NRS and NISRA mid-year estimates (30 June) by single year of age; the estimate for mid-year Y "
    "is filed under year Y+1, as the population on the following 1 January.",
    "Median age: computed from single years of age (90+ open-ended), interpolating linearly within the median year.",
    "North Ayrshire straddles two ITL3 regions (Arran and Cumbrae belong to Highlands and Islands, UKM20): its "
    "population, jobs and life-expectancy weights are split by the islands' share of its population (derived from the "
    "ONS ITL3 populations of the regional GDP tables), with the same age structure on both sides.",
    "Money: pounds converted to euros at Eurostat's annual average GBP/EUR rate (ert_bil_eur_a); PPS figures use "
    "Eurostat's purchasing power parities (prc_ppp_ind, EU27_2020 = 1): GDP's for GDP, household final consumption's "
    "(A01) for household income. GDP of the UK includes extra-regio; per-head figures use ONS mid-year population.",
    "Value added by branch (ONS, balanced GVA at current basic prices): ITL3 tables publish agriculture and mining "
    "together (AB), so at every level A holds AB and B-E holds manufacturing, energy and water (C + D + E), without "
    "mining (UK mining GVA, mostly North Sea oil and gas, counts in A).",
    "Jobs (place of work, 2023 and 2024): BRES 'employment' (employees plus working owners) for Great Britain and "
    "NISRA BRES employee jobs for Northern Ireland. Most self-employed, the armed forces and trainees are excluded, so "
    "figures are below Eurostat's employment in persons. TOTAL is the sum of sections A-U. NISRA's 2023 tables give "
    "only each district's total: its 2023 sections follow the district's 2024 mix.",
    "Airports: UK Civil Aviation Authority terminal passengers (arriving plus departing, transit excluded), annual "
    "2025 release (2015-2025); Jersey, Guernsey, Alderney and the Isle of Man are left out. Positions from OurAirports.",
    "Ports: Department for Transport port freight statistics (PORT0101), the major ports' tonnage in the latest year, "
    "inwards and outwards. Positions from Wikidata and UN/LOCODE; a small table places the few major harbours they "
    "miss or misplace (in 'locode').",
    "Labour market (ONS Annual Population Survey, January-December): unemployment rate aged 16+ (Eurostat: 15-74), "
    "employment rate aged 16-64 (Eurostat: 20-64), share of 16-64 year-olds qualified at level 4 or above (NVQ4+ "
    "until 2021, RQF4+ from 2022; Eurostat: tertiary education ISCED 5-8, ages 25-64). ITL1 and ITL2 figures exist "
    "on ITL 2025 boundaries for 2025 only; the UK and Northern Ireland (its ITL1 and ITL2 region) for every year.",
    "Household income: ONS gross disposable household income (GDHI) per head; Eurostat's figure is net of "
    "consumption of fixed capital (B6N), so UK values are a few percent higher than a net equivalent.",
    "Life expectancy at birth: ONS three-year periods filed under their middle year (2022-2024 → 2023), the mean of "
    "the male and female figures; ITL2 = local authorities weighted by population (City of London and the Isles of "
    "Scilly are not published); ITL1 and the UK are the published region and country figures.",
    "Local units are the December 2022 electoral wards with their census usual residents: 2021 census for England, "
    "Wales and Northern Ireland, Scotland's 2022 census (matched to ward codes by name). The City of London and the "
    "Isles of Scilly, published only as a whole, are one unit each. Areas from the ONS generalised (BGC) boundaries.",
    "Functional urban areas and cities: Eurostat Urban Audit 2020, the last edition with the UK. The Urban Audit "
    "splits London into its 33 boroughs; the Greater London entry (UK001K2) stands in as the city of London (UK001C), "
    "placed on the City of London's point.",
    "Region typologies (mount, urban, coast): those of the NUTS 2021 region with the same code, else of the NUTS 2021 "
    "region holding the ITL3 region's interior point.",
]


# ------------------------------------------------------------------------------------------------- pure helpers


def uk_code(code: str) -> str:
    """ITL code → the map's code: 'TLC31' → 'UKC31', 'TLC' → 'UKC'; the UK itself ('UK', K02000001) → 'UK'."""
    if code in ("UK", UK_CODE):
        return "UK"
    if not code.startswith("TL"):
        raise ValueError(f"not an ITL code: {code!r}")
    return "UK" + code[2:]


def num(s) -> float | None:
    """A spreadsheet or CSV cell → float; None for blanks and markers ('[x]', '[c]', '*', '..', '-')."""
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return float(s)
    s = str(s).strip().replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def median_age(counts: list[float]) -> float | None:
    """Median age from counts by single year of age (last group open-ended), interpolated within the median year."""
    total = sum(counts)
    if total <= 0:
        return None
    half, cum = total / 2, 0.0
    for age, n in enumerate(counts):
        if n > 0 and cum + n >= half:
            return age + (half - cum) / n
        cum += n
    return float(len(counts) - 1)


def signed_area(ring) -> float:
    return sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(ring, ring[1:] + ring[:1])) / 2


def interior_point(rings) -> tuple[float, float]:
    """A point inside a (multi)polygon given as rings (holes by the even-odd rule): the centroid of its largest ring
    when the shape holds it, else the middle of the widest inside stretch of a horizontal line through it."""
    rings = [r for r in rings if len(r) >= 3]
    shape = Shape(rings)
    cx, cy = centroid(rings)
    if cx is not None and shape.contains(cx, cy):
        return cx, cy
    big = max(rings, key=lambda r: abs(signed_area(r)))
    ys = [p[1] for p in big]
    for y in (cy, (min(ys) + max(ys)) / 2, min(ys) + (max(ys) - min(ys)) / 3, min(ys) + 2 * (max(ys) - min(ys)) / 3):
        if y is None:
            continue
        y += 1e-7  # off any vertex
        xs = []
        for r in rings:
            for (x0, y0), (x1, y1) in zip(r, r[1:] + r[:1]):
                if (y0 > y) != (y1 > y):
                    xs.append(x0 + (y - y0) * (x1 - x0) / (y1 - y0))
        xs.sort()
        spans = [(xs[i], xs[i + 1]) for i in range(0, len(xs) - 1, 2)]
        if spans:
            a, b = max(spans, key=lambda s: s[1] - s[0])
            x = (a + b) / 2
            if shape.contains(x, y):
                return round(x, 5), round(y, 5)
    return round(big[0][0], 5), round(big[0][1], 5)


def norm_name(s: str) -> str:
    """Name key for matching: accents and punctuation dropped, '&' read as 'and', lower case."""
    s = unicodedata.normalize("NFD", s.replace("&", " and "))
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn").lower()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", s).split())


def jsonstat(d: dict) -> list[tuple[dict, float]]:
    """JSON-stat 2.0 → [({dimension: code}, value)]."""
    dims, size = d["id"], d["size"]
    codes = [[c for c, _ in sorted(d["dimension"][k]["category"]["index"].items(), key=lambda t: t[1])] for k in dims]
    values = d["value"]
    items = values.items() if isinstance(values, dict) else enumerate(values)
    out = []
    for idx, v in items:
        if v is None:
            continue
        i, key = int(idx), {}
        for k in range(len(dims) - 1, -1, -1):
            key[dims[k]] = codes[k][i % size[k]]
            i //= size[k]
        out.append((key, v))
    return out


def dms(text: str) -> tuple[float, float] | None:
    """UN/LOCODE coordinates "5113N 00425E" → (lon, lat)."""
    m = re.match(r"^(\d{2})(\d{2})([NS])\s+(\d{3})(\d{2})([EW])$", (text or "").strip())
    if not m:
        return None
    lat, lon = int(m[1]) + int(m[2]) / 60, int(m[4]) + int(m[5]) / 60
    return (-lon if m[6] == "W" else lon), (-lat if m[3] == "S" else lat)


def ring_out(r) -> list:
    return [[round(x, 5), round(y, 5)] for x, y in r]


def sheet_table(path, sheet: str, first: str) -> tuple[list, list[list]]:
    """(header, data rows) of a published table whose header row starts with `first`."""
    header, rows = None, []
    for r in read_rows(path, sheet):
        if header is None:
            if r and r[0] is not None and str(r[0]).strip() == first:
                header = [str(x).strip() if x is not None else "" for x in r]
            continue
        if r and any(x not in (None, "") for x in r):
            rows.append(r)
    if header is None:
        raise ValueError(f"{path.name} / {sheet}: no header row starting with {first!r}")
    return header, rows


def itl_table(path, sheet: str) -> dict[str, dict[str, float]]:
    """ONS regional-accounts table (columns ITL, ITL code, Region name, years…) → {map code: {year: value}} for the
    UK and its ITL1-3 regions (England, extra-regio and 'UK less extra-regio' rows are skipped)."""
    header, rows = sheet_table(path, sheet, "ITL")
    years = [(i, h) for i, h in enumerate(header) if re.fullmatch(r"\d{4}", h) and int(h) >= SINCE]
    out = {}
    for r in rows:
        level, code = (str(r[0]).strip() if r[0] else ""), (str(r[1]).strip() if len(r) > 1 and r[1] else "")
        if level not in ("UK", "ITL1", "ITL2", "ITL3") or not (code == "UK" or code.startswith("TL")):
            continue
        row = {y: v for i, y in years if i < len(r) and (v := num(r[i])) is not None}
        if row:
            out[uk_code(code)] = row
    return out


def read_text(path) -> str:
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1", "replace")


# ------------------------------------------------------------------------------------------------------ source


class UkOns(Source):
    info = SourceInfo(
        id="uk_ons",
        title="United Kingdom: ITL regions, wards, urban areas and regional statistics (ONS, NRS, NISRA)",
        publisher="Office for National Statistics (ONS), National Records of Scotland (NRS), Northern Ireland "
        "Statistics and Research Agency (NISRA), through the ONS Open Geography portal and Nomis; Civil Aviation "
        "Authority (airports); Department for Transport (ports); Eurostat (GISCO Urban Audit 2020, exchange rates, "
        "purchasing power parities)",
        homepage="https://www.ons.gov.uk/",
        license="Open Government Licence v3.0; boundaries © Crown copyright and database right, Ordnance Survey / LPS; "
        "GISCO © EuroGeographics",
        description="The United Kingdom, which Eurostat's regional tables no longer cover since Brexit: the ITL 2025 "
        "regions (the UK's successor to NUTS, recoded UK…) with their ONS boundaries; the December 2022 electoral "
        "wards with their census population (2021; 2022 in Scotland); the Urban Audit 2020 functional urban areas and "
        "cities; mid-year population by single year of age; regional GDP, value added by industry and household "
        "income (ONS regional accounts), jobs by industry (BRES), unemployment, employment and qualifications (Annual "
        "Population Survey) and life expectancy, converted to euros and PPS with Eurostat's exchange rates and "
        "purchasing power parities; airport passengers (CAA) and major ports' tonnage (DfT). Differences from the "
        "Eurostat measures: household income is gross, not net; jobs leave out most self-employed people; the labour "
        "force rates use UK age bands (unemployment 16+, employment and qualifications 16-64); life expectancy is the "
        "mean of men's and women's; mid-year population stands for 1 January of the next year; mining counts with "
        "agriculture (ITL3 tables publish them together); no regional poverty rate exists on Eurostat's definition.",
        used_for=["The United Kingdom's regions, cities and local units on the map",
                  "Population, GDP and jobs of British cities and regions", "Socio-economic lenses"],
    )

    # -------------------------------------------------------------------------------------------------- fetch

    def _get(self, name, url, force=False, *, check=None, headers=None, binary=False):
        p = self.download(url, name, force=force, headers=headers, expect_binary=binary)
        if check is not None and not check(p):
            self.discard(name)
            raise UnexpectedContentError(f"uk_ons/{name}: unexpected content from {url}")
        return p

    @staticmethod
    def _is_features(p) -> bool:
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (ValueError, UnicodeDecodeError):
            return False
        return isinstance(d, dict) and "features" in d and "error" not in d

    @staticmethod
    def _is_csv(p) -> bool:
        with open(p, "rb") as f:
            return f.read(1) in (b'"', b"\xef")

    @staticmethod
    def _is_jsonstat(p) -> bool:
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (ValueError, UnicodeDecodeError):
            return False
        return isinstance(d, dict) and "value" in d and "dimension" in d

    def _check_for(self, name):
        if name.endswith((".xlsx", ".ods")):
            return zipfile.is_zipfile
        if name == F_CENSUS_SC:  # a SuperWEB2 export: a few title lines before the table
            return lambda p: b"Electoral Ward 2022" in p.read_bytes()[:4096]
        if name == F_CAA:
            return lambda p: b"rpt_apt_name" in p.read_bytes()[:400]
        if name == F_LOCODE:
            return lambda p: b"Country" in p.read_bytes()[:200]
        if name == F_WIKIDATA:  # a cut-short answer is still CSV: count the rows
            return lambda p: p.read_bytes().startswith(b"code,coord") and p.read_bytes().count(b"\n") > 500
        if name.endswith(".csv"):
            return self._is_csv
        if name in (F_ERT, F_PPP):
            return self._is_jsonstat
        return self._is_features

    @staticmethod
    def _rows_in(p) -> int:
        if p.suffix == ".csv":
            with open(p, encoding="utf-8") as f:
                return sum(1 for _ in f) - 1
        return len(json.loads(p.read_text(encoding="utf-8"))["features"])

    def _pages(self, url_fmt, name_fmt, size, force=False, fetch=True) -> list:
        """Paged API results (Nomis, ArcGIS): page k is saved as name_fmt.format(k); the last page is short."""
        out, k = [], 0
        while True:
            name = name_fmt.format(k)
            if fetch:
                cached = (self.raw_dir / name).exists() and not force
                p = self._get(name, url_fmt.format(offset=k * size), force, check=self._check_for(name))
                if not cached:
                    time.sleep(0.3)  # a polite pause between API pages
            else:
                p = self.raw_dir / name
            out.append(p)
            if self._rows_in(p) < size:
                return out
            k += 1

    def _ons(self, name, url, force, first: bool) -> None:
        if (self.raw_dir / name).exists() and not force:
            return
        if not first:
            time.sleep(ONS_PAUSE)
        for attempt in range(4):
            try:
                self._get(name, url, force, check=zipfile.is_zipfile, headers=ONS_HEADERS, binary=True)
                return
            except (urllib.error.HTTPError, UnexpectedContentError) as exc:
                if isinstance(exc, urllib.error.HTTPError):
                    exc.close()
                    if exc.code not in (403, 429):
                        raise
                if attempt == 3:
                    raise
                wait = 45 * (attempt + 1)
                print(f"      ons.gov.uk refused ({exc}); waiting {wait}s")
                time.sleep(wait)

    def fetch(self, force=False):
        first = True
        ons = iter(ONS_FILES.items())
        # ONS files are spread among the other downloads, which spaces out the requests to ons.gov.uk.
        for k, (name, url) in enumerate(FILES.items()):
            self._get(name, url, force, check=self._check_for(name))
            if k % 3 == 2 and (item := next(ons, None)):
                self._ons(*item, force, first)
                first = False
        for item in ons:
            self._ons(*item, force, first)
            first = False
        self._get(F_WIKIDATA, WIKIDATA_GB, force, check=self._check_for(F_WIKIDATA), headers={"Accept": "text/csv"})
        self._pages(WARDS_URL, F_WARDS, ARC_PAGE, force)
        self._pages(POP_URL, F_POP, NOMIS_PAGE, force)

    # ------------------------------------------------------------------------------------------------ process

    def process(self):
        used: list[str] = []

        def path(name):
            used.append(name)
            return self.raw_dir / name

        geo = self._geography(path)
        rates = self._rates(path)
        pops = self._population(path, geo)
        tables = {"pop3": pops["pop3"], "medage3": pops["medage3"]}
        tables.update(self._accounts(path, rates))
        tables["emp3"] = self._jobs(path, geo, pops)
        tables.update(self._labour(path))
        tables["lifeexp2"] = self._life_expectancy(path, geo, pops)
        tables.update(self._national(tables, rates))
        nuts = self._regions(path, geo)
        lau = self._wards(path)
        fuas, cities = self._urban_audit(path, geo)
        airports = self._airports(path)
        ports = self._ports(path)

        for t, series in tables.items():
            years = sorted({y for s in series.values() for row in s.values() for y in row})
            n = sum(len(s) for s in series.values())
            print(f"    {t:9s} {len(series):2d} series, {n:4d} geo rows, {years[0] if years else '-'}-"
                  f"{years[-1] if years else '-'}")
        print(f"    {len(nuts)} regions ({sum(1 for n in nuts if n['level'] == 3)} ITL3), {len(fuas)} FUAs, "
              f"{len(cities)} cities, {len(lau['rows'])} wards ({sum(r[3] or 0 for r in lau['rows']):,.0f} people)")
        return {
            "vintage": "ONS/NRS/NISRA: ITL 2025, wards Dec 2022 (census 2021, Scotland 2022), mid-2025 population, "
            f"regional accounts 2024, BRES 2023-2024, APS 2025; Urban Audit 2020; CAA airports "
            f"{max(y for t in airports['traffic'].values() for y in t['pax'])}, DfT ports {ports[0]['year']}",
            "_files": sorted(set(used)),
            "nuts": nuts,
            "fuas": fuas,
            "cities": cities,
            "lau": lau,
            "tables": tables,
            "airports": airports,
            "ports": ports,
            "notes": NOTES,
        }

    # --- geography: lookup, hierarchy, ITL3 shapes

    def _geography(self, path) -> dict:
        attrs = [f["attributes"] for f in json.loads(path(F_LOOKUP).read_text(encoding="utf-8"))["features"]]
        names, parent, lad_itl3, lad_name, recode = {}, {}, defaultdict(list), {}, {}
        for a in attrs:
            names[a["ITL125CD"]], names[a["ITL225CD"]], names[a["ITL325CD"]] = (a["ITL125NM"], a["ITL225NM"],
                                                                               a["ITL325NM"])
            parent[a["ITL325CD"]], parent[a["ITL225CD"]] = a["ITL225CD"], a["ITL125CD"]
            if a["ITL325CD"] not in lad_itl3[a["LAD25CD"]]:
                lad_itl3[a["LAD25CD"]].append(a["ITL325CD"])
            lad_name[a["LAD25CD"]] = a["LAD25NM"]
            if a["LAU125CD"] != a["LAD25CD"] and a["LAU125CD"][:1] in "ENW":  # an older code of the same area
                recode[a["LAU125CD"]] = a["LAD25CD"]
        itl3 = sorted(c for c in names if len(c) == 5)
        feats = json.loads(path(F_ITL3).read_text(encoding="utf-8"))["features"]
        rings = {f["properties"]["ITL325CD"]: geojson_rings(f["geometry"]) for f in feats}
        missing = set(itl3) ^ set(rings)
        if missing:
            raise ValueError(f"ITL3 boundaries and lookup disagree on {sorted(missing)}")
        shapes = [Shape(rings[c]) for c in itl3]
        return {"names": names, "parent": parent, "lad_itl3": dict(lad_itl3), "lad_name": lad_name,
                "recode": recode, "itl3": itl3, "rings": rings, "index": ShapeIndex(shapes, cell_km=0.25),
                "shapes": shapes}

    def _ancestors(self, geo, c3: str) -> list[str]:
        c2 = geo["parent"][c3]
        return [c3, c2, geo["parent"][c2], "UK"]

    def _locate(self, geo, lon, lat) -> str:
        """ITL3 code holding a point (the nearest region's when a coastal point falls just outside all of them)."""
        k = geo["index"].locate(lon, lat)
        if k < 0:
            k = min(range(len(geo["shapes"])),
                    key=lambda i: min((x - lon) ** 2 + (y - lat) ** 2 for r in geo["shapes"][i].rings for x, y in r))
        return geo["itl3"][k]

    # --- exchange rates and PPPs

    def _rates(self, path) -> dict:
        rate = {k["time"]: v for k, v in jsonstat(json.loads(path(F_ERT).read_text()))}
        ppp = defaultdict(dict)
        for k, v in jsonstat(json.loads(path(F_PPP).read_text())):
            ppp[(k["na_item"], k["ppp_cat"])][k["time"]] = v
        return {"eur": rate, "ppp_gdp": ppp[("PPP_EU27_2020", "GDP")], "ppp_hh": ppp[("PPP_EU27_2020", "A01")],
                "vi_gdp": ppp[("VI_PPS_EU27_2020_HAB", "GDP")]}

    # --- population by single year of age

    def _population(self, path, geo) -> dict:
        sya: dict = defaultdict(lambda: [0.0] * 91)
        for p in self._pages(POP_URL, F_POP, NOMIS_PAGE, fetch=False):
            used_name = p.name
            path(used_name)
            with open(p, encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    v = num(r["OBS_VALUE"])
                    if v is None:
                        continue
                    lad = geo["recode"].get(r["GEOGRAPHY_CODE"], r["GEOGRAPHY_CODE"])
                    label = str(int(r["DATE_NAME"]) + 1)  # mid-year Y → 1 January Y+1
                    sya[(lad, label)][int(r["C_AGE"]) - 101] += v
        lads = set(geo["lad_itl3"])
        labels = sorted({lab for _, lab in sya})
        unknown = {lad for lad, _ in sya} - lads
        if unknown:
            raise ValueError(f"population for unknown local authorities {sorted(unknown)[:5]}")
        totals = {k: sum(v) for k, v in sya.items()}

        shares = self._split_shares(path, geo, totals, labels)
        by_geo: dict = defaultdict(lambda: [0.0] * 91)
        complete = []
        for label in labels:
            missing = [lad for lad in lads if (lad, label) not in sya]
            if missing:
                print(f"    ! population {label}: {len(missing)} local authorities missing, year skipped")
                continue
            complete.append(label)
            for lad in lads:
                for c3, w in self.weights(geo, shares, lad, label):
                    for g in self._ancestors(geo, c3):
                        acc = by_geo[(g, label)]
                        for a, n in enumerate(sya[(lad, label)]):
                            acc[a] += w * n
        pop3 = {k: {} for k in ("NR|T|TOTAL", "NR|T|Y_LT15", "NR|T|Y15-64", "NR|T|Y_GE65")}
        med = {}
        for (g, label), counts in sorted(by_geo.items()):
            code = uk_code(g)
            for key, (a, b) in (("NR|T|TOTAL", (0, 91)), ("NR|T|Y_LT15", (0, 15)), ("NR|T|Y15-64", (15, 65)),
                                ("NR|T|Y_GE65", (65, 91))):
                pop3[key].setdefault(code, {})[label] = round(sum(counts[a:b]))
            m = median_age(counts)
            if m is not None:
                med.setdefault(code, {})[label] = round(m, 1)
        return {"pop3": pop3, "medage3": {"MEDAGEPOP|YR": med}, "totals": totals, "shares": shares,
                "labels": complete}

    def _split_shares(self, path, geo, totals, labels) -> dict:
        """{(lad, label): {itl3: share}} for local authorities split between ITL3 regions (North Ayrshire): each
        part's population is what the ONS ITL3 population (regional GDP tables, mid-year) leaves after the regions'
        whole local authorities; the latest share stands in for years the tables don't have yet."""
        t6 = itl_table(path(F_GDP), "Table 6")
        whole = defaultdict(list)
        for lad, ts in geo["lad_itl3"].items():
            if len(ts) == 1:
                whole[ts[0]].append(lad)
        shares = {}
        for lad, ts in geo["lad_itl3"].items():
            if len(ts) < 2:
                continue
            found = {}
            for label in labels:
                mid = str(int(label) - 1)
                res = {}
                for t in ts:
                    pub = t6.get(uk_code(t), {}).get(mid)
                    if pub is None or not all((w, label) in totals for w in whole[t]) or (lad, label) not in totals:
                        break
                    res[t] = max(0.0, pub - sum(totals[(w, label)] for w in whole[t]))
                else:
                    if sum(res.values()) > 0:
                        found[label] = {t: r / sum(res.values()) for t, r in res.items()}
            if not found:
                print(f"    ! {geo['lad_name'][lad]}: no ITL3 population to split it, shared equally")
            for label in labels:
                near = min(found, key=lambda y: abs(int(y) - int(label))) if found else None
                shares[(lad, label)] = found[near] if near else {t: 1 / len(ts) for t in ts}
            if found:
                small = min(ts, key=lambda t: statistics.mean(s[t] for s in found.values()))
                vals = [found[y][small] for y in sorted(found)]
                print(f"    {geo['lad_name'][lad]}: {geo['names'][small]} part {min(vals):.1%}-{max(vals):.1%} "
                      f"of its population ({len(found)} years)")
        return shares

    @staticmethod
    def weights(geo, shares, lad, label) -> list[tuple[str, float]]:
        ts = geo["lad_itl3"][lad]
        if len(ts) == 1:
            return [(ts[0], 1.0)]
        sh = shares.get((lad, label)) or shares[min((k for k in shares if k[0] == lad),
                                                    key=lambda k: abs(int(k[1]) - int(label)))]
        return [(t, sh[t]) for t in ts]

    # --- regional accounts: GDP, GVA, household income

    def _accounts(self, path, rates) -> dict:
        eur, ppp_gdp, ppp_hh = rates["eur"], rates["ppp_gdp"], rates["ppp_hh"]
        gdp_p = path(F_GDP)
        gdp_m, gdp_ph = itl_table(gdp_p, "Table 5"), itl_table(gdp_p, "Table 7")
        gdp3 = {"MIO_EUR": {}, "EUR_HAB": {}, "PPS_EU27_2020_HAB": {}}
        for g, row in gdp_m.items():
            for y, v in row.items():
                if y in eur:
                    gdp3["MIO_EUR"].setdefault(g, {})[y] = round(v / eur[y], 2)
        for g, row in gdp_ph.items():
            for y, v in row.items():
                if y in eur:
                    gdp3["EUR_HAB"].setdefault(g, {})[y] = round(v / eur[y])
                if y in ppp_gdp:
                    gdp3["PPS_EU27_2020_HAB"].setdefault(g, {})[y] = round(v / ppp_gdp[y])

        gva_p = path(F_GVA)
        gva3 = {f"CP_MEUR|{b}": {} for b in BRANCHES}
        for sheet in ("Table 1c", "Table 2c", "Table 3c"):
            header, rows = sheet_table(gva_p, sheet, "ITL code")
            years = [(i, h) for i, h in enumerate(header) if re.fullmatch(r"\d{4}", h) and int(h) >= SINCE]
            acc: dict = defaultdict(lambda: defaultdict(float))
            for r in rows:
                code = str(r[0]).strip() if r[0] else ""
                sic = str(r[2]).split(" (")[0].strip() if len(r) > 2 and r[2] else ""
                if not (code == "UK" or (code.startswith("TL") and code not in ("TLB", "TLZ"))) or sic not in GVA_BRANCHES:
                    continue
                g = uk_code(code)
                for i, y in years:
                    v = num(r[i]) if i < len(r) else None
                    if v is None:
                        continue
                    for b in GVA_BRANCHES[sic]:
                        acc[(g, y)][b] += v
            for (g, y), row in acc.items():
                if y not in eur:
                    continue
                for b, v in row.items():
                    gva3[f"CP_MEUR|{b}"].setdefault(g, {})[y] = round(v / eur[y], 2)

        gdhi = itl_table(path(F_GDHI), "Table 3")  # GDHI per head, pounds
        income2 = {"PPS_EU27_2020_HAB|BAL|B6N": {}, "EUR_HAB|BAL|B6N": {}}
        for g, row in gdhi.items():
            if len(g) > 4:  # NUTS 2-like table: ITL2, ITL1 and the UK
                continue
            for y, v in row.items():
                if y in ppp_hh:
                    income2["PPS_EU27_2020_HAB|BAL|B6N"].setdefault(g, {})[y] = round(v / ppp_hh[y])
                if y in eur:
                    income2["EUR_HAB|BAL|B6N"].setdefault(g, {})[y] = round(v / eur[y])
        return {"gdp3": gdp3, "gva3": gva3, "income2": income2, "_gdp_gbp": gdp_m, "_gdp_ph_gbp": gdp_ph}

    # --- jobs by industry (BRES)

    def _jobs(self, path, geo, pops) -> dict:
        years = [str(y) for y in BRES_YEARS]
        by_lad: dict = {y: defaultdict(lambda: defaultdict(float)) for y in years}  # year → LAD → section → jobs
        with open(path(F_BRES), encoding="utf-8") as f:
            for r in csv.DictReader(f):
                sec, v = r["INDUSTRY_NAME"].strip()[:1], num(r["OBS_VALUE"])
                lad = geo["recode"].get(r["GEOGRAPHY_CODE"], r["GEOGRAPHY_CODE"])
                if r["DATE_NAME"] in by_lad and v is not None and sec in SECTION_BRANCHES:
                    by_lad[r["DATE_NAME"]][lad][sec] += v
        # Northern Ireland: districts × sections for 2024; for 2023 NISRA gives each district's total only, shared out
        # over its sections as in 2024.
        ni_code = {norm_name(n): c for c, n in geo["lad_name"].items() if c.startswith("N")}
        header, rows = sheet_table(path(F_BRES_NI), "Table 3.2", "Local Government District")
        i_sec, i_tot = header.index("Section"), header.index("Total")
        ni24: dict = defaultdict(lambda: defaultdict(float))
        for r in rows:
            if len(r) <= i_sec:  # notes and the colour key under the table
                continue
            lgd = ni_code.get(norm_name(str(r[0] or "")))
            sec = str(r[i_sec] or "").strip()
            if lgd and sec in SECTION_BRANCHES:
                v = num(r[i_tot] if i_tot < len(r) else None)
                ni24[lgd][sec] += v or 0.0  # cells suppressed for disclosure count as zero
        header, rows = sheet_table(path(F_BRES_NI_2023), "District Council Area", "District Council Area")
        i_tot = header.index("Total")
        ni23 = {c: num(r[i_tot]) for r in rows if len(r) > i_tot and (c := ni_code.get(norm_name(str(r[0] or ""))))}
        for lgd, secs in ni24.items():
            if "2024" in by_lad:
                by_lad["2024"][lgd] = secs
            if "2023" in by_lad and ni23.get(lgd):
                total = sum(secs.values())
                by_lad["2023"][lgd] = defaultdict(float, {k: v * ni23[lgd] / total for k, v in secs.items()})
        emp3 = {f"THS|EMP|{b}": {} for b in BRANCHES}
        for year in years:
            missing = set(geo["lad_itl3"]) - set(by_lad[year])
            if missing:
                raise ValueError(f"BRES {year}: no jobs for {sorted(missing)[:5]}")
            acc: dict = defaultdict(lambda: defaultdict(float))
            label = str(int(year) + 1)  # population weights of mid-year, filed under the following 1 January
            for lad, secs in by_lad[year].items():
                for c3, w in self.weights(geo, pops["shares"], lad, label):
                    for g in self._ancestors(geo, c3):
                        for sec, v in secs.items():
                            for b in SECTION_BRANCHES[sec] + ["TOTAL"]:
                                acc[uk_code(g)][b] += w * v
            for g, row in acc.items():
                for b in BRANCHES:
                    emp3[f"THS|EMP|{b}"].setdefault(g, {})[year] = round(row.get(b, 0.0) / 1000, 2)
        return emp3

    # --- Annual Population Survey

    def _labour(self, path) -> dict:
        val: dict = defaultdict(dict)  # (variable, geography) → {year: value}
        with open(path(F_APS), encoding="utf-8") as f:
            for r in csv.DictReader(f):
                v = num(r["OBS_VALUE"])
                m = re.search(r"(\d{4})$", r["DATE_NAME"])
                if v is not None and m:
                    val[(r["VARIABLE"], r["GEOGRAPHY_CODE"])][m.group(1)] = v
        out = {"unemp2": {"TOTAL|T|Y15-74|PC": {}}, "emprate2": {"PC|T|Y20-64": {}},
               "tertiary2": {"T|ED5-8|Y25-64|PC": {}}}
        spec = {"unemp2": ("TOTAL|T|Y15-74|PC", ["83"]), "emprate2": ("PC|T|Y20-64", ["45"]),
                "tertiary2": ("T|ED5-8|Y25-64|PC", ["290", "1902"])}  # NVQ4+ until 2021, then RQF4+
        geos = {g for _, g in val}
        for t, (key, variables) in spec.items():
            series = out[t][key]
            for g in geos:
                if g == UK_CODE:
                    targets = ["UK"]
                elif g == NI_CODE:
                    targets = [uk_code(c) for c in NI_ITL]
                elif g.startswith("TL") and len(g) in (3, 4):
                    targets = [uk_code(g)]
                else:
                    continue
                row = {}
                for var in variables:  # later variables take over
                    row.update(val.get((var, g), {}))
                if row:
                    for tg in targets:
                        series[tg] = dict(sorted(row.items()))
        return out

    # --- life expectancy

    def _life_expectancy(self, path, geo, pops) -> dict:
        header, rows = sheet_table(path(F_LE), "1", "Period")
        col = {h: i for i, h in enumerate(header)}
        le: dict = defaultdict(dict)  # (area code, year) → {sex: value}
        for r in rows:
            if (r[col["Age group"]] or "").strip() != "<1":
                continue
            m = re.match(r"(\d{4}) to (\d{4})", str(r[col["Period"]] or ""))
            v = num(r[col["Life expectancy"]])
            if not m or v is None:
                continue
            year = str((int(m.group(1)) + int(m.group(2))) // 2)
            if int(year) < SINCE:
                continue
            le[(str(r[col["Area code"]]).strip(), year)][str(r[col["Sex"]]).strip()] = v
        both = {k: (s["Male"] + s["Female"]) / 2 for k, s in le.items() if "Male" in s and "Female" in s}
        years = sorted({y for _, y in both})
        totals, labels = pops["totals"], pops["labels"]
        out: dict = {}
        for year in years:
            label = min(labels, key=lambda lab: abs(int(lab) - (int(year) + 1)))  # mid-year population of `year`
            num_, den = defaultdict(float), defaultdict(float)
            for lad in geo["lad_itl3"]:
                v = both.get((lad, year))
                if v is None:  # published under the authority's older code?
                    v = next((both[(c, year)] for c, new in geo["recode"].items() if new == lad and (c, year) in both),
                             None)
                if v is None:
                    continue
                for c3, w in self.weights(geo, pops["shares"], lad, label):
                    c2 = geo["parent"][c3]
                    weight = w * totals[(lad, label)]
                    num_[c2] += weight * v
                    den[c2] += weight
            for c2 in den:
                out.setdefault(uk_code(c2), {})[year] = round(num_[c2] / den[c2], 1)
            for area, itl1 in LE_ITL1.items():
                if (area, year) in both:
                    out.setdefault(uk_code(itl1), {})[year] = round(both[(area, year)], 1)
                    if area == NI_CODE:
                        out.setdefault(uk_code("TLN0"), {})[year] = round(both[(area, year)], 1)
            if (UK_CODE, year) in both:
                out.setdefault("UK", {})[year] = round(both[(UK_CODE, year)], 1)
        return {"YR|T|Y_LT1": out}

    # --- national rows (pop0, gdp0, emp0, gva0, gdppc0, gdpidx0)

    @staticmethod
    def _national(tables, rates) -> dict:
        gdp_gbp, gdp_ph = tables.pop("_gdp_gbp"), tables.pop("_gdp_ph_gbp")
        eur, ppp_gdp = rates["eur"], rates["ppp_gdp"]
        uk = "UK"
        return {
            "pop0": {"NR|TOTAL|T": {uk: dict(tables["pop3"]["NR|T|TOTAL"][uk])}},
            "gdp0": {"CP_MEUR|B1GQ": {uk: {y: round(v / eur[y], 1) for y, v in gdp_gbp[uk].items() if y in eur}}},
            "emp0": {f"THS_PER|{b}|EMP_DC": {uk: dict(tables["emp3"][f"THS|EMP|{b}"][uk])} for b in BRANCHES},
            "gva0": {f"CP_MEUR|{b}|B1G": {uk: dict(tables["gva3"][f"CP_MEUR|{b}"][uk])} for b in BRANCHES},
            "gdppc0": {"CP_PPS_EU27_2020_HAB|B1GQ": {uk: {y: round(v / ppp_gdp[y], 1) for y, v in gdp_ph[uk].items()
                                                          if y in ppp_gdp}}},
            "gdpidx0": {"VI_PPS_EU27_2020_HAB|GDP": {uk: {y: v for y, v in rates["vi_gdp"].items()
                                                          if int(y) >= SINCE}}},
        }

    # --- regions in the gisco "nuts" shape

    def _regions(self, path, geo) -> list[dict]:
        typ, shapes, codes = {}, [], []
        for f in json.loads(path(F_NUTS21).read_text(encoding="utf-8"))["features"]:
            p = f["properties"]
            if p["CNTR_CODE"] == "UK" and p["LEVL_CODE"] == 3:
                typ[p["NUTS_ID"]] = (p.get("MOUNT_TYPE"), p.get("URBN_TYPE"), p.get("COAST_TYPE"))
                shapes.append(Shape(geojson_rings(f["geometry"])))
                codes.append(p["NUTS_ID"])
        names = geo["names"]
        nuts = [{"code": "UK", "level": 0, "country": "UK", "name": "United Kingdom", "local": "United Kingdom",
                 "mount": 0, "urban": 0, "coast": 0}]
        for level, n in ((1, 3), (2, 4)):
            for c in sorted(k for k in names if len(k) == n):
                nuts.append({"code": uk_code(c), "level": level, "country": "UK", "name": names[c], "local": names[c],
                             "mount": 0, "urban": 0, "coast": 0})
        same = 0
        for c in geo["itl3"]:
            code = uk_code(c)
            if code in typ:
                t, same = typ[code], same + 1
            else:
                x, y = interior_point(geo["rings"][c])
                k = next((i for i, s in enumerate(shapes) if s.contains(x, y)), None)
                if k is None:
                    k = min(range(len(shapes)), key=lambda i: min((a - x) ** 2 + (b - y) ** 2
                                                                    for r in shapes[i].rings for a, b in r))
                t = typ[codes[k]]
            rings = [ring_out(thin(r, 0.004)) for r in geo["rings"][c]]
            nuts.append({"code": code, "level": 3, "country": "UK", "name": names[c], "local": names[c],
                         "mount": t[0], "urban": t[1], "coast": t[2], "county": True, "rings": rings})
        print(f"    typologies: {same} ITL3 regions keep their NUTS 2021 code, {len(geo['itl3']) - same} located")
        return nuts

    # --- wards as local units

    def _wards(self, path) -> dict:
        ew = {}
        with open(path(F_CENSUS_EW), encoding="utf-8") as f:
            for r in csv.DictReader(f):
                ew[r["GEOGRAPHY_CODE"]] = num(r["OBS_VALUE"])
        sc = {}
        rows = list(csv.reader(io.StringIO(read_text(path(F_CENSUS_SC)))))
        for r in rows:
            if len(r) >= 6 and r[0] == "Individuals" and r[2] == "All people" and r[3] == "Total" and r[4] == "All people":
                sc[r[1].strip()] = num(r[5])
        _, ni_rows = sheet_table(path(F_CENSUS_NI), "Ward", "Geography")
        ni = {str(r[1]).strip(): num(r[2]) for r in ni_rows if len(r) > 2 and r[1]}

        wards = []  # (code, name, lad code, lad name, area m², rings)
        for p in self._pages(WARDS_URL, F_WARDS, ARC_PAGE, fetch=False):
            path(p.name)
            for f in json.loads(p.read_text(encoding="utf-8"))["features"]:
                q = f["properties"]
                if f.get("geometry"):
                    wards.append((q["WD22CD"], q["WD22NM"].strip(), q["LAD22CD"], q["LAD22NM"], q["Shape__Area"] or 0.0,
                                  geojson_rings(f["geometry"])))
        units: dict = {}  # id → [name, pop, area m², rings]
        for code, name, lad, _, area, rings in wards:
            if lad in WHOLE_LA:
                uid, uname, pop = lad, WHOLE_LA[lad], ew.get(lad)
            elif code[0] in "EW":
                uid, uname = code, re.sub(r"\s*\(part [^)]*\)$", "", name)
                # A ward across two former districts is published in parts (E05R…, E05S…): summed back.
                parts = [v for k, v in ew.items() if k[:3] == code[:3] and k[4:] == code[4:] and k[3].isalpha()]
                pop = ew.get(code, sum(v for v in parts if v is not None) if parts else None)
            elif code[0] == "N":
                uid, uname, pop = code, name, ni.get(code)
            else:
                uid, uname, pop = code, name, None  # Scotland: matched by name below
            u = units.setdefault(uid, [uname, pop, 0.0, []])
            u[2] += area
            u[3].extend(rings)

        # Scotland: the census table names wards (some with their council in brackets) but gives no codes.
        left = dict(sc)
        by_norm = defaultdict(list)
        for n in left:
            by_norm[norm_name(n)].append(n)
        scot = [(code, name, ladn) for code, name, _, ladn, _, _ in wards if code[0] == "S"]
        unmatched = []
        for code, name, ladn in scot:
            for key in (norm_name(name), norm_name(f"{name} {ladn}")):
                cands = [n for n in by_norm.get(key, []) if n in left]
                if len(cands) == 1:
                    units[code][1] = left.pop(cands[0])
                    break
            else:
                unmatched.append((code, name))
        for code, name in unmatched:
            best = difflib.get_close_matches(norm_name(name), {norm_name(n): n for n in left}, n=1, cutoff=0.75)
            if best:
                n = next(n for n in left if norm_name(n) == best[0])
                units[code][1] = left.pop(n)
            else:
                print(f"    ! Scottish ward {code} {name}: no census figure")
        no_pop = [k for k, u in units.items() if u[1] is None]
        if no_pop:
            print(f"    ! {len(no_pop)} wards without population: {no_pop[:8]}")

        out = {"columns": ["id", "country", "name", "pop", "area", "lon", "lat"], "rows": []}
        for uid in sorted(units):
            name, pop, area, rings = units[uid]
            lon, lat = interior_point(rings)
            out["rows"].append([f"UK_{uid}", "UK", name, round(pop) if pop is not None else None,
                                round(area / 1e6, 2), lon, lat])
        return out

    # --- Urban Audit 2020: functional urban areas and cities

    def _urban_audit(self, path, geo) -> tuple[list, list]:
        labels = [f for f in json.loads(path(F_URAU).read_text(encoding="utf-8"))["features"]
                  if f["properties"].get("CNTR_CODE") == "UK"]
        city_rows = []
        for f in labels:
            p = f["properties"]
            lon, lat = f["geometry"]["coordinates"][:2]
            if p["URAU_CATG"] == "C":
                city_rows.append((p["URAU_CODE"][:-1], p["URAU_NAME"], p["FUA_CODE"], bool(p.get("CITY_CPTL")),
                                  lon, lat))
        for f in labels:
            p = f["properties"]
            code = p["URAU_CODE"][:5] + "C"
            if p["URAU_CATG"] != "K" or not p.get("CITY_CPTL") or any(c[0] == code for c in city_rows):
                continue
            # London: the Urban Audit lists its boroughs as cities, and the capital only as a greater city (K), whose
            # label point lies in the south of Greater London: the city is placed on its historic core, the borough
            # named after it (the City of London), when there is one.
            lon, lat = f["geometry"]["coordinates"][:2]
            fua = p["URAU_CODE"][:5] + "L"
            heart = [c for c in city_rows if c[2] and c[2][:5] == fua[:5] and p["URAU_NAME"] in c[1]]
            if heart:
                lon, lat = heart[0][4], heart[0][5]
            city_rows.append((code, p["URAU_NAME"], fua, True, lon, lat))
        codes = [c[0] for c in city_rows]
        if len(set(codes)) != len(codes):
            raise ValueError("Urban Audit: two cities map to the same code")
        city_name = {c[0][:5]: c[1] for c in city_rows}
        cities = []
        for code, name, fua, capital, lon, lat in sorted(city_rows):
            cities.append({"code": code, "name": name, "fua": fua[:5] + "F" if fua else None, "country": "UK",
                           "capital": capital, "nuts3": uk_code(self._locate(geo, lon, lat)),
                           "lon": round(lon, 5), "lat": round(lat, 5)})
        core = {c["code"][:5]: (c["lon"], c["lat"]) for c in cities}

        fuas = []
        for f in json.loads(path(F_FUA).read_text(encoding="utf-8"))["features"]:
            p = f["properties"]
            if p.get("CNTR_CODE") != "UK" or not f.get("geometry"):
                continue
            rings = geojson_rings(f["geometry"])
            prefix = p["URAU_CODE"][:5]
            name = p["URAU_NAME"].strip().removesuffix(" Local Government District")
            if name.startswith("FUA of "):
                name = city_name.get(prefix, name.removeprefix("FUA of "))
            lon, lat = core.get(prefix) or interior_point(rings)
            fuas.append({"code": prefix + "F", "name": name, "country": "UK",
                         "nuts3": uk_code(self._locate(geo, lon, lat)), "rings": [ring_out(thin(r)) for r in rings]})
        fuas.sort(key=lambda f: f["code"])
        return fuas, cities

    # --- airports (CAA) in the shape of the airports interim

    def _airports(self, path) -> dict:
        ours = {}
        with open(path(F_OURAIRPORTS), encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if r["iso_country"] == "GB":
                    for code in {r.get("icao_code"), r.get("gps_code"), r.get("ident")}:
                        if code:
                            ours.setdefault(code, r)
        traffic, unknown = {}, []
        with open(path(F_CAA), encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                if r["airport_cluster"].strip() != "1":  # 2 = Channel Islands and Isle of Man
                    continue
                name = r["rpt_apt_name"].strip()
                icao = CAA_ICAO.get(name)
                if icao is None:
                    unknown.append(name)
                    continue
                first = int(re.match(r"\s*(\d{4})", r["span"]).group(1))
                pax = {}
                for k in range(1, 40):
                    v = num(r.get(f"Y{k}"))
                    if f"Y{k}" not in r:
                        break
                    if v is not None:
                        pax[str(first + k - 1)] = round(v)
                if any(pax.values()):
                    traffic[icao] = {"country": "UK", "label": f"{name} airport", "pax": pax}
        if unknown:
            print(f"    ! CAA airports without an ICAO code (add them to CAA_ICAO): {unknown}")
        pos = {}
        for icao in traffic:
            r = ours.get(icao)
            if r:
                pos[icao] = {"name": r["name"], "city": english_name(r["municipality"]) or None,
                             "iata": r["iata_code"] or None, "iso": r["iso_country"],
                             "lon": float(r["longitude_deg"]), "lat": float(r["latitude_deg"])}
        years = sorted({y for t in traffic.values() for y in t["pax"]})
        top = sorted(traffic.items(), key=lambda t: -t[1]["pax"].get(years[-1], 0))[:3]
        print(f"    airports: {len(traffic)} with traffic ({years[0]}-{years[-1]}), {len(pos)} placed; "
              + ", ".join(f"{k} {t['pax'].get('2024', 0) / 1e6:.1f} M (2024)" for k, t in top))
        return {"traffic": traffic, "positions": pos}

    # --- ports (DfT) in the shape of the ports interim's "ports"

    def _ports(self, path) -> list[dict]:
        ods = path(F_PORT0101)

        def table(sheet):
            header, out = None, {}
            for r in ods_rows(ods, sheet):
                if header is None:
                    if r and r[0] == "Ports":
                        header = [(re.match(r"\d{4}", h).group(0) if h and re.match(r"\d{4}", h) else h) for h in r]
                    continue
                if len(r) > 2 and r[2] == "Major Port" and r[0] and not r[0].startswith("Total"):
                    name = re.sub(r"\s*\[Note[^]]*\]", "", r[0]).strip()
                    out[name] = {header[i]: num(r[i]) for i in range(3, min(len(r), len(header)))}
            return out

        both, inw, outw = (table(f"port0101_({d})") for d in ("both_directions", "inwards", "outwards"))
        year = max(y for row in both.values() for y, v in row.items() if v)
        locode = {}
        for r in ods_rows(ods, "Working"):
            if len(r) > 4 and r[2] and r[3] == "Major" and r[4]:
                locode[norm_name(r[4])] = r[2].strip()
        un = {}
        with open(path(F_LOCODE), encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if r["Country"] == "GB" and r["Location"]:
                    un["GB" + r["Location"]] = (r["Name"], dms(r["Coordinates"]))
        wd = {}
        with open(path(F_WIKIDATA), encoding="utf-8") as f:
            for r in csv.DictReader(f):
                code = (r.get("code") or "").replace(" ", "").upper()
                m = re.match(r"^Point\(([-\d.eE]+) ([-\d.eE]+)\)$", r.get("coord") or "")
                if len(code) == 5 and m and code not in wd:
                    wd[code] = (float(m[1]), float(m[2]))
        ports = []
        for name, row in both.items():
            tons = row.get(year)
            if not tons:
                continue
            code = locode.get(norm_name(name))
            if code is None:
                print(f"    ! port {name}: no LOCODE in PORT0101's lookup, left out")
                continue
            un_name, un_pos = un.get(code, (None, None))
            if code in PORT_POS:
                un_pos = PORT_POS[code]
            ins, outs = inw.get(name, {}).get(year), outw.get(name, {}).get(year)
            ports.append({
                "code": f"UK_{code}", "country": "UK", "name": name, "eurostat_name": name, "area": None,
                "locode": code, "locode_name": un_name, "tons": round(tons * 1000),
                "in": round(ins * 1000) if ins is not None else None,
                "out": round(outs * 1000) if outs is not None else None,
                "year": int(year),
                "positions": {"locode": [round(c, 5) for c in un_pos] if un_pos else None,
                              "wikidata": list(wd[code]) if code in wd and code not in PORT_POS else None},
            })
        ports.sort(key=lambda p: -p["tons"])
        unplaced = [p["name"] for p in ports if not (p["positions"]["locode"] or p["positions"]["wikidata"])]
        prev = str(int(year) - 1)
        print(f"    ports: {len(ports)} major ports, {year}: {sum(p['tons'] for p in ports) / 1e6:.1f} Mt "
              f"({prev}: {sum(r.get(prev) or 0 for r in both.values()) / 1e3:.1f} Mt); top "
              + ", ".join(f"{p['name']} {p['tons'] / 1e6:.1f}" for p in ports[:4])
              + (f"; unplaced: {unplaced}" if unplaced else ""))
        return ports
