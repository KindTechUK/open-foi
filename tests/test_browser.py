"""Tests for browser module helpers."""

from unittest.mock import MagicMock

from foi_cli.browser import _is_html_attachment, _parse_content_disposition_filename


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
