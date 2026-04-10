# Legal & Terms of Service Analysis: Publishing foi-cli

**Date**: 2026-04-10
**Question**: Can we publish foi-cli as an open source package, given it bypasses Cloudflare?

---

## 1. Summary of Findings

| Area | Finding | Risk Level |
|---|---|---|
| FOI data reuse | Explicitly encouraged by mySociety | **Low** |
| API/feed access | Officially provided and documented | **Low** |
| Cloudflare bypass (browser fetch) | No explicit policy; grey area | **Medium** |
| robots.txt compliance | Feed tier compliant; browser tier partially compliant | **Low-Medium** |
| Alaveteli software license | AGPLv3 — our CLI is a client, not a derivative | **Low** |
| WhatDoTheyKnow ToS | No general ToS found for the free tier | **Low** |

**Bottom line**: The feed-based search tier (Tier 1) is clearly fine to publish. The Playwright browser tier (Tier 2) is in a grey area — it accesses publicly available pages but bypasses Cloudflare's bot protection. There are practical mitigations to reduce risk.

---

## 2. What mySociety Says About Data Reuse

mySociety is **explicitly pro-reuse**. Key quotes from their own documentation:

> "Our belief is that you should feel free to republish the information in full, just as we do."

> WhatDoTheyKnow is "a permanent public database archive of FOI requests... open to all"

> Their mission: "making information available to all, and of removing the need for multiple people to make the same requests"

FOI responses from UK public authorities are typically **Crown Copyright** and reusable under the [Open Government Licence](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/).

mySociety actively provides:
- JSON feeds at `/feed/search/*.json` (our Tier 1)
- Atom/RSS feeds on most listing pages
- CSV bulk export of all authorities
- An official [API documentation page](https://www.whatdotheyknow.com/help/api)
- A [data portal](https://data.mysociety.org/datasets/whatdotheyknow-api/) cataloguing their API

---

## 3. robots.txt Analysis

The WhatDoTheyKnow `robots.txt` for `User-agent: *`:

**Allowed:**
- `*/request/*/response/*/attach/*` — Attachment downloads explicitly allowed

**Disallowed (relevant to our tool):**
- `/request/*/download` — ZIP download of entire request
- `/request/*/response` — Response pages (but attachments within are allowed)
- `/search` — Search pages
- `/feed` — Feed pages (though the JSON API still works)
- `/profile/*` — User profiles
- Account, signin, track paths

**Impact on our tool:**
| CLI Feature | robots.txt | Status |
|---|---|---|
| `foi search` (feed API) | `/feed` is disallowed | Technically non-compliant, but this is a provided API |
| `foi authorities` (CSV) | Not mentioned | Compliant |
| `foi fetch` (request pages) | `/request/*/response` disallowed | Non-compliant for HTML pages |
| Attachment downloads | Explicitly allowed | Compliant |

**Important context**: robots.txt is designed for **search engine crawlers**, not for API clients or users accessing pages. mySociety provides the `/feed/*.json` endpoint specifically for programmatic access — the robots.txt disallow on `/feed` is likely aimed at preventing search engines from indexing feed URLs, not at blocking API consumers.

---

## 4. Terms of Service

**No general ToS found** for the free WhatDoTheyKnow service. The only legal page found (`/pro/pages/legal`) is specifically for WhatDoTheyKnow Pro (the paid subscription tier) and covers billing, not data access.

The privacy policy exists but is Cloudflare-blocked from programmatic access.

**This means**: There's no explicit prohibition against programmatic access to the free tier, but also no explicit permission beyond the documented API.

---

## 5. The Cloudflare Question

### Why Cloudflare is there
Cloudflare protects WhatDoTheyKnow from:
- DDoS attacks
- Aggressive scraping that impacts server performance
- Bot-driven abuse (spam requests, etc.)

### What our tool does
- **Tier 1 (feeds)**: Uses the official JSON API endpoints. Cloudflare allows these through. **No bypass involved.**
- **Tier 2 (browser)**: Uses headless Chromium to render pages — the same as a real user visiting in a browser. The stealth args prevent Cloudflare from distinguishing it from a regular browser. **This is the grey area.**

### Is bypassing Cloudflare illegal?
Cloudflare bypass is **not inherently illegal** in the UK or US. Key legal considerations:
- The Computer Misuse Act 1990 (UK) prohibits **unauthorized access** to computer systems. Accessing publicly available web pages that don't require authentication is generally not "unauthorized."
- The CFAA (US) has similar provisions. The Supreme Court's *Van Buren* decision narrowed its scope to access beyond one's authorization level.
- There is no login, no authentication bypass, no accessing private data — we're reading public pages.

However, circumventing technical measures **could** be viewed unfavourably if:
- It causes server load issues
- The site operator explicitly objects
- It's done at scale without rate limiting

---

## 6. Risk Mitigation Recommendations

### For publishing the tool as open source:

1. **Separate the tiers clearly in the package**
   - Tier 1 (feed API): Core dependency, no Cloudflare issues
   - Tier 2 (browser): Optional dependency (`pip install foi-cli[browser]`)
   - Make the distinction clear in documentation

2. **Add aggressive rate limiting by default**
   - Current: 1 req/s for feeds, 2s between browser fetches
   - This is more polite than a human clicking through pages

3. **Respect robots.txt in documentation**
   - Document which paths are disallowed
   - Note that the tool is for personal/research use of public data
   - Don't market it as a "scraper" — it's a "CLI client for FOI data"

4. **Contact mySociety proactively**
   - They are a charity that supports open data and transparency
   - Their API page says they're "gradually adding features" for programmatic access
   - They may welcome a well-built client or even provide API access
   - Contact: via their GitHub, or hello@mysociety.org

5. **Add a disclaimer to the README**
   ```
   This tool accesses publicly available FOI data from WhatDoTheyKnow.com.
   Please use responsibly with appropriate rate limiting. The browser-based
   fetch feature requires optional Playwright and should be used in accordance
   with WhatDoTheyKnow's acceptable use expectations.
   ```

6. **Consider contributing upstream**
   - Alaveteli is open source (AGPLv3)
   - You could propose a user-facing JSON API for request detail pages
   - This would eliminate the need for Cloudflare bypass entirely

---

## 7. Licensing for foi-cli Itself

Our CLI is **not a derivative work** of Alaveteli — it's an independent client that consumes their API/web pages. The AGPLv3 license on Alaveteli does not apply to us.

**Recommended license for foi-cli**: MIT or Apache 2.0 (permissive, standard for CLI tools).

---

## 8. Recommended Path Forward

| Step | Action | Priority |
|---|---|---|
| 1 | Publish with MIT license, Tier 1 only in core | **Now** |
| 2 | Include Tier 2 as optional `[browser]` extra | **Now** |
| 3 | Add usage disclaimer + rate limiting docs | **Now** |
| 4 | Email mySociety (hello@mysociety.org) to introduce the project | **Soon** |
| 5 | Open a GitHub discussion on mysociety/alaveteli proposing a user-facing request JSON API | **Soon** |
| 6 | If mySociety objects to browser tier, remove it and rely on their response | **If needed** |

The most likely outcome is that mySociety would be **supportive** — their entire mission is making FOI data accessible, and a well-built CLI tool that respects rate limits aligns with that mission. The worst case is they ask you to remove the browser bypass, in which case Tier 1 still works perfectly.

---

## 9. Sources

- [WhatDoTheyKnow API Documentation](https://www.whatdotheyknow.com/help/api)
- [WhatDoTheyKnow Data Portal](https://data.mysociety.org/datasets/whatdotheyknow-api/)
- [WhatDoTheyKnow robots.txt](https://www.whatdotheyknow.com/robots.txt) — Allows attachments, disallows feed/search/response paths
- [Alaveteli License (AGPLv3)](https://github.com/mysociety/alaveteli/blob/develop/LICENSE.txt)
- [WhatDoTheyKnow Wikipedia](https://en.wikipedia.org/wiki/WhatDoTheyKnow) — "permanent public database archive... open to all"
- [mySociety About](https://www.mysociety.org/about/) — Charity mission: transparency and open data
- [mySociety Big FOI Projects Blog Post](https://www.mysociety.org/2026/02/02/when-you-have-a-big-freedom-of-information-project-many-hands-make-light-work/) — Supports batch FOI work through Pro
- [Open Government Licence v3](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/) — FOI Crown Copyright reuse terms
- [WhatDoTheyKnow Pro Legal Terms](https://www.whatdotheyknow.com/pro/pages/legal) — Only covers paid tier
