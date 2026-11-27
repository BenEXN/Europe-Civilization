"""Rapport d'étape de la calibration empirique de l'Économie Homéostatique (PDF).

  python3 calibration/rapport/rapport_etape.py

Écrit calibration/Rapport_etape_calibration_EH_2026-11-27_v1.3.pdf. Les figures sont dans calibration/rapport/figures/.
Demande reportlab et les polices DejaVu (Sans, Serif, Math TeX Gyre)."""

from __future__ import annotations

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
SORTIE = ICI.parent / "Rapport_etape_calibration_EH_2026-11-27_v1.3.pdf"
VERSION = "1.3"
DATE = "27 novembre 2026"
PIED = f"Calibration empirique de l'Économie Homéostatique — rapport d'étape v{VERSION}, {DATE}"
LOT = "calibration-eh-20261127T1229Z"          # chiffres des sections 4 à 6
LOT_ECO = "calibration-eh-20261127T1820Z"      # chiffres de la section 9

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
        Spacer(1, 48 * mm),
        Paragraph("Calibration empirique de l'Économie Homéostatique", S["titre"]),
        Paragraph("Rapport d'étape : démarche, choix méthodologiques, résultats et suite du travail", S["soustitre"]),
        Spacer(1, 10),
        Paragraph("Programme de recherche de l'Économie Homéostatique (EH)<br/>Benjamin Albouy, auteur du programme de "
                  f"recherche<br/>{DATE} — version {VERSION}", S["meta"]),
        Spacer(1, 10),
        Paragraph("Version 1.3 : ajoute les écodotations (section 9) — ce que le WP dit de leur calibration, l'assiette "
                  f"{Y}, leur ordre de grandeur rapporté au PIB, l'IED de zone et l'exercice monétaire sur la carte ; "
                  "les sections suivantes sont renumérotées. Version 1.2 : ajoute la visualisation sur la carte "
                  "(section 8) et les scores des composantes IEE et IRNR. Version 1.1 : révisée après la "
                  "contre-expertise indépendante ASTRA-EC du 27 novembre 2026 (section 10.3).<br/>"
                  "Dépôt de travail : github.com/BenEXN/Europe-Civilization (branche principale), lots de référence "
                  f"{LOT} (sections 4 à 6) et {LOT_ECO} (section 9).<br/>"
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
            "valeur arrondie de 22 000 € reste défendable ; un chiffre reproductible demande d'indiquer le lot "
            "d'extraction."),
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
                "confirmé les montants 2017 et 2025 à l'euro près, et la contre-expertise les a recalculés "
                "indépendamment pour les onze années.")]
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
            "27 pays ; sa ventilation par catégorie de matières l'est pour 15, le plus souvent jusqu'à 2023."),
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
                   ["IRNR", "Empreinte matière non renouvelable (t/hab)", "7,2 t",
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
              "grandeur globale fixée, 8 milliards réduisent la part par habitant de 12,5 %. Rapportés à la seule part "
              "non renouvelable, les repères matière donnent un rapport au repère inférieur ou égal à celui de "
              "l'empreinte totale. L'égalité par habitant est une règle distributive ; responsabilités historiques et "
              "besoins différenciés appellent d'autres règles, à comparer."),
          p("<b>Inconnues déclarées.</b> Eau douce : le repère d'O'Neill (574 m³/hab/an d'eau bleue) s'applique à une "
            "empreinte de consommation, sans série nationale homogène ; le WEI+ mesure une consommation nette rapportée "
            "aux ressources renouvelables du territoire, publiée aussi par bassin et par saison, avec un seuil de stress "
            "conventionnel (20 %). L'eau est tenue hors de l'IED par choix de construction, pour ne pas agréger une "
            "tension territoriale à des repères globaux par habitant ; son intégration par bassin est une piste "
            f"ouverte. Artificialisation : aucun repère par habitant retenu. Gaz autres que le {CO2} : repère propre à "
            "établir. IBD : traité comme une inconnue, explorée par scénarios (section 6.2)."),
          h2("6.2 Choix testés"),
          p("Le WP fixe l'échelle, la valeur 1 et le sens de la transformation, mais pas la forme de la fonction de "
            "normalisation ni la place des repères 0 et 2. Trois formes candidates, construites pour l'analyse, sont "
            "testées : linéaire (2 − <i>x</i>/<i>T</i>, nulle à deux fois le repère), ratio (<i>T</i>/<i>x</i>, "
            "plafonnée à 2) et hyperbolique (2/(1 + <i>x</i>/<i>T</i>), jamais nulle) ; le placement des valeurs 0 et "
            "2 qu'impose chaque forme est un choix numérique. Elles sont croisées avec quatre fonctions d'agrégation "
            "(moyenne géométrique de la V1.0, moyennes de puissance ρ = −1 et ρ = −5, minimum), appliquées à la fois "
            "entre les sous-indicateurs de l'IEE et entre les composantes de l'IED, quatre jeux de pondérations, les "
            "deux repères IRNR et cinq valeurs de l'IBD communes à tous les pays (0 ; 0,5 ; 1 ; 1,5 ; 2), soit 480 "
            "configurations, qui donnent 196 vecteurs de scores distincts. Trois expériences complètent la grille : "
            "l'agrégation modifiée à un seul étage ; un IBD propre à un pays (0,5 pour ce pays, 1 pour les autres) ; "
            "l'IRNR calculé sur la RMC totale, périmètre identique à celui des repères. La forme hyperbolique sert de "
            "configuration de référence pour la présentation, parce qu'elle est définie sans troncature sur tout le "
            "domaine."),
          p("Règles de mesure : une série absente pour 2023 est remplacée par la plus récente des trois années "
            "précédentes ; une somme et un ratio sont formés à partir de termes de la même année, population comprise ; "
            "les valeurs portant un code Eurostat sont retenues et signalées. Les corrélations de rang sont calculées "
            "sur les scores non arrondis, avec rangs moyens en cas d'ex æquo, et sont sans objet quand l'IED est "
            "identique pour tous les pays."),
          h2("6.3 Résultats"),
          tableau([["Pays", "IED (référence)", "Min (IBD = 1)", "Max (IBD = 1)", "Min (enveloppe)", "Max (enveloppe)"]] + [
              [a, b, "0,00", c, "0,00", d] for a, b, c, d in (
                  ("PT", "0,82", "0,86", "1,22"), ("DE", "0,79", "0,84", "1,19"), ("FR", "0,77", "0,82", "1,16"),
                  ("CZ", "0,75", "0,80", "1,14"), ("SI", "0,73", "0,79", "1,12"), ("AT", "0,73", "0,79", "1,12"),
                  ("HR", "0,70", "0,76", "1,08"), ("LT", "0,60", "0,68", "0,96"), ("RO", "0,57", "0,65", "0,92"))],
              [0.8, 1.1, 1.0, 1.0, 1.0, 1.0]),
          cap("Année 2023. Référence : normalisation hyperbolique, moyenne géométrique aux deux étages, poids égaux, "
              "repère IRNR de 7,2 t, IBD supposé égal à 1. L'enveloppe porte sur toute la grille, IBD de 0 à 2 compris : "
              "c'est une enveloppe de scénarios, non un intervalle de confiance. Neuf pays disposent de toutes les "
              "séries : c'est un sous-ensemble de disponibilité, dont les moyennes et les rangs décrivent ces pays "
              "seulement."),
          tableau([["Choix", "Option", "IED moyen", "Corrélation de rang", "Paires inversées"],
                   ["Normalisation", "linéaire : 2 − <i>x</i>/<i>T</i>", "0,00", "sans objet", "–"],
                   ["", "ratio : <i>T</i>/<i>x</i>", "0,59", "0,983", "SI/AT"],
                   ["", "hyperbolique : 2/(1 + <i>x</i>/<i>T</i>)", "0,72", "1,000", "–"],
                   ["Agrégation, deux étages", "moyenne géométrique (V1.0)", "0,72", "1,000", "–"],
                   ["", "CES ρ = −1 (harmonique)", "0,67", "1,000", "–"],
                   ["", "CES ρ = −5", "0,53", "0,700", "DE/FR, DE/CZ, DE/SI, DE/AT, DE/HR, CZ/SI, AT/HR, LT/RO"],
                   ["", "minimum", "0,37", "0,717", "DE/FR, DE/CZ, DE/SI, DE/AT, DE/HR, AT/HR, LT/RO"],
                   ["Pondérations (IBD, IEE, IRNR)", "égaux (V1.0)", "0,72", "1,000", "–"],
                   ["", "IBD renforcé (2, 1, 1)", "0,78", "1,000", "–"],
                   ["", "IEE renforcé (1, 2, 1)", "0,67", "0,817", "FR/CZ, FR/SI, FR/AT, CZ/SI, CZ/AT, SI/AT, LT/RO"],
                   ["", "IRNR renforcé (1, 1, 2)", "0,71", "0,933", "DE/FR, SI/HR, AT/HR"],
                   ["IBD commun", "0,0", "0,00", "sans objet", "–"],
                   ["", "0,5", "0,57", "1,000", "–"],
                   ["", "1,0", "0,72", "1,000", "–"],
                   ["", "1,5", "0,82", "1,000", "–"],
                   ["", "2,0", "0,90", "1,000", "–"],
                   ["Agrégation, IEE seule", "CES ρ = −1 (harmonique)", "0,70", "0,983", "DE/FR"],
                   ["", "CES ρ = −5", "0,67", "0,767", "DE/FR, DE/CZ, DE/SI, DE/HR, SI/HR, AT/HR"],
                   ["", "minimum", "0,63", "0,717", "DE/FR, DE/CZ, DE/SI, DE/HR, CZ/HR, SI/HR, AT/HR"],
                   ["Agrégation, IED seule", "CES ρ = −1 (harmonique)", "0,69", "1,000", "–"],
                   ["", "CES ρ = −5", "0,62", "0,833", "FR/CZ, FR/SI, FR/AT, CZ/SI, CZ/AT, LT/RO"],
                   ["", "minimum", "0,53", "0,817", "FR/CZ, FR/SI, FR/AT, CZ/SI, CZ/AT, SI/AT, LT/RO"]],
                  [1.25, 1.55, 0.6, 0.8, 2.2]),
          cap("Chaque ligne fait varier un seul choix à partir de la référence. Avec la moyenne géométrique, un IBD "
              "commun multiplie tous les scores par un même facteur : le classement est invariant par construction."),
          tableau([["Pays", "IED de référence", "IED avec IBD = 0,5", "Rang de référence", "Rang du scénario"]] + [
              list(r) for r in (("PT", "0,82", "0,65", "1", "7"), ("DE", "0,79", "0,63", "2", "7"),
                                ("FR", "0,77", "0,61", "3", "7"), ("CZ", "0,75", "0,59", "4", "8"),
                                ("SI", "0,73", "0,58", "5", "8"), ("AT", "0,73", "0,58", "6", "8"),
                                ("HR", "0,70", "0,55", "7", "9"), ("LT", "0,60", "0,47", "8", "9"),
                                ("RO", "0,57", "0,45", "9", "9"))], [0.8, 1.1, 1.2, 1.1, 1.1]),
          cap("IBD propre à un pays : 0,5 pour ce pays, 1 pour les autres. Scénario hypothétique ; aucune de ces valeurs "
              "n'est une observation."),
          p("<b>Variante de périmètre.</b> Rapportée aux repères, qui portent sur le même périmètre, la RMC totale "
            "(biomasse comprise) permet de calculer l'IED de référence pour 20 pays : de 0,90 (NL) à 0,52 (IE) avec le "
            "repère de 7,2 t. L'IRNR y mesure alors la pression matérielle totale, et non la seule consommation de "
            "ressources non renouvelables."),
          h2("6.4 Composantes de l'IED"),
          p("L'analyse publie aussi, depuis la version 1.2, les scores des composantes IEE et IRNR pour chaque pays qui "
            "dispose de leurs séries : l'IEE selon la normalisation et l'agrégation entre ses sous-indicateurs, l'IRNR "
            "selon la normalisation et le repère. L'IEE est ainsi calculé pour 20 pays et l'IRNR pour 15. En "
            "configuration de référence, l'IEE va de 0,76 (Pays-Bas) à 0,26 (Irlande), l'IRNR de 0,94 (Malte) à 0,44 "
            "(Roumanie)."),
          tableau([["Pays", "IED (référence)", "IEE", "IRNR"]] + [
              list(r) for r in (("PT", "0,82", "0,72", "0,77"), ("DE", "0,79", "0,65", "0,76"),
                                ("FR", "0,77", "0,50", "0,91"), ("CZ", "0,75", "0,56", "0,75"),
                                ("SI", "0,73", "0,59", "0,67"), ("AT", "0,73", "0,63", "0,61"),
                                ("HR", "0,70", "0,44", "0,78"), ("LT", "0,60", "0,32", "0,65"),
                                ("RO", "0,57", "0,42", "0,44"))], [0.8, 1.1, 1.1, 1.1]),
          cap("Configuration de référence, IBD supposé égal à 1. L'IED est la moyenne géométrique de l'IBD, de l'IEE et "
              "de l'IRNR ; un test du dépôt vérifie que les trois colonnes satisfont cette relation."),
          p("Dans huit des neuf pays complets, l'IEE est inférieur à l'IRNR ; l'Autriche fait exception. Avec les "
            "repères retenus, la composante des pressions sur les écosystèmes est celle qui tire le plus souvent l'IED "
            "vers le bas."),
          h2("6.5 Constats"),
          puces("<b>Niveau 1.</b> Avec un IBD supposé au plus égal à 1, l'IED ne dépasse pas 0,86 dans la grille ; il "
                f"atteint 1,22 avec un IBD supposé de 2. L'empreinte {CO2} dépasse son repère d'un facteur 2,5 à 5,4. Le "
                "franchissement du niveau 1 dépend donc de la valeur supposée de l'IBD.",
                "<b>Annulation.</b> 224 configurations sur 480 donnent un IED nul pour tous les pays : 160 avec la "
                "normalisation linéaire, qui supprime dans l'échantillon tout pouvoir de discrimination, et 64 avec un "
                "IBD supposé nul. Pour ρ ≤ 0, un zéro est transmis à l'IED, conformément au §6.2.",
                "<b>Compensation interne.</b> Avec une moyenne, un sous-indicateur sous son repère (le phosphore en "
                "Allemagne) compense en partie le dépassement des autres. C'est une propriété de l'agrégation ; le "
                "choix de la fonction d'agrégation se pose aux deux étages (T3), et l'expérience à un seul étage montre "
                "que chacun déplace le classement.",
                "<b>Ce qui déplace le classement.</b> La normalisation ratio inverse la Slovénie et l'Autriche "
                "(corrélation 0,983) ; les agrégations à plus faible substituabilité et les pondérations modifient "
                "davantage le classement (corrélations de 0,70 à 0,98).",
                "<b>Poids de l'inconnue IBD.</b> Un IBD commun change les niveaux sans changer le classement, par "
                "construction. Un IBD propre à un pays le déplace : à 0,5 pour PT, les autres à 1, ce pays passe du "
                "rang 1 au rang 7. Tant que l'IBD n'est pas mesuré, les niveaux d'IED et les classements sont "
                "conditionnels à cette hypothèse.")]
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
                f"<b>Rapports aux repères.</b> Chaque sous-indicateur (empreinte {CO2}, empreinte matière non "
                "renouvelable, empreinte matière totale, azote, phosphore) peut colorer la carte par son rapport à un "
                "repère, pour tous les pays qui disposent de la série.",
                "<b>Lentilles.</b> Un groupe « Économie Homéostatique » du sélecteur de lentilles donne ces indices et "
                "ces rapports en configuration de référence. L'IBD y figure, désactivé : il n'est pas mesuré et "
                "n'entre dans les scénarios que comme valeur supposée.",
                "<b>Écodotations.</b> Un exercice monétaire, à activer, est décrit en section 9.5."),
          p("L'échelle de couleur des indices est fixe sur [0, 2], avec la valeur 1 au centre, pour que la position "
            "d'un pays par rapport au niveau de référence reste lisible d'un scénario à l'autre. Les rapports aux "
            "repères sont en échelle logarithmique, centrée sur 1."),
          figure("figure1.png", "Figure 1. Panneau EH et carte de l'IED en configuration de référence (lot "
                 "calibration-eh-20261127T1414Z). Les neuf pays colorés sont ceux qui disposent de toutes les séries."),
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
            "est recalculée, à l'exception du rapport de la RMC totale aux repères matière (variante de périmètre, "
            f"section 6.3) et de la conversion du PIB et de {Y} en euros constants 2017 (section 9.5). Les découpages "
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
                   ["Analyse de sensibilité", "analyse/sensibilite_ied.py"],
                   ["Écodotations rapportées au PIB et IED de zone", "analyse/ecodotations.py"],
                   ["Contrôle, archivage et rejeu hors réseau d'un lot", "analyse/lot_calibration.py"],
                   ["Résultats et provenance (adresse, date, SHA-256), référence du lot, historique des incidents",
                    "calibration/ et calibration/provenance/"],
                   ["Archive des réponses brutes de chaque lot", "publications GitHub (Releases), nom du lot"],
                   ["Note de synthèse ; analyse de sensibilité",
                    "calibration/NOTE_SYNTHESE.md ; calibration/SENSIBILITE_IED.md"],
                   ["Recalcul mensuel et à chaque modification du code", ".github/workflows/eh-calibration.yml"],
                   ["Découpages transfrontaliers et données de la carte",
                    "pipeline/sources/eh_decoupages.py ; analyse/carte_eh.py ; web/data/eh.json"],
                   ["Carte : panneau, couches et lentilles ; publication",
                    "web/js/ext/eh/ ; .github/workflows/eh-carte.yml"],
                   ["Rapport d'étape (ce document)", "calibration/rapport/rapport_etape.py"],
                   ["Tests", "tests/test_eh_*.py ; tests/test_sensibilite_ied.py ; tests/test_carte_eh.py"]],
                  [3.0, 2.8]),
          Spacer(1, 6),
          p("Un lot n'est enregistré que si les tables requises sont présentes et à jour, si les contrôles après calcul "
            "passent et si son rejeu hors réseau redonne les mêmes séries ; sinon le dernier lot publié reste en place. "
            "Une table accessoire en échec est publiée comme périmée, avec la date de sa dernière réponse. Les chiffres "
            "cités par la note de synthèse sont vérifiés contre chaque lot."),
          p(f"Les chiffres des sections 4 à 6 sont ceux du lot {LOT}. Les lots suivants, jusqu'à {LOT_ECO}, redonnent "
            "les mêmes séries ; seules changent les dates de téléchargement, calibration-eh-20261127T1414Z ajoute les "
            f"scores des composantes (section 6.4) et {LOT_ECO} les écodotations (section 9)."),
          h2("10.2 Évaluation intermédiaire interne"),
          p("Avant la version 1.0, l'ensemble a été relu comme pour une présentation : tests du dépôt, calculs refaits à "
            "la main pour la France, codes Eurostat confrontés à leurs libellés officiels, chiffres de la note de "
            "synthèse confrontés aux fichiers de données, repères confrontés à leurs sources (tableau 1 d'O'Neill et "
            "al. ; résumé et §5.2 de Bringezu). Cette relecture avait conduit à corriger le statut du repère "
            "phosphore, la description du corridor de Bringezu, la mention de la population de référence d'O'Neill et "
            "le suivi des années de remplacement."),
          h2("10.3 Contre-expertise indépendante et corrections"),
          p("La version 1.0 et le dépôt (commit 50a54fd) ont fait l'objet d'une contre-expertise scientifique, "
            "méthodologique et informatique indépendante (ASTRA-EC, 27 novembre 2026). Elle a retrouvé exactement les "
            f"16 réponses Eurostat par leurs empreintes, les 288 configurations et leurs 2 592 scores, et {B} pour les "
            "onze années, par un calcul indépendant. Son verdict : corrections majeures nécessaires avant toute "
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
                  [1.0, 5.0])]
    # 11 --------------------------------------------------------------------------------------------------------
    E += [h1("11. Limites connues"),
          puces("Une seule année (2023) et neuf pays complets : la ventilation MF2–MF4 de la RMC manque pour onze pays, "
                "les séries d'azote et de phosphore pour six, les deux pour la Grèce ; la Slovénie y figure avec ses "
                "séries agricoles de 2021. Les classements portent sur un petit sous-ensemble de disponibilité, et rien "
                "n'est encore dit des évolutions.",
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
                f"Écodotations : {Y} est approchée par les comptes nationaux par secteur, dont les consommations "
                "intermédiaires comprennent les services d'assurance et une part de services financiers ; une seule "
                "année ; flux rapportés au PIB, sans représentation des prix, des comportements ni de la masse "
                "monétaire.")]
    # 12 --------------------------------------------------------------------------------------------------------
    E += [h1("12. Ce qu'il reste à faire"),
          h2("12.1 Ordre de travail retenu"),
          puces("<b>Compléter les découpages.</b> Archiver les districts hydrographiques (WISE WFD 2022) et les régions "
                "biogéographiques (version 2016) téléchargés depuis le site de l'Agence européenne pour "
                "l'environnement, puis les intégrer à la carte.",
                "<b>Dynamique F.</b> Les données décrivent l'évolution passée de S ; elles permettront au mieux de "
                "borner des tendances pour P-F1, pas d'estimer la réponse de S à <i>u</i>. Délais, révisions et pertes "
                "d'information sont à tester dans un modèle aux entrées explicites avant tout branchement sur une "
                "règle monétaire.",
                "<b>Prise de contact avec des chercheurs</b>, appuyée sur la note de synthèse, l'analyse de "
                "sensibilité, la contre-expertise, la carte et le présent rapport."),
          h2("12.2 Points ouverts à traiter"),
          puces("Définir l'objet mesuré par l'IRNR : correspondance entre flux et stocks, références et horizons ; "
                "étendre l'analyse aux pays sans ventilation de la RMC et à plusieurs années.",
                "Choisir un principe d'attribution cohérent pour l'IEE (consommation ou territoire), en lien avec les "
                "zones tampons.",
                "Définir l'IBD avec des écologues : sources d'état (article 17 de la directive Habitats), seuil d'O'Neill "
                "et al. pour l'intégrité de la biosphère (appropriation humaine de la production primaire, 2,62 t "
                "C/hab), sans série nationale chez Eurostat.",
                "Définir les zones tampons et la manière dont leur état entre dans l'IED des zones qu'elles relient.",
                "Étudier le WEI+ par bassin et par saison pour intégrer l'eau.",
                "Identifier des repères, ou déclarer l'inconnue, pour l'artificialisation, la fragmentation et les gaz "
                f"autres que le {CO2}.",
                f"Comparer le déflateur du PIB à une variante en parités de pouvoir d'achat pour {B} ; décider d'une "
                "règle de gel ou de lissage ; retenir le millésime 2025 quand ses valeurs ne porteront plus de code "
                "provisoire, si ce choix est retenu.",
                f"Calibrer les écodotations (E2), avec la fonte (E1) : assiette {Y}, parité entre DTCIT et DTETA, "
                f"harmonisation de {B} entre économies de niveaux de production et de prix différents, échelle de "
                "l'IED servant aux dotations."),
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
            "ASTRA-EC (2026). <i>Contre-expertise scientifique, méthodologique et informatique — Économie Homéostatique, "
            "Europe-Civilization</i>. Rapport intermédiaire indépendant, 27 novembre 2026, commit 50a54fd.",
            "Aubin, J.-P. (1991). <i>Viability theory</i>. Birkhäuser.",
            "Bringezu, S. (2015). Possible target corridor for sustainable use of global material resources. "
            "<i>Resources</i>, 4(1), 25–54. https://doi.org/10.3390/resources4010025",
            "CIEM (ICES). Zones statistiques et écorégions, diffusées par Marine Regions (Flanders Marine Institute, "
            "VLIZ), service WFS, CC BY 4.0. https://www.marineregions.org",
            "Eurostat. Tables gov_10a_main, nama_10_pe, nama_10_gdp, nasa_10_nf_tr, env_ac_mfa, env_ac_rme, "
            "env_ac_ainah_r2, cli_gge_foot, aei_pr_gnb, sdg_06_60, lan_lcv_ovw, sdg_11_32, env_bio2, env_bio3, "
            "env_bio4, sdg_15_42, et leurs métadonnées (notamment env_ac_rme, env_ac_ainah_r2, sdg_06_60, env_biodiv). "
            f"API de diffusion, lots {LOT} et {LOT_ECO} ; provenance détaillée dans calibration/provenance/.",
            "Agence européenne pour l'environnement. <i>Use of freshwater resources in Europe</i> ; <i>Conservation "
            "status of habitats under the EU Habitats Directive</i>.",
            "O'Neill, D. W., Fanning, A. L., Lamb, W. F., &amp; Steinberger, J. K. (2018). A good life for all within "
            "planetary boundaries. <i>Nature Sustainability</i>, 1, 88–95. https://doi.org/10.1038/s41893-018-0021-4",
            "Europe-Civilization (lmveprog), d'après usaciv (A. Karpathy) et franceciv (M. Astruc). Licence MIT. "
            "https://github.com/lmveprog/Europe-Civilization"):
        E.append(Paragraph(t, S["ref"]))
    del R
    return E


def ecodotations():
    """Section 9 (version 1.3)."""
    return [
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
          "(P2), rémunération des salariés (D1) et consommation de capital fixe (P51C, proche des dotations aux "
          "amortissements), des sociétés non financières (S11) et financières (S12). Ces charges d'exploitation brutes "
          "excluent les charges financières, les impôts et les distributions de bénéfices ; les sociétés financières y "
          "entrent avec leurs seules charges d'exploitation. Deux variantes sont calculées : sans la consommation de "
          "capital fixe ; sociétés non financières seules. La lecture exige le sens attendu de chaque opération et "
          "s'arrête sur une erreur si le schéma de la table change."),
        p(f"{B} de référence (22 589 € constants 2017, section 4) est converti en euros courants de 2023 par le même "
          f"déflateur, soit 27 242 €, pour être rapporté au PIB courant (nama_10_gdp). {Y} est lissée sur 2021–2023 "
          "(moyenne des montants courants). Le module analyse/ecodotations.py calcule chaque canal et DG rapportés au "
          "PIB de 2023, au flux de référence (<i>u</i> = 1) et à <i>u</i> = Φ<sub>0</sub>(IED) de la configuration de "
          "référence."),
        p("<b>Comptage par producteur.</b> Les consommations intermédiaires sont comptées chez chaque producteur : un "
          f"bien entre dans les charges de chaque entreprise qui l'achète le long de la chaîne de production. Σ{Y} "
          "dépasse donc la valeur ajoutée d'une économie ; une scission d'activité, stratégie de contournement "
          "examinée au §7.4 du WP, ajoute un étage à cette chaîne."),
        h2("9.3 Résultats"),
        tableau([["Pays", "DTETA = DTCIT", "DTENT", "DG (<i>u</i> = 1)", "<i>u</i> (IED national)",
                  "DG (<i>u</i> = IED)"],
                 ["France", "66 %", "127 %", "259 %", "0,77", "198 %"],
                 ["Allemagne", "53 %", "125 %", "231 %", "0,79", "183 %"],
                 ["Luxembourg", "22 %", "288 %", "333 %", "–", "–"],
                 ["Irlande", "28 %", "126 %", "181 %", "–", "–"],
                 ["Grèce", "126 %", "80 %", "332 %", "–", "–"],
                 ["Pologne", "136 %", "119 %", "392 %", "–", "–"],
                 ["Roumanie", "162 %", "104 %", "428 %", "0,57", "242 %"],
                 ["Neuf pays complets", "66 %", "125 %", "257 %", "par pays", "196 %"],
                 ["26 pays", "70 %", "126 %", "266 %", "–", "–"]], [1.4, 1.1, 0.8, 0.9, 1.1, 1.0]),
        cap(f"Année 2023, en part du PIB. Assiette {Y} de référence. <i>u</i> = Φ<sub>0</sub>(IED national), "
            "configuration de référence de la section 6 (IBD supposé égal à 1). Les agrégats rapportent la somme des "
            "montants à la somme des PIB. La Bulgarie n'a pas encore publié ses comptes par secteur de 2023. Lot "
            f"{LOT_ECO}."),
        puces(f"<b>Ordre de grandeur de Σ{Y}.</b> Au flux de référence, DTENT va de 80 % du PIB (Grèce) à 162 % "
              "(Malte), et atteint 288 % au Luxembourg, où les charges d'exploitation des sociétés financières, secteur qui "
              "comprend les fonds d'investissement et les holdings de groupes, représentent 131 % du PIB. Sur 26 pays, il vaut "
              "126 % du PIB. Sans la consommation de capital fixe, il baisse d'une dizaine de points (France : 117 %).",
              "<b>Dotation globale.</b> Au flux de référence, DG va de 181 % du PIB (Irlande) à 428 % (Roumanie), "
              "266 % sur 26 pays ; à <i>u</i> = IED national, elle vaut 196 % du PIB des neuf pays complets. La "
              "création primaire annuelle serait ainsi supérieure au PIB. À flux constants, la composante monétaire "
              "tend vers M* = (<i>e</i> + R)/λ (§5.5) : l'ordre de grandeur de DG fixe celui de M* pour une fonte "
              "donnée, ce qui relie E2 à E1.",
              f"<b>Canal État et harmonisation.</b> DTETA/PIB = {B} / PIB par habitant : le canal État dépasse le PIB "
              f"dès que le PIB par habitant est inférieur à {B} (27 242 € courants en 2023) — 185 % en Bulgarie, "
              "162 % en Roumanie, contre 22 % au Luxembourg. Un même montant par citoyen, appliqué à des économies de "
              "niveaux de production et de prix différents, fait apparaître la question de l'harmonisation du "
              "système ; une variante en parités de pouvoir d'achat en réduirait l'écart."),
        h2("9.4 IED de zone"),
        p("Dans l'exercice, l'IED qui sert aux dotations peut être celui de chaque pays ou celui de la zone "
          "économique. La zone est ici formée des neuf pays qui disposent de toutes les séries (Autriche, Tchéquie, "
          "Allemagne, France, Croatie, Lituanie, Portugal, Roumanie, Slovénie) : c'est un sous-ensemble de "
          "disponibilité, non l'UE-27, dont Eurostat ne publie pas les comptes par secteur. Les grandeurs physiques "
          "par habitant de la zone sont agrégées d'abord — moyenne des valeurs nationales pondérée par la population "
          "de 2023 — puis normalisées et agrégées comme celles d'un pays, pour les 480 configurations. C'est un "
          "proxy : une valeur nationale reprise d'une année antérieure est pondérée par la population de 2023."),
        p(f"En configuration de référence, l'IED de la zone vaut 0,73 (empreinte {CO2} de 7,0 t/hab, azote fixé "
          "22,4 kg/hab, phosphore minéral 1,6 kg/hab, empreinte matière non renouvelable 12,3 t/hab). Avec un <i>u</i> "
          f"commun, la dotation ne dépend plus, d'un pays à l'autre, que de {B}, de la population et de {Y} : par "
          "rapport à l'échelle nationale, DG passe de 242 % à 314 % du PIB pour la Roumanie et de 275 % à 245 % pour "
          "le Portugal. Le choix d'échelle déplace la distribution entre les pays de la zone ; il rejoint le principe "
          "d'attribution de l'IEE et la définition des zones tampons (section 7)."),
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
          f"Eurostat des termes utilisés. Le PIB et {Y} y sont convertis en euros constants 2017 par le déflateur de "
          f"{B}, ce qui laisse inchangées les parts du PIB. Le panneau précise que les échanges commerciaux entre zones "
          f"ne sont pas représentés dans le calcul des écodotations, certains sous-indicateurs (empreinte {CO2}, "
          "empreinte matière) attribuant toutefois aux pays les pressions liées à leur consommation. Trois lentilles "
          "du groupe « Économie Homéostatique » donnent le canal État et le canal entreprises au flux de référence, et "
          "DG à <i>u</i> = IED national. La masse monétaire, la fonte et la création secondaire ne sont pas "
          "représentées (section 3.2). Lien direct de la figure 4 : #eh=monnaie.dg.nat.pib.0.reference.20002."),
        figure("figure4.png", "Figure 4. Exercice monétaire : dotation globale en part du PIB, <i>u</i> = "
               f"Φ<sub>0</sub>(IED national), configuration de référence (lot {LOT_ECO})."),
    ]


def main():
    doc = Doc(SORTIE)
    doc.multiBuild(couverture() + sommaire() + corps())
    print(f"{SORTIE.name} : {doc.page} pages")


if __name__ == "__main__":
    main()
