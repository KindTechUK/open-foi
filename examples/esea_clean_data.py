"""Orchestrator — clean ESEA FOI attachments into a unified long-format CSV.

Iterates forces in `examples/esea_data/`, applies each force's YAML config
from `examples/esea_cleaning/mappings/`, and writes:

    examples/esea_data_cleaned/esea_long.csv
    examples/esea_data_cleaned/audit/<force_id>.json

Run:
    python examples/esea_clean_data.py                          # all forces
    python examples/esea_clean_data.py --force staffordshire_police
    python examples/esea_clean_data.py --dry-run                # no writes
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from esea_cleaning import force_registry, loaders, shapes  # noqa: E402
from esea_cleaning.ethnicity import apply_mapping, load_force_config  # noqa: E402

OUTPUT_DIR = force_registry.REPO_ROOT / "examples" / "esea_data_cleaned"
MASTER_CSV = OUTPUT_DIR / "esea_long.csv"
AUDIT_DIR = OUTPUT_DIR / "audit"

logger = logging.getLogger("esea_clean")

OUTPUT_COLUMNS = [
    "police_force_id",
    "police_force_name",
    "year",
    "month",
    "granularity",
    "ons_ethnicity",
    "source_ethnicity_label",
    "count",
    "source_file",
]


def _resolve_source_file(entry: force_registry.ForceEntry, configured: str) -> Path:
    candidate = entry.data_dir / configured
    if candidate.exists():
        return candidate
    for f in entry.attachment_files:
        if f.name == configured:
            return f
    raise FileNotFoundError(
        f"{entry.force_id}: source_file '{configured}' not found under {entry.data_dir}"
    )


def clean_force(entry: force_registry.ForceEntry) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Process one force end-to-end. Returns (rows, audit_dict)."""
    if entry.config_path is None:
        raise FileNotFoundError(
            f"{entry.force_id}: no mapping YAML at mappings/{entry.force_id}.yaml"
        )

    config = load_force_config(entry.config_path)
    source_path = _resolve_source_file(entry, config["source_file"])

    extraction = config["extraction"]
    raw = loaders.load(
        source_path,
        sheet=extraction.get("sheet"),
        sheets=extraction.get("sheets"),
        sheet_name_column=extraction.get("sheet_name_column"),
        header=extraction.get("header", 0),
        skiprows=extraction.get("skiprows"),
        table_index=extraction.get("table_index"),
        tables=extraction.get("tables"),
        table_index_column=extraction.get("table_index_column"),
        page=extraction.get("page"),
        pdf_pages=extraction.get("pdf_pages"),
        pdf_tables=extraction.get("pdf_tables"),
        pdf_normalize_columns=extraction.get("pdf_normalize_columns", True),
        pdf_text_page=extraction.get("pdf_text_page"),
        pdf_text_values_per_row=extraction.get("pdf_text_values_per_row"),
        pdf_text_skip_before_label=extraction.get("pdf_text_skip_before_label"),
    )
    # Optional row-level trimming: useful for sheets with multiple stacked
    # tables or annual-summary rows whose dates collide with January.
    nrows = extraction.get("nrows")
    if nrows is not None:
        raw = raw.iloc[:nrows].copy()
    drop_idx = extraction.get("drop_row_indices")
    if drop_idx:
        raw = raw.drop(index=drop_idx).reset_index(drop=True)
    # Optional column renaming — useful after PDF/DOCX load where columns are
    # positional integers; the YAML maps them to human-readable ethnicity labels
    # that become the source_ethnicity_label values in the output.
    rename_map = extraction.get("rename_columns")
    if rename_map:
        raw = raw.rename(columns=rename_map)
    # Optional coalesce: combine multiple source columns into one target. For
    # PDFs where a long label spills across two cells (line-wrap artefacts of
    # pdfplumber), the first non-null value of each candidate is used.
    coalesce = extraction.get("coalesce_columns") or {}
    for target, sources in coalesce.items():
        if len(sources) < 1:
            continue
        coalesced = raw[sources[0]].copy()
        for s in sources[1:]:
            if s in raw.columns:
                empty_mask = coalesced.isna() | coalesced.astype(str).str.strip().eq("")
                coalesced = coalesced.where(~empty_mask, raw[s])
        raw[target] = coalesced
    # Optional forward-fill on specified cols — useful for long-format PDFs
    # where year/month repeats only once per logical group.
    ffill_cols = extraction.get("ffill_columns") or []
    for col in ffill_cols:
        if col in raw.columns:
            raw[col] = raw[col].replace("", None).ffill()
    # Optional: inject constant columns into the raw frame. Useful when a
    # force's file has a single implicit ethnicity (e.g. MPS Tables sheet is
    # entirely "East Asian" with no ethnicity column) that shape handlers still
    # need as a value-bearing column to melt against.
    add_cols = extraction.get("add_columns") or {}
    for col, value in add_cols.items():
        raw[col] = value
    # Optional row-level filter: keep only rows where the given column matches
    # one of the listed values. Useful when a file mixes crime + incident rows
    # and we want crimes only (e.g. Surrey 2023).
    filter_rows = extraction.get("filter_rows") or {}
    for col, allowed in filter_rows.items():
        if col in raw.columns:
            allowed_list = allowed if isinstance(allowed, list) else [allowed]
            raw = raw[raw[col].isin(allowed_list)].copy()
    # Optional value replacement, applied across the whole frame. Used to turn
    # privacy-redacted markers (e.g. Nottinghamshire's "<5") into numeric
    # midpoint estimates so shape handlers can coerce them to counts.
    replace_values = extraction.get("replace_values") or {}
    if replace_values:
        raw = raw.replace(replace_values)
    long_df, extraction_warnings = shapes.to_long(raw, extraction)
    mapped_df, mapping_audit = apply_mapping(long_df, config["mapping"])

    mapped_df.insert(0, "police_force_id", entry.force_id)
    mapped_df.insert(1, "police_force_name", entry.display_name)
    # month=0 is the annual-only sentinel set by shape_wide_years. Every other
    # shape emits month 1–12 so those rows are monthly.
    mapped_df["granularity"] = mapped_df["month"].apply(
        lambda m: "annual" if m == 0 else "monthly"
    )
    mapped_df["source_file"] = source_path.name

    audit = {
        "force_id": entry.force_id,
        "display_name": entry.display_name,
        "source_file": source_path.name,
        "shape_detected": extraction["shape"],
        "rows_out": len(mapped_df),
        **mapping_audit,
        "warnings": extraction_warnings,
    }
    return mapped_df[OUTPUT_COLUMNS], audit


def _write_audit(audit: dict[str, Any]) -> None:
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    path = AUDIT_DIR / f"{audit['force_id']}.json"
    with path.open("w") as f:
        json.dump(audit, f, indent=2, sort_keys=False)


def _log_summary(audit: dict[str, Any]) -> None:
    unmapped = len(audit["unmapped_labels"])
    logger.info(
        "[%s] %d rows, %d labels, %d unmapped (coverage %.0f%%)",
        audit["force_id"],
        audit["rows_out"],
        len(audit["source_labels"]),
        unmapped,
        audit["mapping_coverage"] * 100,
    )
    for w in audit.get("warnings", []):
        logger.warning("  [%s] WARN: %s", audit["force_id"], w)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", help="Process only this force_id.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and report, but don't write CSV or audit files.",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(message)s",
        stream=sys.stderr,
    )

    entries = force_registry.list_forces()
    if args.force:
        entries = [e for e in entries if e.force_id == args.force]
        if not entries:
            logger.error("No force with id %r found.", args.force)
            return 2

    logger.info("Processing %d force(s)...", len(entries))
    all_rows: list[pd.DataFrame] = []
    failures: list[tuple[str, str]] = []

    for entry in entries:
        try:
            rows, audit = clean_force(entry)
        except FileNotFoundError as e:
            logger.warning("[%s] SKIP — %s", entry.force_id, e)
            failures.append((entry.force_id, str(e)))
            continue
        except NotImplementedError as e:
            logger.warning("[%s] NOT YET — %s", entry.force_id, e)
            failures.append((entry.force_id, str(e)))
            continue
        except Exception as e:  # noqa: BLE001 — partial failure is by design
            logger.error("[%s] FAIL — %s: %s", entry.force_id, type(e).__name__, e)
            failures.append((entry.force_id, f"{type(e).__name__}: {e}"))
            continue

        _log_summary(audit)
        all_rows.append(rows)
        if not args.dry_run:
            _write_audit(audit)

    if all_rows and not args.dry_run:
        master = pd.concat(all_rows, ignore_index=True)
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        master.to_csv(MASTER_CSV, index=False)
        logger.info(
            "Wrote %d rows across %d force(s) → %s",
            len(master),
            master["police_force_id"].nunique(),
            MASTER_CSV.relative_to(force_registry.REPO_ROOT),
        )

    if failures:
        logger.warning("%d force(s) failed or skipped:", len(failures))
        for fid, msg in failures:
            logger.warning("  - %s: %s", fid, msg)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
