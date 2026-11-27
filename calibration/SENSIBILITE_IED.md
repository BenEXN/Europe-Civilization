# Sensibilité de l'IED aux choix de construction — 2023

*Économie Homéostatique, WP V1.0. Résultats sous hypothèses, produits par `analyse/sensibilite_ied.py` à partir des séries Eurostat du dossier `calibration/`. Chaque valeur dépend d'un jeu de choix explicite ; l'IBD est une valeur supposée. Les minima et maxima sont une enveloppe de scénarios.*

## Portée : justesse de représentation et échelle géographique

L'enjeu de recherche premier des indicateurs de l'EH est leur justesse à représenter la réalité biophysique : la performativité du dispositif (axiome A4) en dépend.

Les résultats sont calculés par État membre, échelle de publication des statistiques. Deux principes distincts relient un pays au reste du monde. L'empreinte (RMC, CO2) attribue à la demande finale d'un pays des pressions exercées ailleurs : c'est une règle de responsabilité. La continuité des milieux (bassins versants, mers et façades maritimes, aires de répartition des espèces) relie des territoires par leurs interactions biophysiques : c'est l'objet des zones tampons de l'EH. Aucune des séries nationales retenues ne représente cette continuité. Les zones tampons demandent une géométrie, des données spatialisées et une règle de partage de l'état d'une zone tampon entre les zones qu'elle relie ; elles sont à définir au cours de la construction des indicateurs.

## Statut des fonctions de normalisation

Le WP fixe l'échelle [0, 2], la valeur 1 comme référence de la normalisation et le sens de la transformation : décroissante pour une pression (IRNR, IEE), croissante pour un état (IBD). Il laisse à définir, pour chaque indicateur, la traduction des repères 0, 1 et 2 et la forme de la fonction (§6.2). Trois formes candidates, construites pour cette analyse, sont testées (x ≥ 0, T > 0) :

- **linéaire** 2 − x/T : vaut 2 sans pression, 0 à deux fois le repère, puis reste à 0 ;
- **ratio** T/x : vaut 2 jusqu'à la moitié du repère, puis décroît sans atteindre 0 ;
- **hyperbolique** 2/(1 + x/T) : vaut 2 sans pression et décroît sans atteindre 0.

Les trois valent 1 au repère. Le placement des valeurs 0 et 2 qu'impose chaque forme est un choix numérique, au même titre que la forme. La forme hyperbolique sert de configuration de référence pour la présentation, parce qu'elle est définie sans troncature sur tout le domaine ; ce choix est un choix de présentation. Les fonctions vérifient leur domaine (valeurs finies, x ≥ 0, T > 0) et s'arrêtent sur une erreur hors de celui-ci.

## 1. Repères retenus pour la valeur 1 de la normalisation

Les valeurs retenues sont des repères normatifs publiés : cibles, budgets ou limites globales, répartis à parts égales par habitant. Chacune est employée comme scénario de référence, avec sa nature et son périmètre.

| Composante | Sous-indicateur | Valeur 1 | Nature du repère | Périmètre du repère | Source |
|---|---|---|---|---|---|
| IRNR | Empreinte matière non renouvelable (RMC, minerais métalliques + minéraux non métalliques + fossiles) (t/hab) | 7,2 t (O'Neill) | cible de soutenabilité répartie à parts égales par habitant | empreinte matière totale, biomasse comprise | oneill2018 |
| IRNR | Empreinte matière non renouvelable (RMC, minerais métalliques + minéraux non métalliques + fossiles) (t/hab) | 5 t (Bringezu) | cible prospective pour 2050 (corridor), par habitant | empreinte matière totale (matières utilisées biotiques et abiotiques) | bringezu2015 |
| IEE | Empreinte CO2 de la consommation (t CO2/hab) | 1,61 t (O'Neill) | budget cumulé réparti à parts égales par habitant et par an | CO2 seul, 1 000 Gt sur 2011–2100 (2 °C, probabilité 66 %) | oneill2018 |
| IEE | Azote fixé (engrais minéraux + fixation biologique agricole) (kg N/hab) | 8,9 kg (O'Neill) | limite planétaire globale répartie à parts égales par habitant | fixation industrielle et biologique intentionnelle, 62 Tg N/an | oneill2018 |
| IEE | Phosphore minéral appliqué aux sols agricoles (kg P/hab) | 0,89 kg (O'Neill) | limite planétaire définie à l'échelle régionale, répartie à parts égales par habitant | 6,2 Tg P/an extraits et appliqués aux sols érodables | oneill2018 |

- **Empreinte matière non renouvelable (RMC, minerais métalliques + minéraux non métalliques + fossiles)** : Les deux repères portent sur l'empreinte matière totale : 7,2 t chez O'Neill ; corridor de 3 à 6 t d'ici 2050 chez Bringezu, qui propose 5 t comme cible. Rapportés à la seule part non renouvelable, ils donnent un rapport au repère inférieur ou égal à celui de l'empreinte totale. Ce sont des repères de pression sur les flux de matières ; la déplétion des stocks (§6.2 du WP : stocks disponibles, horizon, recyclage, substitutions) demande une référence propre, sans équivalent publié. Le corridor abiotique de Bringezu (6 à 12 t/hab) est exprimé en consommation matérielle totale (TMC), extraction inutilisée comprise, et se compare à la TMC.
- **Empreinte CO2 de la consommation** : Repère daté : le budget restant s'est réduit depuis 2011, et sa révision demande les émissions cumulées, l'horizon, la trajectoire et la probabilité retenus. Il porte sur le seul CO2.
- **Azote fixé (engrais minéraux + fixation biologique agricole)** : La série est une entrée de nouvel azote agricole sur le territoire (engrais minéraux + fixation biologique), mesurée côté production ; le repère d'O'Neill est appliqué côté consommation. La série renseigne une pression d'entrée, distincte de l'excédent du bilan et des transferts vers les eaux.
- **Phosphore minéral appliqué aux sols agricoles** : Mesure territoriale des apports minéraux ; le transfert vers les rivières et les océans, sur lequel porte la limite, dépend des sols et des bassins.
- **Population de référence.** Les valeurs d'O'Neill et al. (2018) répartissent des grandeurs globales pour une population mondiale d'environ 7 milliards. À grandeur globale fixée, une population de 8 milliards réduit la part par habitant de 12,5 %. L'égalité par habitant est une règle distributive ; responsabilités historiques et besoins différenciés appellent d'autres règles, à comparer.

**Sans repère retenu**

- **IEE — eau douce** : La référence d'O'Neill (574 m³/hab/an d'eau bleue consommée) répartit une limite globale par habitant et s'applique à une empreinte de consommation, sans série nationale homogène. Le WEI+ (sdg_06_60) mesure une consommation nette — prélèvements moins restitutions — rapportée aux ressources renouvelables du territoire ; l'Agence européenne pour l'environnement le publie aussi par bassin et par saison. C'est une mesure de tension locale, avec un seuil de stress conventionnel (20 %), et sa valeur nationale ne se convertit pas en m³/hab. Choix de construction de cette analyse : l'eau est tenue hors de l'IED, pour ne pas agréger une tension territoriale à des repères globaux par habitant. Son intégration, par bassin, est une piste ouverte.
- **IEE — artificialisation (LUCAS) et imperméabilisation** : La limite planétaire du changement d'usage des sols porte sur le couvert forestier ; aucun repère d'artificialisation par habitant n'a été retenu.
- **IEE — gaz à effet de serre autres que le CO2** : Le repère d'O'Neill porte sur le seul CO2 ; CH4 et N2O demandent un repère propre.
- **IBD — toutes séries** : Les limites de l'intégrité de la biosphère (extinctions par million d'espèces-années, part de la production primaire appropriée) n'ont pas été traduites ici à l'échelle nationale ; l'indice des oiseaux communs mesure des tendances d'abondance rapportées à une année de base nationale. L'IBD est traité comme une inconnue, explorée par scénarios.

**Sources**

- `oneill2018` : O'Neill, D. W., Fanning, A. L., Lamb, W. F., & Steinberger, J. K. (2018). A good life for all within planetary boundaries. Nature Sustainability, 1, 88–95. https://doi.org/10.1038/s41893-018-0021-4 (tableau 1 et supplément ; valeurs globales réparties par habitant pour une population mondiale d'environ 7 milliards)
- `bringezu2015` : Bringezu, S. (2015). Possible target corridor for sustainable use of global material resources. Resources, 4(1), 25–54. https://doi.org/10.3390/resources4010025 (résumé et §5.2 : corridor de 3 à 6 t/hab d'empreinte matière, matières biotiques et abiotiques utilisées, d'ici 2050 ; 5 t proposé comme cible)

## 2. Mesures, millésimes et rapport au repère par pays (2023)

Valeur observée divisée par le repère : 1 signifie « au repère », 3 « trois fois le repère ». Quand une série n'est pas publiée pour 2023, la valeur la plus récente des 3 années précédentes est utilisée ; l'année figure alors entre parenthèses. Une somme et un ratio sont formés à partir de termes de la même année, population comprise. « – » : série absente dans la fenêtre.

| Pays | RMC MF2–MF4 / 7,2 t | RMC MF2–MF4 / 5 t | CO2 | Azote | Phosphore | Complet |
|---|---|---|---|---|---|---|
| AT | 2,27 | 3,27 | 5,07 | 1,51 | 1,06 | oui |
| BE | 1,29 (2020) | 1,86 (2020) | 5,41 | – | – | non |
| BG | – | – | 3,12 | 6,31 | 6,07 | non |
| CY | 2,69 | 3,87 | 7,23 | – | – | non |
| CZ | 1,66 | 2,39 | 4,34 | 2,75 | 1,32 | oui |
| DE | 1,63 | 2,35 | 5,38 | 1,68 | 0,68 | oui |
| DK | 2,42 | 3,49 | 4,35 | – | – | non |
| EE | 2,81 (2022) | 4,05 (2022) | 4,72 | – | – | non |
| EL | – | – | 4,02 | – | – | non |
| ES | – | – | 3,55 | 1,98 | 2,47 | non |
| FI | – | – | 4,25 | 2,90 | 2,06 | non |
| FR | 1,21 | 1,74 | 3,70 | 3,44 | 2,13 | oui |
| HR | 1,56 | 2,25 | 4,42 | 2,95 | 3,46 | oui |
| HU | – | – | 3,28 | 3,79 | 2,79 | non |
| IE | – | – | 6,96 | 6,66 | 6,53 | non |
| IT | – | – | 4,26 | 1,50 | 1,91 | non |
| LT | 2,07 | 2,98 | 3,65 | 5,80 | 6,43 | oui |
| LU | 2,93 | 4,22 | 6,55 | – | – | non |
| LV | – | – | 3,30 | 5,43 | 5,96 | non |
| MT | 1,13 | 1,62 | 4,25 | – | – | non |
| NL | – | – | 4,77 | 1,30 | 0,37 | non |
| PL | – | – | 4,71 | 3,56 | 3,71 | non |
| PT | 1,60 | 2,31 | 2,53 | 1,36 | 1,52 | oui |
| RO | 3,58 | 5,15 | 3,05 | 3,28 | 5,40 | oui |
| SE | – | – | 3,36 | 2,34 | 1,24 | non |
| SI | 1,99 | 2,86 | 4,36 | 1,70 (2021) | 1,70 (2021) | oui |
| SK | – | – | 3,75 | 2,76 | 1,64 | non |

**Couverture.** 9 pays disposent de toutes les séries (AT, CZ, DE, FR, HR, LT, PT, RO, SI). Séries absentes pour les autres :

- RMC MF2–MF4 : BG, ES, FI, HU, IE, IT, LV, NL, PL, SE, SK
- Azote, Phosphore : BE, CY, DK, EE, LU, MT
- RMC MF2–MF4, Azote, Phosphore : EL

La RMC est publiée par Eurostat en total pour l'ensemble des États membres ; sa ventilation par catégorie de matières (MF2–MF4) est partielle. Sans recul temporel, 8 pays sont complets (SI sortant du groupe). Ce groupe est un sous-ensemble de disponibilité : ses moyennes et ses rangs décrivent ces pays seulement.

**Statuts statistiques des valeurs utilisées.** 13 terme(s) portent un code Eurostat, dont 6 pour les pays complets :

| Pays | Sous-indicateur | Terme | Année | Code | Comparabilité limitée |
|---|---|---|---|---|---|
| AT | Azote | N engrais minéraux (t) | 2023 | dp (définition différente, provisoire) | oui |
| AT | Phosphore | P engrais minéraux (t) | 2023 | dp (définition différente, provisoire) | oui |
| DE | Azote | population (milliers) | 2023 | p (provisoire) | non |
| DE | Phosphore | population (milliers) | 2023 | p (provisoire) | non |
| FR | Azote | N engrais minéraux (t) | 2023 | p (provisoire) | non |
| FR | Phosphore | P engrais minéraux (t) | 2023 | p (provisoire) | non |

Règle : les valeurs marquées sont retenues et signalées ; les codes b et d sont signalés comme limitant la comparabilité. L'absence de code n'équivaut pas à l'absence d'incertitude.

## 3. IED sous la configuration de référence

Normalisation hyperbolique : 2/(1 + x/T) ; agrégation moyenne géométrique (V1.0) aux deux étages ; poids égaux (V1.0) ; repère IRNR 7,2 t (O'Neill) ; **IBD supposé égal à 1,0**.

| Pays | IED (référence) | Min (IBD = 1) | Max (IBD = 1) | Min (enveloppe) | Max (enveloppe) |
|---|---|---|---|---|---|
| PT | 0,82 | 0,00 | 0,86 | 0,00 | 1,22 |
| DE | 0,79 | 0,00 | 0,84 | 0,00 | 1,19 |
| FR | 0,77 | 0,00 | 0,82 | 0,00 | 1,16 |
| CZ | 0,75 | 0,00 | 0,80 | 0,00 | 1,14 |
| SI | 0,73 | 0,00 | 0,79 | 0,00 | 1,12 |
| AT | 0,73 | 0,00 | 0,79 | 0,00 | 1,12 |
| HR | 0,70 | 0,00 | 0,76 | 0,00 | 1,08 |
| LT | 0,60 | 0,00 | 0,68 | 0,00 | 0,96 |
| RO | 0,57 | 0,00 | 0,65 | 0,00 | 0,92 |

L'enveloppe porte sur les 480 configurations de la grille (3 normalisations × 4 agrégations × 4 pondérations × 2 repères IRNR × 5 valeurs de l'IBD), qui donnent 196 vecteurs de scores distincts : le minimum ignore les poids, et la saturation comme le zéro absorbant produisent des répétitions. Le nombre de configurations n'est ni un nombre de réplications ni une probabilité.

## 4. Effet de chaque choix

Pour chaque choix, ce seul paramètre varie à partir de la référence. La corrélation de rang (Spearman, rangs moyens en cas d'ex æquo, calculée sur les scores non arrondis) vaut 1 quand le classement est identique ; elle est sans objet (–) quand l'IED est identique pour tous les pays. La dernière colonne donne les paires de pays dont l'ordre s'inverse.

**Normalisation**

| Option | IED moyen | IED min | IED max | Spearman | Inversions |
|---|---|---|---|---|---|
| linéaire : 2 − x/T | 0,00 | 0,00 | 0,00 | – | – |
| ratio : T/x | 0,59 | 0,42 | 0,71 | 0,983 | SI/AT |
| hyperbolique : 2/(1 + x/T) | 0,72 | 0,57 | 0,82 | 1,000 | – |

**Agrégation, appliquée aux deux étages (scénario conjoint)**

| Option | IED moyen | IED min | IED max | Spearman | Inversions |
|---|---|---|---|---|---|
| moyenne géométrique (V1.0) | 0,72 | 0,57 | 0,82 | 1,000 | – |
| CES ρ = −1 (harmonique) | 0,67 | 0,52 | 0,81 | 1,000 | – |
| CES ρ = −5 | 0,53 | 0,37 | 0,76 | 0,700 | DE/FR, DE/CZ, DE/SI, DE/AT, DE/HR, CZ/SI, AT/HR, LT/RO |
| minimum | 0,37 | 0,27 | 0,57 | 0,717 | DE/FR, DE/CZ, DE/SI, DE/AT, DE/HR, AT/HR, LT/RO |

**Pondérations (IBD, IEE, IRNR)**

| Option | IED moyen | IED min | IED max | Spearman | Inversions |
|---|---|---|---|---|---|
| égaux (V1.0) | 0,72 | 0,57 | 0,82 | 1,000 | – |
| IBD renforcé (2, 1, 1) | 0,78 | 0,65 | 0,86 | 1,000 | – |
| IEE renforcé (1, 2, 1) | 0,67 | 0,51 | 0,80 | 0,817 | FR/CZ, FR/SI, FR/AT, CZ/SI, CZ/AT, SI/AT, LT/RO |
| IRNR renforcé (1, 1, 2) | 0,71 | 0,53 | 0,81 | 0,933 | DE/FR, SI/HR, AT/HR |

**Repère IRNR**

| Option | IED moyen | IED min | IED max | Spearman | Inversions |
|---|---|---|---|---|---|
| 7,2 t (O'Neill) | 0,72 | 0,57 | 0,82 | 1,000 | – |
| 5 t (Bringezu) | 0,66 | 0,51 | 0,76 | 1,000 | – |

**Valeur supposée de l'IBD, commune à tous les pays**

| Option | IED moyen | IED min | IED max | Spearman | Inversions |
|---|---|---|---|---|---|
| 0,0 | 0,00 | 0,00 | 0,00 | – | – |
| 0,5 | 0,57 | 0,45 | 0,65 | 1,000 | – |
| 1,0 | 0,72 | 0,57 | 0,82 | 1,000 | – |
| 1,5 | 0,82 | 0,65 | 0,94 | 1,000 | – |
| 2,0 | 0,90 | 0,71 | 1,04 | 1,000 | – |

Avec la moyenne géométrique, un IBD commun b multiplie chaque score par b à la puissance du poids relatif de l'IBD : le classement est invariant par construction. Cette ligne mesure l'effet d'une biodiversité commune sur le niveau ; l'effet d'une biodiversité propre à chaque pays est donné plus bas.

**Agrégation entre les sous-indicateurs de l'IEE seule (IED en moyenne géométrique)**

| Option | IED moyen | IED min | IED max | Spearman | Inversions |
|---|---|---|---|---|---|
| moyenne géométrique (V1.0) | 0,72 | 0,57 | 0,82 | 1,000 | – |
| CES ρ = −1 (harmonique) | 0,70 | 0,56 | 0,82 | 0,983 | DE/FR |
| CES ρ = −5 | 0,67 | 0,55 | 0,80 | 0,767 | DE/FR, DE/CZ, DE/SI, DE/HR, SI/HR, AT/HR |
| minimum | 0,63 | 0,51 | 0,76 | 0,717 | DE/FR, DE/CZ, DE/SI, DE/HR, CZ/HR, SI/HR, AT/HR |

**Agrégation entre les composantes de l'IED seule (IEE en moyenne géométrique)**

| Option | IED moyen | IED min | IED max | Spearman | Inversions |
|---|---|---|---|---|---|
| moyenne géométrique (V1.0) | 0,72 | 0,57 | 0,82 | 1,000 | – |
| CES ρ = −1 (harmonique) | 0,69 | 0,53 | 0,82 | 1,000 | – |
| CES ρ = −5 | 0,62 | 0,40 | 0,79 | 0,833 | FR/CZ, FR/SI, FR/AT, CZ/SI, CZ/AT, LT/RO |
| minimum | 0,53 | 0,32 | 0,72 | 0,817 | FR/CZ, FR/SI, FR/AT, CZ/SI, CZ/AT, SI/AT, LT/RO |

**IBD propre à un pays (scénario hypothétique : IBD = 0,5 pour ce pays, 1 pour les autres)**

| Pays | IED de référence | IED du scénario | Rang de référence | Rang du scénario | Spearman |
|---|---|---|---|---|---|
| AT | 0,73 | 0,58 | 6 | 8 | 0,950 |
| CZ | 0,75 | 0,59 | 4 | 8 | 0,833 |
| DE | 0,79 | 0,63 | 2 | 7 | 0,750 |
| FR | 0,77 | 0,61 | 3 | 7 | 0,833 |
| HR | 0,70 | 0,55 | 7 | 9 | 0,950 |
| LT | 0,60 | 0,47 | 8 | 9 | 0,983 |
| PT | 0,82 | 0,65 | 1 | 7 | 0,650 |
| RO | 0,57 | 0,45 | 9 | 9 | 1,000 |
| SI | 0,73 | 0,58 | 5 | 8 | 0,900 |

Ces valeurs explorent des hypothèses ; aucune n'est une observation de la biodiversité.

## 5. Constats

- **Annulation de l'IED.** 224 configurations sur 480 donnent un IED nul pour tous les pays : 160 avec la normalisation linéaire, et 64 autres avec un IBD supposé nul. L'empreinte CO2 dépasse son repère d'un facteur 2,5 à 5,4 ; au-delà de deux fois le repère la normalisation linéaire donne 0, et pour ρ ≤ 0 un zéro est transmis à l'IED (§6.2). Dans l'échantillon, la normalisation linéaire supprime tout pouvoir de discrimination, quelle que soit la pondération.
- **Niveau 1.** Avec un IBD supposé au plus égal à 1, l'IED ne dépasse pas 0,864 ; la grille atteint 1,222 avec un IBD supposé de 2. Le franchissement du niveau 1 dépend donc de la valeur supposée de l'IBD.
- **Compensation à l'intérieur de l'IEE.** Sous-indicateurs de l'IEE sous leur repère dans l'échantillon : 1, par exemple phosphore minéral appliqué aux sols agricoles en DE (0,68 fois le repère). Avec une moyenne, une telle valeur compense en partie le dépassement des autres sous-indicateurs, ici l'empreinte CO2 ; c'est une propriété de l'agrégation, sans portée sur une compensation écologique réelle.
- **Ce qui déplace le classement**, à partir de la référence (Spearman, puis paires inversées) :
  - ratio : T/x : 0,983 (SI/AT)
  - CES ρ = −5 : 0,700 (DE/FR, DE/CZ, DE/SI, DE/AT, DE/HR, CZ/SI, AT/HR, LT/RO)
  - minimum : 0,717 (DE/FR, DE/CZ, DE/SI, DE/AT, DE/HR, AT/HR, LT/RO)
  - IEE renforcé (1, 2, 1) : 0,817 (FR/CZ, FR/SI, FR/AT, CZ/SI, CZ/AT, SI/AT, LT/RO)
  - IRNR renforcé (1, 1, 2) : 0,933 (DE/FR, SI/HR, AT/HR)
  - CES ρ = −1 (harmonique), étage IEE seul : 0,983 (DE/FR)
  - CES ρ = −5, étage IEE seul : 0,767 (DE/FR, DE/CZ, DE/SI, DE/HR, SI/HR, AT/HR)
  - minimum, étage IEE seul : 0,717 (DE/FR, DE/CZ, DE/SI, DE/HR, CZ/HR, SI/HR, AT/HR)
  - CES ρ = −5, étage IED seul : 0,833 (FR/CZ, FR/SI, FR/AT, CZ/SI, CZ/AT, LT/RO)
  - minimum, étage IED seul : 0,817 (FR/CZ, FR/SI, FR/AT, CZ/SI, CZ/AT, SI/AT, LT/RO)
- **Biodiversité propre à un pays.** Un IBD de 0,5 pour un seul pays, les autres à 1, modifie son rang dans 8 cas sur 9 (par exemple PT : rang 1 → 7). La conservation du classement sous un IBD commun ne renseigne donc pas sur sa robustesse à une biodiversité différente selon les pays.
