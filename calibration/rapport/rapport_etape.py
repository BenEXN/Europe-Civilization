"""Rapport d'étape de la calibration empirique de l'Économie Homéostatique (PDF).

  python3 calibration/rapport/rapport_etape.py

Écrit calibration/Rapport_etape_calibration_EH_2026-11-28_v1.6.pdf. Les figures sont dans calibration/rapport/figures/.
Les tableaux et chiffres des sections 6 et 9 sont lus dans calibration/sensibilite_ied.json et
calibration/ecodotations.json : ils suivent le lot de calibration enregistré.
Demande reportlab et les polices DejaVu (Sans, Serif, Math TeX Gyre)."""

from __future__ import annotations

import json
import math
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate, Frame, Image, KeepTogether, ListFlowable, ListItem, NextPageTemplate,
                                PageBreak, PageTemplate, Paragraph, Spacer, Table, TableStyle)
from reportlab.platypus.tableofcontents import TableOfContents

ICI = Path(__file__).resolve().parent
SORTIE = ICI.parent / "Rapport_etape_calibration_EH_2026-11-28_v1.6.pdf"
VERSION = "1.6"
DATE = "28 novembre 2026"
PIED = f"Calibration empirique de l'Économie Homéostatique — rapport d'étape v{VERSION}, {DATE}"
CAL = ICI.parent
SENS = json.loads((CAL / "sensibilite_ied.json").read_text())
ECO = json.loads((CAL / "ecodotations.json").read_text())
EVO = json.loads((CAL / "evolution_ied.json").read_text())
BETA = json.loads((CAL / "beta_pub.json").read_text())["data"]
LOT = json.loads((CAL / "provenance" / "lot.json").read_text())["lot"]   # réponses Eurostat des sections 4 à 9

# ----------------------------------------------------------------------------------------------- polices et styles

POLICES = Path("/usr/share/fonts/truetype/dejavu")
for nom, fichier in (("Sans", "DejaVuSans.ttf"), ("Sans-B", "DejaVuSans-Bold.ttf"), ("Sans-I", "DejaVuSans-Oblique.ttf"),
                     ("Sans-BI", "DejaVuSans-BoldOblique.ttf"), ("Serif", "DejaVuSerif.ttf"),
                     ("Serif-B", "DejaVuSerif-Bold.ttf"), ("Serif-I", "DejaVuSerif-Italic.ttf"),
                     ("Serif-BI", "DejaVuSerif-BoldItalic.ttf"), ("Math", "DejaVuMathTeXGyre.ttf")):
    pdfmetrics.registerFont(TTFont(nom, str(POLICES / fichier)))
pdfmetrics.registerFontFamily("Sans", normal="Sans", bold="Sans-B", italic="Sans-I", boldItalic="Sans-BI")
pdfmetrics.registerFontFamily("Serif", normal="Serif", bold="Serif-B", italic="Serif-I", boldItalic="Serif-BI")

ENCRE = colors.HexColor("#1f2a37")
VERT = colors.HexColor("#2f6b4f")
GRIS = colors.HexColor("#6b7280")
FOND = colors.HexColor("#eef3ef")
FILET = colors.HexColor("#c9d3cc")

S = {
    "titre": ParagraphStyle("titre", fontName="Sans-B", fontSize=21, leading=26, textColor=ENCRE),
    "soustitre": ParagraphStyle("soustitre", fontName="Sans", fontSize=12.5, leading=17, textColor=VERT, spaceBefore=10),
    "meta": ParagraphStyle("meta", fontName="Sans", fontSize=9, leading=13, textColor=GRIS),
    "h1": ParagraphStyle("h1", fontName="Sans-B", fontSize=14, leading=18, textColor=ENCRE, spaceBefore=16, spaceAfter=6,
                         keepWithNext=1),
    "h2": ParagraphStyle("h2", fontName="Sans-B", fontSize=11, leading=14, textColor=VERT, spaceBefore=10, spaceAfter=4,
                         keepWithNext=1),
    "p": ParagraphStyle("p", fontName="Serif", fontSize=9.5, leading=14, textColor=ENCRE, alignment=TA_JUSTIFY,
                        spaceAfter=6),
    "li": ParagraphStyle("li", fontName="Serif", fontSize=9.5, leading=14, textColor=ENCRE, alignment=TA_JUSTIFY),
    "cap": ParagraphStyle("cap", fontName="Sans-I", fontSize=7.8, leading=10.5, textColor=GRIS, spaceBefore=3,
                          spaceAfter=8),
    "cell": ParagraphStyle("cell", fontName="Sans", fontSize=8.2, leading=10.5, textColor=ENCRE),
    "cellb": ParagraphStyle("cellb", fontName="Sans-B", fontSize=8.2, leading=10.5, textColor=ENCRE),
    "ref": ParagraphStyle("ref", fontName="Serif", fontSize=9, leading=12.5, textColor=ENCRE, leftIndent=12,
                          firstLineIndent=-12, spaceAfter=4),
    "toc1": ParagraphStyle("toc1", fontName="Sans", fontSize=9.3, leading=12, spaceBefore=4, textColor=ENCRE),
    "toc2": ParagraphStyle("toc2", fontName="Sans", fontSize=8.3, leading=11, textColor=GRIS, leftIndent=14),
}

B = "β<sub>pub</sub>"
Y = '<font name="Math">𝒴</font>'
CO2 = "CO<sub>2</sub>"

# ----------------------------------------------------------------------------------------------- chiffres du lot

NOMS = {"AT": "Autriche", "BE": "Belgique", "BG": "Bulgarie", "CY": "Chypre", "CZ": "Tchéquie", "DE": "Allemagne",
        "DK": "Danemark", "EE": "Estonie", "EL": "Grèce", "ES": "Espagne", "FI": "Finlande", "FR": "France",
        "HR": "Croatie", "HU": "Hongrie", "IE": "Irlande", "IT": "Italie", "LT": "Lituanie", "LU": "Luxembourg",
        "LV": "Lettonie", "MT": "Malte", "NL": "Pays-Bas", "PL": "Pologne", "PT": "Portugal", "RO": "Roumanie",
        "SE": "Suède", "SI": "Slovénie", "SK": "Slovaquie"}
EN_LETTRES = {2: "deux", 3: "trois", 7: "sept", 9: "neuf", 15: "quinze", 19: "dix-neuf", 20: "vingt", 26: "vingt-six", 27: "vingt-sept"}


def fr(x, d=2):
    return f"{x:.{d}f}".replace(".", ",")


def eur(x):
    """Montant en euros arrondi, espace fine insécable entre les milliers."""
    return f"{round(x):,}".replace(",", "\u202f") + " €"


def pct(x, d=0):
    return f"{fr(100 * x, d)} %"


def lettres(n, maj=False):
    t = EN_LETTRES.get(n, str(n))
    return t[0].upper() + t[1:] if maj else t


REF = SENS["configuration_reference"]
COMPLETS = SENS["pays_complets"]
CLE_IRNR = SENS["cle_irnr"]


def resultat(**var):
    """Résultat de la grille : configuration de référence, sauf les options données."""
    cible = {**REF, **var}
    return next(r for r in SENS["resultats"] if all(r[k] == v for k, v in cible.items()))


R0 = resultat()
IED0 = SENS["ied_reference_brut"]
ORDRE = sorted(COMPLETS, key=lambda g: -IED0[g])


def moyenne(d):
    return sum(d.values()) / len(d)


def paires(inv, n_max=6):
    if inv is None:
        return "–"
    if not inv:
        return "aucune"
    return ", ".join(inv) if len(inv) <= n_max else f"{len(inv)} paires"


def spear(x):
    return "sans objet" if x is None else fr(x, 3)


def composante(nom, **var):
    """Scores d'une composante (iee ou irnr) en configuration de référence, sauf les options données."""
    cible = {"normalisation": REF["normalisation"], **({"agregation": REF["agregation"]} if nom == "iee" else
                                                       {"seuil_irnr": REF["seuil_irnr"]}), **var}
    return next(c for c in SENS["composantes"][nom] if all(c[k] == v for k, v in cible.items()))["valeurs"]


IEE0, IRNR0 = composante("iee"), composante("irnr")
PAYS_ECO = {g: r for g, r in ECO["pays"].items() if g in NOMS and r.get("disponible")
            and "reference" in r.get("assiettes", {})}


def agregat(geos, canal, u=None, assiette="reference"):
    """Somme des montants rapportée à la somme des PIB (u = 1 par défaut, ou {pays: u})."""
    num = den = 0.0
    for g in geos:
        r = ECO["pays"][g]
        pib = r["pib_mio_eur"] * 1e6
        deta = r["u1"]["dteta_pib"] * pib
        y = r["assiettes"][assiette]["y_mio_eur"] * 1e6
        num += {"dteta": deta, "dtent": y, "dg": 2 * deta + y}[canal] * (1 if u is None else u[g])
        den += pib
    return num / den


ZONE = ECO["zone"]
IED_ZONE = next(g for g in ZONE["grille"] if all(g[k] == v for k, v in REF.items()))["ied_brut"]

# ----------------------------------------------------------------------------------------------- éléments


class Doc(BaseDocTemplate):
    def __init__(self, chemin):
        super().__init__(str(chemin), pagesize=A4, leftMargin=27 * mm, rightMargin=27 * mm, topMargin=24 * mm,
                         bottomMargin=22 * mm, title=f"Calibration empirique de l'Économie Homéostatique — rapport "
                         f"d'étape v{VERSION}", author="Benjamin Albouy")
        cadre = Frame(self.leftMargin, self.bottomMargin, self.width, self.height, id="f")
        self.addPageTemplates([PageTemplate("couverture", [cadre]), PageTemplate("courant", [cadre], onPage=pied)])

    def afterFlowable(self, f):
        if isinstance(f, Paragraph) and f.style.name in ("h1", "h2"):
            texte = f.getPlainText()
            niveau = 0 if f.style.name == "h1" else 1
            cle = f"s{id(f)}"
            self.canv.bookmarkPage(cle)
            self.canv.addOutlineEntry(texte, cle, level=niveau)
            if texte != "Sommaire":
                self.notify("TOCEntry", (niveau, f.text, self.page, cle))


def pied(canv, doc):
    canv.saveState()
    canv.setFont("Sans", 7.5)
    canv.setFillColor(GRIS)
    canv.drawString(doc.leftMargin - 6, 12 * mm, PIED)
    canv.drawRightString(A4[0] - doc.rightMargin + 6, 12 * mm, str(doc.page))
    canv.restoreState()


def h1(t):
    return Paragraph(t, S["h1"])


def h2(t):
    return Paragraph(t, S["h2"])


def p(t):
    return Paragraph(t, S["p"])


def cap(t):
    return Paragraph(t, S["cap"])


def puces(*items):
    return ListFlowable([ListItem(Paragraph(t, S["li"]), leftIndent=11, value="•") for t in items],
                        bulletType="bullet", bulletFontName="Helvetica", bulletFontSize=10, leftIndent=11,
                        bulletColor=ENCRE, spaceAfter=6)


def tableau(lignes, largeurs, entetes=1):
    """lignes : listes de cellules (texte avec balises) ; la ou les premières lignes sont l'en-tête."""
    total = sum(largeurs)
    larg = [w / total * (A4[0] - 54 * mm + 4) for w in largeurs]
    data = [[Paragraph(c, S["cellb"] if i < entetes else S["cell"]) for c in ligne] for i, ligne in enumerate(lignes)]
    t = Table(data, colWidths=larg, repeatRows=entetes, hAlign="LEFT")
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, entetes - 1), FOND),
        ("LINEBELOW", (0, entetes - 1), (-1, entetes - 1), 0.8, ENCRE),
        ("LINEBELOW", (0, entetes), (-1, -1), 0.4, FILET),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


def figure(nom, legende, largeur=140 * mm):
    img = Image(str(ICI / "figures" / nom))
    img.drawHeight = largeur * img.imageHeight / img.imageWidth
    img.drawWidth = largeur
    img.hAlign = "LEFT"
    return KeepTogether([img, cap(legende)])


def encadre(texte):
    t = Table([[Paragraph(texte, S["p"])]], colWidths=[A4[0] - 54 * mm])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), FOND), ("BOX", (0, 0), (-1, -1), 0.8, VERT),
                           ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                           ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
    return t


# ----------------------------------------------------------------------------------------------- contenu

def couverture():
    return [
        Spacer(1, 36 * mm),
        Paragraph("Calibration empirique de l'Économie Homéostatique", S["titre"]),
        Paragraph("Rapport d'étape : démarche, choix méthodologiques, résultats et suite du travail", S["soustitre"]),
        Spacer(1, 10),
        Paragraph("Programme de recherche de l'Économie Homéostatique (EH)<br/>Benjamin Albouy, auteur du programme de "
                  f"recherche<br/>{DATE} — version {VERSION}", S["meta"]),
        Spacer(1, 10),
        Paragraph("Version 1.6 : précise les outils de travail et la nature des contrôles intermédiaires "
                  "(section 10.1). Version 1.5 : ajoute l'évolution de l'IED de 2015 à 2023 (section 6.6) et la variante de "
                  f"{B} en standards de pouvoir d'achat (sections 4.2 et 9.3). "
                  "Version 1.4 : révisée après le contrôle intermédiaire ASTRA-CAL du 27 novembre 2026 "
                  "(section 10.4) — l'IRNR est calculé sur l'empreinte matière totale, périmètre des repères, ce qui "
                  f"porte de 9 à {len(COMPLETS)} le nombre de pays complets ; l'assiette {Y} est lissée à valeur "
                  "monétaire constante ; l'intégrité des lots, leur publication et l'historique des incidents sont "
                  "renforcés. Version 1.3 : ajoute les écodotations (section 9). Version 1.2 : ajoute la "
                  "visualisation sur la carte (section 8) et les scores des composantes IEE et IRNR. Version 1.1 : "
                  "révisée après le contrôle intermédiaire ASTRA-EC du 27 novembre 2026 (section 10.3).<br/>"
                  "Dépôt de travail : github.com/BenEXN/Europe-Civilization (branche principale). Réponses Eurostat du "
                  f"lot {LOT}, traitées par le code de la version 1.6 (section 10.1).<br/>"
                  "Carte : benexn.github.io/Europe-Civilization<br/>"
                  "Référence : Albouy, B. (2026). <i>L'Économie Homéostatique — Cadre de référence méthodologique et "
                  "conceptuel pour une viabilité macroéconomique dans un monde biophysiquement fini</i>. Working paper, "
                  "version 1.0.", S["meta"]),
        Spacer(1, 10 * mm),
        encadre("<b>En bref.</b> Ce rapport rend compte d'une première étape de calibration empirique du cadre formel "
                "de l'EH. Elle a consisté à rattacher les objets de la formalisation V1.0 (§5.5 du WP) à des données "
                f"publiques traçables, à recalculer le paramètre {B} de la note 47, à rassembler les séries candidates "
                "des trois composantes de l'état biophysique S = (IBD, IEE, IRNR), puis à mesurer la sensibilité de "
                "l'IED aux choix de construction que le WP laisse ouverts, avec des repères normatifs publiés pour la "
                "valeur 1. Ces résultats sont portés sur une carte publique, avec des découpages transfrontaliers sur "
                "lesquels raisonner pour définir les zones tampons. Les formules d'écodotation du WP y sont appliquées "
                "aux données publiques, pour donner à leur calibration un premier ordre de grandeur. Aucune valeur "
                "produite n'est une mesure de l'IED : toutes dépendent de choix explicites, documentés avec elles."),
        NextPageTemplate("courant"),
        PageBreak(),
    ]


def sommaire():
    toc = TableOfContents()
    toc.levelStyles = [S["toc1"], S["toc2"]]
    toc.dotsMinLevel = 0
    toc.tableStyle = TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                 ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 1),
                                 ("BOTTOMPADDING", (0, 0), (-1, -1), 1)])
    return [Paragraph("Sommaire", ParagraphStyle("som", parent=S["titre"], spaceAfter=14)), toc, PageBreak()]


def corps():
    E = []
    # 1 ---------------------------------------------------------------------------------------------------------
    E += [h1("1. But poursuivi"),
          p("Le WP V1.0 formalise l'EH comme un système dynamique contrôlé : un état <i>x</i> = (S, M), où S = (IBD, "
            "IEE, IRNR) regroupe trois indicateurs exo-économiques normalisés sur [0, 2] et M la masse monétaire ; une "
            "rétroaction prescrite <i>u</i> = Φ(IED(S)), où l'IED est la moyenne géométrique des trois composantes de "
            "S ; un corridor de viabilité K = K<sub>S</sub> × K<sub>M</sub>. Le cadre pose la viabilité comme question "
            "première et renvoie à un programme de recherche la caractérisation des classes de modèles et de règles "
            "compatibles avec un noyau de viabilité non vide (P-F1)."),
          p("Ce formalisme ne prend appui sur la réalité biophysique et économique que par l'intermédiaire de grandeurs "
            "mesurables : les sous-indicateurs de S, les seuils qui délimitent K, les paramètres institutionnels des "
            "écodotations. Le but de l'étape décrite ici est de construire ce lien de façon reproductible :"),
          puces("rattacher chaque objet de la formalisation aux données publiques qui peuvent l'alimenter, ou constater "
                "qu'il n'en existe pas ;",
                "recalculer les paramètres déjà calibrés dans le WP, pour les rendre vérifiables par un lecteur ;",
                "rendre visibles et chiffrables les choix de construction que le WP laisse ouverts (normalisation, "
                "agrégation, pondérations), en lien avec les problèmes T3, E4 et I5 ;",
                "le faire dans une infrastructure où chaque chiffre est traçable jusqu'au fichier téléchargé, archivé, "
                "et recalculé automatiquement quand les sources sont mises à jour."),
          p("L'enjeu de recherche qui oriente l'ensemble est la justesse des indicateurs à représenter la réalité "
            "biophysique : c'est d'elle que dépend la performativité du dispositif (axiome A4). Ce critère a guidé les "
            "choix décrits plus loin, en particulier le recours à des repères absolus exprimés en grandeurs physiques "
            "par habitant et l'attention portée à l'échelle géographique des indicateurs.")]
    # 2 ---------------------------------------------------------------------------------------------------------
    E += [h1("2. Point de départ et choix de l'infrastructure"),
          h2("2.1 Les cartes « Civilization » construites sur des données publiques"),
          p("Le point de départ est une série de projets publiés en novembre 2026. Andrej Karpathy a présenté usaciv, "
            "une carte des États-Unis à la manière d'un jeu de stratégie, construite à partir de 31 sources publiques "
            "fusionnées sur une grille hexagonale. Le projet a été adapté à la France (franceciv), puis à l'Europe "
            "(europeciv, dépôt lmveprog/Europe-Civilization). Ces projets ne poursuivent pas de but analytique ; leur "
            "intérêt pour l'EH tient à leur méthode : une chaîne qui télécharge des sources publiques, les met en forme "
            "et les ramène à une grille commune, avec la provenance de chaque fichier."),
          h2("2.2 Pourquoi partir d'un fork d'Europe-Civilization"),
          puces("<b>Licence.</b> Le code est sous licence MIT : il peut être repris, modifié et publié en conservant la "
                "mention de licence. Les données gardent leurs licences propres, presque toutes ouvertes (CC BY 4.0, "
                "Licence Ouverte, domaine public).",
                "<b>Traçabilité.</b> La chaîne suit toujours le même chemin (source, données intermédiaires, "
                "construction) et enregistre pour chaque téléchargement son adresse, sa date et son empreinte SHA-256.",
                "<b>Sobriété technique.</b> La chaîne n'utilise que la bibliothèque standard de Python, ce qui la rend "
                "facile à relire et à exécuter.",
                "<b>Échelle géographique.</b> La grille hexagonale, terrestre et marine, pourra accueillir des données "
                "infranationales et transfrontalières une fois intégrées (section 7)."),
          p("Le fork a été créé sur le compte de l'auteur (github.com/BenEXN/Europe-Civilization). Les calculs y sont "
            "exécutés par GitHub Actions, qui télécharge les données directement auprès d'Eurostat. Chaque passage "
            "constitue un lot : réponses brutes, manifestes et environnement d'exécution sont archivés et publiés sous "
            "le nom du lot, et le lot n'est enregistré que si son rejeu hors réseau redonne les mêmes séries "
            "(section 10).")]
    # 3 ---------------------------------------------------------------------------------------------------------
    E += [h1("3. Lecture du WP et correspondance avec les données"),
          h2("3.1 Travail sur le document source"),
          p("La formalisation a été lue sur le PDF source du WP. Une première version texte, extraite automatiquement, "
            "avait perdu les équations affichées (définition de K, équations (1) à (3) de la dynamique monétaire) ; "
            "elle a été écartée. En mathématiques appliquées, travailler sur un texte dont des symboles ont disparu "
            "n'est pas admissible."),
          h2("3.2 Ce que les données peuvent alimenter"),
          tableau([
              ["Objet du WP", "Statut", "Alimentation possible par des données publiques"],
              ["S = (IBD, IEE, IRNR)", "Indicateurs normalisés, chaînes de construction à spécifier (§6.2)",
               "Pas de série directe : des sous-indicateurs candidats, à normaliser et agréger"],
              ["Normalisation sur [0, 2]", "Échelle, valeur 1 de référence, sens fixés ; forme et repères 0 et 2 "
               "ouverts", "Repères normatifs publiés pour la valeur 1 (section 6)"],
              [f"{B}, <i>c</i>", "Paramètres institutionnels, calibration exploratoire (note 47)",
               "Oui : dépenses publiques et population (Eurostat)"],
              [f"{Y} (assiette des entreprises)", "Charges d'exploitation lissées",
               "Approchée par les comptes nationaux par secteur (section 9)"],
              ["M", "Masse de monnaie <i>ex naturae</i>",
               "Aucune : variable contrefactuelle, la M3 actuelle n'en est pas une mesure"],
              ["λ, Φ", "Paramètre et règle normatifs, fixés <i>ex ante</i>", "Aucune par construction"],
              ["F (dynamique de S)", "Non spécifiée (P-F1)",
               "Tendances passées de S ; pas de réponse de S à <i>u</i>, faute de monnaie <i>ex naturae</i>"],
          ], [1.3, 1.9, 2.4]),
          Spacer(1, 6),
          p("Ce constat a fixé l'ordre du travail : commencer par le seul paramètre déjà défini et vérifiable de bout en "
            f"bout ({B}), puis rassembler les séries candidates des trois composantes de S, sans calculer les "
            "indicateurs eux-mêmes tant que leurs références et leur normalisation ne sont pas spécifiées.")]
    # 4 ---------------------------------------------------------------------------------------------------------
    E += [h1(f"4. Recalcul de {B}"),
          h2("4.1 Méthode"),
          p(f"La note 47 du WP calibre {B} à 22 000 € (valeur arrondie, euros constants 2017) : moyenne des dépenses "
            "publiques par habitant des dix États membres de l'UE-27 où elles sont les plus élevées, calculée sur les "
            "données 2017 publiées en 2019 (22 310 €). Le module eh_beta_pub reproduit ce calcul : dépenses totales des "
            "administrations publiques (gov_10a_main, secteur S13, poste TE, millions d'euros) et population moyenne "
            "annuelle des comptes nationaux (nama_10_pe). Pour les autres années, le passage en euros constants 2017 "
            "par le déflateur implicite du PIB de l'UE-27 (nama_10_gdp) est une extension du fork : le WP fixe le "
            "repère 2017 sans prescrire de déflateur."),
          h2("4.2 Résultats"),
          p("Le recalcul sur les données actuelles retrouve les dix mêmes pays, dans le même ordre (Luxembourg, "
            "Danemark, Suède, Finlande, Autriche, Belgique, France, Pays-Bas, Allemagne, Irlande), et donne 22 589 € "
            "par habitant, soit 1,25 % de plus que la valeur non arrondie de la note 47. Cet écart est compatible avec "
            "les révisions des séries depuis 2019 ; son origine exacte demanderait les données diffusées en 2019. La "
            "valeur arrondie de 22 000 € reste défendable comme paramètre institutionnel exploratoire ; un chiffre "
            "reproductible demande d'indiquer le lot d'extraction."),
          tableau([["Année", f"{B} nominal", f"{B} en € 2017", "Codes, 10 pays retenus et déflateur",
                    "Codes, 17 autres pays", "Marge 10e / 11e"]] + [
              ["2015", "22 075 €", "22 530 €", "1", "0", "14,7 %"],
              ["2016", "22 212 €", "22 508 €", "0", "0", "13,1 %"],
              ["2017 (référence)", "22 589 €", "22 589 €", "0", "0", "12,2 %"],
              ["2018", "23 139 €", "22 822 €", "0", "0", "15,3 %"],
              ["2019", "23 680 €", "22 969 €", "0", "0", "16,3 %"],
              ["2020", "25 928 €", "24 703 €", "0", "1", "21,4 %"],
              ["2021", "26 699 €", "24 840 €", "0", "1", "15,4 %"],
              ["2022", "27 521 €", "24 276 €", "0", "1", "9,9 %"],
              ["2023", "29 081 €", "24 113 €", "1", "1", "11,4 %"],
              ["2024", "30 534 €", "24 500 €", "4", "2", "19,2 %"],
              ["2025", "31 976 €", "24 981 €", "7", "7", "19,9 %"]], [1.1, 1.0, 1.0, 1.4, 1.1, 1.1]),
          cap(f"Source : lot {LOT}, extraction directe Eurostat. Codes : valeurs marquées provisoires, estimées, en "
              "rupture de série ou de définition différente. Marge : écart entre le 10e et le 11e pays (l'Italie chaque "
              "année), rapporté au 10e."),
          p("Le choix du groupe et de la pondération pèse davantage que l'écart de révision. Sur les mêmes données "
            "2017 : moyenne des dix pays pondérée par leur population, 19 493 € ; moyenne des 27 pays, 12 867 € ; "
            "dépense totale des 27 pays rapportée à leur population, 13 933 € ; pays médian, 8 948 €. La convention de "
            "la note 47 est une convention parmi d'autres : les dépenses publiques historiques comprennent des "
            "transferts et des structures institutionnelles propres à chaque pays, et ne mesurent pas directement un "
            f"besoin de création primaire. {B} est un paramètre d'harmonisation à calibrer."),
          p("<b>Variante en standards de pouvoir d'achat (SPA).</b> La même convention, appliquée aux dépenses "
            "par habitant divisées par l'indice de niveau des prix du PIB de chaque pays (prc_ppp_ind, UE-27 = 100), "
            f"donne {eur(BETA['beta_pub_reference']['variante_spa']['beta_pub_spa'])} SPA en 2017, les dix pays retenus "
            f"étant {', '.join(x['geo'] for x in BETA['beta_pub_reference']['variante_spa']['pays'])}. Un montant en SPA "
            "représente un même pouvoir d'achat dans chaque pays ; il se reconvertit en euros par l'indice de niveau "
            "des prix du pays (section 9.3). Le niveau de prix retenu est celui du PIB, qui couvre l'ensemble de la "
            "production."),
          h2("4.3 Choix retenus et raisons"),
          puces("<b>2017 comme millésime de référence.</b> Aucune valeur des 27 pays ni du déflateur n'y porte de code "
                "Eurostat, la marge de sélection est de 12,2 %, et c'est le millésime du WP. La série 2016–2019 est "
                "stable (22 500 à 23 000 € constants). Les montants passent de 22 969 € en 2019 à 24 703 € en 2020 et "
                "restent à ce niveau : un paramètre recalibré automatiquement transmettrait aussi les politiques de "
                "crise, et une règle de gel ou de lissage est un choix distinct, à justifier.",
                "<b>Données 2025 conservées, non utilisées.</b> Quatorze valeurs y portent un code provisoire. Le calcul "
                "mensuel indique quand une année n'en porte plus ; la stabilité se constate ensuite d'un lot à l'autre.",
                "<b>Déflateur du PIB plutôt que l'indice des prix à la consommation</b>, parce qu'il porte sur "
                "l'ensemble de la production. Il ne corrige ni les niveaux de prix nationaux ni la composition des "
                "dépenses ; une variante en parités de pouvoir d'achat est à comparer.",
                "<b>Vérification par extraction directe.</b> Les premières valeurs avaient été relevées par une lecture "
                "indirecte des pages Eurostat ; l'exécution sur GitHub Actions, qui télécharge les fichiers eux-mêmes, a "
                "confirmé les montants 2017 et 2025 à l'euro près, et le contrôle intermédiaire ASTRA-EC les a "
                "recalculés par un programme distinct pour les onze années.")]
    # 5 ---------------------------------------------------------------------------------------------------------
    E += [h1("5. Séries candidates des composantes de S"),
          p("Le WP présente chacun des trois indicateurs comme le résultat d'une chaîne de construction : données, "
            "sous-indicateurs, protocoles, normalisation (§6.2). Trois modules rassemblent les séries publiques "
            "disponibles à l'échelle des États membres, sans calculer les indicateurs. Les codes des tables ont été "
            "établis en consultant le catalogue complet d'Eurostat ; la lecture exige les codes attendus et s'arrête "
            "sur une erreur si le schéma d'une table change."),
          h2("5.1 IRNR — ressources non renouvelables"),
          p("Séries : consommation intérieure de matières (DMC, env_ac_mfa) et empreinte matière (RMC, env_ac_rme), "
            "par habitant, pour les minerais métalliques (MF2), les minéraux non métalliques (MF3) et les matières "
            "énergétiques fossiles (MF4). La DMC couvre les 27 pays de 2010 à 2025. La RMC totale est publiée pour les "
            "27 pays ; sa ventilation par catégorie de matières l'est pour 15, le plus souvent jusqu'à 2023. L'analyse de "
            "sensibilité retient la RMC totale (section 6.1)."),
          tableau([["France, 2023 (t/hab)", "DMC", "RMC", "RMC / DMC"],
                   ["Minerais métalliques", "0,21", "1,03", "≈ 5"],
                   ["Matières énergétiques fossiles", "1,30", "1,91", "≈ 1,5"],
                   ["Minéraux non métalliques", "5,62", "5,76", "≈ 1"]], [2.4, 1, 1, 1]),
          Spacer(1, 6),
          p("La DMC additionne l'extraction intérieure et les importations, moins les exportations, en poids direct ; "
            "la RMC attribue à la demande finale les extractions mobilisées dans les chaînes de production mondiales. "
            "Pour les métaux, la RMC française est cinq fois la DMC : le choix entre les deux mesures est déterminant, "
            "et les données donnent ici sa mesure au point de vigilance du §6.2 sur les échanges internationaux. Ce "
            "sont des flux : ils renseignent la pression ; la durée de disponibilité d'une ressource, sa criticité ou "
            "sa recyclabilité relèvent des stocks et d'autres données."),
          h2("5.2 IEE — pressions sur les écosystèmes et les ressources renouvelables"),
          tableau([["Famille de pression (§6.2)", "Série", "Table", "Couverture"],
                   ["Climat", "Gaz à effet de serre des unités résidentes", "env_ac_ainah_r2", "2010–2025"],
                   ["Climat, côté consommation", f"Empreintes GES et {CO2} (FIGARO)", "cli_gge_foot", "2010–2024"],
                   ["Pollution des sols et des eaux", "Bilans de l'azote et du phosphore agricoles", "aei_pr_gnb",
                    "2010–2023"],
                   ["Ressource renouvelable / renouvellement", "Indice d'exploitation de l'eau (WEI+) : consommation "
                    "nette rapportée aux ressources renouvelables", "sdg_06_60", "2010–2023"],
                   ["Artificialisation", "Occupation du sol (LUCAS)", "lan_lcv_ovw", "2012, 2015, 2018, 2022"],
                   ["Artificialisation", "Imperméabilisation des sols", "sdg_11_32", "2012–2021 (triennal)"]],
                  [1.6, 2.3, 1.2, 1.1]),
          Spacer(1, 6),
          p("Trois enseignements pour la spécification. Les rythmes de publication sont hétérogènes (annuels pour les "
            "émissions, triennaux pour l'artificialisation), ce qui introduit un délai dans le signal. La moyenne "
            "nationale efface les tensions locales : l'exploitation de l'eau vaut 3,2 % pour la France entière, alors "
            "que les tensions sont saisonnières et propres à certains bassins, un cas concret du problème M4. Enfin, "
            f"l'empreinte de consommation de la France (8,1 t éq. {CO2}/hab, 2024) dépasse d'environ 40 % les émissions "
            "de ses unités résidentes (5,9 t) ; parmi les pressions retenues pour l'IEE, seule celle du climat est "
            "publiée côté consommation. Les tables Eurostat consultées ne comportent pas de série nationale de "
            "fragmentation des habitats."),
          h2("5.3 IBD — état de la biodiversité"),
          tableau([["Famille (§6.2)", "Série", "Table", "Couverture"],
                   ["Abondance des espèces", "Oiseaux communs des milieux agricoles", "env_bio2",
                    "23 pays, dernière année variable"],
                   ["Abondance des espèces", "Oiseaux communs, toutes espèces et forêts", "env_bio3", "UE-27 seulement"],
                   ["État des écosystèmes", "Territoire touché par la sécheresse", "sdg_15_42", "27 pays, 2010–2025"],
                   ["Protection des habitats", "Aires protégées terrestres et marines", "env_bio4", "27 pays, 2011–2023"]],
                  [1.5, 2.1, 1.0, 1.6]),
          Spacer(1, 6),
          p("Une seule série mesure l'état du vivant par pays, et partiellement : l'indice des oiseaux communs des "
            "milieux agricoles, rapporté à une année de base propre à chaque pays (2000 pour la plupart ; 1998 pour "
            "l'Autriche, 2004 pour le Portugal, 2005 pour la Slovaquie, 2006 pour Chypre, 2007 pour la Grèce, 2008 "
            "pour la Slovénie, 2010 pour le Luxembourg). Il décrit des tendances nationales ; ses niveaux ne se "
            "comparent pas d'un pays à l'autre. Les aires protégées mesurent un effort, la sécheresse une "
            "perturbation ; la diversité génétique et celle des écosystèmes n'ont pas de série nationale chez "
            "Eurostat. Une source d'état plus large est extérieure à Eurostat : l'état de conservation des habitats et "
            "des espèces rapporté au titre de l'article 17 de la directive Habitats, par région biogéographique et par "
            "pays (Agence européenne pour l'environnement, tous les six ans)."),
          h2("5.4 Bilan des données"),
          tableau([["Composante", "Couverture", "Principal choix de spécification révélé"],
                   ["IRNR", "Bonne (DMC, RMC totale), partielle (ventilation de la RMC)",
                    "Production ou consommation ; flux ou stocks ; référence soutenable par habitant"],
                   ["IEE", "Correcte, rythmes hétérogènes",
                    "Séries non annuelles ; échelle spatiale ; principe d'attribution ; agrégation interne"],
                   ["IBD", "Faible à l'échelle nationale",
                    "Sources hors Eurostat ; distinguer état et effort de protection"]], [0.9, 2.2, 2.7]),
          Spacer(1, 6),
          p("Les trois composantes n'ont pas la même qualité de données. Avec une moyenne géométrique à exposants "
            "égaux, chaque composante a le même poids dans l'IED, quelle que soit la qualité de sa mesure ; "
            "l'incertitude de l'IED dépend alors des erreurs de chaque composante, de leurs variances et de leurs "
            "covariances (T3). La qualité des données, critère cité par E4 pour les pondérations, diffère nettement "
            "d'une composante à l'autre. La note de synthèse détaillée se trouve dans calibration/NOTE_SYNTHESE.md.")]
    # 6 ---------------------------------------------------------------------------------------------------------
    E += section6()
    # 7 ---------------------------------------------------------------------------------------------------------
    E += [h1("7. Échelle géographique, zones tampons et justesse de représentation"),
          p("Les résultats sont calculés par État membre parce que c'est l'échelle de publication des statistiques. Les "
            "processus biophysiques ont leurs propres échelles : un État ne coïncide ni avec un bassin versant, ni avec "
            "un habitat, ni avec une chaîne d'approvisionnement. Dans la conception de l'EH, l'IED est rattaché à une "
            "zone géographique reliée aux autres par des zones tampons : une large part du vivant ne connaît pas de "
            "frontière et relève de plusieurs zones d'influence. Les populations de poissons, par exemple, s'étendent "
            "le long des côtes de plusieurs pays et au large."),
          p(f"Deux principes distincts relient un territoire au reste du monde. L'empreinte (matière, {CO2}) attribue à "
            "la demande finale d'un pays des pressions exercées ailleurs : c'est une règle de responsabilité. La "
            "continuité des milieux — bassins versants, mers, aires de répartition des espèces — relie des territoires "
            "par leurs interactions biophysiques : c'est l'objet des zones tampons. Aucune série nationale ne "
            "représente cette continuité. Les zones tampons demandent une géométrie, des données spatialisées et une "
            "règle de partage de l'état d'une zone tampon entre les zones qu'elle relie ; elles sont à définir au cours "
            "de la construction des indicateurs de l'EH. Les découpages transfrontaliers existants portés sur la carte "
            "(section 8) fournissent des géométries réelles sur lesquelles raisonner ; la résolution des observations "
            "dépend, elle, des données intégrées.")]
    # 8 ---------------------------------------------------------------------------------------------------------
    E += [h1("8. Visualisation sur la carte"),
          p("Les résultats de la calibration sont portés sur la carte du dépôt, publiée par GitHub Pages "
            "(benexn.github.io/Europe-Civilization). Un bouton « EH » ouvre un panneau ; chaque vue a un lien direct, "
            "de la forme #eh=ied.20002, qui désigne l'indice affiché et la configuration retenue. Le panneau rappelle "
            "en tête qu'aucune valeur de la carte n'est une mesure de l'IED."),
          h2("8.1 Indices et rapports aux repères"),
          puces("<b>Indices par scénario.</b> La carte colore chaque pays par l'IED, l'IEE ou l'IRNR d'une "
                "configuration de la grille, choisie par la normalisation, l'agrégation, les pondérations, le repère "
                "IRNR et l'IBD supposé : les 480 configurations sont accessibles. Les choix sans effet sur l'indice "
                "affiché sont désactivés. Pour l'IED, un tableau donne par pays la valeur du scénario, la référence, "
                "l'enveloppe de scénarios et les codes Eurostat des termes utilisés.",
                f"<b>Rapports aux repères.</b> Chaque sous-indicateur (empreinte {CO2}, empreinte matière totale, qui "
                "mesure l'IRNR, empreinte matière non renouvelable en variante, azote, phosphore) peut colorer la carte "
                "par son rapport à un repère, pour tous les pays qui disposent de la série.",
                "<b>Lentilles.</b> Un groupe « Économie Homéostatique » du sélecteur de lentilles donne ces indices et "
                "ces rapports en configuration de référence. L'IBD y figure, désactivé : il n'est pas mesuré et "
                "n'entre dans les scénarios que comme valeur supposée.",
                "<b>Écodotations.</b> Un exercice monétaire, à activer, est décrit en section 9.5."),
          p("L'échelle de couleur des indices est fixe sur [0, 2], avec la valeur 1 au centre, pour que la position "
            "d'un pays par rapport au niveau de référence reste lisible d'un scénario à l'autre. Les rapports aux "
            "repères sont en échelle logarithmique, centrée sur 1."),
          figure("figure1.png", "Figure 1. Panneau EH et carte de l'IED en configuration de référence (réponses du lot "
                 f"{LOT}, version {VERSION}). Les {lettres(len(COMPLETS))} pays colorés sont ceux qui disposent de toutes "
                 "les séries."),
          figure("figure2.png", "Figure 2. Sélecteur de lentilles : groupe « Économie Homéostatique », IEE de référence "
                 "sur la carte, IBD désactivé."),
          h2("8.2 Découpages transfrontaliers"),
          p("Deux découpages sont superposés aux pays, chacun avec son interrupteur, le nom de chaque entité au survol, "
            "sa source, sa date de téléchargement et son empreinte :"),
          tableau([["Découpage", "Entités sur la carte", "Source"],
                   ["Zones statistiques du CIEM, sur lesquelles sont évalués les stocks halieutiques", "55",
                    "CIEM, via Marine Regions (VLIZ), CC BY 4.0"],
                   ["Écorégions du CIEM, alignées sur les régions et sous-régions marines de la directive-cadre "
                    "stratégie pour le milieu marin", "15", "CIEM, via Marine Regions (VLIZ), CC BY 4.0"]],
                  [3.2, 0.9, 1.9]),
          cap("Les entités situées hors du cadre de la carte (Arctique, Atlantique lointain) ne sont pas tracées. Les "
              "géométries sont simplifiées à 1 km pour l'affichage."),
          p("Les districts hydrographiques de la directive-cadre sur l'eau et les régions biogéographiques de la "
            "directive Habitats sont publiés par l'Agence européenne pour l'environnement sur des serveurs qui "
            "n'acceptent pas les connexions des machines de GitHub Actions. La carte les signale comme manquants ; une "
            "copie téléchargée depuis le site de l'Agence, archivée dans le dépôt avec son adresse, sa date et son "
            "empreinte, permettra de les intégrer à la même chaîne."),
          figure("figure3.png", "Figure 3. Zones statistiques (tirets) et écorégions (traits pleins) du CIEM "
                 "superposées aux pays."),
          h2("8.3 Construction et publication"),
          p("Les données de la carte (web/data/eh.json) sont produites par analyse/carte_eh.py à partir des résultats "
            "de l'analyse de sensibilité, du calcul des écodotations et des découpages téléchargés ; aucune valeur n'y "
            f"est recalculée, à l'exception de la conversion du PIB et de {Y} en euros constants 2017 (section 9.5). Les "
            "IED y sont repris sans arrondi, l'arrondi étant fait à l'affichage. Les découpages "
            "sont projetés dans le repère de la carte, dont le calage est vérifié à chaque construction sur des sites "
            "de coordonnées connues. Le workflow « Carte EH » reconstruit et publie la carte après chaque lot de "
            "calibration enregistré et chaque mois ; si un découpage requis manque, le dernier fichier enregistré "
            "reste en place.")]
    E += ecodotations()
    # 10 --------------------------------------------------------------------------------------------------------
    E += [h1("10. Vérification et traçabilité"),
          h2("10.1 Infrastructure"),
          tableau([["Élément", "Emplacement dans le dépôt"],
                   [f"Sources Eurostat ({B}, IRNR, IEE, IBD, assiette {Y}) et règles de lot", "pipeline/sources/eh_*.py"],
                   ["Analyse de sensibilité ; évolution 2015–2023", "analyse/sensibilite_ied.py ; analyse/evolution_ied.py"],
                   ["Écodotations rapportées au PIB et IED de zone", "analyse/ecodotations.py"],
                   ["Contrôle, archivage, vérification d'intégrité et rejeu hors réseau d'un lot",
                    "analyse/lot_calibration.py"],
                   ["Résultats et provenance (adresse, date, SHA-256), référence du lot, incidents des lots enregistrés",
                    "calibration/ et calibration/provenance/"],
                   ["Historique exhaustif des incidents, échecs compris", "branche eh-incidents"],
                   ["Archive des réponses brutes de chaque lot", "publications GitHub (Releases), nom du lot"],
                   ["Note de synthèse ; analyse de sensibilité ; évolution",
                    "calibration/NOTE_SYNTHESE.md ; SENSIBILITE_IED.md ; EVOLUTION_IED.md"],
                   ["Recalcul mensuel et à chaque modification du code", ".github/workflows/eh-calibration.yml"],
                   ["Découpages transfrontaliers et données de la carte",
                    "pipeline/sources/eh_decoupages.py ; analyse/carte_eh.py ; web/data/eh.json"],
                   ["Carte : panneau, couches et lentilles ; publication",
                    "web/js/ext/eh/ ; .github/workflows/eh-carte.yml"],
                   ["Rapport d'étape (ce document)", "calibration/rapport/rapport_etape.py"],
                   ["Tests", "tests/test_eh_*.py ; test_sensibilite_ied.py ; test_evolution_ied.py ; test_carte_eh.py"]],
                  [3.0, 2.8]),
          Spacer(1, 6),
          p("Un lot n'est enregistré que si les tables requises sont présentes et à jour, si les contrôles après calcul "
            "passent, si l'intégrité de son archive est vérifiée — empreinte de chaque réponse brute contre son "
            "manifeste, et de l'archive contre la référence du lot — et si son rejeu hors réseau redonne les mêmes "
            "séries et les mêmes résultats (analyse de sensibilité, écodotations, évolution). L'archive est publiée, puis "
            "téléchargée et vérifiée, avant l'enregistrement des résultats ; sinon le dernier lot publié reste en "
            "place. Une table accessoire en échec est publiée comme périmée, avec la date de sa dernière réponse. Les "
            "incidents sont consignés à chaque exécution, échecs compris, sur une branche dédiée. Les lecteurs exigent "
            "les codes attendus de chaque table et refusent les valeurs non finies. Les chiffres cités par la note de "
            "synthèse sont vérifiés contre chaque lot, et la note porte en tête l'état de ce contrôle."),
          p(f"Les chiffres des sections 4 à 9 sont ceux du lot {LOT}, téléchargé et traité par le code de la version "
            "1.6. Pour les tables communes, ses réponses redonnent les résultats des lots du 27 novembre, sur lesquels "
            "portent les deux contrôles intermédiaires."),
          p("Le code du dépôt, dont celui qui produit ce rapport, a été écrit avec Claude (Anthropic) ; les contrôles "
            "intermédiaires ASTRA-EC et ASTRA-CAL ont été conduits avec l'assistant d'IA Astra. Les choix de "
            "construction, leur justification et les décisions de calibration relèvent de l'auteur."),
          h2("10.2 Évaluation intermédiaire interne"),
          p("Avant la version 1.0, l'ensemble a été relu comme pour une présentation : tests du dépôt, calculs refaits à "
            "la main pour la France, codes Eurostat confrontés à leurs libellés officiels, chiffres de la note de "
            "synthèse confrontés aux fichiers de données, repères confrontés à leurs sources (tableau 1 d'O'Neill et "
            "al. ; résumé et §5.2 de Bringezu). Cette relecture avait conduit à corriger le statut du repère "
            "phosphore, la description du corridor de Bringezu, la mention de la population de référence d'O'Neill et "
            "le suivi des années de remplacement."),
          h2("10.3 Contrôle intermédiaire ASTRA-EC et corrections"),
          p("La version 1.0 et le dépôt (commit 50a54fd) ont fait l'objet d'un contrôle intermédiaire scientifique, "
            "méthodologique et informatique (ASTRA-EC, 27 novembre 2026). Il a retrouvé exactement les "
            f"16 réponses Eurostat par leurs empreintes, les 288 configurations et leurs 2 592 scores, et {B} pour les "
            "onze années, par un calcul distinct. Son verdict : corrections majeures nécessaires avant toute "
            "réutilisation comme référence scientifique, aucun défaut irréparable, réemploi recommandé en conservant "
            "le statut expérimental. Ses 20 constats ont été traités comme suit."),
          tableau([["Constats", "Correction"],
                   ["001, 016", "Rangs moyens et corrélation de Pearson des rangs, sur scores non arrondis ; sans objet "
                    "pour un IED constant ; paires inversées publiées (inversion SI/AT sous la normalisation ratio)."],
                   ["002", "RMC totale (27 pays) et ventilation MF2–MF4 (15 pays) distinguées ; causes des exclusions "
                    "détaillées (ventilation, azote et phosphore) ; variante de périmètre sur la RMC totale."],
                   ["003", "Repères décrits par leur nature (cible, budget, limite répartie) et leur périmètre."],
                   ["004", "WEI+ décrit comme consommation nette ; exclusion de l'eau présentée comme choix de "
                    "construction."],
                   ["005", "Émissions de env_ac_ainah_r2 décrites comme celles des unités résidentes."],
                   ["006", f"Codes Eurostat contrôlés pour les 27 pays dans le calcul de {B} ; marge entre le 10e et le "
                    "11e pays publiée."],
                   ["007, 008, 009", "Termes d'une somme ou d'un ratio de même année, population comprise ; année, "
                    "valeur et code conservés par terme et publiés ; état local à chaque calcul."],
                   ["010, 011", "Codes exigés à la lecture, séries confondues rejetées ; domaines des fonctions et des "
                    "poids contrôlés."],
                   ["012, 013, 017", "Tables requises par source, réponses périmées signalées, lot incomplet non "
                    "enregistré ; archive des réponses brutes par lot, rejeu hors réseau vérifié ; historique horodaté "
                    "des incidents distinct de l'état courant ; chiffres de la note vérifiés à chaque lot."],
                   ["014, 015", "Agrégation conjointe nommée comme telle et expériences à un seul étage ; IBD de 0 à 2 "
                    "et scénarios d'IBD propre à un pays."],
                   ["018", "Années de base nationales de l'indice des oiseaux documentées."],
                   ["019", "Workflow : exécutions concurrentes sérialisées, actions épinglées, environnement enregistré, "
                    "droit d'écriture limité au job."],
                   ["020", "Grille hexagonale présentée comme support de données infranationales à intégrer."]],
                  [1.0, 5.0]),
          h2("10.4 Contrôle intermédiaire ASTRA-CAL et corrections"),
          p("La version 1.3, les trois lots du 27 novembre et le dépôt ont fait l'objet d'un second contrôle "
            "intermédiaire (ASTRA-CAL, 27 novembre 2026). Il a vérifié les 51 réponses brutes des trois archives par "
            "leurs empreintes, rejoué les trois lots hors réseau, et retrouvé par un programme distinct "
            f"{B} pour 2015–2025, les 480 configurations et leurs scores, ainsi que les écodotations publiées. Son "
            "verdict : poursuite scientifique justifiée ; corrections majeures nécessaires sur le lissage de l'assiette "
            f"{Y}, le périmètre de l'assiette et les garanties de contrôle avant toute présentation de la version 1.3 "
            "comme référence méthodologique ; construction des indicateurs non validable en l'état comme mesure des "
            "objets biophysiques, les calculs de scénarios restant valides. Sur les vingt constats d'ASTRA-EC, seize "
            "étaient clos dans leur périmètre initial et quatre partiellement corrigés (011, 012, 017, 019). Ses "
            "dix-huit constats ont été traités comme suit."),
          tableau([["Constats", "Traitement"],
                   ["CAL-001", f"{Y} lissée à valeur monétaire constante : chaque millésime est exprimé à la valeur de "
                    "l'année étudiée par le déflateur de " + B + ", puis la moyenne est formée ; la moyenne des montants "
                    "courants est conservée (section 9)."],
                   ["CAL-002", f"Périmètre du proxy de {Y} documenté (S14, assurance et intermédiation financière, "
                    "consommation de capital fixe) ; table de passage inscrite aux points ouverts (section 12.2)."],
                   ["CAL-003", "Sensibilité de l'assiette à la fragmentation productive : question de recherche du WP "
                    "(§4.2, §7.4), inscrite aux points ouverts avec la comparaison d'assiettes."],
                   ["CAL-004", "IRNR calculé sur l'empreinte matière totale, de même périmètre que les repères ; "
                    "écart avec l'objet IRNR du WP explicité ; part non renouvelable en variante (section 6)."],
                   ["CAL-005, 006", "Limites reconnues (attribution mixte de l'IEE, IBD non mesuré) : points ouverts, à "
                    "traiter avec des spécialistes (section 12)."],
                   ["CAL-007, 008", "Codes attendus exigés par tous les lecteurs (unité, fréquence, secteur, poste) ; "
                    "valeurs non finies et ρ hors domaine refusés ; moyenne de puissance calculée sous forme "
                    "logarithmique, finie pour de très petites valeurs."],
                   ["CAL-009", "Intégrité de l'archive vérifiée avant tout rejeu ; le rejeu recalcule aussi les "
                    "résultats dérivés."],
                   ["CAL-010", "Archive publiée et vérifiée avant l'enregistrement des résultats."],
                   ["CAL-011", "Chiffres de la note recherchés dans son texte ; état du contrôle affiché en tête de la "
                    "note."],
                   ["CAL-012", "Incidents consignés à chaque exécution, échecs compris (branche eh-incidents)."],
                   ["CAL-013", "Workflows de calibration et de carte sérialisés dans un même groupe ; écritures sur la "
                    "branche principale avec reprise."],
                   ["CAL-014, 015", "Carte : état de chargement et d'échec explicites ; codes Eurostat des termes de "
                    "l'IED joints aux dotations nationales et de zone."],
                   ["CAL-016", "IED repris sans arrondi dans les calculs des écodotations et de la carte ; arrondi à "
                    "l'affichage."],
                   ["CAL-017", "Domaine de Φ : le WP pose U = [0, <i>u</i><sub>max</sub>] avec <i>u</i><sub>max</sub> ≥ "
                    "1 ; les formes illustratives de la carte supposent <i>u</i><sub>max</sub> ≥ 2 pour Φ<sub>0</sub> et "
                    "≥ 4 pour <i>z</i>² (point ouvert)."],
                   ["CAL-018", "Exercice statique sans fermeture du circuit monétaire : précision sur λ (section 9.3) ; "
                    "matrice de transactions et de bilans inscrite aux points ouverts."]],
                  [1.0, 5.0])]
    # 11 --------------------------------------------------------------------------------------------------------
    E += [h1("11. Limites connues"),
          puces(f"Une seule année ({SENS['annee']}) et {lettres(len(COMPLETS))} pays complets : les séries d'azote et "
                f"de phosphore manquent pour {', '.join(sorted(g for g in NOMS if g not in COMPLETS))} ; la Slovénie y "
                "figure avec ses séries agricoles de 2021. Les classements portent sur un sous-ensemble de "
                f"disponibilité. L'évolution 2015–2023 porte sur un panel de {len(EVO['panel'])} pays, à repères fixes, "
                "et dépend du millésime de téléchargement des séries révisables.",
                "IRNR : l'empreinte matière totale mesure la pression matérielle totale, biomasse comprise ; ni la "
                "disponibilité des stocks ni la seule consommation de ressources non renouvelables ne sont mesurées.",
                f"Hétérogénéité des mesures au sein de l'IEE : le {CO2} y entre en empreinte de consommation, l'azote et "
                "le phosphore en pression territoriale d'entrée. Un pays exportateur de produits agricoles porte des "
                "pressions liées à la consommation d'autres pays, et une relocalisation de production modifie l'indice "
                "sans évolution équivalente des pressions globales. Les pressions hydriques, chimiques et foncières "
                "sont absentes.",
                "IBD non mesuré : niveaux et classements de l'IED sont conditionnels à sa valeur supposée.",
                "Repères normatifs : allocations égales par habitant de grandeurs globales, datées, de périmètres "
                "propres ; les repères matière portent sur l'empreinte totale.",
                "Formes de normalisation construites pour l'analyse, sans fondement dans le WP au-delà des propriétés "
                "qu'il fixe.",
                "Échelle nationale, en attendant la définition des zones tampons ; sur la carte, les découpages marins "
                "seuls sont intégrés, les districts hydrographiques et les régions biogéographiques restant à "
                "archiver.",
                "Signal non synchrone : données publiées avec deux ans de délai, reprises sur trois ans et révisables ; "
                "l'âge admissible des données et le traitement des révisions sont à définir avant toute régulation.",
                "Variables sans observation : M est contrefactuelle ; aucune donnée ne peut renseigner le couplage de "
                "<i>u</i> à dS/d<i>t</i>, condition de non-dégénérescence posée au §5.5.",
                f"Écodotations : {Y} est approchée par les comptes nationaux par secteur (section 9.2) ; une seule "
                "année ; flux rapportés au PIB, sans représentation des prix, des comportements ni de la masse "
                "monétaire.")]
    # 12 --------------------------------------------------------------------------------------------------------
    E += [h1("12. Ce qu'il reste à faire"),
          h2("12.1 Ordre de travail retenu"),
          puces("<b>Compléter les découpages.</b> Archiver les districts hydrographiques (WISE WFD 2022) et les régions "
                "biogéographiques (version 2016) téléchargés depuis le site de l'Agence européenne pour "
                "l'environnement, puis les intégrer à la carte.",
                "<b>Prise de contact avec des chercheurs</b>, appuyée sur la note de synthèse, l'analyse de "
                "sensibilité, les deux contrôles intermédiaires, la carte et le présent rapport, en proposant comme questions "
                "de travail les points ouverts de la section 12.2 : définition des objets mesurés, circuit monétaire, "
                "pilote spatial, sensibilité globale.",
                "<b>Dynamique F.</b> Les données décrivent l'évolution passée de S ; elles permettront au mieux de "
                "borner des tendances pour P-F1, pas d'estimer la réponse de S à <i>u</i>. Délais, révisions et pertes "
                "d'information sont à tester dans un modèle aux entrées explicites avant tout branchement sur une "
                "règle monétaire. L'étude analytique de P-F1 avance en parallèle de la construction des indicateurs."),
          h2("12.2 Points ouverts à traiter"),
          puces("Définir l'objet mesuré par l'IRNR : un IRNR conforme au WP demande des bilans ressource par ressource "
                "(stocks en usage, réserves, recyclage, pertes dissipatives, horizons) et un repère propre aux "
                "ressources non renouvelables ; étendre l'analyse à plusieurs années.",
                "Choisir un principe d'attribution cohérent pour l'IEE (consommation ou territoire), en lien avec les "
                "zones tampons.",
                "Définir l'IBD avec des écologues : sources d'état (article 17 de la directive Habitats), seuil d'O'Neill "
                "et al. pour l'intégrité de la biosphère (appropriation humaine de la production primaire, 2,62 t "
                "C/hab), sans série nationale chez Eurostat.",
                "Définir les zones tampons et la manière dont leur état entre dans l'IED des zones qu'elles relient.",
                "Étudier le WEI+ par bassin et par saison pour intégrer l'eau.",
                "Identifier des repères, ou déclarer l'inconnue, pour l'artificialisation, la fragmentation et les gaz "
                f"autres que le {CO2}.",
                f"Choisir pour {B} entre euros constants et standards de pouvoir d'achat, et l'indice de niveau des prix "
                "pertinent ; décider d'une règle de gel ou de lissage ; retenir le millésime 2025 quand ses valeurs ne "
                "porteront plus de code provisoire, si ce choix est retenu.",
                f"Calibrer les écodotations (E2), avec la fonte (E1) : assiette {Y}, parité entre DTCIT et DTETA, "
                f"harmonisation de {B} entre économies de niveaux de production et de prix différents, échelle de "
                "l'IED servant aux dotations.",
                f"Établir une table de passage entre comptes d'entreprises, comptes nationaux et postes admissibles de "
                f"{Y} (entreprises individuelles, services d'assurance et d'intermédiation financière, amortissements), "
                "et comparer des assiettes (valeur ajoutée, consolidation de groupe, plafond ou coefficient) au regard "
                "de la fragmentation productive.",
                "Construire une matrice de transactions et de bilans du circuit monétaire (ménages, entreprises, "
                "administrations, émetteur, Projets Régénératifs, reste du monde), avec les deux composantes de la "
                "fonte, pour tester ensemble les paramètres de E1 et de E2."),
          h2("12.3 Questions soumises à l'évaluation"),
          puces("Le recours à des repères normatifs absolus par habitant, et la déclaration des inconnues plutôt que "
                "leur comblement, sont-ils la bonne réponse au critère de justesse de représentation ?",
                "Les séries candidates retenues pour chaque composante sont-elles pertinentes, et quelles sources "
                "manquent ?",
                "La forme de normalisation et les configurations testées couvrent-elles l'espace des choix utile pour "
                "T3 et E4 ?",
                "Quels découpages géographiques serviraient le mieux la définition des zones tampons ?",
                "L'infrastructure de traçabilité est-elle suffisante pour qu'un tiers reproduise chaque chiffre ?",
                f"L'approche de {Y} par les comptes nationaux et les ordres de grandeur obtenus sont-ils une base utile "
                "pour E2 ?")]
    # Références ------------------------------------------------------------------------------------------------
    R = ParagraphStyle
    E += [h1("Références")]
    for t in (
            "Albouy, B. (2026). <i>L'Économie Homéostatique — Cadre de référence méthodologique et conceptuel pour une "
            "viabilité macroéconomique dans un monde biophysiquement fini</i>. Working paper, version 1.0, novembre "
            "2026.",
            "ASTRA-EC (2026). <i>Contrôle intermédiaire scientifique, méthodologique et informatique — Économie "
            "Homéostatique, Europe-Civilization</i>. Rapport intermédiaire, 27 novembre 2026, commit 50a54fd.",
            "ASTRA-CAL (2026). <i>Contrôle intermédiaire du programme de calibration empirique de l'Économie "
            "Homéostatique</i>. Rapport V1.0, 27 novembre 2026, commit 8a787e8.",
            "Aubin, J.-P. (1991). <i>Viability theory</i>. Birkhäuser.",
            "Bringezu, S. (2015). Possible target corridor for sustainable use of global material resources. "
            "<i>Resources</i>, 4(1), 25–54. https://doi.org/10.3390/resources4010025",
            "CIEM (ICES). Zones statistiques et écorégions, diffusées par Marine Regions (Flanders Marine Institute, "
            "VLIZ), service WFS, CC BY 4.0. https://www.marineregions.org",
            "Eurostat. Tables gov_10a_main, nama_10_pe, nama_10_gdp, nasa_10_nf_tr, env_ac_mfa, env_ac_rme, "
            "env_ac_ainah_r2, cli_gge_foot, aei_pr_gnb, sdg_06_60, lan_lcv_ovw, sdg_11_32, env_bio2, env_bio3, "
            "env_bio4, sdg_15_42, et leurs métadonnées (notamment env_ac_rme, env_ac_ainah_r2, sdg_06_60, env_biodiv). "
            f"API de diffusion, lot {LOT} ; provenance détaillée dans calibration/provenance/.",
            "Agence européenne pour l'environnement. <i>Use of freshwater resources in Europe</i> ; <i>Conservation "
            "status of habitats under the EU Habitats Directive</i>.",
            "O'Neill, D. W., Fanning, A. L., Lamb, W. F., &amp; Steinberger, J. K. (2018). A good life for all within "
            "planetary boundaries. <i>Nature Sustainability</i>, 1, 88–95. https://doi.org/10.1038/s41893-018-0021-4",
            "Europe-Civilization (lmveprog), d'après usaciv (A. Karpathy) et franceciv (M. Astruc). Licence MIT. "
            "https://github.com/lmveprog/Europe-Civilization"):
        E.append(Paragraph(t, S["ref"]))
    del R
    return E


def section6():
    """Section 6 : tableaux et constats lus dans calibration/sensibilite_ied.json."""
    E = []
    n = len(COMPLETS)
    var = SENS["variante_irnr_abiotique"]
    seuil0 = REF["seuil_irnr"]
    E += [h1("6. Analyse de sensibilité de l'IED"),
          h2("6.1 Pourquoi des repères absolus"),
          p("La normalisation sur [0, 2] demande une valeur de référence (la valeur 1) pour chaque sous-indicateur. "
            "Deux options ont été envisagées : des repères relatifs, comme la moyenne de l'UE à une date donnée, ou "
            "des repères absolus exprimés en grandeurs physiques par habitant. La seconde a été retenue : une moyenne "
            "fixe des habitudes de consommation, que la littérature situe au-delà des repères de soutenabilité, et ne "
            "renseigne pas l'état biophysique. Les repères retenus sont des repères normatifs publiés — cibles, "
            "budgets ou limites globales — répartis à parts égales par habitant ; chacun est employé comme scénario de "
            "référence, avec sa nature et son périmètre. Là où aucun repère n'est retenu, l'inconnue est déclarée "
            "plutôt que comblée."),
          tableau([["Composante", "Sous-indicateur", "Valeur 1", "Nature du repère", "Périmètre du repère", "Source"],
                   ["IRNR", "Empreinte matière totale, biomasse comprise (t/hab)", "7,2 t",
                    "Cible de soutenabilité répartie par habitant", "Empreinte matière totale, biomasse comprise",
                    "O'Neill et al. 2018"],
                   ["IRNR", "idem", "5 t", "Cible 2050 (corridor de 3 à 6 t)", "Empreinte matière totale",
                    "Bringezu 2015"],
                   ["IEE", f"Empreinte {CO2} de la consommation (t/hab)", "1,61 t",
                    "Budget 2011–2100 (1 000 Gt, 2 °C) réparti par habitant et par an", f"{CO2} seul",
                    "O'Neill et al. 2018"],
                   ["IEE", "Azote fixé, engrais minéraux et fixation biologique (kg/hab)", "8,9 kg",
                    "Limite planétaire globale répartie par habitant", "Fixation intentionnelle, 62 Tg N/an",
                    "O'Neill et al. 2018"],
                   ["IEE", "Phosphore minéral appliqué aux sols (kg/hab)", "0,89 kg",
                    "Limite définie à l'échelle régionale, répartie par habitant", "6,2 Tg P/an, sols érodables",
                    "O'Neill et al. 2018"]], [0.95, 1.6, 0.65, 1.55, 1.4, 1.0]),
          cap("Les valeurs d'O'Neill répartissent des grandeurs globales pour environ 7 milliards d'habitants ; à "
              "grandeur globale fixée, 8 milliards réduisent la part par habitant de 12,5 %. L'égalité par habitant est "
              "une règle distributive ; responsabilités historiques et besoins différenciés appellent d'autres règles, "
              "à comparer."),
          p("<b>Mesure de l'IRNR.</b> L'IRNR est calculé sur l'empreinte matière totale (RMC), biomasse comprise : "
            "c'est le périmètre des deux repères publiés, et la série couvre les 27 États membres. Ce choix a une "
            "contrepartie : la composante ne mesure plus l'objet IRNR du WP, la consommation de ressources non "
            "renouvelables, mais la pression matérielle totale ; la biomasse, renouvelable, recoupe le périmètre de "
            "l'IEE. Aucun repère publié ne porte sur la seule part non renouvelable, et la ventilation de la RMC par "
            "catégorie de matières n'est publiée que pour une partie des pays. L'écart entre l'objet défini par le "
            "cadre et ce que les données et les repères disponibles permettent de mesurer montre la difficulté de "
            "produire et d'utiliser des indicateurs pour un objet théorique. La part non renouvelable (MF2–MF4) est "
            "calculée en variante (section 6.3)."),
          p("<b>Inconnues déclarées.</b> Eau douce : le repère d'O'Neill (574 m³/hab/an d'eau bleue) s'applique à une "
            "empreinte de consommation, sans série nationale homogène ; le WEI+ mesure une consommation nette rapportée "
            "aux ressources renouvelables du territoire, publiée aussi par bassin et par saison, avec un seuil de stress "
            "conventionnel (20 %). L'eau est tenue hors de l'IED par choix de construction, pour ne pas agréger une "
            "tension territoriale à des repères globaux par habitant ; son intégration par bassin est une piste "
            f"ouverte. Artificialisation : aucun repère par habitant retenu. Gaz autres que le {CO2} : repère propre à "
            "établir. Ressources non renouvelables seules : repère propre à établir, sur une logique de stocks. IBD : "
            "traité comme une inconnue, explorée par scénarios (section 6.2)."),
          h2("6.2 Choix testés"),
          p("Le WP fixe l'échelle, la valeur 1 et le sens de la transformation, mais pas la forme de la fonction de "
            "normalisation ni la place des repères 0 et 2. Trois formes candidates, construites pour l'analyse, sont "
            "testées : linéaire (2 − <i>x</i>/<i>T</i>, nulle à deux fois le repère), ratio (<i>T</i>/<i>x</i>, "
            "plafonnée à 2) et hyperbolique (2/(1 + <i>x</i>/<i>T</i>), jamais nulle) ; le placement des valeurs 0 et "
            "2 qu'impose chaque forme est un choix numérique. Elles sont croisées avec quatre fonctions d'agrégation "
            "(moyenne géométrique de la V1.0, moyennes de puissance ρ = −1 et ρ = −5, minimum), appliquées à la fois "
            "entre les sous-indicateurs de l'IEE et entre les composantes de l'IED, quatre jeux de pondérations, les "
            "deux repères IRNR et cinq valeurs de l'IBD communes à tous les pays (0 ; 0,5 ; 1 ; 1,5 ; 2), soit "
            f"{SENS['configurations']} configurations, qui donnent {SENS['vecteurs_distincts']} vecteurs de scores "
            "distincts à neuf décimales près. Trois expériences complètent la grille : l'agrégation modifiée à un seul "
            "étage ; un IBD propre à un pays (0,5 pour ce pays, 1 pour les autres) ; l'IRNR calculé sur la seule part "
            "non renouvelable (MF2–MF4). La forme hyperbolique sert de configuration de référence pour la "
            "présentation, parce qu'elle est définie sans troncature sur tout le domaine."),
          p("Règles de mesure : une série absente pour 2023 est remplacée par la plus récente des trois années "
            "précédentes ; une somme et un ratio sont formés à partir de termes de la même année, population comprise ; "
            "les valeurs portant un code Eurostat sont retenues et signalées. Les corrélations de rang sont calculées "
            "sur les scores non arrondis, avec rangs moyens en cas d'ex æquo, et sont sans objet quand l'IED est "
            "identique pour tous les pays. Les enveloppes sont des ensembles de scénarios, sans probabilité."),
          h2("6.3 Résultats")]
    pr, pe = SENS["plages_ibd_reference"], SENS["plages"]
    E += [tableau([["Pays", "IED (référence)", "Min (IBD = 1)", "Max (IBD = 1)", "Min (enveloppe)", "Max (enveloppe)"]]
                  + [[g, fr(IED0[g]), fr(pr[g]["min"]), fr(pr[g]["max"]), fr(pe[g]["min"]), fr(pe[g]["max"])]
                     for g in ORDRE], [0.8, 1.1, 1.0, 1.0, 1.0, 1.0]),
          cap(f"Année {SENS['annee']}. Référence : normalisation hyperbolique, moyenne géométrique aux deux étages, poids "
              f"égaux, repère IRNR de {seuil0.split(' (')[0]}, IBD supposé égal à 1. L'enveloppe porte sur toute la "
              f"grille, IBD de 0 à 2 compris. {lettres(n, True)} pays disposent de toutes les séries : c'est un "
              "sous-ensemble de disponibilité, dont les moyennes et les rangs décrivent ces pays seulement.")]
    lignes = [["Choix", "Option", "IED moyen", "Corrélation de rang", "Paires inversées"]]
    titres = {"normalisation": "Normalisation", "agregation": "Agrégation, deux étages",
              "poids": "Pondérations (IBD, IEE, IRNR)", "seuil_irnr": "Repère IRNR", "ibd": "IBD commun"}
    for param, titre in titres.items():
        options = list(dict.fromkeys(r[param] for r in SENS["resultats"]))
        for k, o in enumerate(options):
            r = resultat(**{param: o})
            lignes.append([titre if k == 0 else "", fr(o, 1) if isinstance(o, float) else o, fr(moyenne(r["ied"])),
                           spear(r["spearman_vs_reference"]), paires(r["inversions_vs_reference"])])
    for etage, titre in (("iee", "Agrégation, IEE seule"), ("ied", "Agrégation, IED seule")):
        rs = [r for r in SENS["agregation_separee"] if r["etage_varie"] == etage and r["agregation"] != REF["agregation"]]
        for k, r in enumerate(rs):
            lignes.append([titre if k == 0 else "", r["agregation"], fr(moyenne(r["ied"])),
                           spear(r["spearman_vs_reference"]), paires(r["inversions_vs_reference"])])
    E += [tableau(lignes, [1.25, 1.55, 0.6, 0.95, 2.05]),
          cap("Chaque ligne fait varier un seul choix à partir de la référence. Au-delà de six paires inversées, leur "
              "nombre est donné ; la liste figure dans calibration/SENSIBILITE_IED.md. Avec la moyenne géométrique, un "
              "IBD commun multiplie tous les scores par un même facteur : le classement est invariant par "
              "construction.")]
    het = {h["pays"]: h for h in SENS["ibd_heterogene"]}
    E += [tableau([["Pays", "IED de référence", "IED avec IBD = 0,5", "Rang de référence", "Rang du scénario"]]
                  + [[g, fr(het[g]["ied_pays_reference"]), fr(het[g]["ied_pays"]), _rang(het[g]["rang_reference"]),
                      _rang(het[g]["rang"])] for g in ORDRE], [0.8, 1.1, 1.2, 1.1, 1.1]),
          cap("IBD propre à un pays : 0,5 pour ce pays, 1 pour les autres. Scénario hypothétique ; aucune de ces valeurs "
              "n'est une observation.")]
    v0 = var["seuils"][seuil0]
    ref_v = var["reference"][seuil0]
    ecart_fr = (v0["FR"] / ref_v["FR"] - 1) if "FR" in v0 and "FR" in ref_v else None
    E += [p("<b>Variante de périmètre.</b> Rapportée aux mêmes repères, la seule part non renouvelable de "
            f"l'empreinte (MF2–MF4) permet de calculer l'IED pour {lettres(len(var['pays_complets']))} pays "
            f"({', '.join(var['pays_complets'])}). Son rapport au repère est plus faible que celui de l'empreinte "
            "totale, et l'IED plus élevé : "
            + (f"pour la France, {fr(v0['FR'])} avec la variante, contre {fr(ref_v['FR'])} en référence. "
               if ecart_fr is not None else "")
            + "La variante approche l'objet IRNR du WP sans repère de même périmètre.")]
    # 6.4
    n_iee, n_irnr = len(IEE0), len(IRNR0)
    lo_iee, hi_iee = min(IEE0, key=IEE0.get), max(IEE0, key=IEE0.get)
    lo_ir, hi_ir = min(IRNR0, key=IRNR0.get), max(IRNR0, key=IRNR0.get)
    sous = [g for g in COMPLETS if IEE0[g] < IRNR0[g]]
    exceptions = [g for g in COMPLETS if g not in sous]
    E += [h2("6.4 Composantes de l'IED"),
          p("L'analyse publie aussi les scores des composantes IEE et IRNR pour chaque pays qui dispose de leurs "
            "séries : l'IEE selon la normalisation et l'agrégation entre ses sous-indicateurs, l'IRNR selon la "
            f"normalisation et le repère. L'IEE est ainsi calculé pour {n_iee} pays et l'IRNR pour {n_irnr}. En "
            f"configuration de référence, l'IEE va de {fr(IEE0[hi_iee])} ({NOMS[hi_iee]}) à {fr(IEE0[lo_iee])} "
            f"({NOMS[lo_iee]}), l'IRNR de {fr(IRNR0[hi_ir])} ({NOMS[hi_ir]}) à {fr(IRNR0[lo_ir])} ({NOMS[lo_ir]})."),
          tableau([["Pays", "IED (référence)", "IEE", "IRNR"]]
                  + [[g, fr(IED0[g]), fr(IEE0[g]), fr(IRNR0[g])] for g in ORDRE], [0.8, 1.1, 1.1, 1.1]),
          cap("Configuration de référence, IBD supposé égal à 1. L'IED est la moyenne géométrique de l'IBD, de l'IEE et "
              "de l'IRNR ; un test du dépôt vérifie que les trois colonnes satisfont cette relation."),
          p(f"Dans {len(sous)} des {n} pays complets, l'IEE est inférieur à l'IRNR"
            + (f" ; {', '.join(NOMS[g] for g in exceptions)} fait exception" if len(exceptions) == 1 else
               f" ; font exception : {', '.join(NOMS[g] for g in exceptions)}" if exceptions else "")
            + ". Avec les repères retenus, la composante des pressions sur les écosystèmes est celle qui tire le plus "
            "souvent l'IED vers le bas.")]
    # 6.5
    nuls = [r for r in SENS["resultats"] if all(v == 0 for v in r["ied"].values())]
    n_lin = sum(1 for r in nuls if r["normalisation"].startswith("linéaire"))
    n_ibd0 = sum(1 for r in nuls if r["ibd"] == 0 and not r["normalisation"].startswith("linéaire"))
    max1 = max(v for r in SENS["resultats"] if r["ibd"] <= 1 for v in r["ied"].values())
    maxt = max(v for r in SENS["resultats"] for v in r["ied"].values())
    co2 = [SENS["rapport_au_seuil"][g]["iee_co2_empreinte"]["1,61 t (O'Neill)"] for g in COMPLETS]
    ratio = resultat(normalisation="ratio : T/x")
    sp_min = min(x for x in [r["spearman_vs_reference"] for r in SENS["resultats"]
                             if sum(r[k] != REF[k] for k in REF) == 1 and r["ibd"] == REF["ibd"]] if x is not None)
    het_max = max(SENS["ibd_heterogene"], key=lambda h: h["rang"] - h["rang_reference"])
    E += [h2("6.5 Constats"),
          puces(f"<b>Niveau 1.</b> Avec un IBD supposé au plus égal à 1, l'IED ne dépasse pas {fr(max1)} dans la "
                f"grille ; il atteint {fr(maxt)} avec un IBD supposé de 2. L'empreinte {CO2} dépasse son repère d'un "
                f"facteur {fr(min(co2), 1)} à {fr(max(co2), 1)}. Le franchissement du niveau 1 dépend donc de la "
                "valeur supposée de l'IBD.",
                f"<b>Annulation.</b> {len(nuls)} configurations sur {SENS['configurations']} donnent un IED nul pour "
                f"tous les pays : {n_lin} avec la normalisation linéaire, qui supprime dans l'échantillon tout pouvoir "
                f"de discrimination, et {n_ibd0} avec un IBD supposé nul. Pour ρ ≤ 0, un zéro est transmis à l'IED, "
                "conformément au §6.2.",
                "<b>Compensation interne.</b> Avec une moyenne, un sous-indicateur sous son repère compense en partie le "
                "dépassement des autres. C'est une propriété de l'agrégation ; le choix de la fonction d'agrégation se "
                "pose aux deux étages (T3), et l'expérience à un seul étage montre que chacun déplace le classement.",
                "<b>Ce qui déplace le classement.</b> La normalisation ratio donne une corrélation de rang de "
                f"{spear(ratio['spearman_vs_reference'])} (paires inversées : {paires(ratio['inversions_vs_reference'])}) ; "
                "les agrégations à plus faible substituabilité et les pondérations modifient davantage le classement "
                f"(corrélation la plus basse : {spear(sp_min)}).",
                "<b>Poids de l'inconnue IBD.</b> Un IBD commun change les niveaux sans changer le classement, par "
                f"construction. Un IBD propre à un pays le déplace : à 0,5 pour {het_max['pays']}, les autres à 1, ce "
                f"pays passe du rang {_rang(het_max['rang_reference'])} au rang {_rang(het_max['rang'])}. Tant que l'IBD "
                "n'est pas mesuré, les niveaux d'IED et les classements sont conditionnels à cette hypothèse.")]
    E += section66()
    return E


def section66():
    """Section 6.6 : évolution 2015–2023, lue dans calibration/evolution_ied.json."""
    a0, a1 = EVO["annees"][0], EVO["annees"][-1]
    panel, t, rob = EVO["panel"], EVO["tendances"], EVO["robustesse"]
    n_conf = rob["configurations"]
    hausses = [g for g in panel if t[g]["variation"] > 0]
    unanimes = [g for g in panel if rob["pays"][g]["baisse"] == 0 and rob["pays"][g]["hausse"] > 0]
    unanimes_baisse = [g for g in panel if rob["pays"][g]["hausse"] == 0 and rob["pays"][g]["baisse"] > 0]
    iee_dom = [g for g in hausses if t[g]["contribution_iee"] > t[g]["contribution_irnr"]]
    ordre = sorted(panel, key=lambda g: -t[g]["variation_relative"])
    ruptures = [g for g in panel if t[g]["codes_rupture"]]
    lignes = [["Pays", f"IED {a0}", f"IED {a1}", "Variation", "Part IEE", "Part IRNR",
               f"Configurations en hausse / baisse (sur {n_conf})"]]
    for g in ordre:
        x = t[g]
        lignes.append([g, fr(x["ied_debut"]), fr(x["ied_fin"]), pct(x["variation_relative"], 1).replace("-", "−"),
                       fr(x["contribution_iee"], 3).replace("-", "−"), fr(x["contribution_irnr"], 3).replace("-", "−"),
                       f"{rob['pays'][g]['hausse']} / {rob['pays'][g]['baisse']}"])
    return [h2(f"6.6 Évolution {a0}–{a1}"),
            p("Le module analyse/evolution_ied.py prolonge l'analyse dans le temps, avec les mêmes sous-indicateurs, "
              "repères et fonctions. Chaque année est mesurée avec ses seules données, sans reprise d'une année "
              "voisine, et les repères restent fixes ; les populations sont celles de chaque année. Les pays complets "
              f"chaque année de {a0} à {a1} forment un panel de {len(panel)} pays. Pour la moyenne géométrique à poids "
              "égaux et un IBD constant, la variation du logarithme de l'IED se répartit exactement entre l'IEE et "
              "l'IRNR (un tiers de la variation du logarithme de chacun) ; le sens de la variation est aussi calculé "
              f"pour les {n_conf} configurations de la grille où l'IBD vaut 1."),
            tableau(lignes, [0.6, 0.75, 0.75, 0.85, 0.75, 0.8, 1.7]),
            cap("Configuration de référence, IBD supposé égal à 1 et constant. Parts IEE et IRNR : contributions à la "
                "variation du logarithme de l'IED. Les configurations restantes, où l'IED ne varie pas, sont surtout "
                "celles de la normalisation linéaire, qui l'annule les deux années. Détail par année et par "
                "sous-indicateur : calibration/EVOLUTION_IED.md."),
            puces(f"<b>Sens.</b> En configuration de référence, l'IED augmente pour {len(hausses)} des {len(panel)} pays "
                  f"du panel ; pour {len(unanimes)} d'entre eux, aucune configuration ne donne de baisse. Il baisse dans "
                  f"toutes les configurations pour {lettres(len(unanimes_baisse))} pays ({', '.join(unanimes_baisse)}).",
                  f"<b>Composantes.</b> Dans {len(iee_dom)} des {len(hausses)} pays en hausse, la contribution de l'IEE "
                  "dépasse celle de l'IRNR : la baisse des apports d'azote et de phosphore minéraux et de l'empreinte "
                  f"{CO2} porte l'essentiel de la variation, l'empreinte matière totale variant peu.",
                  "<b>Lecture.</b> Une hausse de l'IED traduit une baisse des pressions mesurées par habitant, "
                  "rapportées à des repères fixes ; les niveaux restent sous 1 et l'état biophysique n'est pas mesuré. "
                  "Ces séries bornent des tendances passées ; elles ne renseignent ni la réponse de S au coefficient de "
                  "régulation, ni la dynamique F."
                  + (f" Des ruptures de série ou des définitions différentes touchent des termes de "
                     f"{lettres(len(ruptures))} pays sur la période ({', '.join(ruptures)})." if ruptures else ""))]


def _rang(x):
    return str(int(x)) if x == int(x) else fr(x, 1)


def ecodotations():
    """Section 9 : chiffres lus dans calibration/ecodotations.json."""
    E = [
        h1("9. Écodotations : calibration et exercice monétaire"),
        h2("9.1 Ce que dit le WP"),
        p("Le WP (§4.2) distribue la création monétaire primaire, l'écodotation, entre trois canaux indexés sur l'IED : "
          f"DETA = IED × {B} × <i>c</i> pour l'État ; une dotation des citoyens dont le total, pour chaque État, est égal "
          f"à sa dotation publique ; DENT = IED × {Y} pour chaque entreprise, où {Y} est mesurée par ses charges "
          "d'exploitation (hors impôts, assurances, produits financiers et distribution de bénéfices) lissées sur les "
          "trois dernières années. La dotation globale DG = DTETA + DTCIT + DTENT est un flux brut de création "
          "primaire ; elle ne correspond pas à la masse monétaire en circulation, qui dépend aussi du stock hérité, de "
          f"la fonte et de la création secondaire. Dans la formalisation (§5.5), {B}, <i>c</i> et {Y} définissent le "
          "flux primaire de référence <i>e</i><sub>base</sub>, modulé par le coefficient de régulation : <i>e</i> = "
          "<i>u</i> · <i>e</i><sub>base</sub>, avec <i>u</i> = Φ(IED) ; <i>u</i> = 1 est le régime neutre."),
        p("Sur la calibration de ces flux, le WP pose quatre éléments :"),
        puces("<b>Statut des valeurs.</b> Les valeurs numériques, dont le niveau d'écodotation, sont des ordres de "
              "grandeur exploratoires, un point de départ pour la modélisation et l'analyse de sensibilité ; leur "
              "détermination empirique relève d'un programme de recherche fondé sur l'analyse macroéconomique, les "
              "conditions institutionnelles et les contraintes biophysiques propres à chaque contexte (§4.2).",
              f"<b>{B}.</b> La valeur de 22 000 € (valeur monétaire constante, base 2017, note 47) est un point de "
              "calibration initial susceptible de variation et d'étude de sensibilité ; les montants de création "
              "primaire et d'écodotation sont exprimés à valeur monétaire constante.",
              "<b>Architecture et calibrage.</b> La tripartition des canaux relève de l'architecture du cadre ; leur "
              f"poids relatif — {B}, la parité entre DTCIT et DTETA, l'assiette {Y} — relève du calibrage. La "
              f"définition de l'assiette de {Y}, de sa méthode de lissage et de ses éléments de calibration est une "
              "question de recherche.",
              "<b>Problème E2.</b> La calibration des coefficients d'écodotation est un problème empirique du "
              "programme : sur quelles bases empiriques calibrer ces paramètres, et quels effets différentes valeurs "
              "produisent sur les flux de création primaire, la distribution, les prix, l'activité économique et le "
              "respect des contraintes de viabilité. L'objectif est de caractériser des plages de paramètres "
              "compatibles avec le fonctionnement macroéconomique et biophysique recherché ; la relation entre "
              "création monétaire, production réelle et valeur de la monnaie relève du même problème."),
        p("Le calcul qui suit applique ces formules telles que le WP les écrit. Il fournit à E2 un premier ordre de "
          "grandeur et laisse au calibrage les choix que le WP lui renvoie."),
        h2(f"9.2 Assiette {Y} et méthode"),
        p(f"Le canal entreprises ne demande, pour une zone, que le total de {Y} : DTENT = IED × Σ{Y}. Le module "
          "eh_entreprises l'approche par les comptes nationaux par secteur institutionnel (nasa_10_nf_tr, millions "
          "d'euros courants), qui couvrent les 27 pays sur la même base que le PIB : consommations intermédiaires "
          "(P2), rémunération des salariés (D1) et consommation de capital fixe (P51C), des sociétés non financières "
          "(S11) et financières (S12). Ces charges d'exploitation brutes excluent les charges financières, les impôts "
          "et les distributions de bénéfices ; les sociétés financières y entrent avec leurs seules charges "
          "d'exploitation. Deux variantes sont calculées : sans la consommation de capital fixe ; sociétés non "
          "financières seules. La lecture exige l'unité, la fréquence et le sens attendus de chaque opération et "
          "s'arrête sur une erreur si le schéma de la table change."),
        p(f"C'est un proxy de la somme des {Y} du WP. Il ne comprend pas les entreprises individuelles du secteur des "
          "ménages (S14) ; les consommations intermédiaires y incluent des services d'assurance et d'intermédiation "
          "financière ; la consommation de capital fixe des comptes nationaux est une mesure économique, distincte "
          "des dotations aux amortissements comptables. Ces écarts jouent en sens opposés : leur effet net n'est pas "
          "déterminé sans une table de passage entre comptes d'entreprises, comptes nationaux et postes admissibles "
          "(section 12.2)."),
        p(f"{B} de référence ({eur(ECO['beta_pub_eur_constants_2017'])} constants 2017, section 4) "
          f"est converti en euros courants de {ECO['annee']} par le même déflateur, soit "
          f"{eur(ECO['beta_pub_eur_courants'])}, pour être rapporté au PIB courant (nama_10_gdp). "
          f"{Y} est lissée sur {ECO['annee'] - 2}–{ECO['annee']} selon la même convention de valeur monétaire "
          f"constante que {B} : chaque millésime est exprimé à la valeur de {ECO['annee']} par le déflateur du PIB de "
          "l'UE-27, puis la moyenne des trois millésimes est formée. Le module analyse/ecodotations.py calcule chaque "
          f"canal et DG rapportés au PIB de {ECO['annee']}, au flux de référence (<i>u</i> = 1) et à <i>u</i> = "
          "Φ<sub>0</sub>(IED) de la configuration de référence."),
        p("<b>Comptage par producteur.</b> Les consommations intermédiaires sont comptées chez chaque producteur : un "
          f"bien entre dans les charges de chaque entreprise qui l'achète le long de la chaîne de production. Σ{Y} "
          "dépasse donc la valeur ajoutée d'une économie. Une externalisation ou une scission d'activité, stratégie "
          "de contournement examinée au §7.4 du WP, ajoute un étage à cette chaîne et accroît l'assiette à production "
          "finale inchangée."),
    ]
    E += resultats9()
    E += [
        h2("9.5 Exercice monétaire sur la carte"),
        p("L'exercice s'active dans le panneau EH (case « Afficher les écodotations »), avec une mention qui en indique "
          "l'intérêt et le statut : aucun montant n'est une prévision ni une proposition budgétaire. Une vue "
          "« Écodotations » colore alors la carte selon :"),
        puces("le canal : État, citoyens, entreprises ou dotation globale ;",
              "l'échelle de <i>u</i> : <i>u</i> = 1 (flux de référence), IED national ou IED de zone, pour chacune des "
              "480 configurations ;",
              "la forme de Φ : Φ<sub>0</sub>(<i>z</i>) = <i>z</i>, fonction candidate du WP, et trois formes "
              "construites pour l'illustration, qui vérifient les propriétés minimales que le WP fixe pour Φ "
              "(continue, croissante au sens large, Φ(0) = 0, Φ(1) = 1) : min(<i>z</i>, 1), <i>z</i>², √<i>z</i> ;",
              "l'affichage : euros constants 2017 par habitant, part du PIB, ou rapport au flux de référence (<i>u</i>) ;",
              f"l'assiette {Y} : référence ou l'une des deux variantes."),
        p("Un tableau donne par pays <i>u</i>, le montant par habitant, le total et la part du PIB, avec les codes "
          "Eurostat des comptes utilisés et, quand <i>u</i> dépend de l'IED, ceux des termes de l'IED national ou de "
          f"tous les pays de la zone. Le PIB et {Y} y sont convertis en euros constants 2017 par le déflateur de "
          f"{B}, ce qui laisse inchangées les parts du PIB. Le panneau précise que les échanges commerciaux entre zones "
          f"ne sont pas représentés dans le calcul des écodotations, certains sous-indicateurs (empreinte {CO2}, "
          "empreinte matière) attribuant toutefois aux pays les pressions liées à leur consommation. Trois lentilles "
          "du groupe « Économie Homéostatique » donnent le canal État et le canal entreprises au flux de référence, et "
          "DG à <i>u</i> = IED national. La masse monétaire, la fonte et la création secondaire ne sont pas "
          "représentées (section 3.2). Lien direct de la figure 4 : #eh=monnaie.dg.nat.pib.0.reference.20002."),
        figure("figure4.png", "Figure 4. Exercice monétaire : dotation globale en part du PIB, <i>u</i> = "
               f"Φ<sub>0</sub>(IED national), configuration de référence (réponses du lot {LOT}, version {VERSION})."),
    ]
    return E


def resultats9():
    """Sections 9.3 et 9.4."""
    pays = ["FR", "DE", "LU", "IE", "EL", "PL", "RO"]
    lignes = [["Pays", "DTETA = DTCIT", "DTENT", "DG (<i>u</i> = 1)", "<i>u</i> (IED national)", "DG (<i>u</i> = IED)"]]
    for g in pays:
        r = ECO["pays"][g]
        a = r["assiettes"]["reference"]
        ui = r.get("u_ied")
        lignes.append([NOMS[g], pct(r["u1"]["dteta_pib"]), pct(a["dtent_pib_u1"]), pct(a["dg_pib_u1"]),
                       fr(ui["u"]) if ui else "–", pct(ui["dg_pib_reference"]) if ui else "–"])
    tous = sorted(PAYS_ECO)
    comp = [g for g in COMPLETS if g in PAYS_ECO]
    u_nat = {g: ECO["pays"][g]["u_ied"]["u"] for g in comp}
    lignes.append([f"Pays complets ({len(comp)})", pct(agregat(comp, "dteta")), pct(agregat(comp, "dtent")),
                   pct(agregat(comp, "dg")), "par pays", pct(agregat(comp, "dg", u_nat))])
    lignes.append([f"Ensemble ({len(tous)} pays)", pct(agregat(tous, "dteta")), pct(agregat(tous, "dtent")), pct(agregat(tous, "dg")),
                   "–", "–"])
    sans = sorted(g for g in NOMS if g not in PAYS_ECO)
    dtent = {g: ECO["pays"][g]["assiettes"]["reference"]["dtent_pib_u1"] for g in tous}
    dg = {g: ECO["pays"][g]["assiettes"]["reference"]["dg_pib_u1"] for g in tous}
    lo, hi = min(dtent, key=dtent.get), sorted(dtent, key=dtent.get)
    lu = ECO["pays"]["LU"]["assiettes"]
    s12_lu = lu["reference"]["dtent_pib_u1"] - lu["societes_non_financieres"]["dtent_pib_u1"]
    fr_sans = ECO["pays"]["FR"]["assiettes"]["sans_amortissements"]["dtent_pib_u1"]
    fr_nom = ECO["pays"]["FR"]["assiettes"]["reference"]["dtent_pib_u1_nominal"]
    fr_ref = ECO["pays"]["FR"]["assiettes"]["reference"]["dtent_pib_u1"]
    dg_nom = sum(2 * ECO["pays"][g]["u1"]["dteta_pib"] * ECO["pays"][g]["pib_mio_eur"]
                 + ECO["pays"][g]["assiettes"]["reference"]["y_mio_eur_nominal"] for g in tous) \
        / sum(ECO["pays"][g]["pib_mio_eur"] for g in tous)
    deta = {g: r["u1"]["dteta_pib"] for g, r in ECO["pays"].items() if g in NOMS and r.get("disponible")}

    def spa(g):
        return ECO["pays"][g]["variante_spa"]["dteta_pib"]
    dgs = {g: ECO["pays"][g]["variante_spa"]["dg_pib_u1"] for g in tous if "dg_pib_u1" in ECO["pays"][g].get("variante_spa", {})}
    E = [h2("9.3 Résultats"),
         tableau(lignes, [1.4, 1.1, 0.8, 0.9, 1.1, 1.0]),
         cap(f"Année {ECO['annee']}, en part du PIB. Assiette {Y} de référence, lissée à valeur constante. <i>u</i> = "
             "Φ<sub>0</sub>(IED national), configuration de référence de la section 6 (IBD supposé égal à 1). Les "
             "agrégats rapportent la somme des montants à la somme des PIB. "
             + (f"{', '.join(NOMS[g] for g in sans)} : comptes par secteur de {ECO['annee']} non encore publiés. "
                if sans else "") + f"Lot {LOT}."),
         puces(f"<b>Ordre de grandeur de Σ{Y}.</b> Au flux de référence, DTENT va de {pct(dtent[lo])} du PIB "
               f"({NOMS[lo]}) à {pct(dtent[hi[-2]])} ({NOMS[hi[-2]]}), et atteint {pct(dtent[hi[-1]])} au "
               f"{NOMS[hi[-1]]}, où les charges d'exploitation des sociétés financières, secteur qui comprend les fonds "
               f"d'investissement et les holdings de groupes, représentent {pct(s12_lu)} du PIB. Sur {len(tous)} pays, "
               f"il vaut {pct(agregat(tous, 'dtent'))} du PIB. Sans la consommation de capital fixe, il baisse d'une "
               f"dizaine de points (France : {pct(fr_sans)}). Le lissage à valeur constante relève l'assiette dans "
               f"cette période de hausse des prix : pour la France, {pct(fr_ref)} du PIB contre {pct(fr_nom)} avec la "
               "moyenne des montants courants.",
               f"<b>Dotation globale.</b> Au flux de référence, DG va de {pct(min(dg.values()))} du PIB "
               f"({NOMS[min(dg, key=dg.get)]}) à {pct(max(dg.values()))} ({NOMS[max(dg, key=dg.get)]}), "
               f"{pct(agregat(tous, 'dg'), 1)} sur {len(tous)} pays ({pct(dg_nom, 1)} avec la moyenne des montants "
               f"courants) ; à <i>u</i> = IED national, elle vaut {pct(agregat(comp, 'dg', u_nat))} du PIB des "
               f"{lettres(len(comp))} pays complets dont les comptes sont publiés. Le flux annuel de création primaire "
               "serait ainsi supérieur au PIB ; DG est un flux de création monétaire et le PIB un flux de valeur "
               "ajoutée, leur rapport ne mesure ni un revenu disponible ni une dépense.",
               "<b>Lien avec la fonte.</b> À flux constants, la composante monétaire tend vers M* = (<i>e</i> + R)/λ "
               "(§5.5) : l'ordre de grandeur de DG fixe celui de M* pour une fonte donnée, ce qui relie E2 à E1. Dans "
               "cette relation, λ est, comme au §5.5, le taux de la seule fonte sur encaisses. La fonte sur les "
               "transactions, constitutive de l'architecture et différée dans la formalisation V1.0, dissipe en "
               "proportion du flux de transactions : un rapport M*/PIB calculé avec λ seul décrit le modèle réduit, "
               "non la masse monétaire de l'EH.",
               f"<b>Canal État et harmonisation.</b> DTETA/PIB = {B} / PIB par habitant : le canal État dépasse le PIB "
               f"dès que le PIB par habitant est inférieur à {B} ({eur(ECO['beta_pub_eur_courants'])} "
               f"courants en {ECO['annee']}) — {pct(deta['BG'])} en Bulgarie, {pct(deta['RO'])} en Roumanie, "
               f"contre {pct(deta['LU'])} au Luxembourg. Un même montant par citoyen, appliqué à des économies de "
               "niveaux de production et de prix différents, fait apparaître la question de l'harmonisation du "
               f"système. Avec la variante en SPA (section 4.2), le même pouvoir d'achat par citoyen est reconverti "
               f"pour chaque pays par son indice de niveau des prix de {ECO['annee']} : le canal État passe à "
               f"{pct(spa('BG'))} du PIB en Bulgarie, {pct(spa('RO'))} en Roumanie, {pct(spa('PL'))} en Pologne, "
               f"{pct(spa('FR'))} en France et {pct(spa('LU'))} au Luxembourg ; DG au flux de référence va de "
               f"{pct(min(dgs.values()))} ({NOMS[min(dgs, key=dgs.get)]}) à {pct(max(dgs.values()))} "
               f"({NOMS[max(dgs, key=dgs.get)]}). L'écart entre pays se resserre ; il demeure, porté par le PIB par "
               "habitant en volume et par l'assiette des entreprises.")]
    mz = ZONE["mesures_par_habitant"]
    zc = [g for g in ZONE["pays"] if g in PAYS_ECO]
    def dg_zone(g):
        return IED_ZONE * ECO["pays"][g]["assiettes"]["reference"]["dg_pib_u1"]
    def dg_nat(g):
        return ECO["pays"][g]["u_ied"]["dg_pib_reference"]
    E += [h2("9.4 IED de zone"),
          p("Dans l'exercice, l'IED qui sert aux dotations peut être celui de chaque pays ou celui de la zone "
            f"économique. La zone est ici formée des {lettres(len(ZONE['pays']))} pays qui disposent de toutes les "
            f"séries ({', '.join(ZONE['pays'])}) : c'est un sous-ensemble de disponibilité, non l'UE-27, dont Eurostat "
            "ne publie pas les comptes par secteur. Les grandeurs physiques par habitant de la zone sont agrégées "
            f"d'abord — moyenne des valeurs nationales pondérée par la population de {ECO['annee']} — puis normalisées "
            f"et agrégées comme celles d'un pays, pour les {SENS['configurations']} configurations. C'est un proxy : une "
            f"valeur nationale reprise d'une année antérieure est pondérée par la population de {ECO['annee']}."),
          p(f"En configuration de référence, l'IED de la zone vaut {fr(IED_ZONE)} (empreinte {CO2} de "
            f"{fr(mz['iee_co2_empreinte'], 1)} t/hab, azote fixé {fr(mz['iee_azote'], 1)} kg/hab, phosphore minéral "
            f"{fr(mz['iee_phosphore'], 1)} kg/hab, empreinte matière totale {fr(mz[CLE_IRNR], 1)} t/hab). Avec un "
            f"<i>u</i> commun, la dotation ne dépend plus, d'un pays à l'autre, que de {B}, de la population et de {Y} : "
            f"par rapport à l'échelle nationale, DG passe de {pct(dg_nat('RO'))} à {pct(dg_zone('RO'))} du PIB pour la "
            f"Roumanie et de {pct(dg_nat('PT'))} à {pct(dg_zone('PT'))} pour le Portugal ; sur les "
            f"{lettres(len(zc))} pays de la zone dont les comptes sont publiés, elle vaut "
            f"{pct(agregat(zc, 'dg', {g: IED_ZONE for g in zc}))} du PIB. Le choix d'échelle déplace la distribution "
            "entre les pays de la zone, et l'effet d'une amélioration locale sur <i>u</i> dépend alors de sa part dans "
            "le total ; il rejoint le principe d'attribution de l'IEE et la définition des zones tampons (section 7)."),
          ]
    return E


def main():
    doc = Doc(SORTIE)
    doc.multiBuild(couverture() + sommaire() + corps())
    print(f"{SORTIE.name} : {doc.page} pages")


if __name__ == "__main__":
    main()
