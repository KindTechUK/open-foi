# open-foi

A command-line tool for searching, viewing, and fetching Freedom of Information requests from [WhatDoTheyKnow.com](https://www.whatdotheyknow.com), the UK's primary FOI platform powered by [Alaveteli](https://github.com/mysociety/alaveteli).

Built for researchers, journalists, and anyone working with FOI data at scale.

## Features

- **Search** FOI requests with advanced filters (status, authority, filetype, tags)
- **Structured output** with requests as primary entities and nested event timelines
- **Time tracking** — days between events, total request duration
- **Fetch full content** of request pages and download all attachments
- **Batch operations** — fetch multiple requests with a shared browser session
- **Export** to JSON, CSV, or plain text
- **Caching** — SQLite-backed response cache to avoid redundant API calls
- **Agent-friendly** — JSON output works natively with Claude Code, jq, and other tools

## Installation

Requires Python 3.11+.

```bash
# Install from GitHub
uv pip install git+https://github.com/kindtech/open-foi

# Or clone and install locally
git clone https://github.com/kindtech/open-foi.git
cd open-foi
uv pip install -e .
```

### Optional: Browser-based fetching

To fetch full request content and download attachments (bypasses Cloudflare):

```bash
uv pip install -e ".[browser]"
playwright install chromium
```

## Quick start

### Search FOI requests

```bash
# Search for ESEA hate crime FOI requests
foi search "east and southeast asian hate crimes"

# Filter by status
foi search "ESEA hate crimes" --status successful

# Filter by authority
foi search "NHS funding" --authority department_of_health_and_social_care

# Export to CSV
foi search "ESEA hate crimes" --output results.csv

# Plain text summary
foi search "ESEA hate crimes" --format summary
```

### Output structure

Search results are structured as deduplicated requests with nested event timelines:

```json
{
  "query": "ESEA hate crimes",
  "total_requests": 130,
  "total_events": 255,
  "requests": [
    {
      "title": "East and Southeast Asian (ESEA) Hate Crimes/Incidents Data 2020-25",
      "url": "https://www.whatdotheyknow.com/request/east_and_southeast_asian_esea_ha_63",
      "authority": "Nottinghamshire Police",
      "status": "successful",
      "total_days": 184,
      "events": [
        { "type": "sent", "date": "2025-06-01", "status": "waiting_response", "days_since_previous": null },
        { "type": "response", "date": "2025-12-03", "status": "successful", "days_since_previous": 185 }
      ]
    }
  ]
}
```

### Fetch full content and attachments

```bash
# Fetch a single request (requires [browser] extra)
foi fetch east_and_southeast_asian_esea_ha_63

# Fetch multiple requests (shared browser session)
foi fetch request_one request_two request_three

# Pipe search results into fetch
foi search "ESEA hate crimes" --status successful \
  | jq -r '.requests[].url_title' \
  | head -5 \
  | xargs foi fetch
```

Downloaded content is saved to `./foi-data/<request>/`:

```
foi-data/
  east_and_southeast_asian_esea_ha_63/
    correspondence.json       # Full text of all messages
    attachments/
      response_3236066_8_FOI_Response.pdf
      response_3236066_3_image001.png
```

### Other commands

```bash
# List/search public authorities
foi authorities --search "police"

# Cache management
foi cache stats
foi cache clear

# Verbose logging (debug)
foi -v search "NHS"
```

## Search operators

WhatDoTheyKnow supports a rich query language:

| Flag | Search operator | Example |
|---|---|---|
| `--status` | `latest_status:` | `successful`, `rejected`, `waiting_response` |
| `--authority` | `requested_from:` | `home_office`, `kent_police` |
| `--user` | `requested_by:` | `julian_todd` |
| `--filetype` | `filetype:` | `pdf`, `xlsx`, `csv` |
| `--tag` | `tag:` | `police`, `environment` |

You can also use these operators directly in the query string:

```bash
foi search "climate change filetype:pdf latest_status:successful"
```

## How it works

**Tier 1 — Feed API (no browser needed):** Uses WhatDoTheyKnow's JSON feed endpoints (`/feed/search/*.json`) with undocumented `?page=N` pagination to retrieve all results. No authentication required. Rate-limited to 1 request/second.

**Tier 2 — Browser fetch (optional):** Uses headless Chromium via Playwright to render full request pages, extract complete correspondence text, and download attachments. Cloudflare's bot protection requires stealth browser configuration. Rate-limited to one page every 2 seconds.

## Configuration

Optional config file at `~/.config/foi-cli/config.toml`:

```toml
rate_limit = 1.0          # Seconds between API requests
timeout = 30.0             # HTTP timeout
default_format = "json"    # json, summary, or csv
fetch_output_dir = "./foi-data"

[cache]
enabled = true
ttl = 3600                 # Cache TTL in seconds
```

## Responsible use

This tool accesses publicly available FOI data from WhatDoTheyKnow.com, a service run by [mySociety](https://www.mysociety.org/), a UK charity dedicated to transparency and open data.

- **FOI responses** are typically Crown Copyright, reusable under the [Open Government Licence](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/)
- **Rate limiting** is enforced by default to be respectful of server resources
- **Feed API access** uses officially documented endpoints
- **Browser-based fetching** accesses the same public pages available to any browser user

Please use this tool responsibly. If you plan to make large-scale or high-frequency requests, consider reaching out to mySociety first.

## Development

```bash
git clone https://github.com/kindtech/open-foi.git
cd open-foi
uv venv && uv pip install -e ".[dev,browser]"
playwright install chromium

# Run tests
pytest tests/ -v

# Lint
ruff check src/ tests/
```

## License

[MIT](LICENSE)

## Acknowledgements

- [mySociety](https://www.mysociety.org/) for building and maintaining WhatDoTheyKnow
- [Alaveteli](https://github.com/mysociety/alaveteli) — the open-source FOI platform
- FOI data published on WhatDoTheyKnow is contributed by its users and the public authorities that respond
