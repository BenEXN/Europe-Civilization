"""CORINE Land Cover 2018 for metropolitan France, read from the IGN Géoplateforme WMS as a ~380 m raster."""

from __future__ import annotations

from ..core.geo import INSETS
from ..core.png import read_png
from ..core.source import Source, SourceInfo

YEAR = 2018
LAYER = "LANDCOVER.CLC18_FR"
DOM_LAYER = "LANDCOVER.CLC18_DOM"
DOM_PX = 900
LAT, LON = (41.2, 51.2), (-5.4, 9.9)
TILES = 3  # 3 × 3 requests
TILE_PX = 1000
URL = (
    "https://data.geopf.fr/wms-r/wms?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetMap&LAYERS={layer}&STYLES="
    "&CRS=EPSG:4326&BBOX={s},{w},{n},{e}&WIDTH={px}&HEIGHT={px}&FORMAT=image/png"
)

# CLC level-3 classes: code → (standard legend colour, French name, NLCD-like code the world builder groups).
# NLCD-like codes: 11 water, 12 ice, 21 green urban, 22/23/24 built-up, 31 barren, 41/42/43 forest,
# 52 scrub, 71 grassland, 81 pasture, 82 crops, 95 wetland.
CLASSES = {
    111: ((230, 0, 77), "Tissu urbain continu", 24),
    112: ((255, 0, 0), "Tissu urbain discontinu", 22),
    121: ((204, 77, 242), "Zones industrielles ou commerciales", 23),
    122: ((204, 0, 0), "Réseaux routier et ferroviaire", 23),
    123: ((230, 204, 204), "Zones portuaires", 23),
    124: ((230, 204, 230), "Aéroports", 23),
    131: ((166, 0, 204), "Extraction de matériaux", 31),
    132: ((166, 77, 0), "Décharges", 23),
    133: ((255, 77, 255), "Chantiers", 23),
    141: ((255, 166, 255), "Espaces verts urbains", 21),
    142: ((255, 230, 255), "Équipements sportifs et de loisirs", 21),
    211: ((255, 255, 168), "Terres arables hors irrigation", 82),
    212: ((255, 255, 0), "Périmètres irrigués", 82),
    213: ((230, 230, 0), "Rizières", 82),
    221: ((230, 128, 0), "Vignobles", 82),
    222: ((242, 166, 77), "Vergers", 82),
    223: ((230, 166, 0), "Oliveraies", 82),
    231: ((230, 230, 77), "Prairies", 81),
    241: ((255, 230, 166), "Cultures annuelles et permanentes", 82),
    242: ((255, 230, 77), "Systèmes culturaux et parcellaires complexes", 81),
    243: ((230, 204, 77), "Agriculture et espaces naturels", 81),
    244: ((242, 204, 166), "Territoires agroforestiers", 81),
    311: ((128, 255, 0), "Forêts de feuillus", 41),
    312: ((0, 166, 0), "Forêts de conifères", 42),
    313: ((77, 255, 0), "Forêts mélangées", 43),
    321: ((204, 242, 77), "Pelouses et pâturages naturels", 71),
    322: ((166, 255, 128), "Landes et broussailles", 52),
    323: ((166, 230, 77), "Végétation sclérophylle (maquis, garrigue)", 52),
    324: ((166, 242, 0), "Forêt et végétation arbustive en mutation", 52),
    331: ((230, 230, 230), "Plages, dunes et sable", 31),
    332: ((204, 204, 204), "Roches nues", 31),
    333: ((204, 255, 204), "Végétation clairsemée", 71),
    334: ((0, 0, 0), "Zones incendiées", 52),
    335: ((166, 230, 204), "Glaciers et neiges éternelles", 12),
    411: ((166, 166, 255), "Marais intérieurs", 95),
    412: ((77, 77, 255), "Tourbières", 95),
    421: ((204, 204, 255), "Marais maritimes", 95),
    422: ((230, 230, 255), "Marais salants", 95),
    423: ((166, 166, 230), "Zones intertidales", 95),
    511: ((0, 204, 242), "Cours et voies d'eau", 11),
    512: ((128, 242, 230), "Plans d'eau", 11),
    521: ((0, 255, 166), "Lagunes littorales", 11),
    522: ((166, 255, 230), "Estuaires", 11),
    523: ((230, 242, 255), "Mers et océans", 11),
}
# One character per class so the interim stores each raster row as a short string ("." = no data).
CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqr"
LEGEND = dict(zip(sorted(CLASSES), CHARS))
PALETTE = [(rgb, LEGEND[code]) for code, (rgb, _, _) in CLASSES.items()]


def nearest_char(rgb: tuple[int, int, int]) -> str:
    """The class whose legend colour is nearest (the service resamples, so edges carry blended colours)."""
    r, g, b = rgb
    best, best_d = ".", 1e9
    for (pr, pg, pb), ch in PALETTE:
        d = (r - pr) ** 2 + (g - pg) ** 2 + (b - pb) ** 2
        if d < best_d:
            best, best_d = ch, d
    return best if best_d <= 3 * 40 ** 2 else "."


class Clc(Source):
    info = SourceInfo(
        id="clc",
        title=f"CORINE Land Cover {YEAR}, France métropolitaine",
        publisher="Service des données et études statistiques (SDES), Copernicus / Agence européenne pour "
        "l'environnement ; diffusé par l'IGN (Géoplateforme)",
        homepage="https://www.statistiques.developpement-durable.gouv.fr/corine-land-cover-0",
        license="Licence Ouverte 2.0 (données Copernicus en accès libre)",
        description=f"Occupation du sol en {YEAR} (44 postes, unité minimale 25 ha), lue sur le service WMS de l'IGN en "
        "neuf tuiles d'environ 380 m par pixel. Le biome de chaque hexagone (forêt, lande, prairie, cultures, "
        "zones humides, ville…) et ses parts d'occupation viennent d'environ 400 points tirés à l'intérieur.",
        used_for=["Occupation du sol des hexagones (biomes)", "Parts de forêt, cultures, prairies, ville",
                  "Vignobles et vergers"],
    )

    def _tiles(self):
        dlat, dlon = (LAT[1] - LAT[0]) / TILES, (LON[1] - LON[0]) / TILES
        for j in range(TILES):  # north to south
            n = LAT[1] - j * dlat
            for i in range(TILES):
                w = LON[0] + i * dlon
                yield j, i, f"{LAYER}_{j}{i}.png", URL.format(
                    layer=LAYER, s=round(n - dlat, 6), w=round(w, 6), n=round(n, 6), e=round(w + dlon, 6), px=TILE_PX)

    # The overseas départements: one tile per inset window, from the DOM layer (same legend).
    def _overseas(self):
        for d in INSETS:
            (w, e), (s_, n) = d["lon"], d["lat"]
            name = f"{DOM_LAYER}_{d['dep']}.png"
            yield d, name, URL.format(layer=DOM_LAYER, s=s_, w=w, n=n, e=e, px=DOM_PX)

    def fetch(self, force=False):
        for _, _, name, url in self._tiles():
            self.download(url, name, force=force, expect_binary=True)
        for _, name, url in self._overseas():
            self.download(url, name, force=force, expect_binary=True)

    def _decode(self, name, cache):
        w, h, ch, rows, pal = read_png((self.raw_dir / name).read_bytes())
        out = []
        for row in rows:
            line = []
            for x in range(0, w * ch, ch):
                if ch == 4 and row[x + 3] < 128:
                    line.append(".")
                    continue
                rgb = pal[row[x]] if pal else tuple(row[x:x + 3])
                c = cache.get(rgb)
                if c is None:
                    c = cache[rgb] = nearest_char(rgb)
                line.append(c)
            out.append("".join(line))
        return w, h, out

    def process(self):
        size = TILES * TILE_PX
        grid = [[None] * TILES for _ in range(TILES)]
        cache: dict = {}
        for j, i, name, _ in self._tiles():
            w, h, ch, rows, pal = read_png((self.raw_dir / name).read_bytes())
            if (w, h) != (TILE_PX, TILE_PX):
                raise ValueError(f"{name}: {w}×{h}, expected {TILE_PX}²")
            out = []
            for row in rows:
                line = []
                for x in range(0, w * ch, ch):
                    if ch == 4 and row[x + 3] < 128:
                        line.append(".")
                        continue
                    rgb = pal[row[x]] if pal else tuple(row[x:x + 3])
                    c = cache.get(rgb)
                    if c is None:
                        c = cache[rgb] = nearest_char(rgb)
                    line.append(c)
                out.append("".join(line))
            grid[j][i] = out
        rows = ["".join(grid[j][i][r] for i in range(TILES)) for j in range(TILES) for r in range(TILE_PX)]
        dx = (LON[1] - LON[0]) / size
        dy = -(LAT[1] - LAT[0]) / size
        overseas = []
        for d, name, _ in self._overseas():
            w, h, out = self._decode(name, cache)
            (lw, le), (ls, ln) = d["lon"], d["lat"]
            ddx, ddy = (le - lw) / w, -(ln - ls) / h
            overseas.append({"dep": d["dep"], "x0": lw + ddx / 2, "dx": ddx, "y0": ln + ddy / 2, "dy": ddy,
                             "cols": w, "rows_n": h, "rows": out})
        return {
            "vintage": f"CORINE Land Cover {YEAR}, ~380 m",
            "_files": [name for _, _, name, _ in self._tiles()] + [name for _, name, _ in self._overseas()],
            "overseas": overseas,
            "crs": "EPSG:4326",
            # Pixel CENTRE of column 0 / row 0 and pixel size, in degrees (y size is negative: rows go south).
            "x0": LON[0] + dx / 2, "dx": dx, "y0": LAT[1] + dy / 2, "dy": dy,
            "cols": size, "rows_n": size,
            "legend": {ch: code for code, ch in LEGEND.items()},
            "classes": {code: name for code, (_, name, _) in CLASSES.items()},
            "nlcd": {code: nlcd for code, (_, _, nlcd) in CLASSES.items()},
            "rows": rows,
        }
