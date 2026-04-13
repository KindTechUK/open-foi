"""Tests for browser module helpers."""

from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest

from foi_cli.browser import (
    _download_attachment,
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


# --- _download_attachment ---


def _make_link(filename="data.xlsx", url="https://example.com/attach/2/data.xlsx"):
    return {"filename": filename, "url": url, "message_id": "100", "part": "2"}


def _mock_api_response(ok=True, status=200, content_type="application/octet-stream", body=b"filedata"):
    resp = MagicMock()
    resp.ok = ok
    resp.status = status
    resp.headers = {"content-type": content_type}
    resp.body.return_value = body
    return resp


def test_download_attachment_api_success(tmp_path):
    """Primary path: page.request.get() succeeds, file is written."""
    page = MagicMock()
    page.request.get.return_value = _mock_api_response(ok=True, body=b"spreadsheet data")

    link = _make_link()
    result = _download_attachment(page, link, tmp_path)

    assert result.exists()
    assert result.read_bytes() == b"spreadsheet data"
    assert "data.xlsx" in result.name
    page.context.new_page.assert_not_called()


def test_download_attachment_403_falls_back_to_browser(tmp_path):
    """API returns 403, fallback opens new page and uses expect_download."""
    page = MagicMock()
    page.request.get.return_value = _mock_api_response(ok=False, status=403)

    # Mock the fallback page and download
    dl_page = MagicMock()
    page.context.new_page.return_value = dl_page
    mock_download = MagicMock()

    @contextmanager
    def fake_expect_download(timeout=30000):
        holder = MagicMock()
        holder.value = mock_download
        yield holder

    dl_page.expect_download = fake_expect_download

    link = _make_link()
    filepath = _download_attachment(page, link, tmp_path)

    page.context.new_page.assert_called_once()
    dl_page.goto.assert_called_once_with(link["url"], timeout=30000)
    mock_download.save_as.assert_called_once_with(str(filepath))
    dl_page.close.assert_called_once()


def test_download_attachment_html_challenge_falls_back(tmp_path):
    """API returns 200 but with HTML challenge page (not a real HTML attachment)."""
    page = MagicMock()
    page.request.get.return_value = _mock_api_response(
        ok=True, content_type="text/html", body=b"<html>Just a moment...</html>"
    )

    dl_page = MagicMock()
    page.context.new_page.return_value = dl_page
    mock_download = MagicMock()

    @contextmanager
    def fake_expect_download(timeout=30000):
        holder = MagicMock()
        holder.value = mock_download
        yield holder

    dl_page.expect_download = fake_expect_download

    link = _make_link()
    _download_attachment(page, link, tmp_path)

    page.context.new_page.assert_called_once()
    mock_download.save_as.assert_called_once()
    dl_page.close.assert_called_once()


def test_download_attachment_both_fail_raises(tmp_path):
    """Both API request and browser fallback fail — RuntimeError raised."""
    page = MagicMock()
    page.request.get.return_value = _mock_api_response(ok=False, status=403)

    dl_page = MagicMock()
    page.context.new_page.return_value = dl_page

    @contextmanager
    def fake_expect_download(timeout=30000):
        raise TimeoutError("Download timed out")
        yield  # unreachable, needed for generator syntax

    dl_page.expect_download = fake_expect_download

    link = _make_link()
    with pytest.raises(RuntimeError, match="Both API request and browser download failed"):
        _download_attachment(page, link, tmp_path)

    dl_page.close.assert_called_once()


def test_download_attachment_api_exception_falls_back(tmp_path):
    """API request raises an exception, fallback is attempted."""
    page = MagicMock()
    page.request.get.side_effect = ConnectionError("network down")

    dl_page = MagicMock()
    page.context.new_page.return_value = dl_page
    mock_download = MagicMock()

    @contextmanager
    def fake_expect_download(timeout=30000):
        holder = MagicMock()
        holder.value = mock_download
        yield holder

    dl_page.expect_download = fake_expect_download

    link = _make_link()
    _download_attachment(page, link, tmp_path)

    page.context.new_page.assert_called_once()
    mock_download.save_as.assert_called_once()
