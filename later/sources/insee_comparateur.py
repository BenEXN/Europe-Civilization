import csv
import io
import zipfile

from ..core.source import Source, SourceInfo

URL = "https://www.insee.fr/fr/statistiques/fichier/2521169/comparateur_csv.zip"
FILE = "comparateur_csv.zip"
LEVELS = {"COM", "EPCI", "AAV2020", "DEP", "REG", "FRANCE"}
# Measures kept, as MEASURE → short key; the year is appended (POP_2023, MED_SL_2023...).
MEASURES = {
    "POP": "POP", "SUP": "SUP", "MED_SL": "MED_SL", "PR_MD60": "PR_MD60", "NBEMP_EMPFORM_2": "SAL",
    "DWELLINGS": "LOG", "DWELLINGS_OCS_DW_MAIN": "RP", "DWELLINGS_OCS_DW_MAIN_TSH_100": "RP_PROP",
    "DWELLINGS_OCS_DW_SEC_DW_OCC": "RSEC", "DWELLINGS_OCS_DW_VAC": "LVAC", "LVB": "NAIS", "DTH": "DECES",
    "POP_AGE_Y15T64": "POP15_64", "UNIT_LOC": "ETAB",
}


class InseeComparateur(Source):
    info = SourceInfo(
        id="insee_comparateur",
        title="Base du comparateur de territoires (recensement 2023, Filosofi 2023, état civil)",
        publisher="Insee",
        homepage="https://www.insee.fr/fr/statistiques/2521169",
        license="Licence Ouverte 2.0 (Etalab)",
        description="Les principaux indicateurs de chaque commune, intercommunalité, aire d'attraction, département et "
        "région : population de 1968 à 2023 (recensement), superficie, niveau de vie médian et taux de pauvreté "
        "(Filosofi), emplois salariés, logements (résidences principales, propriétaires, résidences secondaires, "
        "vacants), naissances et décès.",
        used_for=["Population et croissance des villes et départements", "Niveau de vie, pauvreté",
                  "Lentilles : densité, croissance, logement"],
    )

    def fetch(self, force=False):
        self.download(URL, FILE, force=force, expect_binary=True)

    def process(self):
        out: dict[str, dict[str, dict]] = {lv: {} for lv in LEVELS}
        geo_ref = None
        with zipfile.ZipFile(self.raw_dir / FILE) as z:
            name = next(n for n in z.namelist() if n.endswith(".csv") and "metadata" not in n)
            with z.open(name) as f:
                rows = csv.reader(io.TextIOWrapper(f, encoding="utf-8"), delimiter=";")
                head = next(rows)
                ix = {k: head.index(k) for k in ("GEO_REF", "GEO_OBJECT", "GEO", "TIME_PERIOD", "TAB_MEASURE", "OBS_VALUE")}
                for r in rows:
                    lv = r[ix["GEO_OBJECT"]]
                    if lv not in LEVELS:
                        continue
                    key = MEASURES.get(r[ix["TAB_MEASURE"]])
                    if key is None or r[ix["OBS_VALUE"]] in ("", "NA"):
                        continue
                    geo_ref = geo_ref or r[ix["GEO_REF"]]
                    v = float(r[ix["OBS_VALUE"]])
                    out[lv].setdefault(r[ix["GEO"]], {})[f"{key}_{r[ix['TIME_PERIOD']]}"] = int(v) if v.is_integer() else v
        print("    " + ", ".join(f"{lv} {len(g)}" for lv, g in out.items()))
        return {
            "vintage": f"Comparateur de territoires, géographie {geo_ref}",
            "_files": [FILE],
            "geo_ref": geo_ref,
            "levels": out,
        }
