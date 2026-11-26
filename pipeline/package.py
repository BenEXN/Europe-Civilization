"""Build the deploy package: one file, europeciv.zip in the project root. It unzips to a europeciv/ folder holding the static
site, ready to upload as /europeciv/. (dist/europeciv/ is the same folder unzipped, kept for local testing.)

The site gets a copy of the source code as europeciv-source.zip, linked from the in-app help, so anyone can download,
run and remix it. Both zips are deterministic (sorted entries, fixed timestamps), so rebuilding from unchanged files
gives byte-identical archives.
"""

from __future__ import annotations

import hashlib
import shutil
import zipfile
from pathlib import Path

from .core.paths import ROOT, WEB

NAME = "europeciv"
DIST = ROOT / "dist"
SITE = DIST / NAME
SOURCE_ZIP = f"{NAME}-source.zip"

# What goes into the source zip (relative to ROOT). Downloads, caches and build output are left out: anyone can
# recreate them with `uv run python -m pipeline all`.
SOURCE_ITEMS = ["README.md", "LICENSE", "pyproject.toml", "uv.lock", ".gitignore", "docs", "pipeline", "server", "tests", "web"]
SKIP_NAMES = {"__pycache__", ".DS_Store"}
SKIP_SUFFIXES = {".pyc", ".part"}
# Dev-only pages (art gallery, trailer maker) ship in the source zip but not on the public site.
SITE_SKIP_DIRS = {"dev"}
# Served by the API (server/api.py), never as a static file: it lists the challenge's communes and their positions.
SITE_SKIP_FILES = {"data/defi.json"}
API = DIST / "europeciv-api"
API_DATA = ["communes.json", "cities.json", "states.json", "defi.json"]

ZIP_TIME = (2026, 1, 1, 0, 0, 0)


def _files(base: Path, rel_items):
    for item in rel_items:
        p = base / item
        if p.is_file():
            yield p
        elif p.is_dir():
            for f in sorted(p.rglob("*")):
                if f.is_file() and not (SKIP_NAMES & set(f.relative_to(base).parts)) and f.suffix not in SKIP_SUFFIXES:
                    yield f


def _zip(path: Path, files, base: Path, prefix: str) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".zip.part")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for f in sorted(set(files), key=lambda f: f.relative_to(base).as_posix()):
            info = zipfile.ZipInfo(f"{prefix}/{f.relative_to(base).as_posix()}", ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, f.read_bytes(), compresslevel=9)
    tmp.replace(path)
    return path.stat().st_size


def _code_version(site: Path) -> str:
    """'v-' + the first 10 hex digits of a hash of every file under js/ and css/ (path and content)."""
    h = hashlib.sha256()
    for d in ("js", "css"):
        for f in sorted((site / d).rglob("*")):
            if f.is_file():
                h.update(f.relative_to(site).as_posix().encode())
                h.update(f.read_bytes())
    return "v-" + h.hexdigest()[:10]


def cmd_package() -> None:
    missing = [p for p in ("data/cities.json", "data/world.json", "index.html") if not (WEB / p).exists()]
    if missing:
        raise SystemExit(f"web/ is incomplete ({', '.join(missing)} missing): run `uv run python -m pipeline all` first")
    if SITE.exists():
        shutil.rmtree(SITE)
    SITE.mkdir(parents=True)

    # 1. The site: web/ without the dev pages.
    n_site = 0
    for f in _files(WEB, ["."]):
        rel = f.relative_to(WEB)
        if rel.parts[0] in SITE_SKIP_DIRS or rel.as_posix() in SITE_SKIP_FILES:
            continue
        dst = SITE / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, dst)
        n_site += 1

    # 1b. Code and styles go in a folder named after their content (v-<hash>/js, v-<hash>/css), and index.html points
    # there. A CDN or browser that caches scripts for hours (Cloudflare gives .js/.css a 4 h browser TTL whatever the
    # origin says) then never mixes an old script with new data: each release has new script URLs. Modules and the
    # lazily loaded stylesheets use module-relative paths, so they follow; data stays at data/ (revalidated).
    version = _code_version(SITE)
    vdir = SITE / version
    vdir.mkdir()
    for d in ("js", "css"):
        shutil.move(str(SITE / d), str(vdir / d))
    index = SITE / "index.html"
    html = index.read_text()
    for old, new in (('href="css/', f'href="{version}/css/'), ('src="js/', f'src="{version}/js/')):
        if old not in html:
            raise SystemExit(f"index.html has no {old!r} reference to rewrite")
        html = html.replace(old, new)
    index.write_text(html)

    # 1c. The API (server/api.py) and the data it reads, for /srv/hosting/apps/europeciv-api on the server.
    if API.exists():
        shutil.rmtree(API)
    (API / "data").mkdir(parents=True)
    shutil.copy2(ROOT / "server" / "api.py", API / "api.py")
    for name in API_DATA:
        shutil.copy2(WEB / "data" / name, API / "data" / name)

    # 2. The source code, served next to the site.
    src_files = [f for f in _files(ROOT, SOURCE_ITEMS)
                 if not (f.is_relative_to(WEB) and f.relative_to(WEB).as_posix() in SITE_SKIP_FILES)]
    src_size = _zip(SITE / SOURCE_ZIP, src_files, ROOT, NAME)

    # 3. The whole site as one zip, for uploading.
    bundle = ROOT / f"{NAME}.zip"
    site_size = _zip(bundle, _files(SITE, ["."]), SITE, NAME)
    (DIST / f"{NAME}-site.zip").unlink(missing_ok=True)  # older layout

    mb = lambda b: f"{b / 1e6:.1f} MB"
    print(f"{bundle.name}  ({mb(site_size)})  ← upload this: it unzips to {NAME}/ ({n_site} site files + {SOURCE_ZIP}); "
          f"code in {version}/")
    print(f"  {SOURCE_ZIP}: {len(src_files)} files, {mb(src_size)}")
