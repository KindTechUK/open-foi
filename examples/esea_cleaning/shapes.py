"""Shape-specific transformations from raw tables to a canonical long format.

Each `shape_*` function takes a raw DataFrame (as produced by `loaders.load`)
plus an extraction config dict and returns a tuple of:

    (long_df, warnings)

where long_df has columns {year, month, source_ethnicity_label, count} and
warnings is a list of strings surfaced into the per-force audit JSON. Common
warnings include footnote markers stripped from dates, rows dropped because
date parsing failed, and counts coerced to NaN.

The orchestrator uses the `shape` key in a force's YAML to pick which
function to call — no autodetection in Tier 0. New shapes will be added as
later tiers need them.
"""

from __future__ import annotations

import re
from typing import Any

import pandas as pd

CANONICAL_COLUMNS = ["year", "month", "source_ethnicity_label", "count"]

# Monthly shapes emit month 1–12. Annual-only shapes (wide_years) emit month=0
# with granularity="annual" so that downstream queries can explicitly opt in
# or filter out year-granular rows. The orchestrator sets granularity on every
# output row; shape handlers just return month=0 for annual data.
ANNUAL_MONTH_SENTINEL = 0

# Trailing footnote markers we strip from date strings before parsing.
# Police forces often annotate partial/provisional months (e.g. "Nov-25*").
_DATE_TRAILING_MARKERS = re.compile(r"[\s\*\u2020\u2021\u00a7\u00b6]+$")

# Explicit "Mmm-YY" matcher (e.g. "Nov-25" → 2025-11). pandas.to_datetime
# parses this as year 0001 + day 25, silently producing garbage — so we match
# it ourselves before falling back to pandas' heuristics.
_MMM_YY_RE = re.compile(r"^([A-Za-z]{3,9})[\-\s/](\d{2})$")

# Reasonable bounds: FOI data covers ~2019–2026; anything outside is a parse bug.
_MIN_YEAR = 2000
_MAX_YEAR = 2100


class ShapeError(ValueError):
    """Raised when an extraction config references columns that don't exist or
    the resulting long table is empty/unusable."""


def to_long(
    df: pd.DataFrame, extraction: dict[str, Any]
) -> tuple[pd.DataFrame, list[str]]:
    shape = extraction.get("shape")
    handlers = {
        "long": shape_long,
        "long_ffill": shape_long_ffill,
        "wide_months": shape_wide_months,
        "wide_years": shape_wide_years,
        "event_log": shape_event_log,
        "wide_ethnicity": shape_wide_ethnicity,
        "month_sections": shape_month_sections,
        "ethnicity_sections": shape_ethnicity_sections,
        "year_sections": shape_year_sections,
        "ethnicity_year_months": shape_ethnicity_year_months,
        "wide_years_monthly": shape_wide_years_monthly,
        "year_sections_ethnicity_rows": shape_year_sections_ethnicity_rows,
    }
    if shape in handlers:
        return handlers[shape](df, extraction)
    raise NotImplementedError(
        f"Shape '{shape}' not implemented yet. Available: {sorted(handlers)}."
    )


def _clean_date_value(value: Any) -> tuple[Any, str | None]:
    """Strip footnote markers from a date string.

    Returns (cleaned_value, original_if_cleaned). The second element is None
    when no cleaning was needed — the caller uses it to build a warning list.
    """
    if not isinstance(value, str):
        return value, None
    stripped = _DATE_TRAILING_MARKERS.sub("", value).strip()
    if stripped == value.strip():
        return value, None
    return stripped, value


def _parse_date_value(value: Any) -> pd.Timestamp | pd._libs.tslibs.nattype.NaTType:
    """Parse a date cell, preferring explicit Mmm-YY over pandas heuristics.

    pandas.to_datetime treats "Nov-25" as 0001-11-25 (year 0001) — so if the
    cell matches a Mmm-YY pattern we resolve it to 20YY-Mmm-01 explicitly.
    Otherwise we fall back to pandas and reject any result outside the 2000–2100
    band as unparseable. Trailing footnote markers (`*`, `†`, etc.) are stripped
    first so the caller gets consistent behaviour across shape handlers.
    """
    if isinstance(value, str):
        value = _DATE_TRAILING_MARKERS.sub("", value).strip()
        # A bare 4-digit year (e.g. "2020") collides with Jan of that year
        # when pandas parses it — reject so nested-year-section tables can use
        # standard date-parsing to drop their annual-summary rows.
        if re.fullmatch(r"\d{4}", value):
            return pd.NaT
        m = _MMM_YY_RE.match(value)
        if m:
            month_name, yy = m.group(1), int(m.group(2))
            try:
                return pd.Timestamp(year=2000 + yy, month=pd.to_datetime(month_name, format="%b").month, day=1)
            except (ValueError, KeyError):
                return pd.NaT
    ts = pd.to_datetime(value, errors="coerce")
    if pd.isna(ts):
        return pd.NaT
    if ts.year < _MIN_YEAR or ts.year > _MAX_YEAR:
        return pd.NaT
    return ts


def shape_long_ffill(
    df: pd.DataFrame, extraction: dict[str, Any]
) -> tuple[pd.DataFrame, list[str]]:
    """Forward-filled long format: 3 columns, date written once per month-group.

    Expected extraction config:
        columns:
          date: <col name>
          ethnicity: <col name>
          count: <col name>
        ffill_dates: true (default)
        drop_empty_rows: true (default)
        skip_ethnicities: [list of labels to drop, case-insensitive]
    """
    cols = extraction["columns"]
    date_col = cols["date"]
    eth_col = cols["ethnicity"]
    count_col = cols["count"]
    ffill = extraction.get("ffill_dates", True)
    drop_empty = extraction.get("drop_empty_rows", True)
    skip = {s.lower() for s in extraction.get("skip_ethnicities", [])}

    missing = [c for c in (date_col, eth_col, count_col) if c not in df.columns]
    if missing:
        raise ShapeError(
            f"Columns {missing} not found. Available: {list(df.columns)}"
        )

    warnings: list[str] = []

    out = df[[date_col, eth_col, count_col]].copy()
    out.columns = ["date", "source_ethnicity_label", "count"]

    cleaned = out["date"].apply(_clean_date_value)
    out["date"] = cleaned.str[0]
    stripped_originals = sorted({orig for orig in cleaned.str[1] if orig is not None})
    if stripped_originals:
        warnings.append(
            "Stripped footnote markers from date values: "
            + ", ".join(repr(s) for s in stripped_originals)
        )

    if ffill:
        out["date"] = out["date"].ffill()

    if drop_empty:
        out = out.dropna(subset=["source_ethnicity_label", "count"], how="any")

    if skip:
        out = out[~out["source_ethnicity_label"].str.lower().isin(skip)]

    parsed = out["date"].apply(_parse_date_value)
    unparseable_mask = parsed.isna() & out["date"].notna()
    if unparseable_mask.any():
        lost_count = int(pd.to_numeric(out.loc[unparseable_mask, "count"], errors="coerce").sum())
        bad_values = sorted({str(v) for v in out.loc[unparseable_mask, "date"].unique()})
        warnings.append(
            f"Dropped {int(unparseable_mask.sum())} rows ({lost_count} counts) "
            f"with unparseable date(s): {', '.join(repr(v) for v in bad_values)}"
        )
    out["date"] = parsed
    out = out.dropna(subset=["date"])

    out["year"] = out["date"].dt.year.astype(int)
    out["month"] = out["date"].dt.month.astype(int)
    out["source_ethnicity_label"] = out["source_ethnicity_label"].astype(str).str.strip()
    out["count"] = pd.to_numeric(out["count"], errors="coerce")
    dropped_count_rows = int(out["count"].isna().sum())
    if dropped_count_rows:
        warnings.append(f"Dropped {dropped_count_rows} rows with non-numeric count.")
    out = out.dropna(subset=["count"])
    out["count"] = out["count"].astype(int)

    result = out[CANONICAL_COLUMNS].reset_index(drop=True)
    if result.empty:
        raise ShapeError("Extraction produced zero rows — check column names and data.")
    return result, warnings


_MONTH_NAME_TO_NUM = {
    m.lower(): i
    for i, m in enumerate(
        ["January", "February", "March", "April", "May", "June",
         "July", "August", "September", "October", "November", "December"],
        start=1,
    )
}
_MONTH_NAME_TO_NUM.update({m[:3]: i for m, i in list(_MONTH_NAME_TO_NUM.items())})


def _month_to_int(value: Any) -> int | None:
    if pd.isna(value):
        return None
    if isinstance(value, (int, float)) and 1 <= value <= 12:
        return int(value)
    if isinstance(value, str):
        key = value.strip().lower()
        if key in _MONTH_NAME_TO_NUM:
            return _MONTH_NAME_TO_NUM[key]
        ts = pd.to_datetime(value, errors="coerce")
        if not pd.isna(ts):
            return int(ts.month)
    return None


def shape_wide_months(
    df: pd.DataFrame, extraction: dict[str, Any]
) -> tuple[pd.DataFrame, list[str]]:
    """Ethnicity-rows × month-columns → long.

    Two addressing modes for month columns:
      1. Month-year headers (e.g. "Jan-20") — pattern-matched, year extracted.
      2. Month-only headers (e.g. "Jan") with a separate `year` column whose
         value is per-row. Use `month_columns` (explicit list or dict→month int)
         together with `columns.year`. Rows with the same (year, month,
         ethnicity) key are summed — lets us merge Crime/NonCrime sub-sections.

    Expected extraction config:
        columns:
          ethnicity: <col>
          year: <col>                  # optional (mode 2)
        month_pattern: "^[A-Z][a-z]{2}-\\d{2}$"   # mode 1 regex
        month_columns: {Jan: 1, Feb: 2, ...}      # mode 2 mapping
        skip_ethnicities: [list]
        drop_columns: [list]
        table_to_year: {0: 2020, 1: 2021, ...}    # optional year-col remap
    """
    cols = extraction["columns"]
    eth_col = cols["ethnicity"]
    year_col = cols.get("year")
    month_col_map = extraction.get("month_columns")
    pattern = re.compile(extraction.get("month_pattern", r"^[A-Z][a-z]{2}-\d{2}$"))
    skip = {s.lower() for s in extraction.get("skip_ethnicities", [])}
    drop_cols = set(extraction.get("drop_columns", []))
    table_to_year = extraction.get("table_to_year") or {}

    if eth_col not in df.columns:
        raise ShapeError(
            f"Ethnicity column {eth_col!r} not in columns: {list(df.columns)}"
        )

    warnings: list[str] = []

    if month_col_map:
        month_cols = [c for c in month_col_map if c in df.columns]
        missing = [c for c in month_col_map if c not in df.columns]
        if missing:
            warnings.append(f"Month columns not found (ignored): {missing}")
        if year_col is None or year_col not in df.columns:
            raise ShapeError("month_columns mode requires a valid columns.year.")
        id_vars = [eth_col, year_col]
    else:
        month_cols = [c for c in df.columns if isinstance(c, str) and pattern.match(c) and c not in drop_cols]
        if not month_cols:
            raise ShapeError(
                f"No month columns matched pattern {pattern.pattern!r}. "
                f"Columns available: {list(df.columns)}"
            )
        id_vars = [eth_col]

    sub = df[[*id_vars, *month_cols]].copy()
    sub = sub.dropna(subset=[eth_col])
    if skip:
        sub = sub[~sub[eth_col].astype(str).str.strip().str.lower().isin(skip)]

    melted = sub.melt(id_vars=id_vars, var_name="_col", value_name="count")
    melted["count"] = pd.to_numeric(melted["count"], errors="coerce")
    melted = melted.dropna(subset=["count"])

    if month_col_map:
        melted["month"] = melted["_col"].map(month_col_map).astype(int)
        if table_to_year:
            melted["year"] = melted[year_col].map(table_to_year)
        else:
            melted["year"] = pd.to_numeric(melted[year_col], errors="coerce")
        melted = melted.dropna(subset=["year"])
        melted["year"] = melted["year"].astype(int)
    else:
        parsed = melted["_col"].apply(_parse_date_value)
        unparseable = parsed.isna() & melted["_col"].notna()
        if unparseable.any():
            bad = sorted({str(v) for v in melted.loc[unparseable, "_col"].unique()})
            warnings.append(
                f"Dropped {int(unparseable.sum())} rows with unparseable month headers: "
                + ", ".join(repr(v) for v in bad)
            )
        melted = melted[parsed.notna()].copy()
        melted["year"] = parsed[parsed.notna()].dt.year.astype(int)
        melted["month"] = parsed[parsed.notna()].dt.month.astype(int)

    melted["source_ethnicity_label"] = melted[eth_col].astype(str).str.strip()
    melted["count"] = melted["count"].astype(int)
    # Sum rows with the same (year, month, source_ethnicity_label) — useful when
    # the source splits one logical count across multiple raw rows (e.g.
    # Bedfordshire's Crime + NonCrime sub-sections).
    aggregated = (
        melted.groupby(["year", "month", "source_ethnicity_label"], as_index=False)["count"].sum()
    )

    result = aggregated[CANONICAL_COLUMNS].reset_index(drop=True)
    if result.empty:
        raise ShapeError("wide_months produced zero rows — check columns/pattern.")
    return result, warnings


def shape_event_log(
    df: pd.DataFrame, extraction: dict[str, Any]
) -> tuple[pd.DataFrame, list[str]]:
    """One row per incident → groupby (year, month, ethnicity) → count.

    Expected extraction config:
        columns:
          ethnicity: <col name>
          # either a single timestamp column...
          date: <col name>
          # ...or both of these:
          year: <col name>
          month: <col name>
        null_ethnicity_label: "Not recorded"   # how to label NaN ethnicity rows
        skip_null_ethnicity: false             # drop those rows instead
    """
    cols = extraction["columns"]
    eth_col = cols["ethnicity"]
    date_col = cols.get("date")
    year_col = cols.get("year")
    month_col = cols.get("month")
    null_label = extraction.get("null_ethnicity_label", "Not recorded")
    skip_null = extraction.get("skip_null_ethnicity", False)

    if eth_col not in df.columns:
        raise ShapeError(f"Ethnicity column {eth_col!r} missing.")
    if date_col and date_col not in df.columns:
        raise ShapeError(f"Date column {date_col!r} missing.")
    if year_col and year_col not in df.columns:
        raise ShapeError(f"Year column {year_col!r} missing.")
    if month_col and month_col not in df.columns:
        raise ShapeError(f"Month column {month_col!r} missing.")
    if not date_col and not (year_col and month_col):
        raise ShapeError("event_log needs either 'date' or both 'year' and 'month'.")

    warnings: list[str] = []
    sub = df.copy()

    if date_col:
        parsed = sub[date_col].apply(_parse_date_value)
        unparseable = parsed.isna() & sub[date_col].notna()
        if unparseable.any():
            warnings.append(
                f"Dropped {int(unparseable.sum())} rows with unparseable date in {date_col!r}."
            )
        sub["_year"] = parsed.dt.year
        sub["_month"] = parsed.dt.month
    else:
        sub["_year"] = pd.to_numeric(sub[year_col], errors="coerce")
        sub["_month"] = sub[month_col].apply(_month_to_int)
    sub = sub.dropna(subset=["_year", "_month"])
    sub["_year"] = sub["_year"].astype(int)
    sub["_month"] = sub["_month"].astype(int)

    null_rows = sub[eth_col].isna().sum()
    if null_rows:
        if skip_null:
            warnings.append(f"Skipped {int(null_rows)} rows with null ethnicity.")
            sub = sub.dropna(subset=[eth_col])
        else:
            warnings.append(
                f"Relabelled {int(null_rows)} null-ethnicity rows as {null_label!r}."
            )
            sub[eth_col] = sub[eth_col].fillna(null_label)

    sub["_eth"] = sub[eth_col].astype(str).str.strip()
    grouped = (
        sub.groupby(["_year", "_month", "_eth"], as_index=False)
        .size()
        .rename(columns={"_year": "year", "_month": "month", "_eth": "source_ethnicity_label", "size": "count"})
    )

    result = grouped[CANONICAL_COLUMNS].reset_index(drop=True)
    if result.empty:
        raise ShapeError("event_log produced zero rows — check columns.")
    return result, warnings


def shape_wide_ethnicity(
    df: pd.DataFrame, extraction: dict[str, Any]
) -> tuple[pd.DataFrame, list[str]]:
    """One row per month × ethnicity columns → melt.

    Expected extraction config:
        columns:
          date: <col name>          # month column (e.g. "2020-Jan"); OR:
          year: <col name>
          month: <col name>
        ethnicity_columns: [list]   # explicit whitelist (safest)
          # if omitted, all columns other than date/year/month are treated as ethnicity
        drop_columns: [list]        # totals/footers to ignore
        skip_rows_with_null_date: true
    """
    cols = extraction["columns"]
    date_col = cols.get("date")
    year_col = cols.get("year")
    month_col = cols.get("month")
    explicit_eth = extraction.get("ethnicity_columns")
    drop_cols = set(extraction.get("drop_columns", []))

    warnings: list[str] = []
    sub = df.copy()
    sub.columns = [str(c) for c in sub.columns]

    if date_col and date_col in sub.columns:
        id_cols = [date_col]
    elif year_col and month_col and year_col in sub.columns and month_col in sub.columns:
        id_cols = [year_col, month_col]
    else:
        raise ShapeError(
            "wide_ethnicity needs either a valid 'date' column or both 'year' and 'month'."
        )

    if explicit_eth:
        eth_cols = [c for c in explicit_eth if c in sub.columns]
        missing = [c for c in explicit_eth if c not in sub.columns]
        if missing:
            warnings.append(f"Ethnicity columns not found (ignored): {missing}")
    else:
        eth_cols = [c for c in sub.columns if c not in id_cols and c not in drop_cols]

    if not eth_cols:
        raise ShapeError("No ethnicity columns resolved for wide_ethnicity.")

    sub = sub[id_cols + eth_cols].copy()
    melted = sub.melt(id_vars=id_cols, var_name="source_ethnicity_label", value_name="count")
    melted["count"] = pd.to_numeric(melted["count"], errors="coerce")
    melted = melted.dropna(subset=["count"])

    if date_col:
        parsed = melted[date_col].apply(_parse_date_value)
        unparseable = parsed.isna() & melted[date_col].notna()
        if unparseable.any():
            warnings.append(
                f"Dropped {int(unparseable.sum())} rows with unparseable date in {date_col!r}."
            )
        melted["year"] = parsed.dt.year
        melted["month"] = parsed.dt.month
    else:
        melted["year"] = pd.to_numeric(melted[year_col], errors="coerce")
        melted["month"] = melted[month_col].apply(_month_to_int)

    melted = melted.dropna(subset=["year", "month"])
    melted["year"] = melted["year"].astype(int)
    melted["month"] = melted["month"].astype(int)
    melted["source_ethnicity_label"] = melted["source_ethnicity_label"].astype(str).str.strip()
    melted["count"] = melted["count"].astype(int)

    result = melted[CANONICAL_COLUMNS].reset_index(drop=True)
    if result.empty:
        raise ShapeError("wide_ethnicity produced zero rows — check column selection.")
    return result, warnings


_MONTH_NAMES = set(_MONTH_NAME_TO_NUM.keys())


def shape_month_sections(
    df: pd.DataFrame, extraction: dict[str, Any]
) -> tuple[pd.DataFrame, list[str]]:
    """Month-section header rows + ethnicity detail rows × year columns.

    Used for Dorset and West Mercia layouts where each month has a section header
    row (e.g. "January") followed by one row per ethnicity label, with counts
    spread across year columns.

    Expected extraction config:
        columns:
          section: "<section_column>"   # col holding month-name headers + ethnicity labels
        year_columns:                   # dict { raw_column_name: year_int }
          2020: 2020
          "2025 (up until ...)": 2025
        drop_sections: [list of non-ethnicity labels to skip]   # e.g. "(blank)", "Grand Total"
    """
    cols = extraction["columns"]
    section_col = cols["section"]
    year_map = extraction["year_columns"]
    drop_sections = {str(s).strip().lower() for s in extraction.get("drop_sections", [])}

    if section_col not in df.columns:
        raise ShapeError(f"Section column {section_col!r} missing.")
    missing_years = [c for c in year_map if c not in df.columns]
    if missing_years:
        raise ShapeError(f"Year columns not found: {missing_years}")

    warnings: list[str] = []
    sub = df.copy()
    sub["_label"] = sub[section_col].astype("object")

    is_month_header = sub["_label"].apply(
        lambda v: isinstance(v, str) and v.strip().lower() in {m.lower() for m in _MONTH_NAMES}
    )
    sub["_month"] = sub["_label"].where(is_month_header).apply(_month_to_int)
    sub["_month_ffilled"] = sub["_month"].ffill()

    details = sub[~is_month_header & sub["_label"].notna()].copy()
    details["_label_key"] = details["_label"].astype(str).str.strip().str.lower()
    details = details[~details["_label_key"].isin(drop_sections)]
    details = details.dropna(subset=["_month_ffilled"])

    year_cols = list(year_map.keys())
    melted = details.melt(
        id_vars=[section_col, "_month_ffilled"],
        value_vars=year_cols,
        var_name="_year_raw",
        value_name="count",
    )
    melted["count"] = pd.to_numeric(melted["count"], errors="coerce")
    melted = melted.dropna(subset=["count"])

    melted["year"] = melted["_year_raw"].map(lambda c: int(year_map[c]))
    melted["month"] = melted["_month_ffilled"].astype(int)
    melted["source_ethnicity_label"] = melted[section_col].astype(str).str.strip()
    melted["count"] = melted["count"].astype(int)

    result = melted[CANONICAL_COLUMNS].reset_index(drop=True)
    if result.empty:
        raise ShapeError("month_sections produced zero rows — check columns.")
    return result, warnings


def shape_ethnicity_sections(
    df: pd.DataFrame, extraction: dict[str, Any]
) -> tuple[pd.DataFrame, list[str]]:
    """Ethnicity-section header rows + month detail rows in a single value column.

    Used for Merseyside (one sheet per year): each ethnicity gets a header row
    with its annual total, followed by rows naming individual months and their
    counts. The year comes from a separately injected column (see
    `_load_multi_sheet` in the orchestrator).

    Expected extraction config:
        columns:
          section: "<column>"       # holds ethnicity label OR month name
          count: "<column>"         # the numeric count
          year: "<column>"          # year supplied by loader (sheet-name column)
        ethnicity_labels: [list]    # recognised ethnicity labels — rows with these
                                    # values become section headers. Any other non-
                                    # month string is treated as a drop_section.
        drop_sections: [list]       # rows whose section value equals these are skipped
                                    # (e.g. "Racial", "Grand Total", "Not Recorded").
    """
    cols = extraction["columns"]
    section_col = cols["section"]
    count_col = cols["count"]
    year_col = cols["year"]
    eth_labels = {s.strip() for s in extraction.get("ethnicity_labels", [])}
    drop_sections = {s.strip().lower() for s in extraction.get("drop_sections", [])}
    sheet_to_year = extraction.get("sheet_to_year") or {}

    for required in (section_col, count_col, year_col):
        if required not in df.columns:
            raise ShapeError(f"Column {required!r} missing.")

    warnings: list[str] = []
    sub = df.copy()
    sub["_label"] = sub[section_col].astype("object")
    sub["_label_str"] = sub["_label"].where(sub["_label"].apply(lambda v: isinstance(v, str)))

    def _classify(label: Any) -> str:
        if not isinstance(label, str):
            return "ignore"
        s = label.strip()
        low = s.lower()
        if low in drop_sections:
            return "drop"
        if low in {m.lower() for m in _MONTH_NAMES}:
            return "month"
        if s in eth_labels:
            return "ethnicity"
        return "other"

    sub["_kind"] = sub["_label"].apply(_classify)

    unknown_labels = sub.loc[sub["_kind"] == "other", "_label_str"].dropna().unique()
    if len(unknown_labels):
        warnings.append(
            f"Ignored {len(unknown_labels)} unclassified section label(s): "
            + ", ".join(repr(x) for x in sorted(unknown_labels)[:5])
            + (" ..." if len(unknown_labels) > 5 else "")
        )

    sub["_eth"] = sub["_label_str"].where(sub["_kind"] == "ethnicity")
    # Ffill within each sheet/year group only — the last ethnicity of one sheet
    # must not leak into the first rows of the next sheet after concat.
    sub["_eth_ffilled"] = sub.groupby(year_col, sort=False)["_eth"].ffill()

    details = sub[sub["_kind"] == "month"].copy()
    details = details.dropna(subset=["_eth_ffilled"])
    details["month"] = details["_label_str"].apply(_month_to_int)
    details = details.dropna(subset=["month"])
    if sheet_to_year:
        details["year"] = details[year_col].map(sheet_to_year)
    else:
        details["year"] = pd.to_numeric(details[year_col], errors="coerce")
    details = details.dropna(subset=["year"])
    details["source_ethnicity_label"] = details["_eth_ffilled"].astype(str).str.strip()
    details["count"] = pd.to_numeric(details[count_col], errors="coerce")
    details = details.dropna(subset=["count"])
    details["year"] = details["year"].astype(int)
    details["month"] = details["month"].astype(int)
    details["count"] = details["count"].astype(int)

    result = details[CANONICAL_COLUMNS].reset_index(drop=True)
    if result.empty:
        raise ShapeError("ethnicity_sections produced zero rows — check labels/columns.")
    return result, warnings


def shape_year_sections(
    df: pd.DataFrame, extraction: dict[str, Any]
) -> tuple[pd.DataFrame, list[str]]:
    """Year header rows + month detail rows × ethnicity columns.

    Pattern (e.g. Norfolk, Suffolk):
        col 0                  | ethn_A | ethn_B | ...
        "2020"                 | <yr totals>                 ← section header
        "Jan"                  | <jan counts per ethnicity>  ← detail
        "Feb"                  | ...
        ...
        "2021"                 | <yr totals>
        "Jan"                  | ...

    Year-header rows are detected by pd.to_datetime rejecting bare 4-digit
    strings (enforced by _parse_date_value).

    Expected extraction config:
        columns:
          section: <col>                # col holding year / month labels
        ethnicity_columns: [list]       # value cols to melt
        drop_sections: [list]           # non-year, non-month labels to skip
        emit_year_rows_as_annual: bool  # also emit year-marker rows with
                                        # their own counts at month=0 (annual
                                        # sentinel). Used for mixed-granularity
                                        # sources like Durham DOCX where some
                                        # years have annual totals and others
                                        # have month detail.
    """
    cols = extraction["columns"]
    section_col = cols["section"]
    eth_cols = list(extraction.get("ethnicity_columns", []))
    drop_sections = {str(s).strip().lower() for s in extraction.get("drop_sections", [])}

    if section_col not in df.columns:
        raise ShapeError(f"Section column {section_col!r} missing.")
    missing = [c for c in eth_cols if c not in df.columns]
    if missing:
        raise ShapeError(f"Ethnicity columns not found: {missing}")

    warnings: list[str] = []
    sub = df.copy()
    sub["_label"] = sub[section_col].astype("object")

    def _classify(label: Any) -> str:
        # Accept int/float year values (e.g. 2019) as well as string "2019".
        if isinstance(label, (int, float)) and not pd.isna(label):
            year_int = int(label)
            if _MIN_YEAR <= year_int <= _MAX_YEAR:
                return "year"
            return "ignore"
        if not isinstance(label, str):
            return "ignore"
        s = label.strip()
        low = s.lower()
        if low in drop_sections:
            return "drop"
        if re.fullmatch(r"\d{4}", s) and _MIN_YEAR <= int(s) <= _MAX_YEAR:
            return "year"
        if low in {m.lower() for m in _MONTH_NAMES}:
            return "month"
        return "other"

    sub["_kind"] = sub["_label"].apply(_classify)

    def _extract_year(row: Any) -> int | None:
        if row["_kind"] != "year":
            return None
        label = row["_label"]
        if isinstance(label, (int, float)):
            return int(label)
        return int(str(label).strip())

    sub["_year"] = sub.apply(_extract_year, axis=1)
    sub["_year_ffilled"] = sub["_year"].ffill()

    other_count = int((sub["_kind"] == "other").sum())
    if other_count:
        warnings.append(f"Ignored {other_count} unclassified row(s) in section column.")

    emit_annual = bool(extraction.get("emit_year_rows_as_annual", False))

    details = sub[sub["_kind"] == "month"].copy()
    details = details.dropna(subset=["_year_ffilled"])
    details["month"] = details["_label"].apply(_month_to_int)
    details["year"] = details["_year_ffilled"].astype(int)

    frames: list[pd.DataFrame] = []
    if not details.empty:
        melted = details.melt(
            id_vars=["year", "month"],
            value_vars=eth_cols,
            var_name="source_ethnicity_label",
            value_name="count",
        )
        frames.append(melted)

    if emit_annual:
        annual_rows = sub[sub["_kind"] == "year"].copy()
        annual_rows["year"] = annual_rows["_year"].astype(int)
        annual_rows["month"] = ANNUAL_MONTH_SENTINEL
        annual_melted = annual_rows.melt(
            id_vars=["year", "month"],
            value_vars=eth_cols,
            var_name="source_ethnicity_label",
            value_name="count",
        )
        frames.append(annual_melted)

    if not frames:
        raise ShapeError("year_sections produced zero rows — check section column + ethnicity columns.")
    melted = pd.concat(frames, ignore_index=True)
    melted["count"] = pd.to_numeric(melted["count"], errors="coerce")
    melted = melted.dropna(subset=["count"])
    melted["source_ethnicity_label"] = melted["source_ethnicity_label"].astype(str).str.strip()
    melted["count"] = melted["count"].astype(int)

    result = melted[CANONICAL_COLUMNS].reset_index(drop=True)
    if result.empty:
        raise ShapeError("year_sections produced zero rows — check section column + ethnicity columns.")
    return result, warnings


def shape_ethnicity_year_months(
    df: pd.DataFrame, extraction: dict[str, Any]
) -> tuple[pd.DataFrame, list[str]]:
    """Ethnicity-section rows followed by year rows × month columns.

    Pattern (e.g. Cumbria 2022 XLSX):
        col 0                                      | Jan | Feb | ... | Dec | Total
        "Asian - Any Other Asian Background"       | <year-wide totals>          ← section header (ignored)
        "2019"                                     | <jan..dec counts for 2019>  ← data
        "2020"                                     | ...
        "Asian - Bangladeshi"                      | <totals>                    ← next section
        "2019"                                     | ...
        ...
        "Total"                                    | <grand totals>              ← drop

    Expected extraction config:
        columns:
          section: <col>                  # col holding ethnicity names / year labels
        month_columns: [Jan, Feb, ..., Dec]
        ethnicity_labels: [list]          # rows with these values mark section
                                          #   starts (their row values are ignored)
        drop_sections: [list]             # extra rows to skip (e.g. "Total")
    """
    cols = extraction["columns"]
    section_col = cols["section"]
    month_cols = list(extraction.get("month_columns", []))
    eth_labels = [s.strip() for s in extraction.get("ethnicity_labels", [])]
    eth_set = set(eth_labels)
    drop_sections = {str(s).strip().lower() for s in extraction.get("drop_sections", [])}

    if section_col not in df.columns:
        raise ShapeError(f"Section column {section_col!r} missing.")
    missing = [c for c in month_cols if c not in df.columns]
    if missing:
        raise ShapeError(f"Month columns not found: {missing}")

    warnings: list[str] = []
    sub = df.copy()
    sub["_label"] = sub[section_col]

    def _classify(label: Any) -> str:
        if isinstance(label, (int, float)) and not pd.isna(label):
            year_int = int(label)
            if _MIN_YEAR <= year_int <= _MAX_YEAR:
                return "year"
            return "ignore"
        if not isinstance(label, str):
            return "ignore"
        s = label.strip()
        low = s.lower()
        if low in drop_sections:
            return "drop"
        if re.fullmatch(r"\d{4}", s) and _MIN_YEAR <= int(s) <= _MAX_YEAR:
            return "year"
        if s in eth_set:
            return "ethnicity"
        return "other"

    sub["_kind"] = sub["_label"].apply(_classify)

    unknown = sub.loc[sub["_kind"] == "other", "_label"].astype(str).unique()
    if len(unknown):
        warnings.append(
            f"Ignored {len(unknown)} unclassified section label(s): "
            + ", ".join(repr(x) for x in sorted(unknown)[:5])
            + (" ..." if len(unknown) > 5 else "")
        )

    def _eth_value(row: Any) -> str | None:
        if row["_kind"] == "ethnicity":
            return str(row["_label"]).strip()
        return None

    sub["_eth"] = sub.apply(_eth_value, axis=1)
    sub["_eth_ffilled"] = sub["_eth"].ffill()

    details = sub[sub["_kind"] == "year"].copy()
    details = details.dropna(subset=["_eth_ffilled"])

    def _extract_year(label: Any) -> int:
        if isinstance(label, (int, float)):
            return int(label)
        return int(str(label).strip())

    details["year"] = details["_label"].apply(_extract_year).astype(int)

    melted = details.melt(
        id_vars=["year", "_eth_ffilled"],
        value_vars=month_cols,
        var_name="_month_label",
        value_name="count",
    )
    melted["month"] = melted["_month_label"].apply(_month_to_int)
    melted = melted.dropna(subset=["month"])
    melted["count"] = pd.to_numeric(melted["count"], errors="coerce")
    melted = melted.dropna(subset=["count"])
    melted["source_ethnicity_label"] = melted["_eth_ffilled"].astype(str).str.strip()
    melted["month"] = melted["month"].astype(int)
    melted["count"] = melted["count"].astype(int)

    result = melted[CANONICAL_COLUMNS].reset_index(drop=True)
    if result.empty:
        raise ShapeError("ethnicity_year_months produced zero rows — check labels/month columns.")
    return result, warnings


def shape_year_sections_ethnicity_rows(
    df: pd.DataFrame, extraction: dict[str, Any]
) -> tuple[pd.DataFrame, list[str]]:
    """Year section-headers + ethnicity data rows × month columns.

    Pattern (e.g. Northamptonshire 2023 PDF): each section starts with a year
    marker row, followed by one row per ethnicity code (A1, A2, A3, A9, M3, O1).
    Month-column values on each ethnicity row are that (year, ethnicity, month)
    count. Distinct from `ethnicity_year_months` (Cumbria), which flips the
    roles — ethnicity as the section header and year as the data row.

    Expected extraction config:
        columns:
          section: <col>                # col holding year / ethnicity labels
        month_columns: [Jan, Feb, ..., Dec]
        ethnicity_labels: [list]        # rows with these values are data rows
        drop_sections: [list]
    """
    cols = extraction["columns"]
    section_col = cols["section"]
    month_cols = list(extraction.get("month_columns", []))
    eth_labels = {str(s).strip() for s in extraction.get("ethnicity_labels", [])}
    drop_sections = {str(s).strip().lower() for s in extraction.get("drop_sections", [])}

    if section_col not in df.columns:
        raise ShapeError(f"Section column {section_col!r} missing.")
    missing = [c for c in month_cols if c not in df.columns]
    if missing:
        raise ShapeError(f"Month columns not found: {missing}")

    warnings: list[str] = []
    sub = df.copy()
    sub["_label"] = sub[section_col]

    def _classify(label: Any) -> str:
        if isinstance(label, (int, float)) and not pd.isna(label):
            year_int = int(label)
            if _MIN_YEAR <= year_int <= _MAX_YEAR:
                return "year"
            return "ignore"
        if not isinstance(label, str):
            return "ignore"
        s = label.strip()
        low = s.lower()
        if low in drop_sections:
            return "drop"
        if re.fullmatch(r"\d{4}", s) and _MIN_YEAR <= int(s) <= _MAX_YEAR:
            return "year"
        if s in eth_labels:
            return "ethnicity"
        return "other"

    sub["_kind"] = sub["_label"].apply(_classify)

    def _extract_year(row: Any) -> int | None:
        if row["_kind"] != "year":
            return None
        label = row["_label"]
        if isinstance(label, (int, float)):
            return int(label)
        return int(str(label).strip())

    sub["_year"] = sub.apply(_extract_year, axis=1)
    sub["_year_ffilled"] = sub["_year"].ffill()

    unknown = sub.loc[sub["_kind"] == "other", "_label"].astype(str).unique()
    if len(unknown):
        warnings.append(
            f"Ignored {len(unknown)} unclassified section label(s): "
            + ", ".join(repr(x) for x in sorted(unknown)[:5])
            + (" ..." if len(unknown) > 5 else "")
        )

    details = sub[sub["_kind"] == "ethnicity"].copy()
    details = details.dropna(subset=["_year_ffilled"])
    details["year"] = details["_year_ffilled"].astype(int)
    details["source_ethnicity_label"] = details["_label"].astype(str).str.strip()

    melted = details.melt(
        id_vars=["year", "source_ethnicity_label"],
        value_vars=month_cols,
        var_name="_month_label",
        value_name="count",
    )
    melted["month"] = melted["_month_label"].apply(_month_to_int)
    melted = melted.dropna(subset=["month"])
    melted["count"] = pd.to_numeric(melted["count"], errors="coerce")
    melted = melted.dropna(subset=["count"])
    melted["month"] = melted["month"].astype(int)
    melted["count"] = melted["count"].astype(int)

    result = melted[CANONICAL_COLUMNS].reset_index(drop=True)
    if result.empty:
        raise ShapeError(
            "year_sections_ethnicity_rows produced zero rows — check labels/month columns."
        )
    return result, warnings


def shape_long(
    df: pd.DataFrame, extraction: dict[str, Any]
) -> tuple[pd.DataFrame, list[str]]:
    """Already-long data: each row has year, month, ethnicity, count.

    Pattern (e.g. North Wales): one row per (year, month, ethnicity) with the
    count as a numeric column. Different from `long_ffill` which has a single
    date column; this takes year and month as separate columns (or full-text
    month names handled by _month_to_int).

    Expected extraction config:
        columns:
          year: <col>
          month: <col>
          ethnicity: <col>
          count: <col>
        skip_ethnicities: [list]
    """
    cols = extraction["columns"]
    year_col = cols["year"]
    month_col = cols["month"]
    eth_col = cols["ethnicity"]
    count_col = cols["count"]
    skip = {s.strip().lower() for s in extraction.get("skip_ethnicities", [])}

    for required in (year_col, month_col, eth_col, count_col):
        if required not in df.columns:
            raise ShapeError(f"Column {required!r} missing.")

    warnings: list[str] = []
    sub = df.copy()
    sub["year"] = pd.to_numeric(sub[year_col], errors="coerce")
    sub = sub.dropna(subset=["year"])
    sub["month"] = sub[month_col].apply(_month_to_int)
    sub = sub.dropna(subset=["month"])
    sub["year"] = sub["year"].astype(int)
    sub["month"] = sub["month"].astype(int)
    sub["source_ethnicity_label"] = sub[eth_col].astype(str).str.strip()
    sub = sub[sub["source_ethnicity_label"] != ""]
    if skip:
        sub = sub[~sub["source_ethnicity_label"].str.lower().isin(skip)]
    sub["count"] = pd.to_numeric(sub[count_col], errors="coerce")
    dropped = int(sub["count"].isna().sum())
    if dropped:
        warnings.append(f"Dropped {dropped} rows with non-numeric count.")
    sub = sub.dropna(subset=["count"])
    sub["count"] = sub["count"].astype(int)

    # Aggregate duplicate (year, month, ethnicity) tuples via sum.
    aggregated = (
        sub.groupby(["year", "month", "source_ethnicity_label"], as_index=False)["count"].sum()
    )
    if aggregated.empty:
        raise ShapeError("long shape produced zero rows — check columns and values.")
    return aggregated[CANONICAL_COLUMNS].reset_index(drop=True), warnings


def shape_wide_years(
    df: pd.DataFrame, extraction: dict[str, Any]
) -> tuple[pd.DataFrame, list[str]]:
    """Ethnicity rows × year columns → annual-granularity long format.

    For forces that supplied only year-level ethnicity breakdowns (no monthly
    dimension). Emits rows with month=0 and the orchestrator tags them with
    granularity="annual".

    Expected extraction config:
        columns:
          ethnicity: <col>
        year_columns: { col_name_or_idx: year_int, ... }
        skip_ethnicities: [list]
    """
    cols = extraction["columns"]
    eth_col = cols["ethnicity"]
    year_map = extraction["year_columns"]
    skip = {s.strip().lower() for s in extraction.get("skip_ethnicities", [])}

    if eth_col not in df.columns:
        raise ShapeError(f"Ethnicity column {eth_col!r} missing.")
    missing = [c for c in year_map if c not in df.columns]
    if missing:
        raise ShapeError(f"Year columns not found: {missing}")

    warnings: list[str] = []
    year_cols = list(year_map.keys())
    sub = df[[eth_col, *year_cols]].copy()
    sub = sub.dropna(subset=[eth_col])
    if skip:
        sub = sub[~sub[eth_col].astype(str).str.strip().str.lower().isin(skip)]

    melted = sub.melt(id_vars=[eth_col], var_name="_year_raw", value_name="count")
    melted["count"] = pd.to_numeric(melted["count"], errors="coerce")
    melted = melted.dropna(subset=["count"])

    melted["year"] = melted["_year_raw"].map(lambda c: int(year_map[c]))
    melted["month"] = ANNUAL_MONTH_SENTINEL
    melted["source_ethnicity_label"] = melted[eth_col].astype(str).str.strip()
    melted["count"] = melted["count"].astype(int)

    aggregated = (
        melted.groupby(["year", "month", "source_ethnicity_label"], as_index=False)["count"].sum()
    )
    if aggregated.empty:
        raise ShapeError("wide_years produced zero rows — check columns/values.")
    return aggregated[CANONICAL_COLUMNS].reset_index(drop=True), warnings


def shape_wide_years_monthly(
    df: pd.DataFrame, extraction: dict[str, Any]
) -> tuple[pd.DataFrame, list[str]]:
    """One row per (month, ethnicity) with year columns to melt.

    Pattern (e.g. Warwickshire 2022 XLSX):
        Month     | 2019 | 2020 | 2021 | 2022 | Ethnicity                 | Grand Total
        September |  2   |  1   |      |      | Chinese, Japanese, ...    | 3
        April     |      |      |  1   |      | Chinese, Japanese, ...    | 1
        ...
        Grand Total| 6   |  4   |  7   |  2   |                           | 19

    Each row already has a month and ethnicity; counts are split by year
    across N columns. We melt the year columns and drop the Grand Total row.

    Expected extraction config:
        columns:
          month: <col>
          ethnicity: <col>
        year_columns: { col: year_int, ... }
        skip_months: [list]         # e.g. "Grand Total"
        skip_ethnicities: [list]
    """
    cols = extraction["columns"]
    month_col = cols["month"]
    eth_col = cols["ethnicity"]
    year_map = extraction["year_columns"]
    skip_months = {str(s).strip().lower() for s in extraction.get("skip_months", [])}
    skip_eth = {str(s).strip().lower() for s in extraction.get("skip_ethnicities", [])}

    for required in (month_col, eth_col):
        if required not in df.columns:
            raise ShapeError(f"Column {required!r} missing.")
    missing = [c for c in year_map if c not in df.columns]
    if missing:
        raise ShapeError(f"Year columns not found: {missing}")

    warnings: list[str] = []
    year_cols = list(year_map.keys())
    sub = df[[month_col, eth_col, *year_cols]].copy()
    sub = sub.dropna(subset=[month_col])

    month_str = sub[month_col].astype(str).str.strip().str.lower()
    if skip_months:
        sub = sub[~month_str.isin(skip_months)]
    if skip_eth:
        eth_str = sub[eth_col].astype(str).str.strip().str.lower()
        sub = sub[~eth_str.isin(skip_eth)]

    melted = sub.melt(id_vars=[month_col, eth_col], var_name="_year_raw", value_name="count")
    melted["count"] = pd.to_numeric(melted["count"], errors="coerce")
    melted = melted.dropna(subset=["count"])

    melted["year"] = melted["_year_raw"].map(lambda c: int(year_map[c]))
    melted["month"] = melted[month_col].apply(_month_to_int)
    melted = melted.dropna(subset=["month"])
    melted["source_ethnicity_label"] = melted[eth_col].astype(str).str.strip()
    melted["month"] = melted["month"].astype(int)
    melted["count"] = melted["count"].astype(int)

    aggregated = (
        melted.groupby(["year", "month", "source_ethnicity_label"], as_index=False)["count"].sum()
    )
    if aggregated.empty:
        raise ShapeError("wide_years_monthly produced zero rows — check columns/values.")
    return aggregated[CANONICAL_COLUMNS].reset_index(drop=True), warnings
