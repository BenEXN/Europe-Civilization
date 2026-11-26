"""What the Europe map covers: its countries (the map's "states"), their capitals, and the outermost regions drawn in
insets. NUTS 2024 country codes (Eurostat uses EL for Greece)."""

from __future__ import annotations

# code → (English name, capital, sub-region). The 27 EU members, the four EFTA states and the Western Balkans.
COUNTRIES = {
    "AT": ("Austria", "Vienna", "Central Europe"),
    "BE": ("Belgium", "Brussels", "Western Europe"),
    "BG": ("Bulgaria", "Sofia", "South-East Europe"),
    "CY": ("Cyprus", "Nicosia", "Southern Europe"),
    "CZ": ("Czechia", "Prague", "Central Europe"),
    "DE": ("Germany", "Berlin", "Central Europe"),
    "DK": ("Denmark", "Copenhagen", "Northern Europe"),
    "EE": ("Estonia", "Tallinn", "Northern Europe"),
    "EL": ("Greece", "Athens", "Southern Europe"),
    "ES": ("Spain", "Madrid", "Southern Europe"),
    "FI": ("Finland", "Helsinki", "Northern Europe"),
    "FR": ("France", "Paris", "Western Europe"),
    "HR": ("Croatia", "Zagreb", "South-East Europe"),
    "HU": ("Hungary", "Budapest", "Central Europe"),
    "IE": ("Ireland", "Dublin", "Western Europe"),
    "IT": ("Italy", "Rome", "Southern Europe"),
    "LT": ("Lithuania", "Vilnius", "Northern Europe"),
    "LU": ("Luxembourg", "Luxembourg", "Western Europe"),
    "LV": ("Latvia", "Riga", "Northern Europe"),
    "MT": ("Malta", "Valletta", "Southern Europe"),
    "NL": ("Netherlands", "Amsterdam", "Western Europe"),
    "PL": ("Poland", "Warsaw", "Central Europe"),
    "PT": ("Portugal", "Lisbon", "Southern Europe"),
    "RO": ("Romania", "Bucharest", "South-East Europe"),
    "SE": ("Sweden", "Stockholm", "Northern Europe"),
    "SI": ("Slovenia", "Ljubljana", "Central Europe"),
    "SK": ("Slovakia", "Bratislava", "Central Europe"),
    "IS": ("Iceland", "Reykjavik", "Northern Europe"),
    "LI": ("Liechtenstein", "Vaduz", "Central Europe"),
    "NO": ("Norway", "Oslo", "Northern Europe"),
    "CH": ("Switzerland", "Bern", "Central Europe"),
    "AL": ("Albania", "Tirana", "South-East Europe"),
    "BA": ("Bosnia and Herzegovina", "Sarajevo", "South-East Europe"),
    "ME": ("Montenegro", "Podgorica", "South-East Europe"),
    "MK": ("North Macedonia", "Skopje", "South-East Europe"),
    "RS": ("Serbia", "Belgrade", "South-East Europe"),
    "XK": ("Kosovo", "Pristina", "South-East Europe"),
}
EU = {"AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE", "EL", "ES", "FI", "FR", "HR", "HU", "IE", "IT", "LT", "LU", "LV",
      "MT", "NL", "PL", "PT", "RO", "SE", "SI", "SK"}
EFTA = {"IS", "LI", "NO", "CH"}
SUBREGIONS = ["Northern Europe", "Western Europe", "Central Europe", "Southern Europe", "South-East Europe"]

# ISO 3166 alpha-2 for the two codes Eurostat spells differently (GeoNames, Natural Earth, GISCO countries use ISO).
ISO2 = {"EL": "GR"} | {c: c for c in COUNTRIES if c != "EL"}
FROM_ISO2 = {v: k for k, v in ISO2.items()} | {"EL": "EL"}  # GISCO country files use EL too

# NUTS regions left off the map: Svalbard and Jan Mayen (Arctic islands with a few thousand people).
EXCLUDED_NUTS = ("NO0B",)

# The outermost regions, drawn in insets laid on open sea (core/geo.py). nuts: NUTS 2 codes drawn in the inset;
# lon/lat: the window; k: scale relative to the main map; x/y: the frame's top-left corner, in map units, chosen on
# the built map so no frame touches a coast.
INSETS = [
    {"dep": "PT20", "nuts": ["PT20"], "name": "Azores", "lon": [-31.40, -24.90], "lat": [36.85, 39.80], "k": 0.75, "x": 140, "y": 2150},
    {"dep": "PT30", "nuts": ["PT30"], "name": "Madeira", "lon": [-17.35, -16.20], "lat": [32.35, 33.15], "k": 1.0, "x": 160, "y": 2900},
    {"dep": "ES70", "nuts": ["ES70"], "name": "Canary Islands", "lon": [-18.25, -13.30], "lat": [27.55, 29.50], "k": 0.75, "x": 140, "y": 3260},
    {"dep": "FRY1", "nuts": ["FRY1"], "name": "Guadeloupe", "lon": [-61.90, -60.95], "lat": [15.80, 16.55], "k": 1.0, "x": 2300, "y": 300},
    {"dep": "FRY2", "nuts": ["FRY2"], "name": "Martinique", "lon": [-61.30, -60.75], "lat": [14.35, 14.90], "k": 1.0, "x": 2300, "y": 650},
    {"dep": "FRY3", "nuts": ["FRY3"], "name": "French Guiana", "lon": [-54.70, -51.50], "lat": [2.00, 5.85], "k": 0.35, "x": 2300, "y": 950},
    {"dep": "FRY4", "nuts": ["FRY4"], "name": "Réunion", "lon": [55.15, 55.90], "lat": [-21.45, -20.80], "k": 1.0, "x": 2650, "y": 300},
    {"dep": "FRY5", "nuts": ["FRY5"], "name": "Mayotte", "lon": [44.95, 45.35], "lat": [-13.05, -12.60], "k": 1.5, "x": 2650, "y": 600},
]
INSET_NUTS = {n: d["dep"] for d in INSETS for n in d["nuts"]}


def inset_of_nuts(code: str):
    """The inset id ("dep") a NUTS code is drawn in, or None for the main map."""
    for prefix, dep in INSET_NUTS.items():
        if code.startswith(prefix):
            return dep
    return None


def mapped(code: str) -> bool:
    """True for a NUTS code (any level) of a map country, outside the excluded regions."""
    return code[:2] in COUNTRIES and not code.startswith(EXCLUDED_NUTS)


# English names of the cities whose local name an English reader would not use (GISCO and Eurostat give local names).
EXONYMS = {
    "Wien": "Vienna", "Bruxelles / Brussel": "Brussels", "Bruxelles/Brussel": "Brussels", "Brussel": "Brussels",
    "Bruxelles": "Brussels", "Antwerpen": "Antwerp", "Gent": "Ghent", "Brugge": "Bruges", "Liège": "Liège",
    "Sofiya": "Sofia", "Lefkosia": "Nicosia", "Lemesos": "Limassol", "Praha": "Prague", "Plzeň": "Pilsen",
    "München": "Munich", "Köln": "Cologne", "Nürnberg": "Nuremberg", "Hannover": "Hanover",
    "Frankfurt am Main": "Frankfurt", "Freiburg im Breisgau": "Freiburg", "Konstanz": "Constance",
    "København": "Copenhagen", "Athina": "Athens", "Thessaloniki": "Thessaloniki", "Irakleio": "Heraklion",
    "Patra": "Patras", "Sevilla": "Seville", "Donostia/San Sebastián": "San Sebastián",
    "Donostia / San Sebastián": "San Sebastián", "Vitoria/Gasteiz": "Vitoria-Gasteiz", "Pamplona/Iruña": "Pamplona",
    "València": "Valencia", "Lisboa": "Lisbon", "Bucureşti": "Bucharest", "București": "Bucharest",
    "Warszawa": "Warsaw", "Roma": "Rome", "Milano": "Milan", "Napoli": "Naples", "Torino": "Turin",
    "Firenze": "Florence", "Venezia": "Venice", "Genova": "Genoa", "Padova": "Padua", "Mantova": "Mantua",
    "Siracusa": "Syracuse", "Den Haag": "The Hague", "'s-Gravenhage": "The Hague", "Göteborg": "Gothenburg",
    "Helsinki / Helsingfors": "Helsinki", "Helsinki/Helsingfors": "Helsinki", "Turku / Åbo": "Turku",
    "Turku/Åbo": "Turku", "Espoo/Esbo": "Espoo", "Vantaa/Vanda": "Vantaa", "Biel/Bienne": "Biel/Bienne", "Rīga": "Riga", "Beograd": "Belgrade",
    "Tiranë": "Tirana", "Prishtinë": "Pristina", "Prishtina": "Pristina", "Reykjavík": "Reykjavik",
    "Valletta": "Valletta", "Genève": "Geneva", "Zürich": "Zurich", "Basel": "Basel", "Bern": "Bern",
    "Luzern": "Lucerne", "Biel/Bienne": "Biel/Bienne", "Kraków": "Kraków", "Lisboa (greater city)": "Lisbon",
}


def english_name(name: str) -> str:
    return EXONYMS.get(name, name)
