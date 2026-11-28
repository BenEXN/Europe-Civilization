# Évolution de l'IED et de ses composantes — 2015–2023

*Économie Homéostatique, WP V1.0. Résultats sous hypothèses, produits par `analyse/evolution_ied.py` à partir des séries Eurostat du dossier `calibration/`, avec les sous-indicateurs, les repères et les fonctions de `SENSIBILITE_IED.md`. Configuration de référence, IBD supposé égal à 1 et constant. Chaque année est mesurée sans recul ; les repères sont fixes.*

Ces séries décrivent l'évolution passée des pressions mesurées. Elles permettent de borner des tendances ; elles ne renseignent ni la réponse de S au coefficient de régulation u, ni la dynamique F.

## 1. Couverture

| Année | Pays complets | IED moyen du panel |
|---|---|---|
| 2015 | 18 | 0,65 |
| 2016 | 19 | 0,65 |
| 2017 | 19 | 0,64 |
| 2018 | 20 | 0,63 |
| 2019 | 20 | 0,63 |
| 2020 | 19 | 0,65 |
| 2021 | 19 | 0,63 |
| 2022 | 19 | 0,65 |
| 2023 | 19 | 0,68 |

Panel : 16 pays complets chaque année de 2015 à 2023 (AT, CZ, DE, ES, FI, FR, HR, HU, IE, IT, LV, PL, PT, RO, SE, SK). Les moyennes et les tendances décrivent ces pays seulement.

## 2. IED de référence par année

| Pays | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 |
|---|---|---|---|---|---|---|---|---|---|
| IT | 0,77 | 0,77 | 0,78 | 0,77 | 0,79 | 0,81 | 0,78 | 0,77 | 0,79 |
| ES | 0,72 | 0,72 | 0,71 | 0,70 | 0,70 | 0,71 | 0,72 | 0,77 | 0,78 |
| PT | 0,72 | 0,73 | 0,71 | 0,72 | 0,71 | 0,75 | 0,71 | 0,77 | 0,78 |
| DE | 0,68 | 0,68 | 0,69 | 0,69 | 0,71 | 0,72 | 0,70 | 0,73 | 0,76 |
| FR | 0,66 | 0,66 | 0,65 | 0,66 | 0,66 | 0,68 | 0,66 | 0,68 | 0,72 |
| CZ | 0,63 | 0,62 | 0,61 | 0,62 | 0,63 | 0,67 | 0,65 | 0,65 | 0,71 |
| SK | 0,70 | 0,69 | 0,69 | 0,68 | 0,69 | 0,70 | 0,69 | 0,68 | 0,71 |
| AT | 0,64 | 0,62 | 0,65 | 0,65 | 0,66 | 0,66 | 0,65 | 0,66 | 0,69 |
| HU | 0,67 | 0,66 | 0,62 | 0,60 | 0,60 | 0,62 | 0,61 | 0,65 | 0,67 |
| SE | 0,62 | 0,62 | 0,62 | 0,62 | 0,63 | 0,63 | 0,62 | 0,64 | 0,67 |
| HR | 0,70 | 0,74 | 0,65 | 0,65 | 0,64 | 0,65 | 0,64 | 0,65 | 0,66 |
| PL | 0,64 | 0,63 | 0,61 | 0,60 | 0,62 | 0,62 | 0,61 | 0,63 | 0,64 |
| LV | 0,60 | 0,61 | 0,59 | 0,59 | 0,59 | 0,58 | 0,56 | 0,57 | 0,62 |
| RO | 0,64 | 0,63 | 0,63 | 0,59 | 0,56 | 0,56 | 0,53 | 0,55 | 0,55 |
| FI | 0,52 | 0,51 | 0,50 | 0,50 | 0,51 | 0,51 | 0,50 | 0,52 | 0,54 |
| IE | 0,53 | 0,51 | 0,49 | 0,48 | 0,45 | 0,47 | 0,50 | 0,52 | 0,52 |

## 3. Variation 2015–2023 et décomposition

La variation de ln IED se répartit exactement entre l'IEE et l'IRNR (moyenne géométrique à poids égaux, IBD constant) : contribution = ⅓ × variation du logarithme de la composante. Les colonnes des sous-indicateurs donnent la variation de la grandeur mesurée par habitant (une baisse est une pression plus faible).

| Pays | IED 2015 | IED 2023 | Variation | Pente / an | Contribution IEE | Contribution IRNR | CO2 | Azote | Phosphore | Matière totale |
|---|---|---|---|---|---|---|---|---|---|---|
| CZ | 0,63 | 0,71 | +13,8 % | 0,0091 | 0,098 | 0,031 | −15 % | −41 % | −42 % | −13 % |
| DE | 0,68 | 0,76 | +11,9 % | 0,0087 | 0,116 | −0,004 | −19 % | −40 % | −62 % | +2 % |
| ES | 0,72 | 0,78 | +9,5 % | 0,0075 | 0,087 | 0,004 | −13 % | −29 % | −43 % | −2 % |
| FR | 0,66 | 0,72 | +8,3 % | 0,0056 | 0,069 | 0,011 | −15 % | −18 % | −37 % | −5 % |
| PT | 0,72 | 0,78 | +7,9 % | 0,0067 | 0,062 | 0,014 | −23 % | −19 % | −30 % | −6 % |
| SE | 0,62 | 0,67 | +7,9 % | 0,0044 | 0,046 | 0,030 | −28 % | −9 % | −13 % | −11 % |
| AT | 0,64 | 0,69 | +6,7 % | 0,0048 | 0,043 | 0,023 | −9 % | −10 % | −35 % | −9 % |
| FI | 0,52 | 0,54 | +4,9 % | 0,0026 | 0,039 | 0,009 | −28 % | −3 % | −8 % | −3 % |
| LV | 0,60 | 0,62 | +3,1 % | −0,0022 | 0,006 | 0,025 | −17 % | +13 % | −1 % | −11 % |
| IT | 0,77 | 0,79 | +2,2 % | 0,0015 | 0,003 | 0,019 | −8 % | +4 % | +3 % | −9 % |
| HU | 0,67 | 0,67 | +1,0 % | −0,0001 | 0,046 | −0,037 | +2 % | −15 % | −32 % | +18 % |
| SK | 0,70 | 0,71 | +0,9 % | 0,0006 | 0,023 | −0,014 | −4 % | −8 % | −16 % | +7 % |
| PL | 0,64 | 0,64 | −0,3 % | −0,0001 | −0,001 | −0,002 | −3 % | +11 % | −5 % | +1 % |
| IE | 0,53 | 0,52 | −0,8 % | 0,0005 | 0,058 | −0,067 | −3 % | −23 % | −25 % | +33 % |
| HR | 0,70 | 0,66 | −5,4 % | −0,0075 | −0,025 | −0,030 | +26 % | +6 % | −1 % | +15 % |
| RO | 0,64 | 0,55 | −13,3 % | −0,0139 | −0,082 | −0,061 | +20 % | +31 % | +65 % | +26 % |

## 4. Robustesse du sens de la variation

Pour chaque pays, nombre des 96 configurations de la grille (normalisation, agrégation, pondérations, repère IRNR ; IBD = 1) où l'IED augmente, diminue ou ne varie pas entre 2015 et 2023. « Stable » regroupe surtout les configurations où l'IED est nul les deux années (normalisation linéaire).

| Pays | Hausse | Baisse | Stable | Sens en référence |
|---|---|---|---|---|
| AT | 64 | 0 | 32 | hausse |
| CZ | 64 | 0 | 32 | hausse |
| DE | 64 | 0 | 32 | hausse |
| ES | 64 | 0 | 32 | hausse |
| FI | 64 | 0 | 32 | hausse |
| FR | 64 | 0 | 32 | hausse |
| HR | 0 | 64 | 32 | baisse |
| HU | 58 | 6 | 32 | hausse |
| IE | 50 | 14 | 32 | baisse |
| IT | 64 | 0 | 32 | hausse |
| LV | 49 | 15 | 32 | hausse |
| PL | 32 | 32 | 32 | baisse |
| PT | 64 | 0 | 32 | hausse |
| RO | 0 | 64 | 32 | baisse |
| SE | 64 | 0 | 32 | hausse |
| SK | 54 | 10 | 32 | hausse |

## 5. Codes limitant la lecture des tendances

Termes portant un code de rupture de série (b) ou de définition différente (d) sur la période ; la variation correspondante mêle évolution mesurée et changement de méthode.

- **AT** : 2022 N engrais minéraux (t) : d ; 2022 P engrais minéraux (t) : d ; 2023 N engrais minéraux (t) : d ; 2023 P engrais minéraux (t) : d
- **PL** : 2020 population (milliers) : b ; 2022 population (milliers) : b
- **SK** : 2021 population (milliers) : b

## 6. Lecture

- En configuration de référence, l'IED augmente entre 2015 et 2023 pour 12 des 16 pays du panel ; pour 9 d'entre eux, aucune configuration de la grille ne donne de baisse.
- Une hausse de l'IED signale une baisse des pressions mesurées par habitant rapportées à des repères fixes ; elle ne dit pas que le niveau 1 est approché, ni que l'état biophysique s'améliore (l'IBD n'est pas mesuré).
- Les données sont publiées avec un délai de un à deux ans et révisées ; une série temporelle de l'IED dépend du millésime de téléchargement.
