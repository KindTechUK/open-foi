"""End-to-end analysis example on the cleaned ESEA long CSV.

Consumes `examples/esea_data_cleaned/esea_long.csv` and produces four
artefacts under `examples/esea_data_cleaned/analysis/`:

  1. `esea_share_by_force_year.csv` — ESEA's share of racial hate crimes
     per (force, year). This is the headline proportionality metric the
     project brief calls for (ESEA crimes as a % of all racial hate crimes
     in each police jurisdiction).
  2. `esea_monthly_trend.csv` — per-force monthly time series of ESEA
     incidents, ready to plot.
  3. `ons_category_totals.csv` — total incidents across the whole dataset
     grouped by ONS 18+1 category.
  4. `summary_report.txt` — plain-text narrative suitable for pasting into
     a report, including dataset-level totals, per-force breakdown, and
     any unmapped-label warnings surfaced from audit JSONs.

Run:
    python examples/esea_analysis.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
CLEAN_DIR = REPO / "examples" / "esea_data_cleaned"
OUT_DIR = CLEAN_DIR / "analysis"
LONG_CSV = CLEAN_DIR / "esea_long.csv"

# ONS 18+1 categories considered "ESEA" for this project:
# East and South-East Asian populations primarily map to "Asian - Chinese"
# and the ESEA-heavy portion of "Asian - Other" (Cambodian, Vietnamese,
# Thai, Korean, Japanese, etc.). We include Asian - Other as a proxy; forces
# that submitted sub-Asian breakdowns (e.g. Cambridgeshire) would refine
# this — see `research/esea-pipeline-report.md` §Limitations.
ESEA_CATEGORIES = frozenset({"Asian - Chinese", "Asian - Other"})


def main() -> int:
    if not LONG_CSV.exists():
        print(f"ERROR: {LONG_CSV} not found. Run examples/esea_clean_data.py first.")
        return 1

    df = pd.read_csv(LONG_CSV)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    _write_esea_share(df)
    _write_monthly_trend(df)
    _write_ons_totals(df)
    _write_summary_report(df)

    print(f"Wrote 4 analysis artefacts → {OUT_DIR.relative_to(REPO)}")
    return 0


def _write_esea_share(df: pd.DataFrame) -> None:
    per_year = (
        df.groupby(["police_force_id", "police_force_name", "year"])["count"]
        .sum()
        .rename("total_racial_hate")
        .reset_index()
    )
    esea = (
        df[df["ons_ethnicity"].isin(ESEA_CATEGORIES)]
        .groupby(["police_force_id", "year"])["count"]
        .sum()
        .rename("esea_hate")
        .reset_index()
    )
    merged = per_year.merge(esea, on=["police_force_id", "year"], how="left").fillna({"esea_hate": 0})
    merged["esea_hate"] = merged["esea_hate"].astype(int)
    merged["esea_share_pct"] = (merged["esea_hate"] / merged["total_racial_hate"] * 100).round(2)
    merged = merged.sort_values(["police_force_name", "year"])
    merged.to_csv(OUT_DIR / "esea_share_by_force_year.csv", index=False)


def _write_monthly_trend(df: pd.DataFrame) -> None:
    # Annual-granularity rows (month=0) are excluded here — they belong to the
    # year-level share analysis, not the monthly trend view.
    esea = df[df["ons_ethnicity"].isin(ESEA_CATEGORIES) & (df["granularity"] == "monthly")]
    trend = (
        esea.groupby(["police_force_id", "police_force_name", "year", "month"])["count"]
        .sum()
        .reset_index()
    )
    trend["year_month"] = pd.to_datetime(
        trend[["year", "month"]].assign(day=1)
    ).dt.strftime("%Y-%m")
    trend = trend[["police_force_id", "police_force_name", "year_month", "year", "month", "count"]]
    trend = trend.sort_values(["police_force_name", "year", "month"])
    trend.to_csv(OUT_DIR / "esea_monthly_trend.csv", index=False)


def _write_ons_totals(df: pd.DataFrame) -> None:
    totals = (
        df.groupby("ons_ethnicity")["count"]
        .agg(total="sum", rows="size")
        .reset_index()
        .sort_values("total", ascending=False)
    )
    totals["share_pct"] = (totals["total"] / totals["total"].sum() * 100).round(2)
    totals.to_csv(OUT_DIR / "ons_category_totals.csv", index=False)


def _write_summary_report(df: pd.DataFrame) -> None:
    lines: list[str] = []
    lines.append("ESEA Hate Crime Data — Analysis Summary")
    lines.append("=" * 60)
    lines.append("")

    # Headline totals
    total_forces = df["police_force_id"].nunique()
    total_incidents = int(df["count"].sum())
    year_range = f"{df['year'].min()}–{df['year'].max()}"
    lines.append(f"Dataset: {total_forces} police forces, {total_incidents:,} incidents, {year_range}.")

    # Granularity breakdown
    monthly_forces = df[df["granularity"] == "monthly"]["police_force_id"].nunique()
    annual_forces = df[df["granularity"] == "annual"]["police_force_id"].nunique()
    if annual_forces:
        lines.append(
            f"Granularity: {monthly_forces} force(s) with month × ethnicity detail; "
            f"{annual_forces} force(s) with year × ethnicity only (month=0)."
        )
    lines.append("")

    # ESEA-specific totals
    esea = df[df["ons_ethnicity"].isin(ESEA_CATEGORIES)]
    esea_total = int(esea["count"].sum())
    esea_pct = esea_total / total_incidents * 100
    lines.append(
        f"ESEA-category incidents (Asian-Chinese + Asian-Other): "
        f"{esea_total:,} ({esea_pct:.1f}% of all racial hate crimes logged)."
    )
    lines.append("")

    # Per-force ESEA share ranking
    lines.append("Per-force ESEA share (2020–latest):")
    per_force = (
        df.groupby(["police_force_id", "police_force_name"])["count"]
        .sum()
        .rename("total")
        .reset_index()
    )
    esea_per_force = (
        esea.groupby("police_force_id")["count"]
        .sum()
        .rename("esea")
        .reset_index()
    )
    merged = per_force.merge(esea_per_force, on="police_force_id", how="left").fillna({"esea": 0})
    merged["esea"] = merged["esea"].astype(int)
    merged["share_pct"] = (merged["esea"] / merged["total"] * 100).round(1)
    merged = merged.sort_values("share_pct", ascending=False)
    lines.append(f"  {'Force':<35} {'Total':>8} {'ESEA':>7} {'Share':>7}")
    lines.append("  " + "-" * 60)
    for _, row in merged.iterrows():
        lines.append(
            f"  {row['police_force_name'][:35]:<35} {row['total']:>8,} "
            f"{row['esea']:>7,} {row['share_pct']:>6.1f}%"
        )
    lines.append("")

    # ONS coverage
    ons_cats = sorted(df["ons_ethnicity"].dropna().unique())
    lines.append(f"ONS categories present: {len(ons_cats)}/20.")
    missing = {
        "White - English/Welsh/Scottish/Northern Irish/British", "White - Irish",
        "White - Gypsy or Irish Traveller", "White - Roma", "White - Other",
        "Mixed - White and Black Caribbean", "Mixed - White and Black African",
        "Mixed - White and Asian", "Mixed - Other",
        "Asian - Indian", "Asian - Pakistani", "Asian - Bangladeshi",
        "Asian - Chinese", "Asian - Other",
        "Black - African", "Black - Caribbean", "Black - Other",
        "Other - Arab", "Other - Any other ethnic group",
        "Not stated / Unknown",
    } - set(ons_cats)
    if missing:
        lines.append(f"  Missing from dataset: {sorted(missing)}")
    lines.append("")

    # Audit warnings across forces
    audit_dir = CLEAN_DIR / "audit"
    if audit_dir.exists():
        total_warnings = 0
        warning_forces: list[str] = []
        for af in sorted(audit_dir.glob("*.json")):
            audit = json.loads(af.read_text())
            warns = audit.get("warnings", [])
            if warns:
                warning_forces.append(audit["force_id"])
                total_warnings += len(warns)
        lines.append(
            f"Audit: {total_warnings} data-quality warnings across "
            f"{len(warning_forces)} force(s). See audit/<force>.json for details."
        )
        lines.append("")

    # Next-step pointer
    lines.append("Downstream (not part of this script):")
    lines.append("  - Join esea_share_by_force_year.csv to UK Census ONS ETH020")
    lines.append("    demographic counts by police_force_id to compute the")
    lines.append("    ESEA-crime / ESEA-population proportionality ratio.")
    lines.append("  - Plot esea_monthly_trend.csv per force to investigate")
    lines.append("    response to specific events (pandemic, news spikes).")
    lines.append("")

    (OUT_DIR / "summary_report.txt").write_text("\n".join(lines))


if __name__ == "__main__":
    sys.exit(main())
