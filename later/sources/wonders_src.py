"""Wonder candidates: UNESCO World Heritage sites and national parks (Wikidata), a few landmarks named by this
project (positions from Wikidata), universities by enrolment (French ministry of higher education) and museums by
attendance (French ministry of culture)."""

from __future__ import annotations

import csv
import io
import json
import re
import urllib.parse

from ..core.source import Source, SourceInfo

SPARQL = "https://query.wikidata.org/sparql?format=json&query="
API = "https://www.wikidata.org/w/api.php?"
BBOX = (-5.5, 41.2, 9.8, 51.3)

Q_UNESCO = """SELECT ?item ?itemLabel ?whs ?coord ?year ?links WHERE {
  ?item wdt:P757 ?whs; wdt:P17 wd:Q142; wdt:P625 ?coord; wikibase:sitelinks ?links.
  OPTIONAL { ?item p:P1435 ?st. ?st ps:P1435 wd:Q9259. OPTIONAL { ?st pq:P580 ?d. BIND(YEAR(?d) AS ?year) } }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "fr,en". }
}"""
Q_PARKS = """SELECT ?item ?itemLabel ?coord ?area ?year ?links WHERE {
  ?item wdt:P31 wd:Q46169; wdt:P17 wd:Q142; wdt:P625 ?coord; wikibase:sitelinks ?links.
  OPTIONAL { ?item wdt:P2046 ?area }
  OPTIONAL { ?item wdt:P571 ?d. BIND(YEAR(?d) AS ?year) }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "fr,en". }
}"""
# Landmarks this project names by hand (no rule picks them): the French label of their Wikidata item.
# Landmarks this project names by hand (no rule picks them): the French label of their Wikidata item.
LANDMARKS = ["tour Eiffel", "viaduc de Millau", "dune du Pilat", "gorges du Verdon", "mont Blanc",
             "falaises d'Étretat", "pont de Normandie", "château de Chenonceau"]
API_PAUSE_S = 3  # between uncached entity-API requests (Wikidata rate-limits bursts)

MESR = "https://data.enseignementsup-recherche.gouv.fr/api/explore/v2.1/catalog/datasets"
YEAR = "2024-25"
ENROL = (f"{MESR}/fr-esr-sise-effectifs-d-etudiants-inscrits-esr-public/records?"
         + urllib.parse.urlencode({
             "select": "etablissement_id_paysage, etablissement_lib, sum(effectif) as n",
             "where": f"annee_universitaire='{YEAR}' and etablissement_type='Université'",
             "group_by": "etablissement_id_paysage, etablissement_lib", "order_by": "n desc", "limit": 100}))
PLACES = (f"{MESR}/fr-esr-principaux-etablissements-enseignement-superieur/exports/json?"
          + urllib.parse.urlencode({"select": "etablissement_id_paysage, uo_lib, nom_court, coordonnees, com_code, com_nom"}))


def _point(wkt: str) -> tuple[float, float]:
    lon, lat = map(float, re.findall(r"[-\d.]+(?:e-?\d+)?", wkt)[:2])
    return lon, lat


def _inside(lon, lat) -> bool:
    return BBOX[0] <= lon <= BBOX[2] and BBOX[1] <= lat <= BBOX[3]


class WikidataWonders(Source):
    info = SourceInfo(
        id="wikidata_wonders",
        title="Patrimoine mondial de l'UNESCO, parcs nationaux et monuments (Wikidata)",
        publisher="Wikidata (d'après la liste du patrimoine mondial de l'UNESCO et les parcs nationaux de France)",
        homepage="https://www.wikidata.org/",
        license="CC0 1.0 (domaine public)",
        description="Les biens du patrimoine mondial situés en France métropolitaine (identifiant UNESCO, année "
        "d'inscription, position), les parcs nationaux (superficie, création) et la position de quelques monuments "
        "choisis par ce projet.",
        used_for=["Merveilles : patrimoine mondial, parcs nationaux, monuments"],
    )

    def fetch(self, force=False):
        hdr = {"Accept": "application/sparql-results+json"}
        self.download(SPARQL + urllib.parse.quote(Q_UNESCO), "unesco.json", force=force, headers=hdr)
        self.download(SPARQL + urllib.parse.quote(Q_PARKS), "parks.json", force=force, headers=hdr)
        # Landmarks through the entity API (the query service is often rate-limited): the first search hit that has
        # coordinates, then its entity record. Uncached requests are spaced out; a refused one is retried once after a
        # long pause, and a landmark still refused is left for the next fetch (the others go on).
        for label in LANDMARKS:
            slug = re.sub(r"\W+", "_", label.lower())
            search = f"landmarks/search_{slug}.json"
            ok = self._polite(API + urllib.parse.urlencode({"action": "wbsearchentities", "search": label,
                                                             "language": "fr", "uselang": "fr", "format": "json",
                                                             "limit": 5}), search, force)
            if not ok:
                continue
            hits = json.loads((self.raw_dir / search).read_text())["search"]
            ids = "|".join(h["id"] for h in hits)
            if ids:
                self._polite(API + urllib.parse.urlencode({"action": "wbgetentities", "ids": ids,
                                                           "props": "claims|labels|sitelinks", "languages": "fr",
                                                           "format": "json"}), f"landmarks/entities_{slug}.json", force)

    def _polite(self, url: str, rel: str, force: bool) -> bool:
        import time
        import urllib.error

        if (self.raw_dir / rel).exists() and not force:
            return True
        for pause in (API_PAUSE_S, 60):
            time.sleep(pause)
            try:
                self.download(url, rel, force=force)
                return True
            except urllib.error.HTTPError as e:
                if e.code != 429:
                    raise
                print(f"    Wikidata refused {rel} (429), pausing")
        return False

    def _rows(self, name):
        return json.loads((self.raw_dir / name).read_text())["results"]["bindings"]

    def process(self):
        sites: dict[str, dict] = {}
        for b in self._rows("unesco.json"):
            whs = b["whs"]["value"]
            m = re.fullmatch(r"(\d+)(bis|ter|quater|rev)?", whs)
            if not m:
                continue  # a component of a serial property (1283-005)
            lon, lat = _point(b["coord"]["value"])
            if not _inside(lon, lat):
                continue
            base = m.group(1)
            row = {"id": base, "qid": b["item"]["value"].rsplit("/", 1)[-1], "name": b["itemLabel"]["value"],
                   "lon": lon, "lat": lat, "year": int(b["year"]["value"]) if "year" in b else None,
                   "links": int(b["links"]["value"])}
            if base not in sites or row["links"] > sites[base]["links"]:
                sites[base] = row
        parks: dict[str, dict] = {}
        for b in self._rows("parks.json"):
            lon, lat = _point(b["coord"]["value"])
            if not _inside(lon, lat):
                continue
            qid = b["item"]["value"].rsplit("/", 1)[-1]
            parks.setdefault(qid, {"qid": qid, "name": b["itemLabel"]["value"], "lon": lon, "lat": lat,
                                   "area_km2": float(b["area"]["value"]) if "area" in b else None,
                                   "year": int(b["year"]["value"]) if "year" in b else None,
                                   "links": int(b["links"]["value"])})
        marks: dict[str, dict] = {}
        for label in LANDMARKS:
            slug = re.sub(r"\W+", "_", label.lower())
            path = self.raw_dir / f"landmarks/entities_{slug}.json"
            if not path.exists():
                continue
            ents = json.loads(path.read_text()).get("entities", {})
            order = [h["id"] for h in json.loads((self.raw_dir / f"landmarks/search_{slug}.json").read_text())["search"]]
            for qid in order:
                e = ents.get(qid, {})
                coord = (e.get("claims", {}).get("P625") or [{}])[0].get("mainsnak", {}).get("datavalue", {}).get("value")
                if not coord or not _inside(coord["longitude"], coord["latitude"]):
                    continue
                marks[label] = {"qid": qid, "name": label, "lon": coord["longitude"], "lat": coord["latitude"],
                                "links": len(e.get("sitelinks", {}))}
                break
        print(f"    {len(sites)} World Heritage sites, {len(parks)} national parks, {len(marks)} landmarks")
        return {"vintage": "Wikidata", "_files": ["unesco.json", "parks.json"],
                "unesco": sorted(sites.values(), key=lambda s: int(s["id"])), "parks": list(parks.values()),
                "landmarks": [marks[l] for l in LANDMARKS if l in marks]}


class Universities(Source):
    info = SourceInfo(
        id="universities",
        title=f"Effectifs d'étudiants des universités ({YEAR}) et implantations",
        publisher="Ministère de l'Enseignement supérieur et de la Recherche (SIES)",
        homepage="https://data.enseignementsup-recherche.gouv.fr/explore/dataset/fr-esr-sise-effectifs-d-etudiants-inscrits-esr-public/",
        license="Licence Ouverte 2.0 (Etalab)",
        description=f"Étudiants inscrits dans chaque université publique en {YEAR} (système d'information SISE), "
        "placés au siège de l'université (répertoire des principaux établissements).",
        used_for=["Merveilles : grandes universités", "Conseiller du savoir"],
    )

    def fetch(self, force=False):
        self.download(ENROL, f"enrolment_{YEAR}.json", force=force)
        self.download(PLACES, "etablissements.json", force=force)

    def process(self):
        enrol = json.loads((self.raw_dir / f"enrolment_{YEAR}.json").read_text())["results"]
        places = {p["etablissement_id_paysage"]: p for p in json.loads((self.raw_dir / "etablissements.json").read_text())}
        out = []
        for r in enrol:
            p = places.get(r["etablissement_id_paysage"])
            if not p or not p.get("coordonnees"):
                continue
            lon, lat = p["coordonnees"]["lon"], p["coordonnees"]["lat"]
            if not _inside(lon, lat):
                continue
            out.append({"id": r["etablissement_id_paysage"], "name": r["etablissement_lib"],
                        "short": p.get("nom_court") or None, "students": round(r["n"]), "commune": p.get("com_code"),
                        "lon": lon, "lat": lat})
        print(f"    {len(out)} universities placed")
        return {"vintage": f"SISE {YEAR}", "_files": [f"enrolment_{YEAR}.json", "etablissements.json"],
                "year": YEAR, "universities": out}


FREQ_MUSEES = "https://ministere-culture.s3.sbg.io.cloud.ovh.net/FREQ_MUSEES/ENTREES_ET_CATEGORIES_DE_PUBLIC.csv"
MUSEOFILE = "https://ministere-culture.s3.sbg.io.cloud.ovh.net/POP/museofile.csv"


class Museums(Source):
    info = SourceInfo(
        id="museums",
        title="Fréquentation des musées de France et répertoire Muséofile",
        publisher="Ministère de la Culture (service des musées de France)",
        homepage="https://www.data.gouv.fr/fr/datasets/frequentation-des-musees-de-france/",
        license="Licence Ouverte 2.0 (Etalab)",
        description="Entrées annuelles (payantes et gratuites) de chaque musée labellisé « musée de France », placées "
        "avec les coordonnées du répertoire Muséofile. Les musées les plus visités deviennent des merveilles.",
        used_for=["Merveilles : musées les plus visités"],
    )

    def fetch(self, force=False):
        self.download(FREQ_MUSEES, "frequentation_musees.csv", force=force)
        self.download(MUSEOFILE, "museofile.csv", force=force)

    def process(self):
        freq = list(csv.DictReader(io.StringIO((self.raw_dir / "frequentation_musees.csv").read_text(encoding="utf-8-sig")),
                                   delimiter=";"))
        files = list(csv.DictReader(io.StringIO((self.raw_dir / "museofile.csv").read_text(encoding="utf-8-sig")),
                                    delimiter="|"))
        place = {}
        for m in files:
            try:
                lat, lon = (float(v) for v in (m.get("Coordonnees") or "").split(","))
            except ValueError:
                continue
            place[m["Identifiant"]] = {"name": m["Nom_officiel"], "city": m["Ville"], "lon": lon, "lat": lat}
        # The latest year with nearly as many museums reporting as the year before (a fresh year can be partial).
        counts: dict[str, int] = {}
        for r in freq:
            if r["annee"] and r["total"]:
                counts[r["annee"]] = counts.get(r["annee"], 0) + 1
        years = sorted(counts, reverse=True)
        year = next(y for k, y in enumerate(years) if k + 1 >= len(years) or counts[y] >= 0.9 * counts[years[k + 1]])
        best: dict[str, dict] = {}
        for r in freq:
            if r["annee"] != year or not r["total"]:
                continue
            key = r["IDMuseofile"] or f"{r['codeInseeCommune']}:{r['nom_du_musee']}"
            visits = int(float(r["total"]))
            if key in best and best[key]["visits"] >= visits:
                continue  # the file repeats some museums: keep the larger count
            p = place.get(r["IDMuseofile"], {})
            best[key] = {"id": r["IDMuseofile"] or None, "name": r["nom_du_musee"] or p.get("name") or "",
                         "city": r["ville"], "commune": r["codeInseeCommune"], "visits": visits,
                         "lon": p.get("lon"), "lat": p.get("lat")}
        museums = sorted(best.values(), key=lambda m: -m["visits"])
        museums = [m for m in museums if not (m["commune"] or "").startswith(("97", "98"))][:80]
        print(f"    {len(museums)} museums kept from {year} (of {counts[year]} reporting); "
              f"{sum(1 for m in museums if m['lon'] is None)} without coordinates")
        return {"vintage": f"Fréquentation des musées de France {year}", "_files": ["frequentation_musees.csv", "museofile.csv"],
                "year": int(year), "museums": museums}
