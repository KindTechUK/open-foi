"""Search query builder, paginated aggregation, and time delta computation."""

import logging
from collections import defaultdict

from pydantic import ValidationError

from foi_cli.client import WDTKClient
from foi_cli.models import (
    EventSummary,
    FeedEvent,
    RequestResult,
    SearchResult,
)

logger = logging.getLogger(__name__)

BASE_URL = "https://www.whatdotheyknow.com"


def build_query(
    terms: str,
    status: str | None = None,
    authority: str | None = None,
    user: str | None = None,
    filetype: str | None = None,
    tag: str | None = None,
) -> str:
    parts = [terms]
    if status:
        parts.append(f"latest_status:{status}")
    if authority:
        parts.append(f"requested_from:{authority}")
    if user:
        parts.append(f"requested_by:{user}")
    if filetype:
        parts.append(f"filetype:{filetype}")
    if tag:
        parts.append(f"tag:{tag}")
    return " ".join(parts)


def _parse_events(raw_events: list[dict]) -> list[FeedEvent]:
    events = []
    for raw in raw_events:
        try:
            events.append(FeedEvent.model_validate(raw))
        except ValidationError as e:
            logger.warning("Skipping malformed event: %s", e)
    return events


def _aggregate_requests(events: list[FeedEvent], query: str, pages: int) -> SearchResult:
    grouped: dict[str, list[FeedEvent]] = defaultdict(list)
    seen_event_ids: set[int] = set()

    for event in events:
        if event.id in seen_event_ids:
            continue
        seen_event_ids.add(event.id)
        grouped[event.info_request.url_title].append(event)

    results: list[RequestResult] = []
    for url_title, req_events in grouped.items():
        req_events.sort(key=lambda e: e.created_at)
        info = req_events[-1].info_request
        body = req_events[-1].public_body
        user = req_events[-1].user

        event_summaries: list[EventSummary] = []
        for i, ev in enumerate(req_events):
            days_since = None
            if i > 0:
                delta = ev.created_at - req_events[i - 1].created_at
                days_since = delta.days

            event_summaries.append(
                EventSummary(
                    id=ev.id,
                    type=ev.event_type,
                    date=ev.created_at.strftime("%Y-%m-%d"),
                    status=ev.described_state or ev.calculated_state,
                    snippet=ev.snippet,
                    days_since_previous=days_since,
                )
            )

        first_date = req_events[0].created_at
        last_date = req_events[-1].created_at
        total_days = (last_date - first_date).days

        results.append(
            RequestResult(
                title=info.title,
                url_title=info.url_title,
                url=f"{BASE_URL}/request/{info.url_title}",
                authority=body.name,
                authority_url_name=body.url_name,
                requester=user.name,
                status=info.described_state,
                created_at=info.created_at.strftime("%Y-%m-%d"),
                updated_at=info.updated_at.strftime("%Y-%m-%d"),
                total_days=total_days,
                events=event_summaries,
            )
        )

    results.sort(key=lambda r: r.updated_at, reverse=True)

    return SearchResult(
        query=query,
        total_requests=len(results),
        total_events=len(seen_event_ids),
        pages_fetched=pages,
        requests=results,
    )


def search_all(client: WDTKClient, query: str, max_pages: int = 20) -> SearchResult:
    all_events: list[FeedEvent] = []
    page = 1

    while page <= max_pages:
        logger.info("Fetching page %d for query: %s", page, query)
        raw = client.search_feed(query, page=page)
        if not raw:
            break
        parsed = _parse_events(raw)
        all_events.extend(parsed)
        page += 1

    return _aggregate_requests(all_events, query, page - 1)
