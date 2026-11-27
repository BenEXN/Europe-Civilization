# Données publiques pour les composantes de S — note de synthèse

*Économie Homéostatique, WP V1.0 — calibration empirique. Relevé du 27 novembre 2026, données Eurostat ; chiffres cités contrôlés contre chaque nouveau lot (`provenance/controle_note.json`).*

<!-- etat-note -->
> État des chiffres cités : conformes au lot de calibration courant (contrôle du 2026-11-27).
<!-- /etat-note -->

## Objet

Le vecteur d'état biophysique S = (IBD, IEE, IRNR) de la formalisation V1.0 (§5.5) est constitué de trois indicateurs normalisés sur [0, 2], agrégés dans l'IED par moyenne géométrique (§6.2). Le WP précise que chacun est le résultat d'une chaîne de construction — données, sous-indicateurs, protocoles, normalisation — dont la spécification reste à établir.

Cette note fait l'inventaire des séries publiques disponibles à l'échelle des États membres de l'UE-27 pour alimenter cette chaîne, et des contraintes qu'elles imposent à sa spécification. Elle ne calcule aucun des trois indicateurs : les références par habitant, les repères 0, 1 et 2 de la normalisation et, pour l'IEE et l'IBD, l'agrégation interne relèvent du cadre.

Les séries sont téléchargées et recalculées par le workflow « Calibration EH » (sources `eh_irnr`, `eh_iee`, `eh_ibd`). Les fichiers de résultats et la provenance de chaque téléchargement (adresse, date, empreinte SHA-256) sont dans ce dossier ; chaque lot est archivé avec ses réponses brutes (`provenance/lot.json`).

## IRNR — ressources non renouvelables

| Série | Table | Couverture |
|---|---|---|
| Consommation intérieure de matières (DMC), t/hab | env_ac_mfa | 27 pays + UE-27, 2010–2025 |
| Empreinte matière (RMC), t/hab | env_ac_rme | Total : 27 pays + UE-27 ; ventilation par catégorie : 15 pays + UE-27, le plus souvent jusqu'à 2023 |

Catégories non renouvelables : minerais métalliques (MF2), minéraux non métalliques (MF3), matières énergétiques fossiles (MF4). L'analyse de sensibilité retient la RMC totale, biomasse (MF1) comprise, comme mesure de l'IRNR : c'est le périmètre des repères publiés, et elle est disponible pour les 27 États membres. Elle mesure alors la pression matérielle totale et non l'objet IRNR du WP : la biomasse est renouvelable et recoupe le périmètre de l'IEE. La part MF2–MF4 est calculée en variante.

**France, 2023 (t/hab)**

| Catégorie | DMC | RMC | RMC / DMC |
|---|---|---|---|
| Minerais métalliques | 0,21 | 1,03 | ≈ 5 |
| Matières énergétiques fossiles | 1,30 | 1,91 | ≈ 1,5 |
| Minéraux non métalliques | 5,62 | 5,76 | ≈ 1 |

**Contraintes pour la spécification**

- Le choix entre DMC et RMC est déterminant. La DMC additionne l'extraction intérieure et les importations, moins les exportations, en poids direct ; la RMC attribue à la demande finale les extractions mobilisées dans les chaînes de production mondiales. Pour les métaux, l'écart atteint un facteur 5 en France. Le point de vigilance du §6.2 sur les échanges internationaux trouve ici sa mesure.
- La RMC totale est publiée pour les 27 États membres ; sa ventilation par catégorie de matières l'est pour 15. Parmi les pays sans ventilation figurent l'Espagne, l'Italie, les Pays-Bas, la Pologne, la Suède et la Finlande. Un IRNR limité aux matières non renouvelables (MF2–MF4) demande, pour ces pays, une ventilation propre ou des bases internationales ; la RMC totale se compare dès maintenant aux repères, qui portent sur le même périmètre. Les RMC nationales relèvent de modèles nationaux ou d'Eurostat et ne s'additionnent pas nécessairement en agrégat UE-27.
- La nomenclature des comptes de flux de matières compte 76 postes pour la DMC et 66 pour la RMC ; leur disponibilité varie selon les pays. La construction « ressource par ressource » envisagée par le WP part d'une matrice pays × poste × année établissant ce qui est effectivement publié.
- La référence de consommation soutenable par habitant (stocks disponibles, horizon, recyclage, substitutions admises) est un choix normatif du cadre ; des données sur les réserves et les flux de recyclage peuvent en informer la construction. La DMC et la RMC sont des flux : elles renseignent la pression, la durée de disponibilité d'une ressource relève des stocks.

## IEE — pressions sur les écosystèmes et les ressources renouvelables

| Famille de pression (§6.2) | Série | Table | Couverture |
|---|---|---|---|
| Pollution atmosphérique et climat | Gaz à effet de serre des unités résidentes (activités économiques et ménages) | env_ac_ainah_r2 | 27 pays + UE-27, 2010–2025 |
| Idem, selon la consommation | Empreinte GES et empreinte CO₂ (application FIGARO) | cli_gge_foot | 27 pays + UE-27, 2010–2024 |
| Pollution des sols et des eaux | Bilans bruts de l'azote et du phosphore agricoles : apports (engrais minéraux, fixation biologique…), exportations, excédents | aei_pr_gnb | 27 pays, 2010–2023 ; UE-27 jusqu'à 2014 |
| Ressource renouvelable rapportée à son renouvellement | Indice d'exploitation de l'eau (WEI+) : consommation nette (prélèvements moins restitutions) rapportée aux ressources renouvelables | sdg_06_60 | 27 pays + UE-27, 2010–2023 |
| Artificialisation | Occupation du sol (enquête LUCAS) | lan_lcv_ovw | 2012, 2015, 2018, 2022 |
| Artificialisation | Imperméabilisation des sols | sdg_11_32 | 2012, 2015, 2018, 2021 |
| (rapport par habitant) | Population moyenne | nama_10_pe | 27 pays + UE-27 |

**France, dernières valeurs**

- GES des unités résidentes : 5,9 t éq. CO₂/hab (2024) ; empreinte de consommation : 8,1 t (2024), dont 6,0 t de CO₂ (2023).
- Excédent d'azote : 18,4 kg/ha de surface agricole (2023).
- Azote fixé (engrais minéraux et fixation biologique agricole) : 30,6 kg/hab ; phosphore minéral appliqué aux sols : 1,9 kg/hab (2023).
- Exploitation de l'eau : 3,2 % (2023).
- Terres artificialisées : 5,6 % du territoire (2022) ; surfaces imperméabilisées : 298 m²/hab (2021), contre 252 m² pour l'UE-27.

**Contraintes pour la spécification**

- **Rythmes hétérogènes.** Les émissions sont annuelles et disponibles jusqu'à 2025 ; l'artificialisation est mesurée tous les trois ou quatre ans, avec un dernier point en 2022. Un IEE annuel suppose d'interpoler ou de prolonger certaines composantes. Cela introduit dans le signal un délai qui s'ajoute aux délais de rétroaction étudiés en M2.
- **Perte d'information à l'agrégation spatiale.** L'indice d'exploitation de l'eau national (3,2 % pour la France) ne rend pas compte des tensions saisonnières et propres à certains bassins. C'est un cas concret du problème M4. Représenter ces tensions demande des données infranationales, comme le WEI+ par bassin et par saison publié par l'Agence européenne pour l'environnement ; la grille hexagonale du dépôt pourra les accueillir quand elles seront intégrées.
- **Production ou consommation.** Le même choix que pour l'IRNR se pose : pour les gaz à effet de serre, l'empreinte de consommation de la France (8,1 t, 2024) dépasse d'environ 40 % les émissions de ses unités résidentes (5,9 t). Parmi les pressions retenues pour l'IEE, l'empreinte de consommation est publiée pour le climat ; les autres sont mesurées sur le territoire.
- **Fragmentation.** Les tables Eurostat consultées ne comportent pas de série nationale de fragmentation des habitats ; la recherche reste à étendre aux autres sources.
- **Unités incommensurables.** Tonnes par habitant, kilogrammes par hectare, pourcentages : la normalisation interne de l'IEE précède son agrégation avec l'IBD et l'IRNR.
- **Nature des mesures.** Dans l'analyse de sensibilité, le CO₂ entre en empreinte de consommation, l'azote et le phosphore en pression territoriale : les sous-indicateurs d'une même composante relèvent de deux logiques d'attribution. Un pays exportateur de produits agricoles porte alors des pressions liées à la consommation d'autres pays, et une relocalisation de production modifie l'indice sans évolution équivalente des pressions globales.

## IBD — état de la biodiversité

| Famille (§6.2) | Série | Table | Couverture |
|---|---|---|---|
| Abondance des espèces | Oiseaux communs des milieux agricoles (indice, année de base nationale) | env_bio2 | 23 pays (manquent BG, HR, MT, RO), dernière année variable |
| Abondance des espèces | Oiseaux communs, toutes espèces et espèces forestières | env_bio3 | UE-27 seulement, jusqu'à 2024 |
| État des écosystèmes | Part du territoire touchée par la sécheresse | sdg_15_42 | 27 pays + UE-27, 2010–2025 |
| Protection des habitats | Aires protégées terrestres et marines | env_bio4 | 27 pays + UE-27, 2011–2023 |

**France**

- Oiseaux des milieux agricoles : 61,8 en 2010, 53,9 en 2021 (2000 = 100).
- Sécheresse : 30,7 % du territoire en 2022, 5,1 % en 2025.
- Aires protégées terrestres : 28,3 % du territoire (2023).

**Contraintes pour la spécification**

- Une seule série mesure l'état du vivant par pays : l'indice des oiseaux communs des milieux agricoles, partiel dans ses espèces comme dans sa couverture géographique. Il est rapporté à une année de base propre à chaque pays — 2000 pour la plupart, 1998 (AT), 2004 (PT), 2005 (SK), 2006 (CY), 2007 (EL), 2008 (SI), 2010 (LU) — et décrit des tendances nationales ; 100 correspond à l'année de base.
- Les aires protégées mesurent un effort de protection, non un état ; la sécheresse est une perturbation, très variable d'une année à l'autre. Leur place dans un indicateur d'état est à justifier.
- La diversité génétique et la diversité des écosystèmes, incluses dans la définition de l'IBD (article 2 de la Convention sur la diversité biologique), n'ont pas de série nationale chez Eurostat.
- Une source d'état plus large est extérieure à Eurostat : l'état de conservation des habitats et des espèces rapporté au titre de l'article 17 de la directive Habitats, par région biogéographique et par pays, publié par l'Agence européenne pour l'environnement tous les six ans. Sa périodicité pose, en plus marqué, le problème de rythme relevé pour l'IEE.

## Bilan

| Composante | Couverture des données | Principal choix de spécification révélé |
|---|---|---|
| IRNR | Bonne (DMC) ; partielle (RMC) | Production ou consommation ; référence soutenable par habitant |
| IEE | Correcte, rythmes hétérogènes | Traitement des séries non annuelles ; échelle spatiale ; agrégation interne |
| IBD | Faible à l'échelle nationale | Recours à des sources hors Eurostat ; distinction entre état et effort de protection |

Les trois composantes de S n'ont pas la même qualité de données. Ce constat intéresse directement deux problèmes ouverts du WP :

- **T3** (choix de la fonction d'agrégation) : avec une moyenne géométrique à exposants égaux, chaque composante a le même poids dans l'IED, quelle que soit la qualité de sa mesure. L'incertitude de l'IED dépend alors des erreurs de chaque composante, de leurs variances et de leurs covariances.
- **E4** (pondérations) : la qualité des données et l'incertitude de mesure, que le problème E4 cite parmi les critères de comparaison, diffèrent nettement d'une composante à l'autre. Ce relevé en donne une première base factuelle.

Il documente aussi le problème **I5** : chaque table, filtre et millésime retenu est un choix révisable. Chaque lot est archivé avec ses réponses brutes, ses manifestes et son environnement d'exécution, et son rejeu hors réseau est vérifié ; les codes Eurostat des valeurs utilisées sont publiés avec les résultats.

## Repères et analyse de sensibilité

L'analyse de sensibilité de l'IED (`SENSIBILITE_IED.md`, script `analyse/sensibilite_ied.py`) fixe la valeur 1 de la normalisation sur des repères normatifs publiés — cibles, budgets ou limites globales répartis à parts égales par habitant (O'Neill et al., 2018 ; Bringezu, 2015) —, chacun décrit par sa nature et son périmètre. Elle teste trois formes de normalisation, quatre fonctions d'agrégation (aux deux étages ensemble, puis à chacun séparément), quatre jeux de pondérations, cinq valeurs communes de l'IBD et des scénarios d'IBD propre à un pays.

| Composante | Sous-indicateurs dotés d'un repère | Sans repère retenu |
|---|---|---|
| IRNR | Empreinte matière totale (RMC, biomasse comprise), même périmètre que les repères ; part non renouvelable (MF2–MF4) en variante | Repère propre aux ressources non renouvelables, logique de déplétion des stocks |
| IEE | Empreinte CO₂, azote fixé, phosphore appliqué | Eau douce (tension territoriale mesurée par le WEI+, tenue hors de l'IED par choix de construction), artificialisation, gaz autres que le CO₂ |
| IBD | — | Toutes les séries : l'IBD est exploré par scénarios |

Vingt pays disposent de toutes les séries nécessaires en 2023 (AT, BG, CZ, DE, ES, FI, FR, HR, HU, IE, IT, LT, LV, NL, PL, PT, RO, SE, SI, SK). Les séries d'azote et de phosphore manquent pour les sept autres (BE, CY, DK, EE, EL, LU, MT). La Slovénie y figure avec ses séries d'azote et de phosphore de 2021, rapportées à sa population de 2021. Dans la variante MF2–MF4, neuf pays sont complets (AT, CZ, DE, FR, HR, LT, PT, RO, SI).
