# Deferred forces

Forces that have been intentionally left out of the pipeline at this tier,
with the reasoning so a later pass can pick them up.

## (Previously deferred, now processed)

Resolved via the multi-wave fetch (2022/2023/2024/2025 FOI waves instead of
Wave-4-only) — many forces submitted cleaner CSV/XLSX/DOCX in earlier waves
even when their Wave-4 PDF was hard to extract. Also resolved by new shape
handlers: `ethnicity_year_months`, `wide_years_monthly`,
`year_sections_ethnicity_rows`, and the `emit_year_rows_as_annual` flag on
`year_sections`.

- **Police Service of Northern Ireland** — annual × ethnicity (CSV).
- **Hertfordshire Constabulary** — annual × ethnicity (DOCX table 1).
- **Dyfed Powys Police** — annual × ethnicity (DOCX table 2).
- **Cheshire Constabulary** — used Wave-2 (2022) XLSX instead of the
  fragmented Wave-4 PDF.
- **Derbyshire Constabulary** — Wave-3 (2023) CSV (`month_sections` shape).
- **Lincolnshire Police** — Wave-3 (2024) XLSX (`wide_ethnicity` + ffill).
- **South Yorkshire Police** — Wave-2 (2022) XLSX.
- **Kent Police** — Wave-3 (2023) XLSX Table 2 (`wide_years` annual).
- **Humberside Police** — Wave-3 (2023) CSV (`year_sections`).
- **Cumbria Constabulary** — Wave-2 (2022) XLSX (`ethnicity_year_months` —
  new shape for ethnicity-header rows + year rows × month cols; crimes table
  only).
- **Warwickshire Police** — Wave-2 (2022) XLSX crimes-only file
  (`wide_years_monthly` — new shape for month-rows × year-cols + ethnicity).
- **Gloucestershire Constabulary** — Wave-2 (2022) XLSX (`wide_months` with
  positional col renames to Mmm-YY).
- **Essex Police** — Wave-2 (2022) XLSX right table (self-defined).
- **Thames Valley Police** — Wave-2 (2022) XLSX Valid Crime columns.
- **Metropolitan Police Service (MPS)** — Wave-3 (2024) XLSX Tables sheet
  crimes table (`add_columns` injects implicit "East Asian" ethnicity).
- **Police Scotland** — Wave-3 (2023) XLSX Table 4 (monthly incidents by
  hate reason). Note: Police Scotland did not provide ESEA-specific CRIMES
  broken down by ethnicity; Table 4 is INCIDENTS, kept for best-effort
  coverage with CHINESE + ASIAN OTHER labels only.
- **British Transport Police** — Wave-2 (2022) XLSX (`wide_ethnicity`).
- **Cambridgeshire Constabulary** — Wave-4 (2025) PDF annual summary
  (page 0 table 0) via `wide_years`. The Wave-2 XLSX has 4 per-year
  `wide_months` tables stacked; annual rollup is simpler.
- **Cleveland Police** — Wave-2 (2022) XLSX (`year_sections`).
- **Surrey Police** — Wave-3 (2023) XLSX filtered to "HATE CRIME" rows via
  new `filter_rows` preprocessor.
- **Durham Constabulary** — Wave-2 (2022) DOCX table 2 via
  `year_sections` + `emit_year_rows_as_annual` (2019-2021 annual +
  Jan-Apr 2022 monthly, mixed granularity).
- **Gwent Police** — Wave-2 (2022) DOCX table 1 (self-defined ethnicity).
  (The Wave-4 PDF has no ethnicity breakdown — see below.)
- **Northumbria Police** — Wave-2 (2022) PDF (1 page, quarterly rollups).
- **Northamptonshire Police** — Wave-3 (2023) PDF page 1 table via new
  `year_sections_ethnicity_rows` shape. Year markers followed by ethnicity
  rows × month cols.
- **South Wales Police** — Wave-2 (2022) PDF (`year_sections`).
- **West Yorkshire Police** — Wave-4 (2025) PDF pages 3-5 crimes tables
  via multi-page concat. 21 self-defined ethnicity codes (A1..NR) × 65
  months (Jan-20 to May-25).
- **Nottinghamshire Police** — Wave-4 (2025) PDF pages 1-2 crimes tables.
  Privacy-redacted `<5` cells replaced with midpoint (2) via new
  `replace_values` preprocessor. 3 ethnicity rows × 6 year cols × 12 months.
- **Lancashire Constabulary** — Wave-4 (2025) PDF text-layer parse.
  pdfplumber returns zero tables, but the text flow is regular: each row
  ends with 72 whitespace-separated numeric tokens (12 months × 5 years +
  6 months for 2025, plus 6 annual totals). Handled via new
  `load_text_long_rows` loader that accumulates wrapped labels and extracts
  trailing numeric tails. Pages 1-2 for crimes (page 0 is incidents).

## wiltshire_police — country-level, not ethnicity

**File:** `Wiltshire Police/Data 583.xlsx`

Wiltshire submitted nationality/country counts (Afghanistan, Albania,
Bangladesh, ..., Zimbabwe — 82 country columns), not ethnicity. This is a
meaningful distinction and cannot be mapped to ONS 18+1 without an explicit
country→ethnicity lookup table that encodes judgment calls (e.g. "India" →
"Asian - Indian"? always? what about British-born Indian heritage?).

Decision: out of scope for the ONS-mapped master CSV. If country-level data
is useful for downstream analysis, it should live in a separate Wiltshire-
only output, not folded into `esea_long.csv`.

## civil_nuclear_constabulary — letterhead only

**File:** `Civil Nuclear Constabulary/2025 050 Hate Crime 300525.odt`

The ODT contains only the force's letterhead table (one row with the force
name) and a contact-details table; no hate-crime data. This is consistent
with the original FOI tracker marking Civil Nuclear as "No Data".

## north_yorkshire_police — dataset-level total only, no year granularity

**File:** `North Yorkshire Police/0224.2025 26 Response.pdf`

NYP provides (Year × Month) totals without ethnicity AND (Ethnicity × Total)
rolled up across all years. There is no (Ethnicity × Year) breakdown,
making this force coarser than our annual-granularity support. Would need
a third granularity tier (`"dataset_total"` with `year=0, month=0`) plus
the downstream convention that such rows participate only in aggregate
views. Not worth the schema bloat for one force.

## gwent_police Wave-4 — no ethnicity breakdown

**File:** `Gwent Police/DISCLOSURE.pdf`

The Wave-4 PDF provides total racial hate crime counts per year and per
month, but with no ethnicity dimension at all. Gwent is processed from its
Wave-2 (2022) DOCX instead, which does include ethnicity.

## merseyside_police supplementary DOCX

**File:** `Merseyside Police/02 Response Table 2025 FOI 0952.docx`

This is a one-table "Request / Response" cover letter with no data. The
actual Merseyside data lives in the XLSX file (already processed).

## ministry_of_defence_police — no data

The fetch_manifest entry for MoD Police contains no downloaded attachments
(the FOI response was non-responsive or no attachment was linkable). No
YAML is possible.

## Tier-4+ (PDFs requiring OCR)

All PDFs in the survey were text-extractable — no OCR was needed in
practice. If a future force submits a scanned PDF, the existing
`pdf_extract.py` can be extended with Tesseract + pdf2image along the
lines sketched in the original plan.
