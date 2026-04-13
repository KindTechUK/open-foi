"""Fetch all ESEA hate crime FOI requests related to 2025 and save for later attachment processing.

Searches WDTK for "ESEA hate crimes", filters to requests created in 2025 or with "2025" in the
title, and writes a JSON manifest of matching requests with their authority and status info.

Usage:
    python examples/esea_hatecrime_2025.py
    python examples/esea_hatecrime_2025.py --output results.json
"""

import json
import logging
import sys
from pathlib import Path

from foi_cli.client import WDTKClient
from foi_cli.models import FeedEvent

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s", stream=sys.stderr)
logger = logging.getLogger(__name__)

QUERY = "ESEA hate crimes"
OUTPUT_DEFAULT = Path("examples/esea_hatecrime_2025_requests.json")


def fetch_all_events(client: WDTKClient, query: str) -> list[dict]:
    """Paginate through all feed results for a query."""
    all_events = []
    page = 1
    while True:
        logger.info("Fetching page %d ...", page)
        raw = client.search_feed(query, page=page)
        if not raw:
            break
        all_events.extend(raw)
        page += 1
    logger.info("Fetched %d total events across %d pages", len(all_events), page - 1)
    return all_events


def deduplicate_requests(events: list[dict]) -> dict[str, dict]:
    """Group events by request url_title, keep the most recent event's metadata per request."""
    requests: dict[str, dict] = {}
    for event in events:
        url_title = event["info_request"]["url_title"]
        if url_title not in requests or event["created_at"] > requests[url_title]["_latest_event_at"]:
            info = event["info_request"]
            body = event["public_body"]
            requests[url_title] = {
                "url_title": url_title,
                "title": info["title"],
                "url": f"https://www.whatdotheyknow.com/request/{url_title}",
                "authority": body["name"],
                "authority_url_name": body["url_name"],
                "status": info["described_state"],
                "created_at": info["created_at"],
                "updated_at": info["updated_at"],
                "_latest_event_at": event["created_at"],
            }
    # Drop internal field
    for r in requests.values():
        del r["_latest_event_at"]
    return requests


def filter_2025(requests: dict[str, dict]) -> list[dict]:
    """Keep requests created in 2025 or with '2025' in the title."""
    filtered = []
    for r in requests.values():
        created_year = r["created_at"][:4]
        if created_year == "2025" or "2025" in r["title"]:
            filtered.append(r)
    filtered.sort(key=lambda r: (r["created_at"], r["url_title"]))
    return filtered


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Fetch ESEA hate crime 2025 FOI requests")
    parser.add_argument("--output", "-o", type=Path, default=OUTPUT_DEFAULT)
    args = parser.parse_args()

    client = WDTKClient()
    try:
        events = fetch_all_events(client, QUERY)
        requests = deduplicate_requests(events)
        filtered = filter_2025(requests)
    finally:
        client.close()

    # Summary by status
    status_counts: dict[str, int] = {}
    for r in filtered:
        status_counts[r["status"]] = status_counts.get(r["status"], 0) + 1

    manifest = {
        "query": QUERY,
        "filter": "created_at starts with 2025 OR title contains '2025'",
        "total_requests": len(filtered),
        "status_breakdown": status_counts,
        "requests": filtered,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2) + "\n")
    logger.info("Wrote %d requests to %s", len(filtered), args.output)

    # Print summary to stdout
    print(f"\n{'='*70}")
    print(f"ESEA Hate Crime FOI Requests — 2025")
    print(f"{'='*70}")
    print(f"Total matching requests: {len(filtered)}")
    print(f"Status breakdown:")
    for status, count in sorted(status_counts.items(), key=lambda x: -x[1]):
        print(f"  {status:30s} {count:3d}")
    print(f"\nAuthorities covered: {len(set(r['authority'] for r in filtered))}")
    print(f"Output: {args.output}")


if __name__ == "__main__":
    main()
