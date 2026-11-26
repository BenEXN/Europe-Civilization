"""A minimal .xlsx reader (values only, standard library only)."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
import zipfile
from typing import IO, Iterator

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
RNS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


def _col(ref: str) -> int:
    n = 0
    for ch in re.match(r"[A-Z]+", ref).group(0):
        n = n * 26 + ord(ch) - 64
    return n - 1


def sheet_names(source: str | IO[bytes]) -> list[str]:
    with zipfile.ZipFile(source) as z:
        wb = ET.fromstring(z.read("xl/workbook.xml"))
        return [s.get("name") for s in wb.iter(NS + "sheet")]


def read_rows(source: str | IO[bytes], sheet: str | int = 0) -> Iterator[list[str | None]]:
    """Yield each row of a sheet as a list of strings (None for empty cells)."""
    with zipfile.ZipFile(source) as z:
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            for si in ET.fromstring(z.read("xl/sharedStrings.xml")).iter(NS + "si"):
                shared.append("".join(t.text or "" for t in si.iter(NS + "t")))
        wb = ET.fromstring(z.read("xl/workbook.xml"))
        sheets = list(wb.iter(NS + "sheet"))
        target = sheets[sheet] if isinstance(sheet, int) else next(s for s in sheets if s.get("name") == sheet)
        rid = target.get(RNS + "id")
        rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        path = next(r.get("Target") for r in rels if r.get("Id") == rid)
        path = path.lstrip("/") if path.startswith("/") else "xl/" + path
        with z.open(path) as f:
            for _, el in ET.iterparse(f):
                if el.tag != NS + "row":
                    continue
                row: list[str | None] = []
                for c in el.iter(NS + "c"):
                    k = _col(c.get("r"))
                    while len(row) < k:
                        row.append(None)
                    t = c.get("t")
                    if t == "inlineStr":
                        v = "".join(x.text or "" for x in c.iter(NS + "t"))
                    else:
                        node = c.find(NS + "v")
                        v = None if node is None else node.text
                        if t == "s" and v is not None:
                            v = shared[int(v)]
                    row.append(v)
                yield row
                el.clear()
