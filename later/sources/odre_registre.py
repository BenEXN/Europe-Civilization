from ..core.source import Source, SourceInfo

DATASET = "registre-national-installation-production-stockage-electricite-agrege"
FIELDS = ("nominstallation,codeinseecommune,codeinseecommuneimplantation,codefiliere,filiere,codetechnologie,"
          "technologie,combustible,typestockage,puismaxinstallee,puismaxinstalleedischarge,regime,"
          "datemiseenservice_date,nbgroupes,codedepartement")
MIN_KW = 5000
URL = (f"https://odre.opendatasoft.com/api/explore/v2.1/catalog/datasets/{DATASET}/exports/json"
       f"?select={FIELDS}&where=puismaxinstallee%3E%3D{MIN_KW}%20or%20puismaxinstalleedischarge%3E%3D{MIN_KW}")
FILE = f"{DATASET}_ge{MIN_KW}kW.json"


class OdreRegistre(Source):
    info = SourceInfo(
        id="odre_registre",
        title="Registre national des installations de production et de stockage d'électricité",
        publisher="RTE, Enedis et les gestionnaires de réseaux, via Open Data Réseaux Énergies (ODRÉ)",
        homepage=f"https://odre.opendatasoft.com/explore/dataset/{DATASET}/",
        license="Licence Ouverte 2.0 (Etalab)",
        description=f"Chaque installation raccordée d'au moins {MIN_KW // 1000} MW : filière, technologie, puissance "
        "maximale installée, commune d'implantation et régime (en service ou non). Les petites installations sont "
        "agrégées par commune dans le registre et ne sont pas lues ici.",
        used_for=["Centrales nucléaires, barrages, centrales thermiques", "Parcs éoliens et solaires", "Batteries"],
    )

    def fetch(self, force=False):
        self.download(URL, FILE, force=force)

    def process(self):
        import json

        rows = json.loads((self.raw_dir / FILE).read_text())
        out = []
        for r in rows:
            commune = r.get("codeinseecommuneimplantation") or r.get("codeinseecommune")
            if not commune or commune.startswith("97") or commune.startswith("98"):
                continue
            out.append({
                "name": r["nominstallation"], "commune": commune, "filiere": r["codefiliere"],
                "techno": r.get("technologie"), "fuel": r.get("combustible"),
                "kw": max(r.get("puismaxinstallee") or 0, r.get("puismaxinstalleedischarge") or 0),
                "status": r.get("regime"), "since": (r.get("datemiseenservice_date") or "")[:4] or None,
                "units": r.get("nbgroupes"),
            })
        print(f"    {len(out)} installations of {MIN_KW // 1000} MW or more in metropolitan France")
        return {"vintage": "Registre ODRÉ (dernière édition)", "_files": [FILE], "plants": out}
