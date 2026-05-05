"""Shared test fixtures."""

import json

import pytest


SAMPLE_FEED_EVENT = {
    "id": 12345,
    "event_type": "sent",
    "created_at": "2025-06-05T02:16:22+01:00",
    "described_state": "waiting_response",
    "calculated_state": "waiting_response",
    "last_described_at": "2025-06-05T02:16:22+01:00",
    "display_status": "Awaiting response.",
    "snippet": "Dear FOI Officer, I would like to request...",
    "incoming_message_id": None,
    "outgoing_message_id": 101,
    "comment_id": None,
    "info_request": {
        "id": 999,
        "url_title": "east_and_southeast_asian_esea_ha_63",
        "title": "East and Southeast Asian (ESEA) Hate Crimes/Incidents Data 2020-25",
        "created_at": "2025-06-05T02:16:22+01:00",
        "updated_at": "2025-12-09T10:30:00+00:00",
        "described_state": "successful",
        "display_status": "Successful.",
        "awaiting_description": False,
        "prominence": "normal",
        "law_used": "foi",
        "tags": [],
    },
    "public_body": {
        "id": 50,
        "url_name": "northamptonshire_police",
        "name": "Northamptonshire Police",
        "short_name": "",
        "created_at": "2010-01-01T00:00:00+00:00",
        "updated_at": "2020-01-01T00:00:00+00:00",
        "home_page": "https://www.northants.police.uk",
        "notes": "",
        "publication_scheme": "",
        "disclosure_log": "",
        "tags": [],
        "info": {
            "requests_count": 500,
            "requests_successful_count": 200,
            "requests_not_held_count": 50,
            "requests_overdue_count": 10,
            "requests_visible_classified_count": 450,
        },
    },
    "user": {
        "id": 77,
        "url_name": "a_wong",
        "name": "A Wong",
        "ban_text": "",
        "about_me": "",
    },
}

SAMPLE_FEED_EVENT_RESPONSE = {
    **SAMPLE_FEED_EVENT,
    "id": 12346,
    "event_type": "response",
    "created_at": "2025-12-09T10:30:00+00:00",
    "described_state": "successful",
    "calculated_state": "successful",
    "display_status": "Successful.",
    "snippet": "Good morning RE: FREEDOM OF INFORMATION ACT 2000...",
    "incoming_message_id": 201,
    "outgoing_message_id": None,
}


@pytest.fixture
def sample_event():
    return SAMPLE_FEED_EVENT.copy()


@pytest.fixture
def sample_event_response():
    return SAMPLE_FEED_EVENT_RESPONSE.copy()


@pytest.fixture
def sample_feed_page(sample_event, sample_event_response):
    return [sample_event, sample_event_response]


@pytest.fixture
def sample_feed_page_json(sample_feed_page):
    return json.dumps(sample_feed_page)
