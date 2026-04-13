"""Tests for browser module helpers."""

from foi_cli.browser import (
    _filter_attachment_links,
    _is_html_attachment,
    _parse_content_disposition_filename,
)


class _FakeResponse:
    def __init__(self, headers: dict):
        self.headers = headers


# --- _parse_content_disposition_filename ---


def test_parse_plain_filename():
    assert _parse_content_disposition_filename('attachment; filename="report.html"') == "report.html"


def test_parse_plain_filename_unquoted():
    assert _parse_content_disposition_filename("attachment; filename=report.pdf") == "report.pdf"


def test_parse_rfc5987_filename_star():
    header = "attachment; filename*=UTF-8''report%20data.html"
    assert _parse_content_disposition_filename(header) == "report data.html"


def test_parse_rfc5987_url_encoded():
    header = "attachment; filename*=UTF-8''esea%2Fhate%20crimes.htm"
    assert _parse_content_disposition_filename(header) == "esea/hate crimes.htm"


def test_parse_both_prefers_star():
    header = "attachment; filename=\"fallback.txt\"; filename*=UTF-8''real%20name.html"
    assert _parse_content_disposition_filename(header) == "real name.html"


def test_parse_no_filename():
    assert _parse_content_disposition_filename("attachment") is None


def test_parse_empty():
    assert _parse_content_disposition_filename("") is None


# --- _is_html_attachment ---


def test_html_from_content_disposition_plain():
    resp = _FakeResponse({"content-disposition": 'attachment; filename="page.html"'})
    assert _is_html_attachment("https://example.com/attach/1/data", resp) is True


def test_html_from_content_disposition_rfc5987():
    resp = _FakeResponse({"content-disposition": "attachment; filename*=UTF-8''report.html"})
    assert _is_html_attachment("https://example.com/attach/1/data.pdf", resp) is True


def test_non_html_from_content_disposition():
    resp = _FakeResponse({"content-disposition": 'attachment; filename="data.xlsx"'})
    assert _is_html_attachment("https://example.com/attach/1/data.xlsx", resp) is False


def test_html_from_url_fallback():
    resp = _FakeResponse({})
    assert _is_html_attachment("https://example.com/attach/1/response.htm", resp) is True


def test_non_html_from_url_fallback():
    resp = _FakeResponse({})
    assert _is_html_attachment("https://example.com/attach/1/report.pdf", resp) is False


def test_url_with_query_params():
    resp = _FakeResponse({})
    assert _is_html_attachment("https://example.com/attach/1/page.html?cookie_passthrough=1", resp) is True


# --- _filter_attachment_links ---

_SAMPLE_LINKS = [
    {"filename": "data.xlsx", "url": "https://example.com/attach/1", "message_id": "1", "part": "2"},
    {"filename": "letter.pdf", "url": "https://example.com/attach/2", "message_id": "1", "part": "3"},
    {"filename": "image001.png", "url": "https://example.com/attach/3", "message_id": "1", "part": "4"},
    {"filename": "photo.jpg", "url": "https://example.com/attach/4", "message_id": "1", "part": "5"},
    {"filename": "report.csv", "url": "https://example.com/attach/5", "message_id": "2", "part": "2"},
]


def test_filter_no_filters_returns_all():
    result = _filter_attachment_links(_SAMPLE_LINKS)
    assert len(result) == 5


def test_filter_by_extension_whitelist():
    result = _filter_attachment_links(_SAMPLE_LINKS, extensions={"xlsx", "csv"})
    assert len(result) == 2
    assert {r["filename"] for r in result} == {"data.xlsx", "report.csv"}


def test_filter_skip_images():
    result = _filter_attachment_links(_SAMPLE_LINKS, skip_images=True)
    assert len(result) == 3
    assert {r["filename"] for r in result} == {"data.xlsx", "letter.pdf", "report.csv"}


def test_filter_whitelist_and_skip_images():
    result = _filter_attachment_links(_SAMPLE_LINKS, extensions={"pdf", "png"}, skip_images=True)
    assert len(result) == 1
    assert result[0]["filename"] == "letter.pdf"


def test_filter_extension_without_dot():
    """Extensions should be provided without dots."""
    result = _filter_attachment_links(_SAMPLE_LINKS, extensions={"xlsx"})
    assert len(result) == 1
    assert result[0]["filename"] == "data.xlsx"


def test_filter_file_without_extension():
    links = [{"filename": "README", "url": "https://example.com/attach/1", "message_id": "1", "part": "2"}]
    result = _filter_attachment_links(links, extensions={"pdf"})
    assert len(result) == 0
    result_no_filter = _filter_attachment_links(links, skip_images=True)
    assert len(result_no_filter) == 1
