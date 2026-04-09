"""Tests for search query building and aggregation logic."""

from foi_cli.search import build_query, _parse_events, _aggregate_requests


def test_build_query_simple():
    assert build_query("ESEA hate crimes") == "ESEA hate crimes"


def test_build_query_with_status():
    q = build_query("ESEA", status="successful")
    assert q == "ESEA latest_status:successful"


def test_build_query_with_all_filters():
    q = build_query(
        "hate crimes",
        status="rejected",
        authority="kent_police",
        user="a_wong",
        filetype="pdf",
        tag="police",
    )
    assert "hate crimes" in q
    assert "latest_status:rejected" in q
    assert "requested_from:kent_police" in q
    assert "requested_by:a_wong" in q
    assert "filetype:pdf" in q
    assert "tag:police" in q


def test_parse_events(sample_event, sample_event_response):
    events = _parse_events([sample_event, sample_event_response])
    assert len(events) == 2
    assert events[0].event_type == "sent"
    assert events[1].event_type == "response"


def test_parse_events_skips_malformed():
    events = _parse_events([{"bad": "data"}, {"also": "bad"}])
    assert len(events) == 0


def test_aggregate_deduplicates(sample_event, sample_event_response):
    events = _parse_events([sample_event, sample_event_response])
    result = _aggregate_requests(events, "test query", 1)
    assert result.total_requests == 1
    assert result.total_events == 2
    assert result.requests[0].url_title == "east_and_southeast_asian_esea_ha_63"


def test_aggregate_computes_time_deltas(sample_event, sample_event_response):
    events = _parse_events([sample_event, sample_event_response])
    result = _aggregate_requests(events, "test", 1)
    req = result.requests[0]
    assert req.events[0].days_since_previous is None  # first event
    assert req.events[1].days_since_previous > 0  # response came later
    assert req.total_days > 0


def test_aggregate_event_order(sample_event, sample_event_response):
    # Pass events in reverse order — should still sort chronologically
    events = _parse_events([sample_event_response, sample_event])
    result = _aggregate_requests(events, "test", 1)
    req = result.requests[0]
    assert req.events[0].type == "sent"
    assert req.events[1].type == "response"


def test_aggregate_dedup_event_ids(sample_event):
    # Same event appearing twice (e.g., from overlapping pages)
    events = _parse_events([sample_event, sample_event])
    result = _aggregate_requests(events, "test", 2)
    assert result.total_events == 1
    assert len(result.requests[0].events) == 1
