# Sensibilité de l'IED aux choix de construction — 2023

*Économie Homéostatique, WP V1.0. Résultats sous hypothèses, produits par `analyse/sensibilite_ied.py` à partir des séries Eurostat du dossier `calibration/`. Aucune valeur ci-dessous n'est une mesure de l'IED : chacune dépend d'un jeu de choix explicite, et l'IBD n'a pas de mesure absolue disponible.*

## 1. Seuils retenus pour la valeur 1 de la normalisation

| Composante | Sous-indicateur | Seuil | Statut | Source |
|---|---|---|---|---|
| IRNR | Empreinte matière non renouvelable (RMC, minerais métalliques + minéraux non métalliques + fossiles) (t/hab) | 7,2 t (O'Neill) | planétaire | oneill2018 |
| IRNR | Empreinte matière non renouvelable (RMC, minerais métalliques + minéraux non métalliques + fossiles) (t/hab) | 5 t (Bringezu) | planétaire | bringezu2015 |
| IEE | Empreinte CO2 de la consommation (t CO2/hab) | 1,61 t (O'Neill) | planétaire | oneill2018 |
| IEE | Azote fixé (engrais minéraux + fixation biologique agricole) (kg N/hab) | 8,9 kg (O'Neill) | planétaire | oneill2018 |
| IEE | Phosphore minéral appliqué aux sols agricoles (kg P/hab) | 0,89 kg (O'Neill) | planétaire | oneill2018 |
| IEE | Indice d'exploitation de l'eau (WEI+) (%) | 20 % (AEE) | régional | eea_wei |

- **Empreinte matière non renouvelable (RMC, minerais métalliques + minéraux non métalliques + fossiles)** : Les deux seuils portent sur l'empreinte matière totale, biomasse comprise ; appliqués à la seule part non renouvelable, ils sont indulgents. Aucun seuil propre aux matières non renouvelables n'a été identifié, et la logique de déplétion des stocks du WP (§6.2) n'a pas d'équivalent publié.
- **Empreinte CO2 de la consommation** : Budget de 1 000 Gt CO2 sur 2011–2100 (2 °C, probabilité 66 %) réparti uniformément ; le budget restant s'est réduit depuis, le seuil est donc indulgent.
- **Azote fixé (engrais minéraux + fixation biologique agricole)** : Limite de 62 Tg N/an de fixation industrielle et biologique intentionnelle. Mesure territoriale (production), non empreinte de consommation.
- **Phosphore minéral appliqué aux sols agricoles** : Limite régionale de 6,2 Tg P/an extraits et appliqués aux sols érodables. Mesure territoriale.
- **Indice d'exploitation de l'eau (WEI+)** : Seuil de stress hydrique d'usage courant, non dérivé d'une limite planétaire. La limite planétaire de l'eau douce (574 m³/hab chez O'Neill 2018) suppose une série de prélèvements par habitant non rassemblée ici.

**Sans seuil absolu identifié**

- **IEE — artificialisation (LUCAS) et imperméabilisation** : La limite planétaire du changement d'usage des sols porte sur le couvert forestier ; aucune limite biophysique de l'artificialisation par habitant n'a été identifiée.
- **IEE — gaz à effet de serre autres que le CO2** : Le seuil d'O'Neill (2018) porte sur le seul CO2.
- **IBD — toutes séries** : Les limites de l'intégrité de la biosphère (extinctions par million d'espèces-années, part de la production primaire appropriée) n'ont pas de traduction nationale ; l'indice des oiseaux communs n'a pas de seuil absolu.

**Sources**

- `oneill2018` : O'Neill, D. W., Fanning, A. L., Lamb, W. F., & Steinberger, J. K. (2018). A good life for all within planetary boundaries. Nature Sustainability, 1, 88–95. https://doi.org/10.1038/s41893-018-0021-4 (tableau 1 ; population mondiale de 7 milliards, 2011)
- `bringezu2015` : Bringezu, S. (2015). Possible target corridor for sustainable use of global material resources. Resources, 4(1), 25–54. https://doi.org/10.3390/resources4010025 (§5.2, cible 2050)
- `eea_wei` : Agence européenne pour l'environnement : seuil conventionnel de stress hydrique de l'indice d'exploitation de l'eau, 20 % (stress), 40 % (stress sévère)

## 2. Rapport au seuil par pays (2023)

Valeur observée divisée par le seuil : 1 signifie « au seuil », 3 signifie « trois fois le seuil ». Quand une série n'est pas publiée pour 2023, la valeur la plus récente des 3 années précédentes est utilisée (astérisque).

| Pays | IRNR / 7,2 t | IRNR / 5 t | CO2 | Azote | Phosphore | Eau (WEI+) |
|---|---|---|---|---|---|---|
| AT | 2,27 | 3,27 | 5,07 | 1,51 | 1,06 | 0,09 |
| BE | 1,29* | 1,86* | 5,41 | – | – | 0,17 |
| BG | – | – | 3,12 | 6,31 | 6,07 | 0,04 |
| CY | 2,69 | 3,87 | 7,23 | – | – | 3,77 |
| CZ | 1,66 | 2,39 | 4,34 | 2,75 | 1,32 | 0,11 |
| DE | 1,63 | 2,35 | 5,38 | 1,68 | 0,68 | 0,17 |
| DK | 2,42 | 3,49 | 4,35 | – | – | 0,19 |
| EE | 2,81* | 4,05* | 4,72 | – | – | 0,06 |
| EL | – | – | 4,02 | – | – | 0,66 |
| ES | – | – | 3,55 | 1,98 | 2,47 | 0,36 |
| FI | – | – | 4,25 | 2,90 | 2,06 | 0,03 |
| FR | 1,21 | 1,74 | 3,70 | 3,44 | 2,13 | 0,16 |
| HR | 1,56 | 2,25 | 4,42 | 2,95 | 3,46 | 0,01 |
| HU | – | – | 3,28 | 3,79 | 2,79 | 0,07 |
| IE | – | – | 6,96 | 6,66 | 6,53 | 0,05 |
| IT | – | – | 4,26 | 1,50 | 1,91 | 0,50 |
| LT | 2,07 | 2,98 | 3,65 | 5,80 | 6,43 | 0,02 |
| LU | 2,93 | 4,22 | 6,55 | – | – | 0,09 |
| LV | – | – | 3,30 | 5,43 | 5,96 | 0,01 |
| MT | 1,13 | 1,62 | 4,25 | – | – | 1,50 |
| NL | – | – | 4,77 | 1,30 | 0,37 | 0,14 |
| PL | – | – | 4,71 | 3,56 | 3,71 | 0,26 |
| PT | 1,60 | 2,31 | 2,53 | 1,36 | 1,52 | 0,36 |
| RO | 3,58 | 5,15 | 3,05 | 3,28 | 5,40 | 2,37 |
| SE | – | – | 3,36 | 2,34 | 1,24 | 0,01 |
| SI | 1,99 | 2,86 | 4,36 | 1,69* | 1,69* | 0,02 |
| SK | – | – | 3,75 | 2,76 | 1,64 | 0,01 |

## 3. IED sous la configuration de référence

Normalisation hyperbolique : 2/(1 + x/T) ; agrégation moyenne géométrique (V1.0) ; poids égaux (V1.0) ; seuil IRNR 7,2 t (O'Neill) ; **IBD fixé à 1,0 faute de mesure**. Pays disposant de toutes les séries : 9.

| Pays | IED (référence) | IED min | IED max | Écart |
|---|---|---|---|---|
| PT | 0,87 | 0,00 | 1,11 | 1,11 |
| DE | 0,86 | 0,00 | 1,09 | 1,09 |
| FR | 0,85 | 0,00 | 1,08 | 1,08 |
| CZ | 0,82 | 0,00 | 1,06 | 1,06 |
| SI | 0,81 | 0,00 | 1,05 | 1,05 |
| AT | 0,80 | 0,00 | 1,03 | 1,03 |
| HR | 0,79 | 0,00 | 1,03 | 1,03 |
| LT | 0,69 | 0,00 | 0,93 | 0,93 |
| RO | 0,58 | 0,00 | 0,82 | 0,82 |

Min et max portent sur les 288 configurations testées (3 normalisations × 4 agrégations × 4 pondérations × 2 seuils IRNR × 3 valeurs de l'IBD).

## 4. Effet de chaque choix

Pour chaque choix, on fait varier ce seul paramètre à partir de la référence. La corrélation de rang (Spearman) mesure si le classement des pays est conservé (1 = classement identique).

**Normalisation**

| Option | IED moyen | IED min | IED max | Spearman |
|---|---|---|---|---|
| linéaire : 2 − x/T | 0,00 | 0,00 | 0,00 | 0,23 |
| ratio : T/x | 0,67 | 0,44 | 0,79 | 1,00 |
| hyperbolique : 2/(1 + x/T) | 0,79 | 0,58 | 0,87 | 1,00 |

**Agrégation**

| Option | IED moyen | IED min | IED max | Spearman |
|---|---|---|---|---|
| moyenne géométrique (V1.0) | 0,79 | 0,58 | 0,87 | 1,00 |
| CES ρ = −1 (harmonique) | 0,73 | 0,54 | 0,85 | 0,98 |
| CES ρ = −5 | 0,55 | 0,39 | 0,78 | 0,70 |
| minimum | 0,37 | 0,27 | 0,57 | 0,72 |

**Pondérations**

| Option | IED moyen | IED min | IED max | Spearman |
|---|---|---|---|---|
| égaux (V1.0) | 0,79 | 0,58 | 0,87 | 1,00 |
| IBD renforcé (2, 1, 1) | 0,83 | 0,67 | 0,90 | 1,00 |
| IEE renforcé (1, 2, 1) | 0,76 | 0,55 | 0,87 | 0,85 |
| IRNR renforcé (1, 1, 2) | 0,76 | 0,54 | 0,86 | 0,90 |

**Seuil IRNR**

| Option | IED moyen | IED min | IED max | Spearman |
|---|---|---|---|---|
| 7,2 t (O'Neill) | 0,79 | 0,58 | 0,87 | 1,00 |
| 5 t (Bringezu) | 0,72 | 0,53 | 0,81 | 0,98 |

**Valeur supposée de l’IBD**

| Option | IED moyen | IED min | IED max | Spearman |
|---|---|---|---|---|
| 0,5 | 0,62 | 0,46 | 0,69 | 1,00 |
| 1,0 | 0,79 | 0,58 | 0,87 | 1,00 |
| 1,5 | 0,90 | 0,67 | 1,00 | 1,00 |

## 5. Constats

- **Annulation de l'IED.** 96 configurations sur 288 donnent un IED nul pour tous les pays, dont 96 avec la normalisation linéaire. L'empreinte CO2 dépasse le seuil d'un facteur 2,5 à 5,4 ; au-delà de deux fois le seuil, la normalisation linéaire donne 0, et la moyenne géométrique comme le minimum transmettent ce 0 à l'IED (§6.2 : si une composante tend vers zéro, l'IED tend vers zéro).
- **Aucun pays n'atteint la valeur de référence.** Avec un IBD supposé au plus égal à 1, l'IED ne dépasse pas 0,90 ; il n'atteint 1,11 qu'en supposant un IBD de 1,5, c'est-à-dire une biodiversité en meilleur état que la référence.
- **Compensation à l'intérieur de l'IEE.** Avec une moyenne, un indice d'exploitation de l'eau très inférieur à son seuil (note proche de 2) compense en partie un dépassement important de l'empreinte CO2. Le choix de la fonction d'agrégation se pose donc deux fois : entre les sous-indicateurs d'une composante, et entre les composantes (T3).
- **Ce qui déplace le classement.** Les normalisations ratio et hyperbolique conservent le classement ; les agrégations à faible substituabilité (CES ρ = −5, minimum) et les pondérations le modifient (corrélations de rang de la section 4).
