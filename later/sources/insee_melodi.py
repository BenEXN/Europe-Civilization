"""Census (recensement de la population 2023) tables from the Insee Melodi catalogue.

Each dataset is one zipped CSV with every geographic level; we keep the levels the map uses and one or two
dimensions, as {level: {geo code: {key: value}}}.
"""

from __future__ import annotations

import csv
import io
import zipfile

from ..core.source import Source, SourceInfo

BASE = "https://api.insee.fr/melodi/file/{ds}/{ds}_{year}_CSV_FR"
LEVELS = ("EPCI", "AAV2020", "DEP", "REG", "FRANCE")
YEAR = 2023
LICENSE = "Licence Ouverte 2.0 (Etalab)"
PUBLISHER = "Insee, recensement de la population 2023 (catalogue Melodi)"


class _Melodi(Source):
    DS: str
    LEVELS = LEVELS

    @property
    def file(self):
        return f"{self.DS}_{YEAR}_CSV_FR.zip"

    def fetch(self, force=False):
        self.download(BASE.format(ds=self.DS, year=YEAR), self.file, force=force, expect_binary=True)

    def keep(self, r: dict) -> str | None:
        """The key a row is stored under, or None to skip it."""
        raise NotImplementedError

    def process(self):
        out: dict[str, dict[str, dict]] = {lv: {} for lv in self.LEVELS}
        with zipfile.ZipFile(self.raw_dir / self.file) as z:
            name = next(n for n in z.namelist() if n.endswith(".csv") and "metadata" not in n)
            with z.open(name) as f:
                rows = csv.reader(io.TextIOWrapper(f, encoding="utf-8"), delimiter=";")
                head = next(rows)
                for vals in rows:
                    r = dict(zip(head, vals))
                    lv = r["GEO_OBJECT"]
                    if lv not in out or r["OBS_VALUE"] in ("", "NA"):
                        continue
                    key = self.keep(r)
                    if key is None:
                        continue
                    out[lv].setdefault(r["GEO"], {})[key] = round(float(r["OBS_VALUE"]), 1)
        print("    " + ", ".join(f"{lv} {len(g)}" for lv, g in out.items()))
        return {"vintage": f"Recensement de la population {YEAR}", "_files": [self.file], "levels": out}


class InseeEmploiActivite(_Melodi):
    DS = "DS_RP_TD_EMPLOI_LT_EMPFORMACTIVITY_COMP"
    LEVELS = ("COM",) + LEVELS
    info = SourceInfo(
        id="insee_emploi",
        title=f"Emploi au lieu de travail selon l'activité économique (recensement {YEAR}, EMP2)",
        publisher=PUBLISHER,
        homepage="https://catalogue-donnees.insee.fr/fr/catalogue/recherche/DS_RP_TD_EMPLOI_LT_EMPFORMACTIVITY_COMP",
        license=LICENSE,
        description="Les emplois (salariés et non salariés, agriculteurs et indépendants compris) comptés là où l'on "
        "travaille, en 38 secteurs d'activité (NAF A38), pour chaque commune, intercommunalité, aire d'attraction et "
        "département. Ils font les rendements Nourriture, Production, Science et Culture, et répartissent le PIB "
        "départemental entre les villes.",
        used_for=["Rendements des villes (Nourriture, Production, Science, Culture)", "Emplois par secteur",
                  "Partage du PIB entre villes"],
    )

    def keep(self, r):
        if r["SEX"] != "_T" or r["EMPFORM"] != "_T":
            return None
        return r["EMP_ACTIVITY"]


class InseeDiplomes(_Melodi):
    DS = "DS_RP_DIPLOMES_PRINC"
    info = SourceInfo(
        id="insee_diplomes",
        title=f"Diplômes et formation (recensement {YEAR})",
        publisher=PUBLISHER,
        homepage="https://catalogue-donnees.insee.fr/fr/catalogue/recherche/DS_RP_DIPLOMES_PRINC",
        license=LICENSE,
        description="Population non scolarisée de 15 ans ou plus selon le diplôme le plus élevé.",
        used_for=["Lentille Diplômés du supérieur", "Panneaux des villes et départements"],
    )

    def keep(self, r):
        if r["SEX"] != "_T" or r["AGE"] != "Y_GE15" or r["TIME_PERIOD"] != str(YEAR):
            return None
        return r["EDUC"]


class InseePopulationAge(_Melodi):
    DS = "DS_RP_POPULATION_PRINC"
    info = SourceInfo(
        id="insee_population",
        title=f"Population par âge (recensement {YEAR})",
        publisher=PUBLISHER,
        homepage="https://catalogue-donnees.insee.fr/fr/catalogue/recherche/DS_RP_POPULATION_PRINC",
        license=LICENSE,
        description="Population par grandes tranches d'âge.",
        used_for=["Lentilles Jeunes et Seniors", "Panneaux des villes"],
    )

    def keep(self, r):
        if r["SEX"] != "_T" or r["TIME_PERIOD"] != str(YEAR) or r["RP_MEASURE"] != "POP":
            return None
        return r["AGE"]


class InseeActivite(_Melodi):
    DS = "DS_RP_EMPLOI_LR_PRINC"
    info = SourceInfo(
        id="insee_activite",
        title=f"Population active et chômage (recensement {YEAR})",
        publisher=PUBLISHER,
        homepage="https://catalogue-donnees.insee.fr/fr/catalogue/recherche/DS_RP_EMPLOI_LR_PRINC",
        license=LICENSE,
        description="Actifs, actifs occupés et chômeurs de 15 à 64 ans, au lieu de résidence (au sens du recensement).",
        used_for=["Taux de chômage des villes et départements", "Lentille Chômage"],
    )

    def keep(self, r):
        if r.get("SEX", "_T") != "_T" or r["TIME_PERIOD"] != str(YEAR):
            return None
        dims = [f"{k}={v}" for k, v in r.items() if k not in ("GEO", "GEO_OBJECT", "SEX", "FREQ", "OBS_STATUS",
                                                             "TIME_PERIOD", "OBS_VALUE") and v != "_T"]
        return "|".join(dims) or "_T"


def _all_dims(r: dict) -> str | None:
    if r.get("SEX", "_T") != "_T" or r.get("TIME_PERIOD") != str(YEAR):
        return None
    dims = [f"{k}={v}" for k, v in r.items() if k not in ("GEO", "GEO_OBJECT", "SEX", "FREQ", "OBS_STATUS",
                                                         "TIME_PERIOD", "OBS_VALUE") and v != "_T"]
    return "|".join(dims) or "_T"


class InseePcsActivite(_Melodi):
    DS = "DS_RP_TD_ACTIVITE_PCSACTIVITY_COMP"
    LEVELS = ("AAV2020", "FRANCE")
    info = SourceInfo(
        id="insee_pcs",
        title=f"Population active selon la catégorie socioprofessionnelle et l'activité (recensement {YEAR}, ACT4-ACT5)",
        publisher=PUBLISHER,
        homepage="https://catalogue-donnees.insee.fr/fr/catalogue/recherche/DS_RP_TD_ACTIVITE_PCSACTIVITY_COMP",
        license=LICENSE,
        description="Actifs occupés selon leur catégorie socioprofessionnelle et le secteur de leur employeur, au lieu "
        "de résidence. Ils donnent la rangée « Métiers » des citoyens de chaque ville.",
        used_for=["Citoyens : métiers"],
    )
    keep = staticmethod(_all_dims)



class InseeNavettes(_Melodi):
    DS = "DS_RP_NAVETTES_PRINC"
    LEVELS = ("EPCI", "AAV2020", "DEP", "FRANCE")
    info = SourceInfo(
        id="insee_navettes",
        title=f"Déplacements domicile-travail (recensement {YEAR})",
        publisher=PUBLISHER,
        homepage="https://catalogue-donnees.insee.fr/fr/catalogue/recherche/DS_RP_NAVETTES_PRINC",
        license=LICENSE,
        description="Actifs occupés selon le mode de transport principal pour aller travailler et le lieu de travail.",
        used_for=["Citoyens : trajets domicile-travail", "Lentilles Voiture et Transports en commun"],
    )
    keep = staticmethod(_all_dims)


class InseeImmigration(_Melodi):
    DS = "DS_RP_TD_IMMI_AGESEXEMPSTA_PRINC"
    LEVELS = ("EPCI", "AAV2020", "DEP", "FRANCE")
    info = SourceInfo(
        id="insee_immigration",
        title=f"Population selon la situation quant à l'immigration (recensement {YEAR})",
        publisher=PUBLISHER,
        homepage="https://catalogue-donnees.insee.fr/fr/catalogue/recherche/DS_RP_TD_IMMI_AGESEXEMPSTA_PRINC",
        license=LICENSE,
        description="Habitants immigrés (nés étrangers à l'étranger) et non immigrés.",
        used_for=["Citoyens : origines", "Lentille Immigrés"],
    )
    keep = staticmethod(_all_dims)
