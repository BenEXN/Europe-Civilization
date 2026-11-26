"""CORINE Land Cover 2018 of the French outermost regions (Guadeloupe, Martinique, Guyane, La Réunion, Mayotte), read
from the IGN Géoplateforme WMS: the European land-cover map (corine_eu) does not reach them."""

from __future__ import annotations

from ..core.europe import INSETS
from ..core.png import read_png
from ..core.source import Source, SourceInfo
from .corine_eu import CLASSES

LAYER = "LANDCOVER.CLC18_DOM"
PX = 900
URL = ("https://data.geopf.fr/wms-r/wms?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetMap&LAYERS={layer}&STYLES="
       "&CRS=EPSG:4326&BBOX={s},{w},{n},{e}&WIDTH={px}&HEIGHT={px}&FORMAT=image/png")
# Standard CORINE legend colours (the WMS draws these).
COLOURS = {
    111: (230, 0, 77), 112: (255, 0, 0), 121: (204, 77, 242), 122: (204, 0, 0), 123: (230, 204, 204),
    124: (230, 204, 230), 131: (166, 0, 204), 132: (166, 77, 0), 133: (255, 77, 255), 141: (255, 166, 255),
    142: (255, 230, 255), 211: (255, 255, 168), 212: (255, 255, 0), 213: (230, 230, 0), 221: (230, 128, 0),
    222: (242, 166, 77), 223: (230, 166, 0), 231: (230, 230, 77), 241: (255, 230, 166), 242: (255, 230, 77),
    243: (230, 204, 77), 244: (242, 204, 166), 311: (128, 255, 0), 312: (0, 166, 0), 313: (77, 255, 0),
    321: (204, 242, 77), 322: (166, 255, 128), 323: (166, 230, 77), 324: (166, 242, 0), 331: (230, 230, 230),
    332: (204, 204, 204), 333: (204, 255, 204), 334: (0, 0, 0), 335: (166, 230, 204), 411: (166, 166, 255),
    412: (77, 77, 255), 421: (204, 204, 255), 422: (230, 230, 255), 423: (166, 166, 230), 511: (0, 204, 242),
    512: (128, 242, 230), 521: (0, 255, 166), 522: (166, 255, 230), 523: (230, 242, 255),
}
DOM = [d for d in INSETS if d["dep"].startswith("FRY")]


def nearest_code(rgb):
    """The class whose legend colour is nearest (the service resamples, so edges carry blended colours), or 0."""
    best, best_d = 0, 1e9
    for code, (r, g, b) in COLOURS.items():
        d = (rgb[0] - r) ** 2 + (rgb[1] - g) ** 2 + (rgb[2] - b) ** 2
        if d < best_d:
            best, best_d = code, d
    return best if best_d <= 3 * 40 ** 2 else 0


class ClcDom(Source):
    info = SourceInfo(
        id="clc_dom",
        title="CORINE Land Cover 2018, French overseas regions",
        publisher="SDES (French Ministry for the Ecological Transition), Copernicus; served by IGN (Géoplateforme)",
        homepage="https://www.statistiques.developpement-durable.gouv.fr/corine-land-cover-0",
        license="Licence Ouverte 2.0 (Copernicus open data)",
        description="2018 land cover of Guadeloupe, Martinique, French Guiana, Réunion and Mayotte, read from IGN's "
        "WMS (one image per inset). CORINE maps only French Guiana's coastal strip: the interior, Amazon rainforest, "
        "is classed as broadleaf forest.",
        used_for=["Land cover of the French outermost regions"],
    )

    def _items(self):
        for d in DOM:
            (w, e), (s_, n) = d["lon"], d["lat"]
            yield d, f"{LAYER}_{d['dep']}.png", URL.format(layer=LAYER, s=s_, w=w, n=n, e=e, px=PX)

    def fetch(self, force=False):
        for _, name, url in self._items():
            self.download(url, name, force=force, expect_binary=True)

    def process(self):
        out, cache = [], {}
        for d, name, _ in self._items():
            w, h, ch, rows, pal = read_png((self.raw_dir / name).read_bytes())
            grid = []
            for row in rows:
                line = []
                for x in range(0, w * ch, ch):
                    if ch == 4 and row[x + 3] < 128:
                        line.append(0)
                        continue
                    rgb = pal[row[x]] if pal else tuple(row[x:x + 3])
                    c = cache.get(rgb)
                    if c is None:
                        c = cache[rgb] = nearest_code(rgb)
                    line.append(c)
                grid.append(line)
            (lw, le), (ls, ln) = d["lon"], d["lat"]
            dx, dy = (le - lw) / w, -(ln - ls) / h
            out.append({"dep": d["dep"], "x0": lw + dx / 2, "dx": dx, "y0": ln + dy / 2, "dy": dy, "cols": w,
                        "rows": grid})
        return {"vintage": "CORINE Land Cover 2018 (DOM)", "_files": [n for _, n, _ in self._items()], "rasters": out,
                "classes": {str(c): n for c, (n, _) in CLASSES.items()}}
