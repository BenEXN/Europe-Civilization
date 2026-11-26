"""Place names for an English-speaking map: Greek and Cyrillic transliterated to Latin letters (simplified ELOT 743 and
BGN-style romanisation), administrative words dropped ("Κοινότητα …", "Municipiul …", "… vald")."""

from __future__ import annotations

import re
import unicodedata

GREEK_DIGRAPHS = [("ου", "ou"), ("αι", "ai"), ("ει", "ei"), ("οι", "oi"), ("αυ", "av"), ("ευ", "ev"), ("γγ", "ng"),
                  ("γκ", "gk"), ("μπ", "mp"), ("ντ", "nt"), ("τσ", "ts"), ("τζ", "tz")]
GREEK = dict(zip("αβγδεζηθικλμνξοπρσςτυφχψω", ["a", "v", "g", "d", "e", "z", "i", "th", "i", "k", "l", "m", "n", "x",
                                                "o", "p", "r", "s", "s", "t", "y", "f", "ch", "ps", "o"]))
CYRILLIC = {"а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ж": "zh", "з": "z", "и": "i", "й": "y",
            "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
            "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sht", "ъ": "a", "ь": "y", "ю": "yu", "я": "ya",
            "ѓ": "gj", "ѕ": "dz", "ј": "j", "љ": "lj", "њ": "nj", "ќ": "kj", "џ": "dzh", "ђ": "dj", "ћ": "c", "э": "e",
            "ы": "y", "ё": "yo", "є": "ye", "і": "i", "ї": "yi"}
PREFIXES = re.compile(r"^(Δημοτική Κοινότητα|Τοπική Κοινότητα|Ψευδοκοινότητα|Ψευδοκοινοτητα|Κοινότητα|Δήμος|"
                      r"Municipiul|Oraş|Oraș|Comuna|Gmina|Miasto)\s+", re.I)
SUFFIXES = re.compile(r"(\s+(vald|linn|novads|pilsēta|miesto savivaldybė|rajono savivaldybė|savivaldybė)|"
                      r",\s*[^,]*(stadt|Stadt|Markt|Gemeinde|Flecken|gemeinde)[^,]*)$")


def _strip_accents(s: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFD", s) if unicodedata.category(ch) != "Mn")


def _word(w: str) -> str:
    low = _strip_accents(w.lower())
    if re.search(r"[Ͱ-Ͽ]", low):
        if low.startswith("μπ"):
            low = "b" + low[2:]
        elif low.startswith("ντ"):
            low = "d" + low[2:]
        for a, b in GREEK_DIGRAPHS:
            low = low.replace(a, b)
        out = "".join(GREEK.get(ch, ch) for ch in low)
    elif re.search(r"[Ѐ-ӿ]", low):
        out = "".join(CYRILLIC.get(ch, ch) for ch in low)
    else:
        return w
    return out[:1].upper() + out[1:]


def latin(name: str) -> str:
    """'Κοινότητα Νέας Απολλωνίας' → 'Nea Apollonia'; 'Велес' → 'Veles'; 'Alutaguse vald' → 'Alutaguse'."""
    genitive = bool(re.match(r"^(Δημοτική |Τοπική )?(Ψευδο)?[Κκ]οιν", name.strip()))  # "community of X": X is genitive
    n = SUFFIXES.sub("", PREFIXES.sub("", name.strip()))
    if not re.search("[\u0370-\u04ff]", n):
        return n
    out = "".join(_word(w) for w in re.split(r"(\s+|-)", n) if w)
    if genitive:  # back to the nominative, the form maps use: Thessalonikis → Thessaloniki, Pyrgou → Pyrgos
        out = " ".join(_nominative(w) for w in out.split(" "))
    return out


def _nominative(w: str) -> str:
    for gen, nom in (("ias", "ia"), ("ou", "os"), ("is", "i"), ("as", "a")):
        if w.endswith(gen) and len(w) > len(gen) + 2:
            return w[: -len(gen)] + nom
    return w


# GISCO names every Belgian municipality in Dutch. In Wallonia and Brussels the French name is the one in use there
# (Brussels is bilingual; English-language maps use the French names): Dutch exonym → French name.
BE_FRENCH = {
    "Brussel": "Bruxelles", "Elsene": "Ixelles", "Oudergem": "Auderghem", "Schaarbeek": "Schaerbeek",
    "Sint-Agatha-Berchem": "Berchem-Sainte-Agathe", "Sint-Gillis": "Saint-Gilles", "Sint-Jans-Molenbeek": "Molenbeek-Saint-Jean",
    "Sint-Joost-ten-Node": "Saint-Josse-ten-Noode", "Sint-Lambrechts-Woluwe": "Woluwe-Saint-Lambert",
    "Sint-Pieters-Woluwe": "Woluwe-Saint-Pierre", "Ukkel": "Uccle", "Vorst": "Forest",
    "Watermaal-Bosvoorde": "Watermael-Boitsfort",
    "Luik": "Liège", "Namen": "Namur", "Doornik": "Tournai", "Bergen": "Mons", "Aarlen": "Arlon", "Aat": "Ath",
    "Bastenaken": "Bastogne", "Nijvel": "Nivelles", "Eigenbrakel": "Braine-l'Alleud", "Kasteelbrakel": "Braine-le-Château",
    "'s-Gravenbrakel": "Braine-le-Comte", "Waver": "Wavre", "Hoei": "Huy", "Edingen": "Enghien", "Moeskroen": "Mouscron",
    "Komen-Waasten": "Comines-Warneton", "Lessen": "Lessines", "Zinnik": "Soignies", "Geldenaken": "Jodoigne",
    "Terhulpen": "La Hulpe", "Tubeke": "Tubize", "Itter": "Ittre", "Roosbeek": "Rebecq", "Opzullik": "Silly",
    "Vloesberg": "Flobecq", "Elzele": "Ellezelles", "Wezet": "Visé", "Borgworm": "Waremme", "Hannuit": "Hannut",
    "Limburg": "Limbourg", "Stablo": "Stavelot", "Gembloers": "Gembloux", "Genepiën": "Genappe", "Graven": "Grez-Doiceau",
    "Bevekom": "Beauvechain", "Perwijs": "Perwez", "Lijsem": "Lincent", "Heylissem": "Hélécine", "Nieuwkasteel": "Neufchâteau",
    "Martelingen": "Martelange", "Blieberg": "Plombières", "Lens (Henegouwen)": "Lens", "Sint-Joris-Weert": "Saint-Georges",
    "Steenkerque": "Steenkerque", "Lembeek": "Lembeek", "Ottignies-Louvain-la-Neuve": "Ottignies-Louvain-la-Neuve",
    "Bitsingen": "Bassenge", "Jurbeke": "Jurbise", "Oerle": "Oreye", "’s Gravenbrakel": "Braine-le-Comte",
    "Weismes": "Waimes",
}


def belgian_local(name: str, nuts3: str | None) -> str:
    """The French name of a Walloon or Brussels municipality (NUTS BE1, BE3), else the name as given."""
    if not nuts3 or not nuts3.startswith(("BE1", "BE3")):
        return name
    base = name.split(" (")[0].strip()
    return BE_FRENCH.get(name, BE_FRENCH.get(base, base))
