"""Natural-disaster decrees by commune (GASPAR, CatNat) and the 2022 presidential second round by commune."""

from __future__ import annotations

import csv
import io
import zipfile
from collections import Counter, defaultdict

from ..core.source import Source, SourceInfo

GASPAR = "https://files.georisques.fr/GASPAR/gaspar.zip"
SINCE = "2000-01-01"
# GASPAR risk labels → the hazard families the map shows.
FAMILY = {
    "Inondations et/ou Coulées de Boue": "flood", "Inondations Remontée Nappe": "flood",
    "Inondations par choc mécanique des vagues": "sea", "Chocs Mécaniques liés à l'action des Vagues": "sea",
    "Submersion marine": "sea", "Sécheresse": "drought", "Mouvement de Terrain": "ground",
    "Glissement de Terrain": "ground", "Effondrement et/ou Affaisement": "ground", "Eboulement et/ou Chute de Blocs": "ground",
    "Affaissement minier": "ground", "Tempête": "storm", "Grêle": "storm", "Poids de la Neige": "storm",
    "Vents Cycloniques": "storm", "Secousse Sismique": "quake", "Avalanche": "avalanche",
}


class Catnat(Source):
    info = SourceInfo(
        id="catnat",
        title="Arrêtés de catastrophe naturelle par commune (base GASPAR)",
        publisher="Ministère de la Transition écologique, Géorisques",
        homepage="https://www.georisques.gouv.fr/donnees/bases-de-donnees/base-gaspar",
        license="Licence Ouverte 2.0 (Etalab)",
        description=f"Chaque reconnaissance de l'état de catastrophe naturelle (« CatNat ») publiée au Journal officiel "
        f"pour une commune, avec le type de risque. On compte les arrêtés distincts depuis le {SINCE[8:]}/"
        f"{SINCE[5:7]}/{SINCE[:4]} par commune et par famille de risque.",
        used_for=["Lentilles Catastrophes naturelles et Risque dominant"],
    )

    def fetch(self, force=False):
        self.download(GASPAR, "gaspar.zip", force=force, expect_binary=True)

    def process(self):
        with zipfile.ZipFile(self.raw_dir / "gaspar.zip") as z:
            name = next(n for n in z.namelist() if n.startswith("catnat_") and n.endswith(".csv"))
            raw = z.read(name)
        text = raw.decode("utf-8", errors="replace")
        counts: dict[str, set] = defaultdict(set)
        fam: dict[str, Counter] = defaultdict(Counter)
        unknown = Counter()
        for r in csv.DictReader(io.StringIO(text), delimiter=";"):
            if (r.get("date_debut") or "") < SINCE:
                continue
            com = r["code_commune"]
            key = (r["id_gaspar"], r["lib_risque_jo"])
            if key in counts[com]:
                continue
            counts[com].add(key)
            f = FAMILY.get(r["lib_risque_jo"])
            if f is None:
                unknown[r["lib_risque_jo"]] += 1
                f = "other"
            fam[com][f] += 1
        if unknown:
            print(f"    risk labels counted as 'other': {dict(unknown.most_common(6))}")
        print(f"    {sum(len(v) for v in counts.values())} decrees since {SINCE} in {len(counts)} communes")
        return {"vintage": f"GASPAR ({name.split('_')[-1][:10]}), arrêtés depuis {SINCE[:4]}", "_files": ["gaspar.zip"],
                "since": SINCE, "communes": {c: {"total": len(v), "by": dict(fam[c])} for c, v in counts.items()}}


PR2022 = ("https://static.data.gouv.fr/resources/election-presidentielle-des-10-et-24-avril-2022-resultats-definitifs-"
          "du-2nd-tour/20220428-142333/resultats-par-niveau-subcom-t2-france-entiere.txt")
DOM = {"ZA": "971", "ZB": "972", "ZC": "973", "ZD": "974", "ZM": "976"}


class Presidentielle2022(Source):
    info = SourceInfo(
        id="presidentielle_2022",
        title="Élection présidentielle 2022, résultats définitifs du second tour par commune",
        publisher="Ministère de l'Intérieur",
        homepage="https://www.data.gouv.fr/datasets/election-presidentielle-des-10-et-24-avril-2022-resultats-definitifs-du-2nd-tour",
        license="Licence Ouverte 2.0 (Etalab)",
        description="Inscrits, abstentions, votants, exprimés et voix de chaque candidat au second tour du 24 avril "
        "2022, pour chaque commune (géographie de 2022).",
        used_for=["Lentilles Présidentielle 2022 et Abstention"],
    )

    def fetch(self, force=False):
        self.download(PR2022, "pr2022_t2_communes.txt", force=force)

    def process(self):
        text = (self.raw_dir / "pr2022_t2_communes.txt").read_bytes().decode("latin-1")
        rows = csv.reader(io.StringIO(text), delimiter=";")
        head = next(rows)
        ix = {k: head.index(k) for k in ("Code du département", "Code de la commune", "Inscrits", "Abstentions", "Exprimés")}
        name_cols = [k for k, h in enumerate(head) if h == "Nom"]
        out = {}
        for r in rows:
            if not r or len(r) < len(head):
                continue
            dep = DOM.get(r[ix["Code du département"]], r[ix["Code du département"]])
            com = r[ix["Code de la commune"]]
            code = (dep + com[-2:]) if len(dep) == 3 else dep.zfill(2) + com.zfill(3)
            votes = {}
            k = name_cols[0]
            while k < len(r) and r[k]:
                votes[r[k]] = int(r[k + 2])  # Nom, Prénom, Voix
                k += 7
            out[code] = {"inscrits": int(r[ix["Inscrits"]]), "abstentions": int(r[ix["Abstentions"]]),
                         "exprimes": int(r[ix["Exprimés"]]), "voix": votes}
        print(f"    {len(out)} communes; candidates: {sorted({n for v in out.values() for n in v['voix']})}")
        return {"vintage": "Présidentielle 2022, 2nd tour (24 avril 2022)", "_files": ["pr2022_t2_communes.txt"],
                "communes": out}
