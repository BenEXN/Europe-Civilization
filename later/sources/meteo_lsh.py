"""Warming at Météo-France's stations: the homogenised long monthly series (LSH) of daily minimum and maximum
temperature, metropolitan France and overseas.

Homogenisation removes the breaks a series gets when a station moves or changes instruments, which is what a
trend needs (the Safran grid is not homogenised). The monthly mean is (TN + TX) / 2; a station's warming is its mean
over OLD minus its mean over RECENT, both fully homogenised thirty-year windows, each needing 27 complete years.
"""

from __future__ import annotations

import csv
import io
import zipfile

from ..core.source import Source, SourceInfo

BASE = "https://meteofrance.s3.sbg.io.cloud.ovh.net/data/synchro_ftp/REF_CC/LSH/"
ZIPS = {("TN", "metro"): "SH_TN_metropole.zip", ("TX", "metro"): "SH_TX_metropole.zip",
        ("TN", "om"): "SH_TN_Outremer.zip", ("TX", "om"): "SH_TX_Outremer.zip"}
OLD, RECENT = (1961, 1990), (1993, 2022)
MIN_YEARS = 27


def read_series(text: str) -> tuple[dict, dict]:
    """One LSH file → ({lat, lon, alt, name}, {(year, month): value}) for its homogenised months (Q_HOM = 1)."""
    meta, values = {}, {}
    lines = text.splitlines()
    k = 0
    for k, line in enumerate(lines):
        if not line.startswith("#"):
            break
        key, _, val = line[1:].partition("=")
        key = key.strip().upper()
        if key.startswith("LATITUDE"):
            meta["lat"] = float(val)
        elif key.startswith("LONGITUDE"):
            meta["lon"] = float(val)
        elif key.startswith("ALTITUDE"):
            meta["alt"] = float(val)
        elif key.startswith("NOM_USUEL"):
            meta["name"] = val.strip()
    for row in csv.DictReader(io.StringIO("\n".join(lines[k:])), delimiter=";"):
        if row.get("Q_HOM") == "1" and row.get("VALEUR") not in (None, ""):
            ym = row["YYYYMM"]
            values[(int(ym[:4]), int(ym[4:]))] = float(row["VALEUR"])
    return meta, values


class MeteoLsh(Source):
    info = SourceInfo(
        id="meteo_lsh",
        title="Longues séries homogénéisées de températures (Météo-France)",
        publisher="Météo-France",
        homepage="https://www.data.gouv.fr/datasets/donnees-changement-climatique-lsh-longues-series-homogeneisees",
        license="Licence Ouverte 2.0 (Etalab)",
        description="Températures minimales et maximales mensuelles de quelques centaines de stations, corrigées des "
        "ruptures (déplacement d'un poste, changement d'instrument) : la base qui convient pour mesurer une tendance. "
        f"Le réchauffement d'une station est l'écart entre ses moyennes {RECENT[0]}-{RECENT[1]} et {OLD[0]}-{OLD[1]} ; "
        "chaque hexagone prend la moyenne des stations voisines pondérée par l'inverse du carré de la distance.",
        used_for=["Lentille Réchauffement"],
    )

    def fetch(self, force=False):
        for name in ZIPS.values():
            self.download(BASE + name, name, force=force, expect_binary=True)

    def process(self):
        series: dict = {}  # (zone, station id) → {"meta", "TN", "TX"}
        for (var, zone), name in ZIPS.items():
            with zipfile.ZipFile(self.raw_dir / name) as z:
                for f in z.namelist():
                    if not f.lower().endswith(".csv"):
                        continue
                    meta, values = read_series(z.read(f).decode("latin-1"))
                    sid = f.split("/")[-1][6:-4]  # SH_MTN202320001.csv → 202320001 (shared by TN and TX)
                    s = series.setdefault((zone, sid), {"meta": meta})
                    s[var] = values

        def window_mean(tn, tx, period):
            years = []
            for y in range(period[0], period[1] + 1):
                months = [(tn[(y, m)] + tx[(y, m)]) / 2 for m in range(1, 13) if (y, m) in tn and (y, m) in tx]
                if len(months) == 12:
                    years.append(sum(months) / 12)
            return sum(years) / len(years) if len(years) >= MIN_YEARS else None

        stations = []
        for (zone, sid), s in sorted(series.items()):
            if "TN" not in s or "TX" not in s:
                continue
            old, recent = window_mean(s["TN"], s["TX"], OLD), window_mean(s["TN"], s["TX"], RECENT)
            if old is None or recent is None:
                continue
            m = s["meta"]
            stations.append({"name": m.get("name"), "lat": m["lat"], "lon": m["lon"], "alt": m.get("alt"), "zone": zone,
                             "t_old": round(old, 2), "t_recent": round(recent, 2), "warming": round(recent - old, 2)})
        metro = [s["warming"] for s in stations if s["zone"] == "metro"]
        print(f"    {len(stations)} stations with both windows; metropolitan mean warming "
              f"{sum(metro) / len(metro):+.2f} °C (min {min(metro):+.2f}, max {max(metro):+.2f})")
        return {"vintage": f"Météo-France LSH, {OLD[0]}-{OLD[1]} et {RECENT[0]}-{RECENT[1]}", "_files": list(ZIPS.values()),
                "old": OLD, "recent": RECENT, "stations": stations}
