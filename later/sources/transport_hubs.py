"""Airports (Eurostat passenger counts, OurAirports positions) and seaports (Eurostat tonnage; Natural Earth points as a
fallback) of metropolitan France."""

from __future__ import annotations

import csv
import io
import json
import re

from ..core.geo import load_geojson
from ..core.source import Source, SourceInfo

CODELIST = "https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/codelist/ESTAT/REP_AIRP"
AVIA = ("https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/avia_paoa?format=JSON&lang=fr"
        "&tra_meas=PAS_CRD&schedule=TOTAL&tra_cov=TOTAL&unit=PAS&freq=A")
OURAIRPORTS = "https://davidmegginson.github.io/ourairports-data/airports.csv"
NE_PORTS = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/v5.1.2/geojson/ne_10m_ports.geojson"
PORT_CODELIST = "https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/codelist/ESTAT/REP_MAR"
# Gross weight of goods handled in all ports, by port (thousand tonnes); in = unloaded, out = loaded.
PORT_TONS = ("https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/mar_go_aa?format=JSON&lang=fr"
             "&unit=THS_T&freq=A")
BBOX = (-5.5, 41.2, 9.8, 51.3)


class Airports(Source):
    info = SourceInfo(
        id="airports",
        title="Trafic de passagers des aéroports (Eurostat) et positions (OurAirports)",
        publisher="Eurostat (avia_paoa, d'après la DGAC) ; OurAirports",
        homepage="https://ec.europa.eu/eurostat/databrowser/view/avia_paoa/default/table",
        license="Eurostat : réutilisation libre (CC BY 4.0) ; OurAirports : domaine public",
        description="Passagers transportés par chaque aéroport français déclaré à Eurostat (vols réguliers et non "
        "réguliers, arrivées et départs), placés par leur code OACI avec la base OurAirports.",
        used_for=["Aéroports sur la carte"],
    )

    def fetch(self, force=False):
        self.download(CODELIST, "rep_airp_codelist.xml", force=force)
        codes = sorted(set(re.findall(r'id="(FR_LF[A-Z]{2})"', (self.raw_dir / "rep_airp_codelist.xml").read_text(encoding="utf-8"))))
        self.download(AVIA + "".join(f"&rep_airp={c}" for c in codes), "avia_paoa_fr.json", force=force)
        self.download(OURAIRPORTS, "ourairports_airports.csv", force=force)

    def process(self):
        d = json.loads((self.raw_dir / "avia_paoa_fr.json").read_text())
        dims, size = d["id"], d["size"]
        airp, time = d["dimension"]["rep_airp"]["category"], d["dimension"]["time"]["category"]
        ai, ti = dims.index("rep_airp"), dims.index("time")
        stride = [1] * len(dims)
        for k in range(len(dims) - 2, -1, -1):
            stride[k] = stride[k + 1] * size[k + 1]
        years = {v: k for k, v in time["index"].items()}
        traffic = {}
        for code, a in airp["index"].items():
            series = {}
            for t, year in years.items():
                v = d["value"].get(str(a * stride[ai] + t * stride[ti]))
                if v is not None:
                    series[year] = v
            if series:
                traffic[code[3:]] = {"label": airp["label"][code], "pax": series}
        pos = {}
        text = (self.raw_dir / "ourairports_airports.csv").read_text(encoding="utf-8")
        for r in csv.DictReader(io.StringIO(text)):
            icao = r.get("icao_code") or r.get("gps_code") or r.get("ident")
            if icao in traffic:
                pos[icao] = {"name": r["name"], "city": r["municipality"], "iata": r["iata_code"] or None,
                             "lon": float(r["longitude_deg"]), "lat": float(r["latitude_deg"])}
        print(f"    {len(traffic)} airports with traffic, {len(pos)} placed")
        return {"vintage": "Eurostat avia_paoa", "_files": ["avia_paoa_fr.json", "ourairports_airports.csv"],
                "traffic": traffic, "positions": pos}


class Ports(Source):
    info = SourceInfo(
        id="ports",
        title="Trafic des ports maritimes (Eurostat) ; ports de Natural Earth",
        publisher="Eurostat (statistiques des transports maritimes, d'après le SDES) ; Natural Earth",
        homepage="https://ec.europa.eu/eurostat/databrowser/view/mar_go_aa/default/table",
        license="Eurostat : réutilisation libre (CC BY 4.0) ; Natural Earth : domaine public",
        description="Poids brut des marchandises traitées par chaque port de France métropolitaine déclaré à Eurostat "
        "(milliers de tonnes, dernière année complète), séparé en marchandises débarquées et embarquées. Le Havre et "
        "Rouen ne sont publiés qu'ensemble (HAROPA). Les points de Natural Earth ne servent que si Eurostat manque.",
        used_for=["Ports sur la carte, classés par tonnage", "Conseiller du commerce"],
    )

    def fetch(self, force=False):
        self.download(NE_PORTS, "ne_10m_ports.geojson", force=force)
        self.download(PORT_CODELIST, "rep_mar_codelist.xml", force=force)
        codes = self._codes()
        self.download(PORT_TONS + "".join(f"&rep_mar={c}" for c in codes), "mar_go_aa_fr.json", force=force)

    def _codes(self) -> dict[str, str]:
        """Eurostat code → name of each metropolitan French port (FR_1: Atlantic/North Sea, FR_2: Mediterranean)."""
        xml = (self.raw_dir / "rep_mar_codelist.xml").read_text(encoding="utf-8")
        return dict(re.findall(r'<s:Code id="(FR_[12]FR[^"]*)"[^>]*>.*?<c:Name xml:lang="en">([^<]*)</c:Name>', xml, re.S))

    def _eurostat(self) -> tuple[list[dict], str | None]:
        path = self.raw_dir / "mar_go_aa_fr.json"
        if not path.exists():
            return [], None
        d = json.loads(path.read_text())
        dims, size = d["id"], d["size"]
        stride = [1] * len(dims)
        for k in range(len(dims) - 2, -1, -1):
            stride[k] = stride[k + 1] * size[k + 1]
        idx = {k: d["dimension"][k]["category"]["index"] for k in dims}
        years = sorted(idx["time"], reverse=True)

        def val(port, year, direct):
            key = {"freq": "A", "direct": direct, "unit": "THS_T", "rep_mar": port, "time": year}
            if any(key[k] not in idx[k] for k in dims):
                return None
            return d["value"].get(str(sum(idx[k][key[k]] * stride[i] for i, k in enumerate(dims))))

        # The latest year that most ports have reported, compared with the five years before it (a fresh year can be
        # partial; old years list ports that have since closed or merged).
        counts = {y: sum(1 for p in idx["rep_mar"] if val(p, y, "TOTAL")) for y in years}
        year = next((y for k, y in enumerate(years) if counts[y] and counts[y] >= 0.8 * max(counts[z] for z in years[k:k + 6])), None)
        names = self._codes()
        out = []
        for port in idx["rep_mar"]:
            t = val(port, year, "TOTAL") if year else None
            if not t:
                continue
            i, o = val(port, year, "IN"), val(port, year, "OUT")
            out.append({"code": port, "name": names.get(port, port), "tons": round(t * 1000),
                        "in": round(i * 1000) if i is not None else None,
                        "out": round(o * 1000) if o is not None else None, "year": int(year)})
        out.sort(key=lambda p: -p["tons"])
        return out, year

    def process(self):
        ne = []
        for f in load_geojson(self.raw_dir / "ne_10m_ports.geojson"):
            lon, lat = f["geometry"]["coordinates"][:2]
            if BBOX[0] <= lon <= BBOX[2] and BBOX[1] <= lat <= BBOX[3]:
                p = f["properties"]
                ne.append({"name": p.get("name"), "rank": p.get("scalerank"), "natlscale": p.get("natlscale"),
                           "lon": lon, "lat": lat})
        tonnage, year = self._eurostat()
        print(f"    {len(tonnage)} ports with Eurostat tonnage ({year}), {len(ne)} Natural Earth ports in the window")
        return {"vintage": f"Eurostat mar_go_aa {year}" if year else "Natural Earth v5.1.2",
                "_files": ["mar_go_aa_fr.json", "rep_mar_codelist.xml", "ne_10m_ports.geojson"],
                "year": int(year) if year else None, "tonnage": tonnage, "ports": ne}
