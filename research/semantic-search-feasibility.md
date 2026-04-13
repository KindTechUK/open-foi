# Semantic Search Feasibility for open-foi

**Date:** 2026-04-12
**Status:** Research / Not started

---

## 1. How WDTK's Keyword Search Works

WhatDoTheyKnow runs on [Alaveteli](https://github.com/mysociety/alaveteli), a Ruby on Rails platform. Search is powered by **Xapian**, a C++ full-text search engine, integrated via the `acts_as_xapian` plugin.

### 1.1 What Gets Indexed

Each `InfoRequestEvent` is indexed with two text fields:

| Field | Content |
|---|---|
| `search_text_main` | Message body: outgoing text for `sent`/`followup_sent`, incoming text for `response`, comment body for `comment` events |
| `title` | The FOI request title |

Source: [InfoRequestEvent model](https://github.com/mysociety/alaveteli/blob/develop/app/models/info_request_event.rb)

### 1.2 Search Prefixes

These prefixes are indexed as Xapian boolean terms and can be used in queries:

| Query syntax | Xapian prefix | Description |
|---|---|---|
| `latest_status:` | `L` | Request status (successful, rejected, waiting_response, etc.) |
| `requested_from:` | `F` | Authority url_name |
| `requested_by:` | `B` | Requester url_name |
| `filetype:` | `T` | Attachment file type (pdf, xlsx, etc.) |
| `tag:` | `U` | Request tag |
| `variety:` | `V` | Event type (sent, response, comment) |
| `latest_variety:` | `K` | Latest event type on the request |
| `request:` | `R` | Specific request url_title |
| `commented_by:` | `C` | Commenter url_name |
| `request_public_body_tag:` | `X` | Authority tag |

Our `build_query()` in `search.py` currently supports: `latest_status`, `requested_from`, `requested_by`, `filetype`, `tag`.

### 1.3 Xapian Query Parsing

When a query like `ESEA hate crimes` hits `/feed/search/ESEA%20hate%20crimes.json`, Xapian's QueryParser processes it as follows:

- **Default operator is OR** — `ESEA OR hate OR crimes`
- **English stemmer** is applied — "crimes" matches "crime", "criminal"
- **Ranking** uses BM25 (term frequency / inverse document frequency)

### 1.4 Xapian Operators Available (but unexposed in our CLI)

| Operator | Syntax | Example |
|---|---|---|
| AND | `term1 AND term2` | `ESEA AND hate` |
| OR | `term1 OR term2` | `Asian OR oriental` (default) |
| NOT | `term1 NOT term2` | `crime NOT cybercrime` |
| Phrase | `"exact phrase"` | `"hate crime"` |
| NEAR | `term1 NEAR term2` | `Asian NEAR attack` (within 10 words) |
| NEAR/n | `term1 NEAR/5 term2` | Within 5 words |
| ADJ | `term1 ADJ term2` | Like NEAR but preserves word order |
| Wildcard | `prefix*` | `discrim*` matches discrimination, discriminatory |
| Required | `+term` | `+ESEA hate` (ESEA required) |
| Exclude | `-term` | `hate -cyber` (exclude cyber) |

Reference: [Xapian QueryParser Syntax](https://xapian.org/docs/queryparser.html)

### 1.5 Limitations of Keyword Search

Xapian is a bag-of-words engine with no concept of meaning. It fails when:

- **Synonyms**: Searching "hate crimes" won't find "racist incidents" or "racial attacks"
- **Conceptual queries**: "discrimination against East Asians" won't match documents that discuss the concept without those exact terms
- **Abbreviations**: "ESEA" won't match "East and Southeast Asian" unless both appear in the same document
- **Paraphrasing**: "police refusal to provide data" won't match "constabulary declined the request"

---

## 2. Semantic Search Approaches

Since WDTK's API is purely keyword-based, any semantic capability must be client-side.

### 2.1 Query Expansion

**Idea:** Use an LLM or synonym model to expand the user's query with semantically related terms before sending to WDTK.

```
User query:    "ESEA hate crimes"
Expanded:      ("ESEA" OR "East Asian" OR "Southeast Asian") AND ("hate crime" OR "racist incident" OR "racial attack" OR "racially motivated")
```

**Pros:**
- No local storage or index needed
- Works with existing API — just a smarter query builder
- Broadens recall for conceptual queries

**Cons:**
- Requires an LLM API call (or a local model) for expansion
- Risk of over-broadening — expanded terms may introduce noise
- Expansion quality depends on the model's knowledge of FOI domain terminology

**Implementation complexity:** Low
**New dependencies:** An LLM API (Anthropic/OpenAI) or a local synonym source

### 2.2 Result Re-ranking

**Idea:** Fetch results with keyword search, then re-rank using embedding cosine similarity against the original query.

```
1. foi search "ESEA hate crimes" → 50 keyword results
2. Embed query + each result's title/snippet
3. Re-rank by cosine similarity
4. Return top-N most semantically relevant
```

**Pros:**
- Improves precision within keyword results
- Can surface relevant results that keyword ranking buried
- Works as a transparent post-processing step

**Cons:**
- Recall is still bounded by keyword search — can't find what keywords missed
- Requires an embedding model (API or local)
- Adds latency (embedding computation per result)

**Implementation complexity:** Medium
**New dependencies:** Embedding model (API or `sentence-transformers` ~100MB local)

### 2.3 Local Semantic Index

**Idea:** Build a local vector store from previously fetched/cached FOI request data. Store embeddings in SQLite alongside the existing cache at `~/.config/open-foi/`.

```
1. User runs `foi search` or `foi fetch` → results cached
2. Background: embed titles + snippets + message bodies → store vectors
3. `foi semantic-search "concept"` → query the local vector index
```

**Pros:**
- True semantic search — finds conceptually related requests
- Works fully offline after initial fetch
- Reuses data already in the cache
- Could support cross-request discovery ("show me requests similar to this one")

**Cons:**
- Only searches previously fetched data — not the full WDTK corpus
- Requires an embedding model
- Storage overhead for vectors (~1.5KB per embedding at 384 dimensions)
- Needs an indexing step (could be lazy/background)

**Implementation complexity:** High
**New dependencies:** Embedding model, numpy or similar for cosine similarity

### 2.4 Hybrid: Expansion + Re-ranking

**Idea:** Combine approaches 2.1 and 2.2 for best recall and precision.

```
1. Expand query with LLM-generated synonyms
2. Fetch broader keyword results from WDTK
3. Re-rank results by semantic similarity to original query
4. Optionally index results locally for future semantic queries
```

**Pros:**
- Best of both worlds — broader recall + precise ranking
- Gracefully degrades (expansion alone still helps if re-ranking is skipped)

**Cons:**
- Most complex to implement
- Two model calls per search (expansion + embedding)
- Highest latency

**Implementation complexity:** High

---

## 3. Embedding Model Options

| Option | Size | Speed | Quality | Offline | Auth required |
|---|---|---|---|---|---|
| `all-MiniLM-L6-v2` (sentence-transformers) | ~80MB | Fast | Good | Yes | No |
| `all-mpnet-base-v2` (sentence-transformers) | ~420MB | Medium | Better | Yes | No |
| OpenAI `text-embedding-3-small` | API | Fast | Very good | No | Yes |
| Anthropic (via Claude) | API | Slower | Excellent | No | Yes |
| `fastembed` (ONNX-based) | ~50MB | Fast | Good | Yes | No |

For a CLI tool that should work without auth, **`all-MiniLM-L6-v2` via `sentence-transformers`** or **`fastembed`** are the most practical choices. Both run locally and need no API key.

---

## 4. Quick Wins Before Semantic Search

Before building semantic search, there's low-hanging fruit from Xapian's existing capabilities that we're not exposing:

1. **Expose AND operator** — `--all` flag to AND terms instead of OR
2. **Expose phrase search** — auto-quote multi-word queries or add `--phrase` flag
3. **Expose NEAR operator** — `--near` flag for proximity search
4. **Expose wildcards** — document that `discrim*` works in queries
5. **Add more prefix filters** — `variety:`, `request:`, `commented_by:`

These require zero new dependencies and would significantly improve search precision.

---

## 5. Recommended Path

```
Phase 0: Expose Xapian operators (no new deps, immediate value)
    ↓
Phase 1: Query expansion (single LLM call, big recall improvement)
    ↓
Phase 2: Result re-ranking (embeddings, precision improvement)
    ↓
Phase 3: Local semantic index (full offline semantic search)
```

Each phase is independently useful and builds on the previous one.

---

## 6. Open Questions

- Should semantic search require an API key, or must it work fully offline?
- Is the `[browser]` extra pattern a good model for a `[semantic]` extra?
- How much latency is acceptable for a CLI search command?
- Should we use the same SQLite cache DB for embeddings, or a separate store?
- Is there value in a `foi similar <url_title>` command that finds related requests?

---

## References

- [Xapian QueryParser Syntax](https://xapian.org/docs/queryparser.html)
- [Alaveteli acts_as_xapian source](https://github.com/mysociety/alaveteli/blob/develop/lib/acts_as_xapian/acts_as_xapian.rb)
- [Alaveteli InfoRequestEvent model](https://github.com/mysociety/alaveteli/blob/develop/app/models/info_request_event.rb)
- [acts_as_xapian wiki](https://github.com/frabcus/acts_as_xapian/wiki/)
- [WhatDoTheyKnow API page](https://www.whatdotheyknow.com/help/api)
- [sentence-transformers](https://www.sbert.net/)
- [fastembed](https://github.com/qdrant/fastembed)
