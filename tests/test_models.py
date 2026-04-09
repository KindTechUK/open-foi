"""Tests for Pydantic model parsing."""

from foi_cli.models import FeedEvent, InfoRequest, PublicBody, User


def test_parse_feed_event(sample_event):
    event = FeedEvent.model_validate(sample_event)
    assert event.id == 12345
    assert event.event_type == "sent"
    assert event.info_request.url_title == "east_and_southeast_asian_esea_ha_63"
    assert event.public_body.name == "Northamptonshire Police"
    assert event.user.name == "A Wong"


def test_parse_feed_event_ignores_extra_fields(sample_event):
    sample_event["unknown_field"] = "should be ignored"
    sample_event["info_request"]["also_unknown"] = True
    event = FeedEvent.model_validate(sample_event)
    assert event.id == 12345


def test_parse_event_with_null_states(sample_event):
    sample_event["described_state"] = None
    sample_event["calculated_state"] = None
    event = FeedEvent.model_validate(sample_event)
    assert event.described_state is None
    assert event.calculated_state is None


def test_info_request_dates(sample_event):
    event = FeedEvent.model_validate(sample_event)
    req = event.info_request
    assert req.created_at.year == 2025
    assert req.updated_at.month == 12


def test_public_body_info(sample_event):
    event = FeedEvent.model_validate(sample_event)
    info = event.public_body.info
    assert info.requests_count == 500
    assert info.requests_successful_count == 200
