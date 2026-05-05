"""Fetch all ESEA hate crime FOI requests across every wave and save for later attachment processing.

Searches WDTK for "ESEA hate crimes" and writes a JSON manifest of every successful or
partially-successful request. The FOI campaign has been run annually since 2022, so a
given force may have 2–4 separate requests on WDTK — this manifest covers all of them.

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


def filter_responsive(requests: dict[str, dict]) -> list[dict]:
    """Keep requests with a data-bearing status across all campaign waves.

    Earlier versions of this script filtered to the 2025 wave only and missed
    ~100 FOI threads from 2022/2023/2024 waves, some of which were the only
    successful response for a given force (e.g. Northumbria's 2025 thread
    had no attachments but its 2023 and 2022 threads did).
    """
    filtered = [
        r for r in requests.values()
        if r["status"] in ("successful", "partially_successful")
    ]
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
        filtered = filter_responsive(requests)
    finally:
        client.close()

    # Summary by status
    status_counts: dict[str, int] = {}
    for r in filtered:
        status_counts[r["status"]] = status_counts.get(r["status"], 0) + 1

    manifest = {
        "query": QUERY,
        "filter": "status in (successful, partially_successful) across all campaign waves",
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
