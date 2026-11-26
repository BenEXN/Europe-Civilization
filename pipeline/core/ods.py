"""A minimal OpenDocument spreadsheet (.ods) reader (values only, standard library only)."""

from __future__ import annotations

import xml.etree.ElementTree as ET
import zipfile
from typing import IO, Iterator

TABLE = "{urn:oasis:names:tc:opendocument:xmlns:table:1.0}"
OFFICE = "{urn:oasis:names:tc:opendocument:xmlns:office:1.0}"
TEXT = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}"
MAX_REPEAT = 1000  # repeated empty cells/rows pad sheets to 16k columns / 1M rows: never expanded past this


def _cell_value(c: ET.Element) -> str | None:
    """A cell's value as text: the typed value (office:value, date-value…) when there is one, else its paragraphs."""
    for attr in ("value", "date-value", "time-value", "boolean-value"):
        v = c.get(OFFICE + attr)
        if v is not None:
            return v
    paras = ["".join(p.itertext()) for p in c.iter(TEXT + "p")]
    return "\n".join(paras) if paras else None


def sheet_names(source: str | IO[bytes]) -> list[str]:
    with zipfile.ZipFile(source) as z, z.open("content.xml") as f:
        return [el.get(TABLE + "name") for _, el in ET.iterparse(f) if el.tag == TABLE + "table"]


def read_rows(source: str | IO[bytes], sheet: str | int = 0) -> Iterator[list[str | None]]:
    """Yield each row of a sheet as a list of strings (None for empty cells), trailing empty cells dropped."""
    with zipfile.ZipFile(source) as z, z.open("content.xml") as f:
        k = -1
        for _, el in ET.iterparse(f, events=("end",)):
            if el.tag != TABLE + "table":
                continue
            k += 1
            if (isinstance(sheet, int) and k != sheet) or (isinstance(sheet, str) and el.get(TABLE + "name") != sheet):
                el.clear()
                continue
            for row in el.iter(TABLE + "table-row"):
                cells: list[str | None] = []
                for c in row:
                    if c.tag not in (TABLE + "table-cell", TABLE + "covered-table-cell"):
                        continue
                    n = min(int(c.get(TABLE + "number-columns-repeated", "1")), MAX_REPEAT)
                    cells.extend([_cell_value(c)] * n)
                while cells and cells[-1] in (None, ""):
                    cells.pop()
                reps = min(int(row.get(TABLE + "number-rows-repeated", "1")), MAX_REPEAT) if cells else 1
                for _ in range(reps):
                    yield list(cells)
            return
    raise KeyError(f"no sheet {sheet!r}")
