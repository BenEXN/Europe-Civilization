"""Version anglaise du rapport d'étape (English version of the progress report).

Exécute rapport_etape.py avec les textes anglais de rapport_etape_en.json : la mise en page, les tableaux et les
figures sont ceux du rapport français ; les nombres des cellules sont convertis au format anglais. Les traductions
correspondent au lot de la version 1.6 : si un texte français n'a pas de traduction, la génération s'arrête et le liste.

Écrit calibration/Calibration_progress_report_EH_2026-11-28_v1.6_EN.pdf.
"""
import json
import re
import sys
from pathlib import Path

import reportlab.platypus as rp
import reportlab.platypus.paragraph as rpp

ICI = Path(__file__).resolve().parent
SOURCE = ICI / "rapport_etape.py"
EN = json.loads((ICI / "rapport_etape_en.json").read_text(encoding="utf-8"))
MANQUANTS = []


def nombre(t):
    """Cellule sans texte : virgule décimale -> point, espaces de milliers -> virgules, € et % au format anglais."""
    t = re.sub(r"(\d),(\d)", r"\1.\2", t)
    while re.search(r"(\d)[   ](\d{3})(?!\d)", t):
        t = re.sub(r"(\d)[   ](\d{3})(?!\d)", r"\1,\2", t)
    t = re.sub(r"^(−?[\d.,]+) €$", r"€\1", t)
    t = re.sub(r"(\d) %", r"\1%", t)
    return t


class Paragraphe(rpp.Paragraph):
    def __init__(self, text, *a, **k):
        if isinstance(text, str):
            if text in EN:
                text = EN[text]
            elif "drawTOCEntryEnd" in text or text.startswith("Placeholder for table of contents"):
                pass  # entrées du sommaire, construites à partir des titres déjà traduits
            elif not re.search(r"[A-Za-zÀ-ÿ]{2,}", re.sub(r"<[^>]+>", "", text)):
                text = nombre(text)
            else:
                MANQUANTS.append(text)
        super().__init__(text, *a, **k)


rp.Paragraph = Paragraphe
rpp.Paragraph = Paragraphe

src = SOURCE.read_text(encoding="utf-8")
REMPLACEMENTS = [
    ('SORTIE = ICI.parent / "Rapport_etape_calibration_EH_2026-11-28_v1.6.pdf"',
     'SORTIE = ICI.parent / "Calibration_progress_report_EH_2026-11-28_v1.6_EN.pdf"'),
    ('PIED = f"Calibration empirique de l\'Économie Homéostatique — rapport d\'étape v{VERSION}, {DATE}"',
     'PIED = f"Empirical calibration of Homeostatic Economics — progress report v{VERSION}, 28 November 2026 — English translation"'),
    ('title=f"Calibration empirique de l\'Économie Homéostatique — rapport "\n                         f"d\'étape v{VERSION}"',
     'title=f"Empirical calibration of Homeostatic Economics — progress report v{VERSION} (English translation)"'),
    ('if texte != "Sommaire":', 'if texte != "Contents":'),
]
for a, b in REMPLACEMENTS:
    if src.count(a) != 1:
        sys.exit(f"Structure de rapport_etape.py inattendue : {a[:60]}")
    src = src.replace(a, b)

espace = {"__name__": "__main__", "__file__": str(SOURCE)}
exec(compile(src, str(SOURCE), "exec"), espace)
if MANQUANTS:
    print(f"{len(MANQUANTS)} texte(s) sans traduction :")
    for t in dict.fromkeys(MANQUANTS):
        print(" -", t[:120])
    sys.exit(1)
