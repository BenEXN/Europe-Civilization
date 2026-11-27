# Données publiques pour les composantes de S — note de synthèse

*Économie Homéostatique, WP V1.0 — calibration empirique. Relevé du 27 novembre 2026, données Eurostat.*

## Objet

Le vecteur d'état biophysique S = (IBD, IEE, IRNR) de la formalisation V1.0 (§5.5) est constitué de trois indicateurs normalisés sur [0, 2], agrégés dans l'IED par moyenne géométrique (§6.2). Le WP précise que chacun est le résultat d'une chaîne de construction — données, sous-indicateurs, protocoles, normalisation — dont la spécification reste à établir.

Cette note fait l'inventaire des séries publiques disponibles à l'échelle des États membres de l'UE-27 pour alimenter cette chaîne, et des contraintes qu'elles imposent à sa spécification. Elle ne calcule aucun des trois indicateurs : les références par habitant, les repères 0, 1 et 2 de la normalisation et, pour l'IEE et l'IBD, l'agrégation interne relèvent du cadre.

Les séries sont téléchargées et recalculées par le workflow « Calibration EH » (sources `eh_irnr`, `eh_iee`, `eh_ibd`). Les fichiers de résultats et la provenance de chaque téléchargement (adresse, date, empreinte SHA-256) sont dans ce dossier.

## IRNR — ressources non renouvelables

| Série | Table | Couverture |
|---|---|---|
| Consommation intérieure de matières (DMC), t/hab | env_ac_mfa | 27 pays + UE-27, 2010–2025 |
| Empreinte matière (RMC), t/hab | env_ac_rme | 15 pays + UE-27, le plus souvent jusqu'à 2023 |

Catégories retenues : minerais métalliques (MF2), minéraux non métalliques (MF3), matières énergétiques fossiles (MF4). La biomasse (MF1), renouvelable, est exclue.

**France, 2023 (t/hab)**

| Catégorie | DMC | RMC | RMC / DMC |
|---|---|---|---|
| Minerais métalliques | 0,21 | 1,03 | ≈ 5 |
| Matières énergétiques fossiles | 1,30 | 1,91 | ≈ 1,5 |
| Minéraux non métalliques | 5,62 | 5,76 | ≈ 1 |

**Contraintes pour la spécification**

- Le choix entre DMC et RMC est déterminant. La DMC compte les matières en poids brut à la frontière ; la RMC attribue à la demande finale les extractions mobilisées dans les chaînes de production mondiales. Pour les métaux, l'écart atteint un facteur 5 en France. Le point de vigilance du §6.2 sur les échanges internationaux trouve ici sa mesure.
- La RMC n'est publiée que pour 15 États membres. Parmi les absents figurent l'Espagne, l'Italie, les Pays-Bas, la Pologne, la Suède et la Finlande. Un IRNR fondé sur la RMC demande, pour ces pays, une estimation propre ou le recours à des bases internationales.
- Les comptes de flux de matières sont publiés par grandes catégories et sous-catégories (76 postes pour la DMC, 66 pour la RMC). La construction « ressource par ressource » envisagée par le WP peut s'appuyer sur ce détail.
- La référence de consommation soutenable par habitant (stocks disponibles, horizon, recyclage, substitutions admises) n'a pas de source statistique : c'est un choix normatif du cadre.

## IEE — pressions sur les écosystèmes et les ressources renouvelables

| Famille de pression (§6.2) | Série | Table | Couverture |
|---|---|---|---|
| Pollution atmosphérique et climat | Gaz à effet de serre, activités et ménages | env_ac_ainah_r2 | 27 pays + UE-27, 2010–2025 |
| Idem, selon la consommation | Empreinte GES et empreinte CO₂ (application FIGARO) | cli_gge_foot | 27 pays + UE-27, 2010–2024 |
| Pollution des sols et des eaux | Bilans bruts de l'azote et du phosphore agricoles : apports (engrais minéraux, fixation biologique…), exportations, excédents | aei_pr_gnb | 27 pays, 2010–2023 ; UE-27 jusqu'à 2014 |
| Ressource renouvelable rapportée à son renouvellement | Indice d'exploitation de l'eau (WEI+) | sdg_06_60 | 27 pays + UE-27, 2010–2023 |
| Artificialisation | Occupation du sol (enquête LUCAS) | lan_lcv_ovw | 2012, 2015, 2018, 2022 |
| Artificialisation | Imperméabilisation des sols | sdg_11_32 | 2012, 2015, 2018, 2021 |
| (rapport par habitant) | Population moyenne | nama_10_pe | 27 pays + UE-27 |

**France, dernières valeurs**

- GES produits sur le territoire : 5,9 t éq. CO₂/hab (2024) ; empreinte de consommation : 8,1 t (2024), dont 6,0 t de CO₂ (2023).
- Excédent d'azote : 18,4 kg/ha de surface agricole (2023).
- Azote fixé (engrais minéraux et fixation biologique agricole) : 30,6 kg/hab ; phosphore minéral appliqué aux sols : 1,9 kg/hab (2023).
- Exploitation de l'eau : 3,2 % (2023).
- Terres artificialisées : 5,6 % du territoire (2022) ; surfaces imperméabilisées : 298 m²/hab (2021), contre 252 m² pour l'UE-27.

**Contraintes pour la spécification**

- **Rythmes hétérogènes.** Les émissions sont annuelles et disponibles jusqu'à 2025 ; l'artificialisation est mesurée tous les trois ou quatre ans, avec un dernier point en 2022. Un IEE annuel suppose d'interpoler ou de prolonger certaines composantes. Cela introduit dans le signal un délai qui s'ajoute aux délais de rétroaction étudiés en M2.
- **Perte d'information à l'agrégation spatiale.** L'indice d'exploitation de l'eau national (3,2 % pour la France) ne rend pas compte des tensions saisonnières et propres à certains bassins. C'est un cas concret du problème M4. La carte par hexagones du dépôt permet de représenter ce que la moyenne nationale efface.
- **Production ou consommation.** Le même choix que pour l'IRNR se pose : pour les gaz à effet de serre, l'empreinte de consommation dépasse de 40 % environ les émissions territoriales en France. L'empreinte n'existe aujourd'hui que pour le climat ; les autres pressions sont mesurées sur le territoire.
- **Fragmentation.** Aucune série nationale de fragmentation des habitats n'a été identifiée dans les tables Eurostat.
- **Unités incommensurables.** Tonnes par habitant, kilogrammes par hectare, pourcentages : la normalisation interne de l'IEE précède son agrégation avec l'IBD et l'IRNR.
- **Nature des mesures.** Dans l'analyse de sensibilité, le CO₂ entre en empreinte de consommation, l'azote et le phosphore en pression territoriale : les sous-indicateurs d'une même composante relèvent de deux logiques d'attribution.

## IBD — état de la biodiversité

| Famille (§6.2) | Série | Table | Couverture |
|---|---|---|---|
| Abondance des espèces | Oiseaux communs des milieux agricoles (base 2000 = 100) | env_bio2 | 23 pays (manquent BG, HR, MT, RO), dernière année variable |
| Abondance des espèces | Oiseaux communs, toutes espèces et espèces forestières | env_bio3 | UE-27 seulement, jusqu'à 2024 |
| État des écosystèmes | Part du territoire touchée par la sécheresse | sdg_15_42 | 27 pays + UE-27, 2010–2025 |
| Protection des habitats | Aires protégées terrestres et marines | env_bio4 | 27 pays + UE-27, 2011–2023 |

**France**

- Oiseaux des milieux agricoles : 61,8 en 2010, 53,9 en 2021 (2000 = 100).
- Sécheresse : 30,7 % du territoire en 2022, 5,1 % en 2025.
- Aires protégées terrestres : 28,3 % du territoire (2023).

**Contraintes pour la spécification**

- Une seule série mesure l'état du vivant par pays : l'indice des oiseaux communs des milieux agricoles, partiel dans ses espèces comme dans sa couverture géographique.
- Les aires protégées mesurent un effort de protection, non un état ; la sécheresse est une perturbation, très variable d'une année à l'autre. Leur place dans un indicateur d'état est à justifier.
- La diversité génétique et la diversité des écosystèmes, incluses dans la définition de l'IBD (article 2 de la Convention sur la diversité biologique), n'ont pas de série nationale chez Eurostat.
- La source d'état la plus complète est extérieure à Eurostat : l'état de conservation des habitats et des espèces rapporté au titre de l'article 17 de la directive Habitats, publié par l'Agence européenne pour l'environnement tous les six ans. Sa périodicité pose, en plus marqué, le problème de rythme relevé pour l'IEE.

## Bilan

| Composante | Couverture des données | Principal choix de spécification révélé |
|---|---|---|
| IRNR | Bonne (DMC) ; partielle (RMC) | Production ou consommation ; référence soutenable par habitant |
| IEE | Correcte, rythmes hétérogènes | Traitement des séries non annuelles ; échelle spatiale ; agrégation interne |
| IBD | Faible à l'échelle nationale | Recours à des sources hors Eurostat ; distinction entre état et effort de protection |

Les trois composantes de S n'ont pas la même qualité de données. Ce constat intéresse directement deux problèmes ouverts du WP :

- **T3** (choix de la fonction d'agrégation) : avec une moyenne géométrique, une composante mal mesurée pèse autant que les autres sur l'IED. La robustesse du signal dépend donc de la composante la moins bien documentée.
- **E4** (pondérations) : la qualité des données et l'incertitude de mesure, que le problème E4 cite parmi les critères de comparaison, diffèrent nettement d'une composante à l'autre. Ce relevé en donne une première base factuelle.

Il documente aussi le problème **I5** : chaque table, filtre et millésime retenu est un choix révisable, et la provenance enregistrée par le workflow en assure la traçabilité.

## Seuils planétaires et analyse de sensibilité

L'analyse de sensibilité de l'IED (`SENSIBILITE_IED.md`, script `analyse/sensibilite_ied.py`) fixe la valeur 1 de la normalisation sur des seuils biophysiques absolus, tirés des limites planétaires ramenées par habitant (O'Neill et al., 2018 ; Bringezu, 2015). Elle teste trois formes de normalisation, quatre fonctions d'agrégation, quatre jeux de pondérations et trois valeurs de l'IBD.

| Composante | Sous-indicateurs dotés d'un seuil | Sans seuil absolu utilisable |
|---|---|---|
| IRNR | Empreinte matière non renouvelable (seuils portant sur l'empreinte totale) | Seuil propre aux ressources non renouvelables, logique de déplétion des stocks |
| IEE | Empreinte CO₂, azote fixé, phosphore appliqué | Eau douce (pas de série de consommation), artificialisation, gaz autres que le CO₂ |
| IBD | — | Toutes les séries : les limites de l'intégrité de la biosphère n'ont pas de traduction nationale |

Neuf pays disposent de toutes les séries nécessaires en 2023, faute d'empreinte matière pour les autres.
