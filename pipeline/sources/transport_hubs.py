"""Airports (Eurostat passenger counts, OurAirports positions) and seaports (Eurostat tonnage, positions from Wikidata
and UN/LOCODE) of the map's 37 countries.

Eurostat refuses big extractions (HTTP 413), so both tables are requested one country at a time (and in chunks of
CHUNK codes for the countries with many ports or airports), only from SINCE on.
"""

from __future__ import annotations

import csv
import io
import json
import re
import urllib.error
import urllib.parse

from ..core.europe import COUNTRIES, english_name
from ..core.source import Source, SourceInfo
from .gisco import uk_part

SINCE = 2016
CHUNK = 100  # codes per Eurostat request
ESTAT = "https://ec.europa.eu/eurostat/api/dissemination"
AIRP_CODELIST = f"{ESTAT}/sdmx/2.1/codelist/ESTAT/REP_AIRP"
MAR_CODELIST = f"{ESTAT}/sdmx/2.1/codelist/ESTAT/REP_MAR"
# Passengers carried (arrivals + departures), scheduled and non-scheduled, all of an airport's traffic.
AVIA = (f"{ESTAT}/statistics/1.0/data/avia_paoa?format=JSON&lang=en&tra_meas=PAS_CRD&schedule=TOTAL&tra_cov=TOTAL"
        f"&unit=PAS&freq=A&sinceTimePeriod={SINCE}")
# Gross weight of goods handled in all ports, by port (thousand tonnes); IN = unloaded, OUT = loaded.
MAR = f"{ESTAT}/statistics/1.0/data/mar_go_aa?format=JSON&lang=en&unit=THS_T&freq=A&sinceTimePeriod={SINCE}"
OURAIRPORTS = "https://davidmegginson.github.io/ourairports-data/airports.csv"
LOCODE_TAG = "2024-2"  # pinned release of the datasets/un-locode mirror of the UNECE list
LOCODE = f"https://raw.githubusercontent.com/datasets/un-locode/{LOCODE_TAG}/data/code-list.csv"
# Every Wikidata item with a UN/LOCODE (P1937) and a position (P625): the ports' first choice of position (the UN/LOCODE
# list leaves many big ports without coordinates and misplaces a few).
WIKIDATA_QUERY = "SELECT ?code ?coord WHERE { ?item wdt:P1937 ?code; wdt:P625 ?coord. }"
WIKIDATA = "https://query.wikidata.org/sparql?" + urllib.parse.urlencode({"query": WIKIDATA_QUERY})
WIKIDATA_MIN_ROWS = 30_000  # fewer means the answer was cut short
YEAR_COMPLETE = 0.7  # share of last year's reporting ports a year needs to count as complete

# Eurostat reports a few ports as one merged authority: placed at the UN/LOCODE of their main harbour.
PORT_AT = {
    "BE_0BE003": "BEANR",  # Antwerp-Bruges → Antwerp
    "FR_1FR001": "FRLEH",  # HAROPA (Le Havre and Rouen) → Le Havre
    "NL_0NLZSP": "NLVLI",  # Zeeland Seaports → Vlissingen
    "FI_0FI002": "FIKTK",  # HaminaKotka → Kotka
    "NO_0NOGVL": "NOPOR",  # Porsgrunn, Rafnes, Herøya, Brevik, Skien, … → Porsgrunn
    "FR_5REPDG": "RELPT",  # Port Réunion → Le Port
    "DK_0DKSTT": "DKKAL",  # Statoil-Havnen → Kalundborg
    "DK_0DKASV": "DKKAL",  # Asnæsværkets Havn → Kalundborg
    "DK_0DKAIT": "DKKAL",  # Asnæs Inter Terminal → Kalundborg
    "DK_0DKEIT": "DKAAB",  # Ensted Inter Terminal → Aabenraa
    "IT_0IT004": "ITLIP",  # Eolie (Aeolian Islands) → Lipari
    "IT_0IT002": "ITPFE",  # Isola d'Elba → Portoferraio
    "IT_0IT003": "ITFAV",  # Egadi → Favignana
    "FR_1FRNTE": "FRSNR",  # Nantes Saint-Nazaire → Saint-Nazaire (most of the tonnage: Montoir, Donges)
    "DK_0DKAVE": "DKCPH",  # Avedøreværkets Havn (Hvidovre) → Copenhagen
    "DK_0DKTHR": "DKROD",  # Tunnel Port Rødby → Rødbyhavn
    "NO_0NOHAD": "NOSKN",  # Hadsel → Stokmarknes
    "IS_0ISSTR": "ISREY",  # Straumsvík (Hafnarfjörður) → Reykjavík
    "IS_0ISRFJ": "ISMJH",  # Reyðarfjörður → Mjóeyrarhöfn, its aluminium smelter's harbour
    "EL_0GRSUD": "GRCHQ",  # Souda Bay → Chania
}
# The parts of a merged port, dropped in a year the merged port reports (never counted twice).
MERGED_PARTS = {
    "BE_0BE003": ["BE_0BEANR", "BE_0BEZEE"],
    "FR_1FR001": ["FR_1FRLEH", "FR_1FRURO"],
    "NL_0NLZSP": ["NL_0NLVLI", "NL_0NLTNZ"],
    "FI_0FI002": ["FI_0FIHMN", "FI_0FIKTK"],
}
# English names for the ports whose Eurostat label is local or a list (english_name() covers the city exonyms).
PORT_NAMES = {
    "BE_0BE003": "Antwerp-Bruges", "BE_0BEANR": "Antwerp", "BE_0BEZEE": "Zeebrugge", "BE_0BEGNE": "Ghent",
    "BE_0BEOST": "Ostend", "BE_0BEBRU": "Brussels", "BE_0BELGG": "Liège",
    "FR_1FR001": "Le Havre – Rouen (HAROPA)", "FR_5REPDG": "Port Réunion (Le Port)",
    "NL_0NLZSP": "Zeeland Seaports (Vlissingen – Terneuzen)", "FI_0FI002": "HaminaKotka",
    "NO_0NOGVL": "Grenland (Porsgrunn, Brevik, Skien)", "IT_0IT004": "Aeolian Islands", "IT_0IT002": "Elba",
    "IT_0IT003": "Egadi Islands", "DK_0DKFRC": "Fredericia", "DK_0DKHLS": "Helsingør", "EL_0GRPIR": "Piraeus",
    "EL_0GRSKG": "Thessaloniki", "PL_0PLGDN": "Gdańsk", "DE_3DEFRA": "Frankfurt", "SE_2SEGOT": "Gothenburg",
    "IT_0ITGOA": "Genoa", "IT_0ITVCE": "Venice", "IT_0ITNAP": "Naples", "IT_0ITSIR": "Syracuse",
    "IT_0ITLIV": "Livorno", "PT_0PTLIS": "Lisbon", "ES_2ESSVQ": "Seville", "DK_0DKCPH": "Copenhagen",
    "FR_1FRNTE": "Nantes – Saint-Nazaire", "FR_1FRDKK": "Dunkirk", "FR_1FRSML": "Saint-Malo",
    "FR_4MQFDF": "Fort-de-France (Martinique)", "ES_1ESLCG": "A Coruña", "ES_2ESLPA": "Las Palmas (Gran Canaria)",
    "DK_0DKAAR": "Aarhus", "DK_0DKSTT": "Kalundborg (Statoil harbour)", "DK_0DKASV": "Asnæs power station (Kalundborg)",
    "DK_0DKEIT": "Ensted (Aabenraa)", "DK_0DKAVE": "Avedøre power station (Copenhagen)",
    "DK_0DKTHR": "Rødbyhavn (Fehmarn Belt tunnel works)", "DK_0DKROF": "Rødby (ferry port)",
    "DK_0DKSSV": "Studstrup power station", "DE_2DEBSK": "Fehmarn (Burgstaaken)",
    "NO_0NOKSU": "Kristiansund", "NO_0NOTRD": "Trondheim", "NO_0NOKRS": "Kristiansand", "NO_0NOFRO": "Florø",
    "NO_0NOHAD": "Hadsel (Stokmarknes)", "EL_0GRRHO": "Rhodes", "EL_0GRCFU": "Corfu", "EL_0GRJTR": "Santorini (Thira)",
    "EL_0GRLIN": "Linoperamata (Heraklion)", "EL_0GRSUD": "Souda Bay (Chania)", "PL_0PLSWI": "Świnoujście",
    "LT_0LTKLJ": "Klaipėda", "RO_0ROCND": "Constanța", "RO_0ROGAL": "Galați", "ES_1ESVIL": "Vilagarcía de Arousa",
    "IS_0ISSTR": "Straumsvík (Hafnarfjörður)", "IS_0ISRFJ": "Reyðarfjörður",
}
AGGREGATE = re.compile(r"\bother\b|offshore|confidential|ship to ship|unknown|unspecified", re.I)


def port_name(code: str, name: str) -> str:
    """English display name: PORT_NAMES, else the Eurostat label with the city exonyms, 'Açores' and no 'Havn'."""
    if code in PORT_NAMES:
        return PORT_NAMES[code]
    name = re.sub(r"\s+", " ", name).strip()
    name = name.replace("Ilha de S. Miguel", "São Miguel").replace("Ilha ", "").replace("Açores", "Azores")
    name = re.sub(r"\s+Havn(en)?$", "", name)
    return english_name(name)


def _codelist(path) -> dict[str, str]:
    """Eurostat SDMX code list → {code: English name}."""
    xml = path.read_text(encoding="utf-8")
    return dict(re.findall(r'<s:Code id="([^"]+)"[^>]*>.*?<c:Name xml:lang="en">([^<]*)</c:Name>', xml, re.S))


def _chunks(items: list, n: int) -> list[list]:
    return [items[k:k + n] for k in range(0, len(items), n)]


def _cube(d: dict) -> dict[tuple, float]:
    """JSON-stat 2.0 → {(category of each dimension, in d["id"] order): value}."""
    dims, size = d["id"], d["size"]
    cats = []
    for dim in dims:
        idx = d["dimension"][dim]["category"]["index"]
        inv = [None] * len(idx)
        for code, i in (idx.items() if isinstance(idx, dict) else enumerate(idx)):
            inv[i] = code
        cats.append(inv)
    values = d.get("value") or {}
    if isinstance(values, list):
        values = {str(i): v for i, v in enumerate(values) if v is not None}
    out = {}
    for key, v in values.items():
        if v is None:
            continue
        k, coords = int(key), []
        for n in reversed(size):
            k, r = divmod(k, n)
            coords.append(r)
        out[tuple(cats[i][c] for i, c in enumerate(reversed(coords)))] = v
    return out


def _dms(text: str) -> tuple[float, float] | None:
    """UN/LOCODE coordinates "5113N 00425E" → (lon, lat)."""
    m = re.match(r"^(\d{2})(\d{2})([NS])\s+(\d{3})(\d{2})([EW])$", (text or "").strip())
    if not m:
        return None
    lat = int(m[1]) + int(m[2]) / 60
    lon = int(m[4]) + int(m[5]) / 60
    return (-lon if m[6] == "W" else lon), (-lat if m[3] == "S" else lat)



class _EurostatByCountry(Source):
    """Shared fetch: one Eurostat request per country (and per CHUNK codes)."""

    TABLE_URL = ""
    DIM = ""
    FOLDER = ""

    def _country_codes(self) -> dict[str, list[str]]:
        raise NotImplementedError

    def _fetch_tables(self, force: bool) -> None:
        for cc, codes in sorted(self._country_codes().items()):
            for k, chunk in enumerate(_chunks(codes, CHUNK)):
                rel = f"{self.FOLDER}/{cc}{f'_{k}' if k else ''}.json"
                url = self.TABLE_URL + "".join(f"&{self.DIM}={c}" for c in chunk)
                try:
                    self.download(url, rel, force=force)
                except urllib.error.HTTPError as exc:
                    if exc.code not in (400, 404):
                        raise
                    print(f"    {cc}: no data in {self.FOLDER} (HTTP {exc.code})")

    def _tables(self) -> list[dict]:
        return [json.loads(p.read_text()) for p in sorted((self.raw_dir / self.FOLDER).glob("*.json"))]

    def _files(self) -> list[str]:
        return [f"{self.FOLDER}/{p.name}" for p in sorted((self.raw_dir / self.FOLDER).glob("*.json"))]


class Airports(_EurostatByCountry):
    after = ("uk_ons",)
    info = SourceInfo(
        id="airports",
        title="Airport passenger traffic (Eurostat) and positions (OurAirports)",
        publisher="Eurostat (avia_paoa, from the national civil aviation authorities); OurAirports",
        homepage="https://ec.europa.eu/eurostat/databrowser/view/avia_paoa/default/table",
        license="Eurostat: free reuse (CC BY 4.0); OurAirports: public domain",
        description="Passengers carried by each airport of the map's countries that reports to Eurostat (scheduled "
        "and non-scheduled flights, arrivals plus departures, a year), placed by its ICAO code with the OurAirports "
        "database. Liechtenstein has no airport and Albania reports no figures.",
        used_for=["Airports on the map", "Commerce advisor"],
    )

    TABLE_URL, DIM, FOLDER = AVIA, "rep_airp", "avia_paoa"

    def _country_codes(self) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        for code in _codelist(self.raw_dir / "rep_airp_codelist.xml"):
            m = re.match(r"^([A-Z]{2})_([A-Z]{4})$", code)
            if m and m[1] in COUNTRIES and m[2] != "OTHR":
                out.setdefault(m[1], []).append(code)
        return out

    def fetch(self, force=False):
        self.download(AIRP_CODELIST, "rep_airp_codelist.xml", force=force)
        self._fetch_tables(force)
        self.download(OURAIRPORTS, "ourairports_airports.csv", force=force)

    def process(self):
        traffic: dict[str, dict] = {}
        for d in self._tables():
            dims = d["id"]
            ai, ti = dims.index("rep_airp"), dims.index("time")
            labels = d["dimension"]["rep_airp"]["category"].get("label", {})
            for key, v in _cube(d).items():
                code, year = key[ai], key[ti]
                cc, icao = code.split("_", 1)
                t = traffic.setdefault(icao, {"country": cc, "label": labels.get(code, code), "pax": {}})
                t["pax"][year] = v
        pos = {}
        text = (self.raw_dir / "ourairports_airports.csv").read_text(encoding="utf-8")
        for r in csv.DictReader(io.StringIO(text)):
            for icao in {r.get("icao_code"), r.get("gps_code"), r.get("ident")}:
                if icao and icao in traffic and icao not in pos:
                    pos[icao] = {"name": r["name"], "city": english_name(r["municipality"]) or None,
                                 "iata": r["iata_code"] or None, "iso": r["iso_country"],
                                 "lon": float(r["longitude_deg"]), "lat": float(r["latitude_deg"])}
        uk = uk_part()  # the UK's airports: Civil Aviation Authority figures (sources/uk_ons.py)
        if uk and uk.get("airports"):
            traffic.update(uk["airports"]["traffic"])
            pos.update(uk["airports"]["positions"])
        years = sorted({y for t in traffic.values() for y in t["pax"]})
        print(f"    {len(traffic)} airports with traffic ({years[0]}–{years[-1]}) in "
              f"{len({t['country'] for t in traffic.values()})} countries, {len(pos)} placed by OurAirports")
        return {"vintage": f"Eurostat avia_paoa {years[0]}–{years[-1]}" + ("; UK: CAA" if uk else ""),
                "_files": ["rep_airp_codelist.xml", *self._files(), "ourairports_airports.csv"],
                "traffic": traffic, "positions": pos}


class Ports(_EurostatByCountry):
    after = ("uk_ons",)
    info = SourceInfo(
        id="ports",
        title="Seaport freight (Eurostat), placed with Wikidata and UN/LOCODE",
        publisher="Eurostat (maritime transport statistics, from the national authorities); Wikidata; UNECE UN/LOCODE",
        homepage="https://ec.europa.eu/eurostat/databrowser/view/mar_go_aa/default/table",
        license="Eurostat: free reuse (CC BY 4.0); UN/LOCODE: free reuse (UNECE); Wikidata: CC0",
        description="Gross weight of goods handled by each port of the map's countries that reports to Eurostat "
        "(thousand tonnes a year, unloaded plus loaded), each country's latest complete year (the latest year in which "
        "at least 70% of the ports that reported the year before report too). Eurostat names a port by its UN/LOCODE; "
        "the port is placed at the Wikidata place carrying that code, or, where Wikidata has none, at the code's "
        f"coordinates in the UN/LOCODE list (release {LOCODE_TAG}; it has a few misplaced entries, e.g. Delfzijl and "
        "Kaskinen, which is why Wikidata comes first). Rows that are not one place (\"other ports\", offshore "
        "installations, confidential totals) are left out.",
        used_for=["Ports on the map, ranked by tonnage", "Commerce advisor"],
    )

    TABLE_URL, DIM, FOLDER = MAR, "rep_mar", "mar_go_aa"

    def _country_codes(self) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        for code in _codelist(self.raw_dir / "rep_mar_codelist.xml"):
            m = re.match(r"^([A-Z]{2})_\d[A-Z0-9]{5}$", code)
            if m and m[1] in COUNTRIES:
                out.setdefault(m[1], []).append(code)
        return out

    def fetch(self, force=False):
        self.download(MAR_CODELIST, "rep_mar_codelist.xml", force=force)
        self._fetch_tables(force)
        self.download(LOCODE, f"un-locode-{LOCODE_TAG}/code-list.csv", force=force)
        path = self.download(WIKIDATA, "wikidata_locode.csv", force=force, headers={"Accept": "text/csv"})
        rows = sum(1 for _ in path.open(encoding="utf-8")) - 1
        if rows < WIKIDATA_MIN_ROWS:
            self.discard("wikidata_locode.csv")
            raise RuntimeError(f"Wikidata answered {rows} UN/LOCODE rows (expected {WIKIDATA_MIN_ROWS:,}+): cut short, "
                               "run fetch ports again")

    def _locodes(self) -> tuple[dict, dict]:
        """UN/LOCODE → (name, (lon, lat) | None) from the UN/LOCODE list, and → (lon, lat) from Wikidata."""
        un = {}
        text = (self.raw_dir / f"un-locode-{LOCODE_TAG}" / "code-list.csv").read_text(encoding="utf-8")
        for r in csv.DictReader(io.StringIO(text)):
            if r["Location"]:
                un[r["Country"] + r["Location"]] = (r["Name"], _dms(r["Coordinates"]))
        wd = {}
        text = (self.raw_dir / "wikidata_locode.csv").read_text(encoding="utf-8")
        for r in csv.DictReader(io.StringIO(text)):
            code = (r.get("code") or "").replace(" ", "").upper()
            m = re.match(r"^Point\(([-\d.eE]+) ([-\d.eE]+)\)$", r.get("coord") or "")
            if len(code) == 5 and m and code not in wd:
                wd[code] = (float(m[1]), float(m[2]))
        return un, wd

    def process(self):
        names = _codelist(self.raw_dir / "rep_mar_codelist.xml")
        values: dict[str, dict[str, dict[str, float]]] = {}  # port → year → direction → thousand tonnes
        for d in self._tables():
            dims = d["id"]
            pi, ti, di = dims.index("rep_mar"), dims.index("time"), dims.index("direct")
            for key, v in _cube(d).items():
                values.setdefault(key[pi], {}).setdefault(key[ti], {})[key[di]] = v
        un, wd = self._locodes()

        # Each country's latest complete year: the latest year in which at least YEAR_COMPLETE of the ports that
        # reported the year before report too (a fresh year can be partial, e.g. Norway's 2025 lists 38 of 91 ports).
        by_country: dict[str, list[str]] = {}
        for code in values:
            by_country.setdefault(code[:2], []).append(code)
        ports, skipped, years = [], [], {}
        for cc, codes in sorted(by_country.items()):
            seen: dict[str, set] = {}
            for code in codes:
                if AGGREGATE.search(names.get(code, "")):
                    continue
                for y, dv in values[code].items():
                    if dv.get("TOTAL"):
                        seen.setdefault(y, set()).add(code)
            ys = sorted(seen, reverse=True)
            year = next((y for y in ys if str(int(y) - 1) not in seen
                         or len(seen[y] & seen[str(int(y) - 1)]) >= YEAR_COMPLETE * len(seen[str(int(y) - 1)])), None)
            if year is None:
                continue
            years[cc] = int(year)
            reported = {c for c in codes if values[c].get(year, {}).get("TOTAL")}
            for merged, parts in MERGED_PARTS.items():
                if merged in reported:
                    reported -= set(parts)
            for code in sorted(reported):
                name = names.get(code, code)
                if AGGREGATE.search(name):
                    skipped.append(name)
                    continue
                dv = values[code][year]
                locode = PORT_AT.get(code, code[4:])
                un_name, un_pos = un.get(locode, (None, None))
                ports.append({
                    "code": code, "country": cc, "name": port_name(code, name),
                    "eurostat_name": name, "area": names.get(code[:4]), "locode": locode, "locode_name": un_name,
                    "tons": round(dv["TOTAL"] * 1000),
                    "in": round(dv["IN"] * 1000) if dv.get("IN") is not None else None,
                    "out": round(dv["OUT"] * 1000) if dv.get("OUT") is not None else None,
                    "year": int(year),
                    "positions": {"locode": list(un_pos) if un_pos else None,
                                  "wikidata": list(wd[locode]) if locode in wd else None},
                })
        uk = uk_part()  # the UK's major ports: Department for Transport figures (sources/uk_ons.py)
        if uk and uk.get("ports"):
            ports += uk["ports"]
            years["UK"] = max(p["year"] for p in uk["ports"])
        ports.sort(key=lambda p: -p["tons"])
        n_wd = sum(1 for p in ports if p["positions"]["wikidata"])
        n_un = sum(1 for p in ports if not p["positions"]["wikidata"] and p["positions"]["locode"])
        lo, hi = min(years.values()), max(years.values())
        print(f"    {len(ports)} ports with tonnage in {len(years)} countries ({lo}–{hi}); positions: {n_wd} Wikidata, "
              f"{n_un} UN/LOCODE only, {len(ports) - n_un - n_wd} none; {len(skipped)} aggregate rows left out")
        return {"vintage": (f"Eurostat mar_go_aa {lo}" if lo == hi else f"Eurostat mar_go_aa {lo}–{hi}") + ("; UK: DfT" if uk else ""),
                "_files": ["rep_mar_codelist.xml", *self._files(), f"un-locode-{LOCODE_TAG}/code-list.csv",
                           "wikidata_locode.csv"],
                "years": years, "ports": ports, "aggregates_left_out": skipped}
