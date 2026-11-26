"""Eurostat structural business statistics by region (SBS, table sbs_r_nuts2021): persons employed in the local units
of enterprises, by NACE Rev. 2 section and division (two digits), for NUTS 2 regions (with their NUTS 1 and country
totals), 2021 onwards, through the dissemination API (JSON-stat 2.0, one request).

Counted where the work is done (local units, not head offices). Covers the business economy, sections B to N plus the
market parts of P, Q, R and S95-S96; public administration (O) and most public education and health are outside SBS.
Values Eurostat withholds as confidential are kept apart from those it does not publish at all."""

from __future__ import annotations

import json
import urllib.parse

from ..core.source import Source, SourceInfo
from .eurostat import API, mapped_geo, parse

TABLE = "sbs_r_nuts2021"
SINCE = 2021
INDICATOR = "EMP_LOC_NR"  # persons employed in local units
FILE = f"{TABLE}_{INDICATOR}.json"


def url() -> str:
    q = [("indic_sbs", INDICATOR), ("sinceTimePeriod", str(SINCE))]
    return API.format(table=TABLE, query=urllib.parse.urlencode(q))


def withheld(d: dict) -> dict:
    """{geo: {year: [NACE codes withheld as confidential]}} from the JSON-stat status flags ("|C", "b|C", "c")."""
    dims, size = d["id"], d["size"]
    stride = [1] * len(dims)
    for k in range(len(dims) - 2, -1, -1):
        stride[k] = stride[k + 1] * size[k + 1]
    cats = {dim: {i: code for code, i in d["dimension"][dim]["category"]["index"].items()} for dim in dims}
    out: dict = {}
    for key, flag in (d.get("status") or {}).items():
        if "C" not in flag.upper() or str(key) in d["value"]:
            continue
        idx, rest = {}, int(key)
        for k, dim in enumerate(dims):
            idx[dim], rest = divmod(rest, stride[k])
        geo, year, code = cats["geo"][idx["geo"]], cats["time"][idx["time"]], cats["nace_r2"][idx["nace_r2"]]
        if mapped_geo(geo):
            out.setdefault(geo, {}).setdefault(year, []).append(code)
    for g in out.values():
        for y in g:
            g[y].sort()
    return out


class Sbs(Source):
    info = SourceInfo(
        id="sbs",
        title="Eurostat structural business statistics by NUTS 2 region",
        publisher="Eurostat (European Commission), from the national statistical institutes",
        homepage="https://ec.europa.eu/eurostat/databrowser/view/sbs_r_nuts2021/default/table",
        license="Free reuse (Eurostat reuse policy, CC BY 4.0)",
        description="Persons employed in the local units of enterprises by NACE Rev. 2 section and division, for the "
        "NUTS 2 regions, " + str(SINCE) + " onwards (table " + TABLE + "). Business economy only: sections B to N and "
        "the market parts of P, Q, R and S. Not published for Switzerland, Liechtenstein and the Western Balkans "
        "except Serbia and North Macedonia; figures withheld as confidential are flagged.",
        used_for=["City View districts: industry specialities (divisions) of each city's region"],
    )

    def fetch(self, force=False):
        self.download(url(), FILE, force=force)

    def process(self):
        d = json.loads((self.raw_dir / FILE).read_text())
        series = parse(d)  # {"C29|EMP_LOC_NR": {geo: {year: value}}}
        values: dict = {}
        for key, rows in series.items():
            code = key.split("|")[0]
            for geo, row in rows.items():
                for year, v in row.items():
                    values.setdefault(geo, {}).setdefault(year, {})[code] = v
        held = withheld(d)
        labels = d["dimension"]["nace_r2"]["category"].get("label", {})
        years = sorted({y for g in values.values() for y in g})
        n2 = [g for g in values if len(g) == 4]
        print(f"    {len(values)} geographies ({len(n2)} NUTS 2), years {years[0]}-{years[-1]}, "
              f"{sum(len(c) for g in held.values() for c in g.values())} confidential cells")
        return {
            "vintage": f"Eurostat SBS by NUTS 2 region ({TABLE}), {years[-1]}; updated {d.get('updated', '')[:10]}",
            "_files": [FILE],
            "table": TABLE,
            "indicator": INDICATOR,
            "updated": d.get("updated"),
            "years": years,
            "titles": {code: labels.get(code, code) for code in d["dimension"]["nace_r2"]["category"]["index"]},
            "values": values,      # {geo: {year: {nace: persons employed}}}
            "withheld": held,      # {geo: {year: [nace withheld as confidential]}}
        }
