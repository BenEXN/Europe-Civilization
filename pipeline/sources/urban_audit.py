"""Eurostat city statistics (Urban Audit): the population mix of functional urban areas and core cities.

The City View's citizen rows (pipeline/build/citizens.py) read the age structure, citizenship and country of birth,
educational attainment, journeys to work and labour market of each functional urban area ("…F" codes, table urb_l*)
and of its core city ("…C" codes, table urb_c*). Each request names its indicators (indic_ur), since the API refuses
whole-table extractions (HTTP 413). Each table is reduced to {indicator: {city code: {year: value}}} with the JSON-stat
parser of sources/eurostat.py, keeping only the map's countries."""

from __future__ import annotations

import json
import urllib.parse

from ..core.source import Source, SourceInfo
from .eurostat import parse

API = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/{table}?format=JSON&lang=en&{query}"

AGE = [
    "DE1001V",  # total
    "DE1040V", "DE1074V", "DE1077V",  # 0-4, 5-9, 10-14
    "DE1046V", "DE1049V",  # 15-19, 20-24
    "DE1058V", "DE1101V", "DE1104V",  # 25-34 = 25-29 + 30-34
    "DE1061V", "DE1107V", "DE1110V",  # 35-44 = 35-39 + 40-44
    "DE1064V", "DE1113V", "DE1116V",  # 45-54 = 45-49 + 50-54
    "DE1025V", "DE1119V", "DE1122V",  # 55-64 = 55-59 + 60-64
    "DE1028V", "DE1125V", "DE1128V",  # 65-74 = 65-69 + 70-74
    "DE1055V", "DE1131V", "DE1134V", "DE1137V",  # 75+ = 75-79 + 80-84 + 85+
]
MEDIAN = ["DE1073V"]  # median population age
ORIGIN = ["DE2001V", "DE2002V", "DE2003V", "DE2012V",  # nationals, EU foreigners, non-EU foreigners, foreigners
          "DE2008V", "DE2009V", "DE2010V", "DE2011V"]  # native-born, foreign-born, born in an EU / a non-EU country
EDUCATION = ["TE2025V", "TE2028V", "TE2031V"]  # aged 25-64 by highest ISCED level: 0-2, 3-4, 5-8
COMMUTE = ["TT1003V", "TT1010V", "TT1006V", "TT1007V", "TT1008V", "TT1012V"]  # % of journeys to work by mode
LABOUR = ["EC1001V", "EC1010V", "EC1177V", "EC2020V"]  # active, unemployed, employed 20-64, jobs at the workplace

# id → (table, indicators, first year, English description). "l" tables = functional urban areas, "c" = core cities.
TABLES = {
    "age_fua": ("urb_lpop1", AGE, 2011, "Population on 1 January by age group, functional urban areas"),
    "age_city": ("urb_cpop1", AGE, 2011, "Population on 1 January by age group, core cities"),
    "median_fua": ("urb_lpopstr", MEDIAN, 2011, "Median age of the population, functional urban areas"),
    "median_city": ("urb_cpopstr", MEDIAN, 2011, "Median age of the population, core cities"),
    "origin_fua": ("urb_lpopcb", ORIGIN, 2011, "Population by citizenship and country of birth, functional urban areas"),
    "origin_city": ("urb_cpopcb", ORIGIN, 2011, "Population by citizenship and country of birth, core cities"),
    "education_fua": ("urb_leduc", EDUCATION, 2011, "Population aged 25-64 by highest level of education, functional urban areas"),
    "education_city": ("urb_ceduc", EDUCATION, 2011, "Population aged 25-64 by highest level of education, core cities"),
    "commute_fua": ("urb_ltran", COMMUTE, 2008, "Journeys to work by mode of transport, functional urban areas"),
    "commute_city": ("urb_ctran", COMMUTE, 2008, "Journeys to work by mode of transport, core cities"),
    "labour_fua": ("urb_llma", LABOUR, 2011, "Labour market (active, unemployed, employed, jobs), functional urban areas"),
    "labour_city": ("urb_clma", LABOUR, 2011, "Labour market (active, unemployed, employed, jobs), core cities"),
}


def _labels(d: dict) -> dict:
    return dict(d.get("dimension", {}).get("indic_ur", {}).get("category", {}).get("label", {}))


class UrbanAudit(Source):
    info = SourceInfo(
        id="urban_audit",
        title="Eurostat city statistics (Urban Audit)",
        publisher="Eurostat (European Commission), from the national statistical institutes",
        homepage="https://ec.europa.eu/eurostat/web/cities/database",
        license="Free reuse (Eurostat reuse policy, CC BY 4.0)",
        description="Population by age group, median age, citizenship and country of birth, highest level of "
        "education (ages 25-64), journeys to work by mode of transport and labour market of the functional urban "
        "areas and their core cities, 2021 Urban Audit geography, read through Eurostat's dissemination API. Tables: "
        + ", ".join(sorted({t for t, _, _, _ in TABLES.values()})) + ".",
        used_for=["City View citizens: generations, commute, education and origins"],
    )

    @staticmethod
    def _url(table: str, indicators: list[str], since: int) -> str:
        q = [("sinceTimePeriod", str(since))] + [("indic_ur", i) for i in indicators]
        return API.format(table=table, query=urllib.parse.urlencode(q))

    def fetch(self, force=False):
        for key, (table, indicators, since, _) in TABLES.items():
            self.download(self._url(table, indicators, since), f"{key}.json", force=force)

    def process(self):
        tables, labels, files, updated = {}, {}, [], []
        for key, (table, indicators, since, label) in TABLES.items():
            d = json.loads((self.raw_dir / f"{key}.json").read_text())
            files.append(f"{key}.json")
            suffix = "F" if key.endswith("_fua") else "C"
            series = {ind: {g: row for g, row in rows.items() if len(g) == 6 and g.endswith(suffix)}
                      for ind, rows in parse(d).items()}
            labels.update(_labels(d))
            if d.get("updated"):
                updated.append(d["updated"][:10])
            n = sum(len(s) for s in series.values())
            last = max((y for s in series.values() for row in s.values() for y in row), default=None)
            print(f"    {key:15s} {table:12s} {len(series)} indicators, {n} rows, latest {last}")
            tables[key] = {"table": table, "level": "fua" if suffix == "F" else "city", "label": label,
                           "since": since, "updated": d.get("updated"), "series": series}
        return {
            "vintage": "Eurostat city statistics (Urban Audit), updated " + (max(updated) if updated else "?"),
            "_files": files,
            "labels": {k: labels[k] for k in sorted(labels)},
            "tables": tables,
        }
