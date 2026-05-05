"""Load ONS 18+1 canonical categories and per-force mappings; apply to long data.

Each force's YAML file has two top-level keys the orchestrator uses:
    extraction:  how to read the raw table (consumed by shapes.py)
    mapping:     {source_label: ons_category} — consumed here
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import yaml

MAPPINGS_DIR = Path(__file__).resolve().parent / "mappings"
ONS_FILE = MAPPINGS_DIR / "_ons_18_plus_1.yaml"


def load_ons_categories() -> frozenset[str]:
    with ONS_FILE.open() as f:
        data = yaml.safe_load(f)
    return frozenset(data["categories"])


ONS_CATEGORIES: frozenset[str] = load_ons_categories()


def load_force_config(config_path: Path) -> dict[str, Any]:
    with config_path.open() as f:
        config = yaml.safe_load(f)

    required = {"force_id", "display_name", "source_file", "extraction", "mapping"}
    missing = required - set(config or {})
    if missing:
        raise ValueError(f"{config_path.name}: missing keys {sorted(missing)}")

    mapping = config["mapping"] or {}
    unknown = [v for v in mapping.values() if v not in ONS_CATEGORIES]
    if unknown:
        raise ValueError(
            f"{config_path.name}: mapping targets not in ONS 18+1: {sorted(set(unknown))}"
        )
    config["mapping"] = mapping
    return config


def apply_mapping(df: pd.DataFrame, mapping: dict[str, str]) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Add `ons_ethnicity` column; return (df, audit_dict).

    Rows with unmapped labels retain `ons_ethnicity=None`. The audit dict
    lists every source label seen, how it mapped, and which ones were unmapped.
    """
    out = df.copy()
    out["ons_ethnicity"] = out["source_ethnicity_label"].map(mapping)

    source_labels = sorted(out["source_ethnicity_label"].unique())
    applied = {label: mapping[label] for label in source_labels if label in mapping}
    unmapped = sorted(label for label in source_labels if label not in mapping)

    audit = {
        "source_labels": source_labels,
        "mapping": applied,
        "unmapped_labels": unmapped,
        "mapping_coverage": round(len(applied) / max(len(source_labels), 1), 3),
    }
    return out, audit
