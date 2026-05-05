"""PDF table extraction via pdfplumber.

Per-force YAML configs point at a specific (page, table_index) to extract,
or a list of `(page, table_index)` pairs to concatenate. OCR fallback via
Tesseract is a later tier — for now every PDF in the ESEA dataset is
text-extractable so pdfplumber alone is sufficient.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pandas as pd


def load_tables(
    path: Path,
    *,
    page: int | None = None,
    table_index: int | None = None,
    pages: list[int] | None = None,
    tables: list[tuple[int, int]] | list[list[int]] | None = None,
    table_index_column: str | None = None,
    header: int | None = 0,
    normalize_columns: bool = True,
) -> pd.DataFrame:
    """Extract one or more tables from a PDF.

    Addressing modes (exactly one required):
      - page + table_index  → single table on that page (0-indexed).
      - pages                → concatenate table 0 of each listed page.
      - tables               → concatenate list of (page, table_index) pairs.

    Concat mode renames columns to positional integers (same convention as
    multi-sheet XLSX / multi-table DOCX) and adds a `_page` or `_table_index`
    column so downstream shapes can distinguish source rows.
    """
    import pdfplumber

    if sum(x is not None for x in (page, table_index, pages, tables)) == 0:
        raise ValueError("Must specify one of: page, table_index, pages, tables.")
    col_name = table_index_column or "_pdf_idx"

    with pdfplumber.open(path) as doc:
        if tables is not None:
            refs: list[tuple[int, int]] = [tuple(t) for t in tables]
        elif pages is not None:
            refs = [(p, 0) for p in pages]
        else:
            refs = [(page or 0, table_index or 0)]

        frames: list[pd.DataFrame] = []
        for p_idx, t_idx in refs:
            if p_idx >= len(doc.pages):
                raise ValueError(f"Page {p_idx} out of range ({len(doc.pages)} pages).")
            page_obj = doc.pages[p_idx]
            page_tables = page_obj.extract_tables() or []
            if t_idx >= len(page_tables):
                raise ValueError(
                    f"Table {t_idx} out of range on page {p_idx} ({len(page_tables)} tables)."
                )
            raw = page_tables[t_idx]
            frame = _rows_to_df(raw, header=header)
            if len(refs) > 1:
                if normalize_columns:
                    frame.columns = list(range(len(frame.columns)))
                frame[col_name] = f"{p_idx}:{t_idx}"
            frames.append(frame)

    if len(frames) == 1:
        return frames[0]
    return pd.concat(frames, ignore_index=True)


def _rows_to_df(rows: list[list[Any]], *, header: int | None) -> pd.DataFrame:
    cleaned = [[_clean_cell(c) for c in row] for row in rows]
    if not cleaned:
        return pd.DataFrame()
    if header is not None:
        cols = cleaned[header]
        seen: dict[str, int] = {}
        unique: list[str] = []
        for c in cols:
            key = c or ""
            if key in seen:
                seen[key] += 1
                unique.append(f"{key}.{seen[key]}")
            else:
                seen[key] = 0
                unique.append(key)
        return pd.DataFrame(cleaned[header + 1:], columns=unique)
    return pd.DataFrame(cleaned)


def _clean_cell(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("\n", " ").strip()


def load_text_long_rows(
    path: Path,
    *,
    page: int | list[int],
    values_per_row: int,
    skip_before_label: str | None = None,
) -> pd.DataFrame:
    """Parse a page's text layer where each logical row is `<label> <N numbers>`.

    Designed for PDFs whose tables pdfplumber can't resolve but whose text
    flow is regular — e.g. Lancashire 2025 crimes page has 22 ethnicity rows,
    each followed by 72 whitespace-separated numeric counts spanning 65 months
    + 6 annual totals. Labels may wrap across preceding lines.

    The scanner accumulates non-numeric lines as label fragments; when a line
    containing >= values_per_row numeric tokens is hit, the leading non-numeric
    tokens (plus any accumulated fragments) become the label, the trailing
    `values_per_row` tokens become columns 0..N-1.

    `skip_before_label` — if provided, rows are ignored until a line starting
    with this literal is seen (used to skip leader text between the header
    area and the data rows). Applies only to the first page; continuation
    pages start collecting immediately.

    `page` may be a single page index or a list of page indices; multi-page
    rows are concatenated so labels wrapping across a page break still
    resolve correctly.
    """
    import pdfplumber

    pages = [page] if isinstance(page, int) else list(page)

    with pdfplumber.open(path) as doc:
        texts = [doc.pages[p].extract_text() or "" for p in pages]
    text = "\n".join(texts)

    started = skip_before_label is None
    accum: list[str] = []
    rows: list[list[Any]] = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        if not started:
            if line.startswith(skip_before_label):
                started = True
            else:
                continue
        tokens = line.split()
        # Split trailing numeric tokens.
        trailing: list[str] = []
        i = len(tokens) - 1
        while i >= 0 and re.fullmatch(r"-?\d+", tokens[i]):
            trailing.insert(0, tokens[i])
            i -= 1
        if len(trailing) >= values_per_row:
            # Everything before the numeric tail + accumulated fragments is the label.
            leading = tokens[: i + 1]
            label_parts = [*accum, *leading]
            label = " ".join(p for p in label_parts if p).strip()
            # If the numeric tail is longer than values_per_row, the extra
            # prefix numbers are treated as part of the label (rare — e.g.
            # labels that include a digit).
            extra_numeric = trailing[: len(trailing) - values_per_row]
            if extra_numeric:
                label = (label + " " + " ".join(extra_numeric)).strip()
            values = trailing[-values_per_row:]
            rows.append([label, *values])
            accum = []
        else:
            accum.append(line)

    return pd.DataFrame(rows, columns=[0, *range(1, values_per_row + 1)])
