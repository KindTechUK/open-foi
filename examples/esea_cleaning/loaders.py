"""Format-specific loaders that read raw FOI attachments into pandas DataFrames.

Each loader returns the raw table (or tables) "as-is" — shape detection and
transformation happen in `shapes.py`. For XLSX and ODS the caller passes the
sheet name via the extraction config.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd


def load(
    path: Path,
    *,
    sheet: str | int | None = None,
    sheets: list[str] | None = None,
    sheet_name_column: str | None = None,
    header: int | None = 0,
    skiprows: int | list[int] | None = None,
    table_index: int | None = None,
    tables: list[int] | None = None,
    table_index_column: str | None = None,
    page: int | None = None,
    pdf_pages: list[int] | None = None,
    pdf_tables: list[list[int]] | None = None,
    pdf_normalize_columns: bool = True,
    pdf_text_page: int | list[int] | None = None,
    pdf_text_values_per_row: int | None = None,
    pdf_text_skip_before_label: str | None = None,
) -> pd.DataFrame:
    """Read a raw FOI attachment into a DataFrame.

    Dispatches on suffix. The optional `header` / `skiprows` arguments are
    passed straight through to pandas so per-force YAML configs can handle
    sheets with leading metadata rows (e.g. City of London has a blank row
    then the headers on row 1).

    Multi-sheet aggregation: pass `sheets=[...]` plus a `sheet_name_column`
    name to read several sheets and concatenate them with an added column
    carrying each row's source sheet name (used by Merseyside where each
    sheet is a year).

    For Tier 0 only CSV and XLSX are implemented; other formats raise
    NotImplementedError so the orchestrator can record a clean audit entry
    instead of crashing.
    """
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return _read_csv(path, header=header, skiprows=skiprows)
    if suffix in {".xlsx", ".xls"}:
        if sheets:
            return _read_xlsx_multi(path, sheets=sheets, sheet_name_column=sheet_name_column, header=header, skiprows=skiprows)
        return _read_xlsx(path, sheet=sheet, header=header, skiprows=skiprows)
    if suffix == ".docx":
        if tables:
            return _read_docx_multi(path, tables=tables, table_index_column=table_index_column, header=header)
        return _read_docx(path, table_index=table_index or 0, header=header)
    if suffix == ".odt":
        return _read_odt(path, table_index=table_index or 0, header=header)
    if suffix == ".pdf":
        from esea_cleaning import pdf_extract
        if pdf_text_values_per_row is not None:
            return pdf_extract.load_text_long_rows(
                path,
                page=pdf_text_page if pdf_text_page is not None else 0,
                values_per_row=pdf_text_values_per_row,
                skip_before_label=pdf_text_skip_before_label,
            )
        return pdf_extract.load_tables(
            path,
            page=page,
            table_index=table_index,
            pages=pdf_pages,
            tables=pdf_tables,
            table_index_column=table_index_column,
            header=header,
            normalize_columns=pdf_normalize_columns,
        )
    raise ValueError(f"Unsupported file format: {suffix}")


def _read_csv(
    path: Path,
    *,
    header: int | None,
    skiprows: int | list[int] | None,
) -> pd.DataFrame:
    return pd.read_csv(path, header=header, skiprows=skiprows)


def _read_xlsx(
    path: Path,
    *,
    sheet: str | int | None,
    header: int | None,
    skiprows: int | list[int] | None,
) -> pd.DataFrame:
    target = sheet if sheet is not None else 0
    return pd.read_excel(path, sheet_name=target, header=header, skiprows=skiprows)


def _read_xlsx_multi(
    path: Path,
    *,
    sheets: list[str],
    sheet_name_column: str | None,
    header: int | None,
    skiprows: int | list[int] | None,
) -> pd.DataFrame:
    """Concatenate several sheets, tagging each row with its sheet name.

    Column names are normalised to positional integers (0, 1, 2, ...) across
    all sheets so that per-sheet header variations (e.g. Merseyside uses the
    year as the header text of column 0) don't prevent concatenation.
    """
    frames: list[pd.DataFrame] = []
    col_name = sheet_name_column or "_sheet_name"
    for sheet in sheets:
        frame = pd.read_excel(path, sheet_name=sheet, header=header, skiprows=skiprows)
        frame = frame.copy()
        frame.columns = list(range(len(frame.columns)))
        frame[col_name] = sheet
        frames.append(frame)
    return pd.concat(frames, ignore_index=True)


def _docx_table_to_df(table, *, header: int | None) -> pd.DataFrame:
    """Convert a python-docx Table into a DataFrame. If header is int, use that
    row as column names and drop leading rows through it; None → positional cols.
    """
    rows = [[cell.text.strip() for cell in row.cells] for row in table.rows]
    if not rows:
        return pd.DataFrame()
    if header is not None:
        cols = rows[header]
        # Disambiguate duplicate column names the same way pandas does (".1" suffix).
        seen: dict[str, int] = {}
        unique_cols: list[str] = []
        for c in cols:
            if c in seen:
                seen[c] += 1
                unique_cols.append(f"{c}.{seen[c]}")
            else:
                seen[c] = 0
                unique_cols.append(c)
        data = rows[header + 1:]
        return pd.DataFrame(data, columns=unique_cols)
    return pd.DataFrame(rows)


def _read_docx(path: Path, *, table_index: int, header: int | None) -> pd.DataFrame:
    from docx import Document
    doc = Document(path)
    if table_index >= len(doc.tables):
        raise ValueError(f"table_index {table_index} out of range (doc has {len(doc.tables)} tables).")
    return _docx_table_to_df(doc.tables[table_index], header=header)


def _read_docx_multi(
    path: Path,
    *,
    tables: list[int],
    table_index_column: str | None,
    header: int | None,
) -> pd.DataFrame:
    """Concatenate several DOCX tables, tagging each row with its source table index.

    Column names are normalised to positional integers across all tables to avoid
    concat misalignment when per-table headers differ.
    """
    from docx import Document
    doc = Document(path)
    col_name = table_index_column or "_table_index"
    frames: list[pd.DataFrame] = []
    for idx in tables:
        if idx >= len(doc.tables):
            raise ValueError(f"table_index {idx} out of range (doc has {len(doc.tables)} tables).")
        frame = _docx_table_to_df(doc.tables[idx], header=header)
        frame.columns = list(range(len(frame.columns)))
        frame[col_name] = idx
        frames.append(frame)
    return pd.concat(frames, ignore_index=True)


def _read_odt(path: Path, *, table_index: int, header: int | None) -> pd.DataFrame:
    from odf.opendocument import load as odf_load
    from odf.table import Table, TableCell, TableRow
    from odf.text import P
    doc = odf_load(str(path))
    tables = doc.getElementsByType(Table)
    if table_index >= len(tables):
        raise ValueError(f"table_index {table_index} out of range (doc has {len(tables)} tables).")
    rows_out: list[list[str]] = []
    for row in tables[table_index].getElementsByType(TableRow):
        cells = row.getElementsByType(TableCell)
        values = []
        for c in cells:
            paragraphs = c.getElementsByType(P)
            text = "".join(str(p) for p in paragraphs).strip()
            repeat = int(c.getAttribute("numbercolumnsrepeated") or 1)
            values.extend([text] * repeat)
        rows_out.append(values)
    if not rows_out:
        return pd.DataFrame()
    width = max(len(r) for r in rows_out)
    rows_out = [r + [""] * (width - len(r)) for r in rows_out]
    if header is not None:
        return pd.DataFrame(rows_out[header + 1:], columns=rows_out[header])
    return pd.DataFrame(rows_out)


def _tier_for(suffix: str) -> int:
    return {".docx": 2, ".odt": 2, ".pdf": 3}.get(suffix, 0)
