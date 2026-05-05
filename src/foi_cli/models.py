"""Pydantic models for WhatDoTheyKnow feed API responses and CLI output."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


# --- API models (match raw feed JSON structure) ---


class User(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    url_name: str
    name: str
    ban_text: str | None = ""
    about_me: str | None = ""


class PublicBodyInfo(BaseModel):
    model_config = ConfigDict(extra="ignore")

    requests_count: int = 0
    requests_successful_count: int = 0
    requests_not_held_count: int = 0
    requests_overdue_count: int = 0
    requests_visible_classified_count: int = 0


class PublicBody(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    url_name: str
    name: str
    short_name: str | None = ""
    created_at: datetime | None = None
    updated_at: datetime | None = None
    home_page: str | None = ""
    notes: str | None = ""
    publication_scheme: str | None = ""
    disclosure_log: str | None = ""
    tags: list = Field(default_factory=list)
    info: PublicBodyInfo = Field(default_factory=PublicBodyInfo)


class InfoRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    url_title: str
    title: str
    created_at: datetime
    updated_at: datetime
    described_state: str
    display_status: str
    awaiting_description: bool = False
    prominence: str = "normal"
    law_used: str = "foi"
    tags: list = Field(default_factory=list)


class FeedEvent(BaseModel):
    """Raw event from the /feed/search/*.json endpoint."""

    model_config = ConfigDict(extra="ignore")

    id: int
    event_type: str
    created_at: datetime
    described_state: str | None = None
    calculated_state: str | None = None
    last_described_at: datetime | None = None
    display_status: str | None = ""
    snippet: str | None = ""
    incoming_message_id: int | None = None
    outgoing_message_id: int | None = None
    comment_id: int | None = None
    info_request: InfoRequest
    public_body: PublicBody
    user: User


# --- Output models (CLI-facing, with computed fields) ---


class EventSummary(BaseModel):
    """A single event within a request, with time delta."""

    id: int
    type: str
    date: str  # ISO date string
    status: str | None = None
    snippet: str = ""
    days_since_previous: int | None = None


class RequestResult(BaseModel):
    """A deduplicated FOI request with nested event timeline."""

    title: str
    url_title: str
    url: str
    authority: str
    authority_url_name: str
    requester: str
    status: str
    created_at: str  # ISO date string
    updated_at: str  # ISO date string
    total_days: int
    events: list[EventSummary]


class SearchResult(BaseModel):
    """Top-level search result container."""

    query: str
    total_requests: int
    total_events: int
    pages_fetched: int
    requests: list[RequestResult]


# --- Browser fetch output models ---


class Attachment(BaseModel):
    """A single attachment from a correspondence message."""

    url: str
    filename: str
    message_id: str
    part: str
    local_path: str | None = None


class CorrespondenceMessage(BaseModel):
    """A single outgoing or incoming message on a request page."""

    id: str  # e.g. "incoming-3236066" or "outgoing-12345"
    direction: str  # "incoming" or "outgoing"
    author: str
    date: str
    body: str
    attachments: list[Attachment] = Field(default_factory=list)


class FetchResult(BaseModel):
    """Result of fetching a single FOI request page."""

    url_title: str
    url: str
    output_dir: str
    correspondence: list[CorrespondenceMessage]
    attachments_downloaded: list[str] = Field(default_factory=list)
    error: str | None = None
