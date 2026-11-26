import io
import zipfile

from ..core.source import Source, SourceInfo
from ..core.xlsx import read_rows

YEAR = 2026
URL = f"https://www.insee.fr/fr/statistiques/fichier/4803954/AAV2020_au_01-01-{YEAR}.zip"
FILE = f"AAV2020_au_01-01-{YEAR}.zip"
# CATEAAV2020: 11 commune-centre, 12 other commune of the main pole, 13 commune of a secondary pole,
# 20 commune of the ring (couronne), 30 outside any area.
CATEGORIES = {"11": "Commune-centre", "12": "Autre commune du pôle principal", "13": "Commune d'un pôle secondaire",
              "20": "Commune de la couronne", "30": "Commune hors attraction des villes"}
# TAAV2017: size band of the area (population 2017).
BANDS = {"0": "Hors attraction des villes", "1": "Moins de 50 000 habitants", "2": "50 000 à 200 000 habitants",
         "3": "200 000 à 700 000 habitants", "4": "700 000 habitants ou plus (hors Paris)", "5": "Aire de Paris"}


class InseeAav(Source):
    info = SourceInfo(
        id="insee_aav",
        title=f"Aires d'attraction des villes 2020, composition communale au 1er janvier {YEAR}",
        publisher="Insee",
        homepage="https://www.insee.fr/fr/information/4803954",
        license="Licence Ouverte 2.0 (Etalab)",
        description="Les 699 aires d'attraction des villes : un pôle de population et d'emploi et sa couronne, les "
        "communes dont au moins 15 % des actifs travaillent dans le pôle. Ce sont les villes de la carte, l'équivalent "
        "français des aires métropolitaines américaines, chacune posée sur sa commune-centre.",
        used_for=["Villes de la carte", "Communes de chaque aire", "Commune-centre"],
    )

    def fetch(self, force=False):
        self.download(URL, FILE, force=force, expect_binary=True)

    def process(self):
        with zipfile.ZipFile(self.raw_dir / FILE) as z:
            book = io.BytesIO(z.read(z.namelist()[0]))
        areas, communes = {}, []
        header = None
        for row in read_rows(book, "AAV2020"):
            if row and row[0] == "AAV2020":
                header = row
                continue
            if header and row and row[0] and row[0] != "000":
                areas[row[0]] = {"code": row[0], "name": row[1], "band": row[2], "band_detail": row[3],
                                 "communes": int(row[4])}
        book.seek(0)
        header = None
        for row in read_rows(book, "Composition_communale"):
            if row and row[0] == "CODGEO":
                header = row
                continue
            if header and row and row[0]:
                communes.append({"code": row[0], "name": row[1], "aav": row[2], "cat": row[4], "dep": row[5],
                                 "region": row[6]})
        print(f"    {len(areas)} aires, {len(communes)} communes")
        return {
            "vintage": f"AAV 2020, géographie au 1er janvier {YEAR}",
            "_files": [FILE],
            "areas": areas,
            "communes": communes,
            "categories": CATEGORIES,
            "bands": BANDS,
        }
