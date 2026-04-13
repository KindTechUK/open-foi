# open-foi

CLI tool for searching and fetching FOI requests from WhatDoTheyKnow.com.

## Commands

```bash
# Install
uv venv && uv pip install -e ".[dev,browser]"
playwright install chromium

# Test
pytest tests/ -v

# Lint
ruff check src/ tests/

# Run
foi search "ESEA hate crimes"
foi fetch east_and_southeast_asian_esea_ha_63
foi fetch east_and_southeast_asian_esea_ha_63 --ext xlsx,csv --skip-images
foi attachments east_and_southeast_asian_esea_ha_63
foi attachments east_and_southeast_asian_esea_ha_63 --skip-images --format summary
foi authorities --search police
foi cache stats
```

## Versioning

Uses **hatch-vcs** — version derived from git tags, not hardcoded.

- `git tag v0.2.0 && git push --tags` to release
- Between tags: auto-generates `0.1.1.dev0+gSHA`
- `_version.py` is generated at build time (gitignored)
- Single source of truth: git tags only

## Architecture

Two-tier design:

- **Tier 1 (Feed API):** `client.py` → `search.py` → `output.py`. Uses `/feed/search/*.json?page=N` (no auth, no Cloudflare issues). 25 events/page, paginate until empty.
- **Tier 2 (Browser):** `browser.py` uses Playwright headless Chromium with stealth config to bypass Cloudflare. Fetches full correspondence + attachments.

```
src/foi_cli/
├── cli.py          # Click commands (search, fetch, attachments, authorities, cache)
├── client.py       # WDTKClient — httpx, rate limiting, retries, cache integration
├── search.py       # Query builder + paginated event aggregation + time deltas
├── models.py       # Pydantic v2: API models (FeedEvent, etc.) + output models (SearchResult, etc.)
├── browser.py      # Playwright stealth fetch + attachment download
├── output.py       # JSON/CSV/summary formatters + file export
├── cache.py        # SQLite cache at ~/.config/open-foi/cache.db
└── config.py       # TOML config at ~/.config/open-foi/config.toml
```

## Key Patterns

- **API models vs output models** in `models.py`: API models match raw JSON (`extra="ignore"`), output models reshape for CLI (nested events, computed `days_since_previous`)
- **Nullable string fields**: WDTK API returns `null` for many string fields — use `str | None = ""` not `str = ""`
- **Event deduplication**: Feed returns events, not requests. `search.py` groups by `url_title`, sorts chronologically, computes time deltas
- **Lazy Playwright import**: `browser.py` is imported at call time inside `cli.py` try/except so the core CLI works without the `[browser]` extra

## Gotchas

- **Cloudflare blocks all `/request/` paths** for programmatic access — only `/feed/` endpoints work without a browser
- **Cloudflare blocks `page.request.get()` for attachment downloads** — `_download_attachment()` falls back to browser navigation (`expect_download` + `goto`) when the API request gets 403
- **Stealth args required**: Playwright needs `--disable-blink-features=AutomationControlled` + `navigator.webdriver` removal. Config lives in `_create_stealth_context()`
- **`?unfold=1`** must be appended to request URLs or quoted sections are hidden
- **`cookie_passthrough=1`** must be on attachment download URLs
- **Feed pagination** is undocumented — stop only on empty page, never on page size heuristics
- **CSS selectors use BEM double underscores**: `.correspondence__header__author` not `.correspondence_header`
- **Content-Disposition parsing**: Must handle RFC 5987 `filename*=UTF-8''encoded%20name.pdf` format
- **HTML attachment detection**: Check URL path + Content-Disposition, not anchor text (can be generic "Download")

## Testing

- 47 tests, all offline (mocked HTTP via `respx`, mocked Playwright)
- Fixtures in `tests/conftest.py` with real ESEA query event data
- CLI tests use Click's `CliRunner`
- No live API tests in CI — manual smoke testing only

## Repository

- GitHub: `KindTechUK/open-foi`
- License: MIT
- Package name: `open-foi` (CLI command: `foi`)
