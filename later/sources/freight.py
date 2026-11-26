"""Freight flows between regions (NUTS 2), road, rail and inland waterways, from the ministry's national flow files."""

from __future__ import annotations

from ..core.source import Source, SourceInfo
from ..core.xlsx import read_rows

YEAR = 2019
BASE = "https://www.ecologie.gouv.fr/sites/default/files/documents"
# file → (mode, measure columns): road is in tonne-km only; rail comes as two files (tonnes, tonne-km).
FILES = {
    "TRM_2019.xlsx": "road",
    "Ferro_tonnes_2019_diff.xlsx": "rail_t",
    "Ferro_2019_diff.xlsx": "rail_tkm",
    "VNF_2019.xlsx": "water",
}


def _num(v) -> float | None:
    """A published number, or None for a blank or a value withheld by statistical secrecy ('#N/A')."""
    if v in (None, "", "#N/A", "NA"):
        return None
    try:
        return float(v)
    except ValueError:
        return None


class Freight(Source):
    info = SourceInfo(
        id="freight",
        title=f"Flux de marchandises entre régions, route, rail et voie d'eau ({YEAR})",
        publisher="Ministère de la Transition écologique, d'après le SDES (enquête TRM), les entreprises ferroviaires "
        "et Voies navigables de France",
        homepage="https://www.ecologie.gouv.fr/politiques-publiques/donnees-nationales-flux-marchandises",
        license="Licence Ouverte 2.0 (Etalab)",
        description=f"Les flux de marchandises de {YEAR} entre régions NUTS 2 (les 22 anciennes régions de la France "
        "métropolitaine, et les régions et pays voisins) : par la route en tonnes-kilomètres (enquête TRM, camions sous "
        "pavillon français, hors transit), par le rail en tonnes et tonnes-kilomètres, par la voie d'eau en tonnes et "
        "tonnes-kilomètres. Les valeurs couvertes par le secret statistique (moins de 3 opérateurs, ou un opérateur à "
        "plus de 85 %) ne sont pas publiées.",
        used_for=["Routes commerciales entre régions", "Échanges de chaque région"],
    )

    def fetch(self, force=False):
        for name in FILES:
            self.download(f"{BASE}/{name}", f"{YEAR}/{name}", force=force, expect_binary=True)

    def process(self):
        flows: dict[tuple[str, str], dict] = {}
        names: dict[str, str] = {}
        centres: dict[str, tuple[float, float]] = {}
        withheld = {"rail_t": 0, "rail_tkm": 0}
        for name, kind in FILES.items():
            rows = read_rows(self.raw_dir / f"{YEAR}/{name}")
            head = next(rows)
            ix = {k: head.index(k) for k in head if k}
            for r in rows:
                if not r or not r[0]:
                    continue
                r = list(r) + [None] * (len(head) - len(r))
                o, d = r[ix["ORIG_NUTS2016"]], r[ix["DEST_NUTS2016"]]
                names.setdefault(o, r[ix["ORIG_NUTS2016_LIBELLE"]])
                names.setdefault(d, r[ix["DEST_NUTS2016_LIBELLE"]])
                for code, lon_k, lat_k in ((o, "ORIG_NUTS2016_longitude", "ORIG_NUTS2016_latitude"),
                                           (d, "DEST_NUTS2016_longitude", "DEST_NUTS2016_latitude")):
                    lon, lat = _num(r[ix[lon_k]]), _num(r[ix[lat_k]])
                    if lon is not None and lat is not None:
                        centres.setdefault(code, (round(lon, 4), round(lat, 4)))
                f = flows.setdefault((o, d), {})
                if kind == "road":
                    f["road_tkm"] = (f.get("road_tkm") or 0.0) + (_num(r[ix["TKM"]]) or 0.0)
                elif kind == "rail_t":
                    v = _num(r[ix["KTONNES"]])
                    if v is None:
                        withheld["rail_t"] += 1
                    f["rail_t"] = None if v is None else v * 1000
                elif kind == "rail_tkm":
                    v = _num(r[ix["MTKM"]])
                    if v is None:
                        withheld["rail_tkm"] += 1
                    f["rail_tkm"] = None if v is None else v * 1e6
                else:  # water: one row per flag (pavillon); sum them
                    t, tkm = _num(r[ix["TONNES"]]), _num(r[ix["TKM"]])
                    f["water_t"] = (f.get("water_t") or 0.0) + (t or 0.0)
                    f["water_tkm"] = (f.get("water_tkm") or 0.0) + (tkm or 0.0)
        out = [{"o": o, "d": d, **{k: (round(v, 1) if isinstance(v, float) else v) for k, v in f.items()}}
               for (o, d), f in sorted(flows.items())]
        print(f"    {len(out)} region pairs; rail values withheld: {withheld}")
        return {
            "vintage": f"Flux nationaux de marchandises {YEAR} (route, rail, voie d'eau)",
            "_files": [f"{YEAR}/{n}" for n in FILES],
            "year": YEAR,
            "names": names,
            "centres": {k: list(v) for k, v in centres.items()},
            "flows": out,
            "withheld": withheld,
        }
