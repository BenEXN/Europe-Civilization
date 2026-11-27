# Sensibilité de l'IED aux choix de construction — 2023

*Économie Homéostatique, WP V1.0. Résultats sous hypothèses, produits par `analyse/sensibilite_ied.py` à partir des séries Eurostat du dossier `calibration/`. Aucune valeur ci-dessous n'est une mesure de l'IED : chacune dépend d'un jeu de choix explicite, et l'IBD n'a pas de mesure absolue disponible.*

## Portée : justesse de représentation et zones tampons

L'enjeu de recherche premier des indicateurs de l'EH est leur justesse à représenter la réalité biophysique : la performativité du dispositif (axiome A4) en dépend.

Les résultats sont calculés par État membre parce que c'est l'échelle de publication des statistiques. Les processus biophysiques ont leurs propres échelles. Dans l'EH, l'IED est rattaché à une zone géographique reliée aux autres par des zones tampons : une large part du vivant ne connaît pas de frontière et relève de plusieurs zones d'influence. Les populations de poissons, par exemple, s'étendent le long des côtes de plusieurs pays et au large.

Deux formes de liaison entre zones apparaissent déjà dans les données :

- **l'attribution par la consommation** : l'empreinte matière (RMC) et l'empreinte CO2 imputent à une zone des pressions exercées ailleurs ;
- **la continuité des milieux** : bassins versants, mers et façades maritimes, aires de répartition des espèces. Aucune des séries nationales retenues ne la représente.

La définition des zones tampons — leur géométrie, et la manière dont l'état d'une zone tampon entre dans l'IED des zones qu'elle relie — fait partie de la construction des indicateurs de l'EH. Les chiffres par pays de ce document en sont une approximation.

## Statut des fonctions de normalisation

Le WP fixe l'échelle [0, 2], la valeur 1 comme référence de la normalisation et le sens de la transformation : décroissante pour une pression (IRNR, IEE), croissante pour un état (IBD). Il laisse à définir, pour chaque indicateur, la traduction biophysique des repères 0, 1 et 2 et la forme de la fonction (§6.2). Ce document retient les seuils planétaires pour la valeur 1 et teste trois formes candidates, construites pour cette analyse :

- **linéaire** 2 − x/T : vaut 2 sans pression et 0 à deux fois le seuil, puis reste à 0 ;
- **ratio** T/x : vaut 2 jusqu'à la moitié du seuil, puis décroît sans atteindre 0 ;
- **hyperbolique** 2/(1 + x/T) : vaut 2 sans pression et décroît sans atteindre 0.

Chaque forme place implicitement les repères 0 et 2 : ce placement est un choix de construction au même titre que la forme. La forme hyperbolique sert de configuration de référence pour la présentation des résultats (sections 3 et 5), parce qu'elle est définie pour toute valeur observée sans troncature. Ce n'est ni une spécification du WP ni une recommandation : la section 4 montre l'effet de chaque forme.

## 1. Seuils retenus pour la valeur 1 de la normalisation

| Composante | Sous-indicateur | Seuil | Statut | Source |
|---|---|---|---|---|
| IRNR | Empreinte matière non renouvelable (RMC, minerais métalliques + minéraux non métalliques + fossiles) (t/hab) | 7,2 t (O'Neill) | planétaire | oneill2018 |
| IRNR | Empreinte matière non renouvelable (RMC, minerais métalliques + minéraux non métalliques + fossiles) (t/hab) | 5 t (Bringezu) | planétaire | bringezu2015 |
| IEE | Empreinte CO2 de la consommation (t CO2/hab) | 1,61 t (O'Neill) | planétaire | oneill2018 |
| IEE | Azote fixé (engrais minéraux + fixation biologique agricole) (kg N/hab) | 8,9 kg (O'Neill) | planétaire | oneill2018 |
| IEE | Phosphore minéral appliqué aux sols agricoles (kg P/hab) | 0,89 kg (O'Neill) | régional | oneill2018 |

- **Empreinte matière non renouvelable (RMC, minerais métalliques + minéraux non métalliques + fossiles)** : Les deux seuils portent sur l'empreinte matière (RMC) totale, biomasse comprise : 7,2 t chez O'Neill ; corridor de 3 à 6 t d'ici 2050 chez Bringezu, qui propose 5 t comme cible. Appliqués à la seule part non renouvelable, ils sont indulgents. Bringezu propose aussi un corridor propre aux matières abiotiques (6 à 12 t/hab), exprimé en consommation matérielle totale (TMC), qui inclut l'extraction inutilisée : il n'est pas comparable à la RMC. La logique de déplétion des stocks du WP (§6.2) n'a pas d'équivalent publié.
- **Empreinte CO2 de la consommation** : Budget de 1 000 Gt CO2 sur 2011–2100 (2 °C, probabilité 66 %) réparti uniformément ; le budget restant s'est réduit depuis, le seuil est donc indulgent.
- **Azote fixé (engrais minéraux + fixation biologique agricole)** : Limite de 62 Tg N/an de fixation industrielle et biologique intentionnelle. Mesure territoriale (production), non empreinte de consommation.
- **Phosphore minéral appliqué aux sols agricoles** : Limite régionale de 6,2 Tg P/an extraits et appliqués aux sols érodables. Mesure territoriale.
- **Population de référence** : O'Neill et al. (2018) ramènent les limites planétaires par habitant pour une population mondiale de 7 milliards (2011). Avec la population de 2023, de l'ordre de 8 milliards, les mêmes limites globales donnent des seuils par habitant inférieurs d'environ 12 % : les seuils retenus sont, à cet égard aussi, indulgents.

**Sans seuil absolu identifié**

- **IEE — eau douce** : La limite planétaire de l'eau douce (consommation d'eau bleue, 574 m³/hab/an chez O'Neill 2018) n'a pas de série nationale correspondante : les statistiques publiques portent sur les prélèvements, dont une large part est restituée. L'indice d'exploitation de l'eau (WEI+) mesure une tension régionale, par rapport aux ressources renouvelables du bassin ; son seuil de stress (20 %) est conventionnel. L'eau est donc exclue du calcul, en attendant une série de consommation ou une mesure par bassin.
- **IEE — artificialisation (LUCAS) et imperméabilisation** : La limite planétaire du changement d'usage des sols porte sur le couvert forestier ; aucune limite biophysique de l'artificialisation par habitant n'a été identifiée.
- **IEE — gaz à effet de serre autres que le CO2** : Le seuil d'O'Neill (2018) porte sur le seul CO2.
- **IBD — toutes séries** : Les limites de l'intégrité de la biosphère (extinctions par million d'espèces-années, part de la production primaire appropriée) n'ont pas de traduction nationale ; l'indice des oiseaux communs n'a pas de seuil absolu.

**Sources**

- `oneill2018` : O'Neill, D. W., Fanning, A. L., Lamb, W. F., & Steinberger, J. K. (2018). A good life for all within planetary boundaries. Nature Sustainability, 1, 88–95. https://doi.org/10.1038/s41893-018-0021-4 (tableau 1 ; limites ramenées par habitant pour une population mondiale de 7 milliards, 2011)
- `bringezu2015` : Bringezu, S. (2015). Possible target corridor for sustainable use of global material resources. Resources, 4(1), 25–54. https://doi.org/10.3390/resources4010025 (résumé et §5.2 : corridor de 3 à 6 t/hab d'empreinte matière, matières biotiques et abiotiques utilisées, d'ici 2050 ; 5 t proposé comme cible)

## 2. Rapport au seuil par pays (2023)

Valeur observée divisée par le seuil : 1 signifie « au seuil », 3 signifie « trois fois le seuil ». Quand une série n'est pas publiée pour 2023, la valeur la plus récente des 3 années précédentes est utilisée (astérisque).

| Pays | IRNR / 7,2 t | IRNR / 5 t | CO2 | Azote | Phosphore |
|---|---|---|---|---|---|
| AT | 2,27 | 3,27 | 5,07 | 1,51 | 1,06 |
| BE | 1,29* | 1,86* | 5,41 | – | – |
| BG | – | – | 3,12 | 6,31 | 6,07 |
| CY | 2,69 | 3,87 | 7,23 | – | – |
| CZ | 1,66 | 2,39 | 4,34 | 2,75 | 1,32 |
| DE | 1,63 | 2,35 | 5,38 | 1,68 | 0,68 |
| DK | 2,42 | 3,49 | 4,35 | – | – |
| EE | 2,81* | 4,05* | 4,72 | – | – |
| EL | – | – | 4,02 | – | – |
| ES | – | – | 3,55 | 1,98 | 2,47 |
| FI | – | – | 4,25 | 2,90 | 2,06 |
| FR | 1,21 | 1,74 | 3,70 | 3,44 | 2,13 |
| HR | 1,56 | 2,25 | 4,42 | 2,95 | 3,46 |
| HU | – | – | 3,28 | 3,79 | 2,79 |
| IE | – | – | 6,96 | 6,66 | 6,53 |
| IT | – | – | 4,26 | 1,50 | 1,91 |
| LT | 2,07 | 2,98 | 3,65 | 5,80 | 6,43 |
| LU | 2,93 | 4,22 | 6,55 | – | – |
| LV | – | – | 3,30 | 5,43 | 5,96 |
| MT | 1,13 | 1,62 | 4,25 | – | – |
| NL | – | – | 4,77 | 1,30 | 0,37 |
| PL | – | – | 4,71 | 3,56 | 3,71 |
| PT | 1,60 | 2,31 | 2,53 | 1,36 | 1,52 |
| RO | 3,58 | 5,15 | 3,05 | 3,28 | 5,40 |
| SE | – | – | 3,36 | 2,34 | 1,24 |
| SI | 1,99 | 2,86 | 4,36 | 1,69* | 1,69* |
| SK | – | – | 3,75 | 2,76 | 1,64 |

## 3. IED sous la configuration de référence

Normalisation hyperbolique : 2/(1 + x/T) ; agrégation moyenne géométrique (V1.0) ; poids égaux (V1.0) ; seuil IRNR 7,2 t (O'Neill) ; **IBD fixé à 1,0 faute de mesure**. Pays disposant de toutes les séries : 9.

| Pays | IED (référence) | IED min | IED max | Écart |
|---|---|---|---|---|
| PT | 0,82 | 0,00 | 1,06 | 1,06 |
| DE | 0,79 | 0,00 | 1,03 | 1,03 |
| FR | 0,77 | 0,00 | 1,00 | 1,00 |
| CZ | 0,75 | 0,00 | 0,98 | 0,98 |
| SI | 0,73 | 0,00 | 0,97 | 0,97 |
| AT | 0,73 | 0,00 | 0,97 | 0,97 |
| HR | 0,70 | 0,00 | 0,94 | 0,94 |
| LT | 0,60 | 0,00 | 0,83 | 0,83 |
| RO | 0,57 | 0,00 | 0,80 | 0,80 |

Min et max portent sur les 288 configurations testées (3 normalisations × 4 agrégations × 4 pondérations × 2 seuils IRNR × 3 valeurs de l'IBD).

## 4. Effet de chaque choix

Pour chaque choix, on fait varier ce seul paramètre à partir de la référence. La corrélation de rang (Spearman) mesure si le classement des pays est conservé (1 = classement identique).

**Normalisation**

| Option | IED moyen | IED min | IED max | Spearman |
|---|---|---|---|---|
| linéaire : 2 − x/T | 0,00 | 0,00 | 0,00 | 0,23 |
| ratio : T/x | 0,59 | 0,42 | 0,71 | 0,98 |
| hyperbolique : 2/(1 + x/T) | 0,72 | 0,57 | 0,82 | 1,00 |

**Agrégation**

| Option | IED moyen | IED min | IED max | Spearman |
|---|---|---|---|---|
| moyenne géométrique (V1.0) | 0,72 | 0,57 | 0,82 | 1,00 |
| CES ρ = −1 (harmonique) | 0,67 | 0,52 | 0,81 | 1,00 |
| CES ρ = −5 | 0,53 | 0,37 | 0,76 | 0,70 |
| minimum | 0,37 | 0,27 | 0,57 | 0,72 |

**Pondérations**

| Option | IED moyen | IED min | IED max | Spearman |
|---|---|---|---|---|
| égaux (V1.0) | 0,72 | 0,57 | 0,82 | 1,00 |
| IBD renforcé (2, 1, 1) | 0,78 | 0,65 | 0,86 | 1,00 |
| IEE renforcé (1, 2, 1) | 0,67 | 0,51 | 0,80 | 0,82 |
| IRNR renforcé (1, 1, 2) | 0,71 | 0,53 | 0,81 | 0,93 |

**Seuil IRNR**

| Option | IED moyen | IED min | IED max | Spearman |
|---|---|---|---|---|
| 7,2 t (O'Neill) | 0,72 | 0,57 | 0,82 | 1,00 |
| 5 t (Bringezu) | 0,66 | 0,51 | 0,76 | 1,00 |

**Valeur supposée de l’IBD**

| Option | IED moyen | IED min | IED max | Spearman |
|---|---|---|---|---|
| 0,5 | 0,57 | 0,45 | 0,65 | 1,00 |
| 1,0 | 0,72 | 0,57 | 0,82 | 1,00 |
| 1,5 | 0,82 | 0,65 | 0,94 | 1,00 |

## 5. Constats

- **Annulation de l'IED.** 96 configurations sur 288 donnent un IED nul pour tous les pays, dont 96 avec la normalisation linéaire. L'empreinte CO2 dépasse le seuil d'un facteur 2,5 à 5,4 ; au-delà de deux fois le seuil, la normalisation linéaire donne 0, et la moyenne géométrique comme le minimum transmettent ce 0 à l'IED (§6.2 : si une composante tend vers zéro, l'IED tend vers zéro).
- **Aucun pays n'atteint la valeur de référence.** Avec un IBD supposé au plus égal à 1, l'IED ne dépasse pas 0,86 ; il n'atteint 1,06 qu'en supposant un IBD de 1,5, c'est-à-dire une biodiversité en meilleur état que la référence.
- **Compensation à l'intérieur de l'IEE.** 1 valeur(s) de sous-indicateur de l'IEE sont sous leur seuil, par exemple phosphore minéral appliqué aux sols agricoles en DE (0,68 fois le seuil). Avec une moyenne, une telle valeur compense en partie le dépassement des autres sous-indicateurs, ici l'empreinte CO2. Le choix de la fonction d'agrégation se pose donc deux fois : entre les sous-indicateurs d'une composante, et entre les composantes (T3).
- **Ce qui déplace le classement.** Les normalisations ratio et hyperbolique conservent le classement ; les agrégations à faible substituabilité (CES ρ = −5, minimum) et les pondérations le modifient (corrélations de rang de la section 4).
