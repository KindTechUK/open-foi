# open-foi

A command-line tool for searching Freedom of Information requests on [WhatDoTheyKnow.com](https://www.whatdotheyknow.com), the UK's primary FOI platform powered by [Alaveteli](https://github.com/mysociety/alaveteli).

Built for researchers, journalists, and anyone working with FOI data at scale.

## Features

- **Search** FOI requests with advanced filters (status, authority, filetype, tags)
- **Structured output** with requests as primary entities and nested event timelines
- **Time tracking** — days between events, total request duration
- **Export** to JSON, CSV, or plain text
- **Caching** — SQLite-backed response cache to avoid redundant API calls
- **Agent-friendly** — JSON output works natively with Claude Code, jq, and other tools

`open-foi` is a feed-API client only. Each result includes the full request URL on WhatDoTheyKnow — open it in your browser to read the correspondence and download any attachments.

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

The `url` on each request is the canonical WhatDoTheyKnow page. Open it in your browser to read the full correspondence and download attachments.

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

`open-foi` uses WhatDoTheyKnow's JSON feed endpoints (`/feed/search/*.json`) with `?page=N` pagination to retrieve all results. No authentication required. Rate-limited to 1 request/second by default.

For everything beyond search — full correspondence text, attachments — open the request URL in your browser.

## Configuration

Optional config file at `~/.config/foi-cli/config.toml`:

```toml
rate_limit = 1.0          # Seconds between API requests
timeout = 30.0             # HTTP timeout
default_format = "json"    # json, summary, or csv

[cache]
enabled = true
ttl = 3600                 # Cache TTL in seconds
```

## Responsible use

This tool accesses publicly available FOI data from WhatDoTheyKnow.com, a service run by [mySociety](https://www.mysociety.org/), a UK charity dedicated to transparency and open data.

- **FOI responses** are typically Crown Copyright, reusable under the [Open Government Licence](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/)
- **Rate limiting** is enforced by default to be respectful of server resources
- **Feed API access** uses officially documented endpoints

Please use this tool responsibly. If you plan to make large-scale or high-frequency requests, consider reaching out to mySociety first.

## Development

```bash
git clone https://github.com/kindtech/open-foi.git
cd open-foi
uv venv && uv pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Lint
ruff check src/ tests/
```

## License

[Apache-2.0](LICENSE)

## Acknowledgements

- [mySociety](https://www.mysociety.org/) for building and maintaining WhatDoTheyKnow
- [Alaveteli](https://github.com/mysociety/alaveteli) — the open-source FOI platform
- FOI data published on WhatDoTheyKnow is contributed by its users and the public authorities that respond
