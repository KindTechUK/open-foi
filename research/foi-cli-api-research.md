# FOI CLI Tool — API Research & Feasibility Analysis

**Date**: 2026-04-09
**Objective**: Build a CLI interface for finding, submitting, and following up on FOI (Freedom of Information) requests, suitable for agent-driven workflows (e.g., Claude Code).

---

## 1. Available API Surfaces

### 1.1 WhatDoTheyKnow Read API (No Auth Required)

WhatDoTheyKnow (WDTK) is the UK's primary FOI platform, powered by Alaveteli. It exposes a **read-only JSON API** by appending `.json` to most URLs. **No API key is required for read access.**

#### JSON Endpoints (Public, Unauthenticated)

| Endpoint Pattern | Description | Example |
|---|---|---|
| `/request/<url_title>.json` | Single FOI request details | `/request/nhs_funding_2024.json` |
| `/user/<url_name>.json` | User profile & request history | `/user/john_smith.json` |
| `/body/<url_name>.json` | Public authority details | `/body/cabinet_office.json` |
| `/search/<query>.json` | Search results as JSON | `/search/climate+change.json` |
| `/body/all-authorities.csv` | Bulk CSV export of all authorities | Direct download |
| `/feed/search/<query>` | Atom feed for search (also `.json`) | `/feed/search/nhs.json` |
| `/feed/body/<url_name>` | Atom feed for authority events | `/feed/body/home_office` |
| `/feed/user/<url_name>` | Atom feed for user activity | `/feed/user/jane_doe` |

#### Request JSON Schema (from `json_for_api`)

```json
{
  "id": 12345,
  "url_title": "nhs_funding_2024",
  "title": "NHS Funding Allocations 2024",
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-03-20T14:00:00Z",
  "described_state": "waiting_response",
  "display_status": "Awaiting response",
  "awaiting_description": false,
  "prominence": "normal",
  "law_used": "foi",
  "tags": ["nhs", "health", "funding"],
  "user": { /* user object */ },
  "public_body": { /* authority object */ },
  "info_request_events": [ /* event history */ ]
}
```

#### Advanced Search Query Syntax

WDTK supports a rich query language that can be used in both the search UI and API:

| Operator | Description | Example |
|---|---|---|
| `status:<state>` | Requests that have **ever** had this status | `status:rejected` |
| `latest_status:<state>` | Requests **currently** in this status | `latest_status:waiting_response` |
| `variety:<type>` | Events of a specific variety | `variety:sent` |
| `latest_variety:<type>` | Events currently of this variety | `latest_variety:response` |
| `requested_from:<url_name>` | Requests to a specific authority | `requested_from:home_office` |
| `requested_by:<url_name>` | Requests by a specific user | `requested_by:julian_todd` |
| `filetype:<ext>` | Responses containing file type | `filetype:pdf` |
| `request_public_body_tag:<tag>` | Requests to tagged authorities | `request_public_body_tag:charity` |
| `"exact phrase"` | Exact phrase match | `"climate change"` |
| `word1 OR word2` | Boolean OR | `nhs OR health` |
| `tag:<name>` | Requests with specific tag | `tag:environment` |

Date range filtering is also supported via the Atom/JSON feed parameters.

#### Known Status Values

- `waiting_response` — Awaiting response from authority
- `waiting_classification` — Needs user to classify response
- `waiting_response_overdue` — Response is overdue
- `waiting_response_very_overdue` — Response is very overdue
- `not_held` — Information not held by authority
- `rejected` — Request refused
- `successful` — Request fulfilled
- `partially_successful` — Partially fulfilled
- `waiting_clarification` — Authority needs clarification
- `gone_postal` — Being handled by post
- `internal_review` — Under internal review
- `error_message` — Delivery error
- `requires_admin` — Needs admin attention
- `attention_requested` — Flagged for attention
- `user_withdrawn` — Withdrawn by requester

### 1.2 Alaveteli Write API v2 (Authority-Only — Not Used by This CLI)

The Write API exists but is designed exclusively for **public bodies** (not end-users). It requires a per-body API key set in the admin interface. Endpoints include creating requests, adding correspondence, and updating state at `/api/v2/request.json`.

> **We will NOT use this API.** It's irrelevant for a citizen-facing CLI. Instead, end-user submission and follow-up will use **browser agent automation** (see Section 5).

### 1.3 Programmatic Request Submission (Browser-Flow)

For **end-user** FOI request submission, Alaveteli supports pre-populating the request form via URL parameters:

```
https://www.whatdotheyknow.com/new/<public_body_url_name>
  ?title=Request+Summary
  &default_letter=Body+of+the+request
  &tags=tag1+tag2+machine:value
```

| Parameter | Description |
|---|---|
| `title` | Pre-filled request summary/title |
| `default_letter` | Request body (system adds salutation/sign-off) |
| `body` | Complete request text (custom salutation/sign-off) |
| `tags` | Space-separated tags; supports machine tags with `:` |

**Key limitation**: This opens a browser form — it does **not** submit the request programmatically. The user must still be logged in and manually confirm submission. This is intentional to prevent abuse.

### 1.4 Atom/RSS Feeds

Every listing page has an Atom feed equivalent (append `/feed` or use `<link rel="alternate">` discovery). These support the same advanced search operators as JSON endpoints.

---

## 2. Existing Tools & Libraries

### 2.1 No Existing CLI Tools or Client Libraries

After thorough research:
- **No Python library** exists on PyPI for Alaveteli/WDTK
- **No npm package** exists for Alaveteli/WDTK
- **No official CLI tool** has been built by mySociety
- **No third-party wrappers** were found on GitHub

This is a **greenfield opportunity** — the CLI we build would be the first dedicated programmatic client for WDTK/Alaveteli.

### 2.2 Related Projects

| Project | Language | Description |
|---|---|---|
| [Alaveteli](https://github.com/mysociety/alaveteli) | Ruby on Rails | The FOI platform itself (source of the API) |
| [whatdotheyknow-theme](https://github.com/mysociety/whatdotheyknow-theme) | Ruby | UK-specific Alaveteli theme |
| [Froide](https://github.com/okfde/froide) | Python/Django | Alternative FOI platform (German origin) — has its own API but different schema |

---

## 3. Feasibility Assessment

### 3.1 What We CAN Do Programmatically (Today)

| Capability | Method | Auth Required |
|---|---|---|
| Search FOI requests | GET `/search/<query>.json` | No |
| View request details | GET `/request/<url_title>.json` | No |
| View authority details | GET `/body/<url_name>.json` | No |
| View user profiles | GET `/user/<url_name>.json` | No |
| List all authorities | GET `/body/all-authorities.csv` | No |
| Monitor request updates | GET feed endpoints | No |
| Filter by status/authority/date | Advanced search operators | No |

### 3.2 What Requires Browser Automation

| Capability | Why No API | Solution |
|---|---|---|
| Submit FOI requests as end-user | No public submission API; requires login + form | Browser agent automation (see Section 5) |
| Follow up on requests as end-user | No end-user write API | Browser agent navigates to follow-up form |
| Authenticate as end-user | No OAuth/token-based user auth | Browser agent handles login flow |
| Classify/update request status | Requires authenticated session | Browser agent interacts with status form |
| Download attachments | No attachment API endpoint | Browser agent or parse event HTML for direct URLs |

### 3.3 The Pre-Populated URL Bridge

Alaveteli supports pre-populating the request form via URL parameters (see Section 1.3). This is the **bridge between the CLI and browser agent**:

1. **CLI generates** the draft text, selects the authority, builds the URL
2. **Browser agent receives** the pre-populated URL and handles login + form submission
3. **CLI monitors** the request status via the read API after submission

This separation keeps the CLI focused on intelligence (search, draft, monitor) while delegating the browser interaction to a dedicated agent layer.

---

## 4. Proposed CLI Architecture

### 4.1 Core CLI Commands

```
foi search <query> [--status <status>] [--authority <name>] [--filetype <ext>]
    Search FOI requests with advanced filtering

foi request show <id_or_url_title>
    Display full details of an FOI request

foi request list [--by <user>] [--to <authority>] [--status <status>]
    List requests with filters

foi authority show <url_name>
    Display authority details and contact info

foi authority list [--tag <tag>] [--search <query>]
    List/search public authorities

foi authority export
    Download all authorities as CSV

foi monitor <query_or_request_id> [--interval <seconds>]
    Watch for updates on a request or search

foi draft <authority> --title "..." --body "..."
    Generate a draft FOI request and open submission URL

foi follow-up draft <request_id> --body "..."
    Draft a follow-up message for a request

foi status <request_id>
    Quick status check on a request

foi feed <query_or_authority_or_user> [--format json|atom]
    Stream feed of events
```

### 4.2 Agent-Friendly Features (for Claude Code integration)

For an AI agent workflow, the CLI should support:

1. **Structured JSON output** (`--json` flag on all commands) for machine parsing
2. **Template-based request drafting** with variable substitution
3. **Batch operations** — search, filter, and act on multiple requests
4. **Status monitoring** with webhook/callback support
5. **Request analysis** — summarize response text, extract key information
6. **Follow-up generation** — given a rejection reason, draft appropriate follow-up
7. **Authority intelligence** — which authorities respond fastest, rejection rates, etc.

### 4.3 Technology Choices

| Decision | Recommendation | Rationale |
|---|---|---|
| Language | **Python** | Rich HTTP/CLI ecosystem, agent-friendly, Claude Code native |
| CLI Framework | **Click** or **Typer** | Modern, type-safe, good help generation |
| HTTP Client | **httpx** | Async support, modern Python |
| Output Formatting | **Rich** | Beautiful terminal tables, JSON, markdown |
| Browser Automation | **Playwright** (primary) | Deterministic, reliable for known WDTK forms |
| Browser AI Fallback | **browser-use** (optional) | LLM-driven fallback for edge cases / changed layouts |
| Session Management | **Playwright `storageState`** | Persist login cookies across CLI invocations |
| Config Storage | **~/.config/foi-cli/** | XDG-compliant, stores preferences + session state |
| Package Distribution | **PyPI** (`foi-cli`) | Standard Python distribution |

### 4.4 Proposed Project Structure

```
my-society-cli/
├── src/
│   └── foi_cli/
│       ├── __init__.py
│       ├── cli.py              # Main CLI entry point (Click/Typer)
│       ├── client.py           # Alaveteli/WDTK read API client
│       ├── models.py           # Pydantic models for API responses
│       ├── search.py           # Advanced search query builder
│       ├── formatters.py       # Output formatting (table, json, markdown)
│       ├── monitor.py          # Feed monitoring / polling
│       ├── drafting.py         # Request/follow-up draft generation
│       ├── config.py           # Configuration management
│       └── browser/
│           ├── __init__.py
│           ├── agent.py        # Browser agent orchestration
│           ├── auth.py         # Login & session management
│           ├── submit.py       # Request submission automation
│           ├── followup.py     # Follow-up & review submission
│           └── scripts/        # Deterministic Playwright scripts
├── tests/
├── research/
├── pyproject.toml
└── README.md
```

---

## 5. Browser Agent Strategy for Submission & Follow-Up

### 5.1 Why Browser Agents

The WDTK/Alaveteli platform has no end-user write API by design (to prevent abuse). All submission, follow-up, and status classification requires an authenticated browser session. **Browser agents** solve this by automating the browser interaction while keeping the human in the loop for confirmation.

The workflow is:
1. **CLI** handles intelligence: search, draft generation, monitoring, strategy
2. **Browser agent** handles interaction: login, form filling, submission confirmation
3. **Human** reviews and approves before final submission

### 5.2 Browser Agent Options Comparison

| Tool | Language | Approach | Stars | Best For |
|---|---|---|---|---|
| **[browser-use](https://github.com/browser-use/browser-use)** | Python | LLM-driven via CDP | 50k+ | Full autonomy, natural language tasks |
| **[Stagehand](https://github.com/browserbase/stagehand)** | TypeScript | AI primitives on Playwright (`act()`, `extract()`, `observe()`) | 15k+ | Structured, reliable web automation |
| **[Playwright](https://playwright.dev/)** (direct) | Python/TS/Java/.NET | Deterministic scripting | 70k+ | Predictable forms, known page structure |
| **Claude Computer Use** | API | Screenshot-based, mouse/keyboard control | N/A | General-purpose, works on any UI |
| **[Browserbase MCP](https://github.com/browserbase/mcp-server-browserbase)** | TypeScript | MCP server wrapping Stagehand | 3k+ | Direct LLM tool integration |

### 5.3 Recommended Approach: Hybrid Playwright + browser-use

**For WDTK specifically**, the forms are well-structured and predictable, making a hybrid approach optimal:

#### Layer 1: Playwright Scripts (Deterministic — 80% of work)

WDTK's form structure is stable — the submission and follow-up forms rarely change. Deterministic Playwright scripts handle:
- **Login**: Navigate to `/profile/sign_in`, fill email/password, submit
- **Request submission**: Navigate to pre-populated `/new/<authority>` URL, verify form contents, click submit
- **Follow-up**: Navigate to request page, click "Write a reply", fill follow-up text, submit
- **Status classification**: Navigate to request page, select status from dropdown, submit

```python
# Example: Deterministic Playwright submission
async def submit_request(page, authority: str, title: str, body: str):
    url = f"https://www.whatdotheyknow.com/new/{authority}"
    url += f"?title={quote(title)}&default_letter={quote(body)}"
    await page.goto(url)
    # Verify pre-populated content
    await page.wait_for_selector("#outgoing_message_body")
    # Human confirmation step (or auto-submit if configured)
    await page.click("input[type='submit'][value='Send request']")
```

#### Layer 2: browser-use Fallback (AI-Driven — 20% edge cases)

For unexpected CAPTCHAs, changed layouts, or complex multi-step flows, fall back to `browser-use`:

```python
from browser_use import Agent
agent = Agent(
    task="Log into WhatDoTheyKnow, navigate to the FOI request at /request/xyz, "
         "click 'Write a follow up', paste the following text, and submit: ...",
    llm=model
)
await agent.run()
```

### 5.4 Browser Agent Workflows

#### Workflow A: Submit New FOI Request

```
CLI: foi submit --to cabinet_office --title "..." --body "..."
  │
  ├─ 1. CLI validates authority exists (JSON API)
  ├─ 2. CLI generates pre-populated URL
  ├─ 3. CLI invokes browser agent with URL
  │     ├─ Browser agent checks login state
  │     ├─ Browser agent logs in if needed (stored credentials)
  │     ├─ Browser agent navigates to pre-populated form
  │     ├─ Browser agent displays preview for human confirmation
  │     └─ Browser agent submits on confirmation
  ├─ 4. CLI extracts new request URL from browser
  └─ 5. CLI begins monitoring via JSON API
```

#### Workflow B: Follow Up on Rejected Request

```
CLI: foi follow-up <request_id> --reason rejection --body "..."
  │
  ├─ 1. CLI fetches request details (JSON API)
  ├─ 2. CLI analyzes rejection reason from response events
  ├─ 3. CLI drafts follow-up text (or uses provided --body)
  ├─ 4. CLI invokes browser agent
  │     ├─ Browser agent navigates to request page
  │     ├─ Browser agent clicks "Write a follow up"
  │     ├─ Browser agent fills follow-up text
  │     ├─ Browser agent displays preview for human confirmation
  │     └─ Browser agent submits
  └─ 5. CLI confirms submission and updates monitoring
```

#### Workflow C: Request Internal Review

```
CLI: foi review-request <request_id> --body "..."
  │
  ├─ 1. CLI fetches request + authority details
  ├─ 2. CLI generates internal review letter from template
  ├─ 3. CLI invokes browser agent for follow-up submission
  └─ 4. CLI updates request tracking
```

### 5.5 Authentication & Credential Management

The browser agent needs WDTK login credentials. Options:

| Method | Security | UX |
|---|---|---|
| **Environment variables** (`WDTK_EMAIL`, `WDTK_PASSWORD`) | Medium | Simple, agent-friendly |
| **System keychain** (via `keyring` library) | High | Secure, cross-platform |
| **Browser profile persistence** (Playwright `storageState`) | Medium | Login once, reuse session cookies |
| **Interactive login** (agent opens browser, user logs in manually) | High | One-time, then session persists |

**Recommended**: Use Playwright's `storageState` to persist session cookies after an initial interactive login. This avoids storing passwords while maintaining session persistence across CLI invocations.

### 5.6 Key Technical Considerations

#### Rate Limiting
WDTK doesn't document rate limits, but aggressive automation will likely trigger blocking. The CLI should implement:
- Configurable delays between browser actions
- Response caching (with TTL) for read API calls
- Exponential backoff on 429/503 responses
- Respect for `robots.txt` and site terms

#### Human-in-the-Loop
All submission actions should default to requiring human confirmation before final submit. This can be configured:
- `--confirm` (default): Show preview, wait for user approval
- `--dry-run`: Generate everything but don't submit
- `--auto-submit`: Skip confirmation (for trusted automated workflows)

#### Data Completeness
The JSON API returns basic fields. For full request text, correspondence history, and attachments:
- Fetch the deep JSON (with events) for full correspondence
- Browser agent can extract attachment download URLs from rendered pages
- Follow pagination for long correspondence threads

---

## 6. Implementation Phases

### Phase 1: Read-Only CLI (MVP)
- Search requests, authorities, users
- View request details and status
- Advanced search with all operators
- JSON output mode for agent consumption (Claude Code can use directly)
- Feed monitoring

### Phase 2: Draft & Submit via Browser Agent
- Generate draft FOI requests from templates
- Playwright-based browser agent for login & submission
- Pre-populated URL bridge between CLI and browser
- Human-in-the-loop confirmation before submission
- Session persistence via `storageState`
- Track submitted requests

### Phase 3: Follow-Up Intelligence + Browser Agent
- Monitor request status changes
- Detect rejections and suggest follow-up strategies
- Draft follow-up letters based on rejection reasons
- Browser agent submits follow-ups, internal review requests
- ICO complaint drafting
- `browser-use` fallback for edge cases

### Phase 4 (Optional): Enhanced Analytics
- Authority analytics (response times, success rates)
- Batch operations across multiple requests
- Request outcome prediction based on historical data
- Note: Claude Code can use the CLI directly — no MCP wrapper needed

---

## 7. Sources

### Alaveteli / WhatDoTheyKnow
- [WhatDoTheyKnow API Help Page](https://www.whatdotheyknow.com/help/api)
- [WhatDoTheyKnow API Dataset](https://data.mysociety.org/datasets/whatdotheyknow-api/)
- [Alaveteli API Documentation](https://alaveteli.org/docs/developers/api/)
- [Alaveteli GitHub Repository](https://github.com/mysociety/alaveteli)
- [Alaveteli API Controller Source](https://github.com/mysociety/alaveteli/blob/develop/app/controllers/api_controller.rb)
- [Alaveteli InfoRequest Model Source](https://github.com/mysociety/alaveteli/blob/develop/app/models/info_request.rb)
- [Alaveteli High-level Overview](http://alaveteli.org/docs/developers/overview/)
- [mySociety GitHub Organization](https://github.com/mysociety)
- [mySociety Datasets & APIs](https://data.mysociety.org/sources/mysociety/)

### Browser Agent Tools
- [browser-use — AI Browser Agent (Python)](https://github.com/browser-use/browser-use) — 50k+ stars, LLM-driven CDP automation
- [Stagehand — AI Web Agent SDK (TypeScript)](https://github.com/browserbase/stagehand) — `act()`, `extract()`, `observe()` primitives on Playwright
- [Playwright — Browser Automation](https://playwright.dev/) — Deterministic scripting, Python/TS/Java/.NET
- [Browserbase MCP Server](https://github.com/browserbase/mcp-server-browserbase) — MCP server wrapping Stagehand for LLM tool use
- [Claude Computer Use Tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/computer-use-tool) — Screenshot-based browser control
- [Agentic Browser Landscape 2026](https://nohacks.co/blog/agentic-browser-landscape-2026) — Comprehensive comparison
- [Stagehand vs Browser Use vs Playwright Comparison](https://www.nxcode.io/resources/news/stagehand-vs-browser-use-vs-playwright-ai-browser-automation-2026)
