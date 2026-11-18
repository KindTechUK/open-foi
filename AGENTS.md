# Working on open-foi

For anyone, person or agent, changing this repository. `open-foi` is a CLI tool for searching FOI requests on WhatDoTheyKnow.com via its public JSON feed API.

The shared [contributing guide](https://github.com/KindTechUK/.github/blob/main/CONTRIBUTING.md) and [AI policy](https://github.com/KindTechUK/.github/blob/main/AI_POLICY.md) apply here. This file adds what is specific to this repository.

## How a change is made

- Work on a branch and open a pull request against `main`. Keep it to one change.
- Run `ruff check src/ tests/` and `pytest tests/` before you push. CI runs both on Python 3.11 to 3.13.
- Tests never call the network. Mock HTTP with `respx` and use the saved fixtures.
- Do not add personal data about real people to code, tests, fixtures or docs. FOI requests name the people who made them, so new fixtures use invented requester names.
- Use conventional commit messages (`fix:`, `feat:`, `docs:`, `chore:`).
- Do not add co-author or tool trailers to commits. Say in the pull request description which tools helped.
- Agents: list only the checks you actually ran, and say what you could not run.

## Commands

```bash
# Install
uv venv && uv pip install -e ".[dev]"

# Optional: install data-cleaning extras (for examples/esea_clean_data.py)
uv pip install -e ".[clean]"
# For OCR fallback on image-only PDFs:
brew install tesseract poppler

# Test
pytest tests/ -v

# Lint
ruff check src/ tests/

# Run
foi search "ESEA hate crimes"
foi search "ESEA hate crimes" --status successful --format summary
foi authorities --search police
foi cache stats

# ESEA data cleaning pipeline (prototype, examples/ only)
python examples/esea_clean_data.py                          # all forces
python examples/esea_clean_data.py --force staffordshire_police
python examples/esea_clean_data.py --dry-run

# ESEA analysis example — run AFTER esea_clean_data.py
python examples/esea_analysis.py
```

## Versioning

Uses **hatch-vcs** — version derived from git tags, not hardcoded.

- `git tag v0.2.0 && git push --tags` to release
- Between tags: auto-generates `0.1.1.dev0+gSHA`
- `_version.py` is generated at build time (gitignored)
- Single source of truth: git tags only

## Architecture

Single-tier feed-API client. Search results include the canonical WhatDoTheyKnow URL per request — users open those URLs in a browser to read correspondence and download attachments. The CLI does not scrape request pages or download attachments programmatically.

```
src/foi_cli/
├── cli.py          # Click commands (search, authorities, cache)
├── client.py       # WDTKClient — httpx, rate limiting, retries, cache integration
├── search.py       # Query builder + paginated event aggregation + time deltas
├── models.py       # Pydantic v2: API models (FeedEvent, etc.) + output models (SearchResult, etc.)
├── output.py       # JSON/CSV/summary formatters + file export
├── cache.py        # SQLite cache at ~/.config/open-foi/cache.db
└── config.py       # TOML config at ~/.config/open-foi/config.toml

examples/esea_cleaning/          # ESEA cleaning pipeline (prototype, not part of CLI)
├── force_registry.py            # Join fetch_manifest.json with per-force YAML configs
├── loaders.py                   # CSV/XLSX/DOCX/ODT/PDF → pandas DataFrame
├── shapes.py                    # 8 shape handlers (long, long_ffill, wide_months,
│                                #   wide_ethnicity, event_log, month_sections,
│                                #   ethnicity_sections, year_sections)
├── ethnicity.py                 # Apply source→ONS mapping; produce audit dict
├── pdf_extract.py               # pdfplumber wrapper (pages, tables, multi-page concat)
└── mappings/
    ├── _ons_18_plus_1.yaml      # Canonical UK census 19+1 categories
    ├── _template.yaml           # Per-force config template
    ├── _deferred.md             # Why forces without YAMLs aren't processed
    └── <force_id>.yaml          # One per processed force — extraction + mapping
examples/esea_clean_data.py      # Orchestrator: loaders → shapes → mapping → long CSV
examples/esea_analysis.py        # End-to-end example: loads long CSV, produces
                                 #   per-force ESEA shares + monthly trends + report
research/esea-pipeline-report.md # Summary of what works, what was deferred, and why
```

The cleaning pipeline operates entirely on locally-stored files; it does not fetch from WhatDoTheyKnow.

## Key Patterns

- **API models vs output models** in `models.py`: API models match raw JSON (`extra="ignore"`), output models reshape for CLI (nested events, computed `days_since_previous`)
- **Nullable string fields**: WDTK API returns `null` for many string fields — use `str | None = ""` not `str = ""`
- **Event deduplication**: Feed returns events, not requests. `search.py` groups by `url_title`, sorts chronologically, computes time deltas
- **Feed pagination** is undocumented — stop only on empty page, never on page size heuristics

## Testing

- All tests offline (mocked HTTP via `respx`)
- Fixtures in `tests/conftest.py` with real ESEA query event data
- CLI tests use Click's `CliRunner`
- No live API tests in CI — manual smoke testing only

## Repository

- GitHub: `KindTechUK/open-foi`
- License: see `LICENSE`
- Package name: `open-foi` (CLI command: `foi`)
