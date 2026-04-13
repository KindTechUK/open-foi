"""CLI integration tests using Click's CliRunner."""

import json

from click.testing import CliRunner
from unittest.mock import patch, MagicMock

from foi_cli.cli import cli
from tests.conftest import SAMPLE_FEED_EVENT, SAMPLE_FEED_EVENT_RESPONSE


def _mock_search_feed(query, page=1):
    """Return sample data on page 1, empty on page 2."""
    if page == 1:
        return [SAMPLE_FEED_EVENT, SAMPLE_FEED_EVENT_RESPONSE]
    return []


@patch("foi_cli.cli.WDTKClient")
@patch("foi_cli.cli.Cache")
def test_search_json_output(mock_cache_cls, mock_client_cls):
    mock_client = MagicMock()
    mock_client.search_feed = _mock_search_feed
    mock_client._cache = None
    mock_client_cls.return_value = mock_client
    mock_cache_cls.return_value = MagicMock()

    runner = CliRunner()
    result = runner.invoke(cli, ["search", "ESEA hate crimes"])
    assert result.exit_code == 0, result.output

    data = json.loads(result.output)
    assert data["total_requests"] == 1
    assert data["total_events"] == 2
    assert data["requests"][0]["authority"] == "Northamptonshire Police"
    assert len(data["requests"][0]["events"]) == 2


@patch("foi_cli.cli.WDTKClient")
@patch("foi_cli.cli.Cache")
def test_search_summary_output(mock_cache_cls, mock_client_cls):
    mock_client = MagicMock()
    mock_client.search_feed = _mock_search_feed
    mock_client._cache = None
    mock_client_cls.return_value = mock_client
    mock_cache_cls.return_value = MagicMock()

    runner = CliRunner()
    result = runner.invoke(cli, ["search", "ESEA", "--format", "summary"])
    assert result.exit_code == 0
    assert "Found 1 requests" in result.output
    assert "Northamptonshire Police" in result.output


@patch("foi_cli.cli.WDTKClient")
@patch("foi_cli.cli.Cache")
def test_search_csv_output(mock_cache_cls, mock_client_cls):
    mock_client = MagicMock()
    mock_client.search_feed = _mock_search_feed
    mock_client._cache = None
    mock_client_cls.return_value = mock_client
    mock_cache_cls.return_value = MagicMock()

    runner = CliRunner()
    result = runner.invoke(cli, ["search", "ESEA", "--format", "csv"])
    assert result.exit_code == 0
    assert "title" in result.output  # CSV header
    assert "Northamptonshire Police" in result.output


@patch("foi_cli.cli.WDTKClient")
@patch("foi_cli.cli.Cache")
def test_search_with_status_filter(mock_cache_cls, mock_client_cls):
    mock_client = MagicMock()
    mock_client.search_feed = MagicMock(side_effect=_mock_search_feed)
    mock_client._cache = None
    mock_client_cls.return_value = mock_client
    mock_cache_cls.return_value = MagicMock()

    runner = CliRunner()
    result = runner.invoke(cli, ["search", "ESEA", "--status", "successful"])
    assert result.exit_code == 0
    call_args = mock_client.search_feed.call_args_list[0]
    assert "latest_status:successful" in call_args[0][0]


@patch("foi_cli.cli.WDTKClient")
@patch("foi_cli.cli.Cache")
def test_fetch_missing_playwright(mock_cache_cls, mock_client_cls):
    """foi fetch should show a clean error when the runtime playwright import fails."""
    mock_client_cls.return_value = MagicMock()
    mock_cache_cls.return_value = MagicMock()

    runner = CliRunner()
    # Simulate the real failure: browser module imports fine, but fetch_request
    # raises ModuleNotFoundError when it tries `from playwright.sync_api import ...`
    with patch(
        "foi_cli.browser.fetch_request",
        side_effect=ModuleNotFoundError("No module named 'playwright'"),
    ):
        result = runner.invoke(cli, ["fetch", "some_request"])
    assert result.exit_code != 0
    assert "Playwright is required" in result.output
    assert "open-foi[browser]" in result.output


@patch("foi_cli.cli.WDTKClient")
@patch("foi_cli.cli.Cache")
def test_fetch_batch_partial_failure_exits_nonzero(mock_cache_cls, mock_client_cls):
    """Batch fetch should output results AND exit non-zero when some requests fail."""
    mock_client_cls.return_value = MagicMock()
    mock_cache_cls.return_value = MagicMock()

    partial_results = [
        {"url_title": "good_request", "url": "http://...", "correspondence": [], "attachments_downloaded": []},
        {"url_title": "bad_request", "error": "Timeout"},
    ]
    with patch("foi_cli.browser.fetch_batch", return_value=partial_results):
        runner = CliRunner()
        result = runner.invoke(cli, ["fetch", "good_request", "bad_request"])
    assert result.exit_code != 0
    # Output should still contain the JSON results
    assert "good_request" in result.output
    assert "bad_request" in result.output
    assert "1/2 requests failed" in result.output


# --- foi fetch --ext and --skip-images ---


@patch("foi_cli.cli.WDTKClient")
@patch("foi_cli.cli.Cache")
def test_fetch_passes_ext_filter(mock_cache_cls, mock_client_cls):
    """--ext flag should be parsed and passed to fetch_request."""
    mock_client_cls.return_value = MagicMock()
    mock_cache_cls.return_value = MagicMock()

    mock_result = {"url_title": "test", "url": "http://...", "correspondence": [], "attachments_downloaded": []}
    with patch("foi_cli.browser.fetch_request", return_value=mock_result) as mock_fetch:
        runner = CliRunner()
        result = runner.invoke(cli, ["fetch", "test_request", "--ext", "xlsx,csv"])
    assert result.exit_code == 0
    _, kwargs = mock_fetch.call_args
    assert kwargs["extensions"] == {"xlsx", "csv"}


@patch("foi_cli.cli.WDTKClient")
@patch("foi_cli.cli.Cache")
def test_fetch_passes_skip_images(mock_cache_cls, mock_client_cls):
    """--skip-images flag should be passed to fetch_request."""
    mock_client_cls.return_value = MagicMock()
    mock_cache_cls.return_value = MagicMock()

    mock_result = {"url_title": "test", "url": "http://...", "correspondence": [], "attachments_downloaded": []}
    with patch("foi_cli.browser.fetch_request", return_value=mock_result) as mock_fetch:
        runner = CliRunner()
        result = runner.invoke(cli, ["fetch", "test_request", "--skip-images"])
    assert result.exit_code == 0
    _, kwargs = mock_fetch.call_args
    assert kwargs["skip_images"] is True


# --- foi attachments ---


_SAMPLE_ATTACHMENTS_RESULT = {
    "url_title": "test_request",
    "url": "https://www.whatdotheyknow.com/request/test_request",
    "total_attachments": 2,
    "attachments": [
        {"filename": "data.xlsx", "url": "https://example.com/attach/1", "message_id": "100", "part": "2"},
        {"filename": "response.pdf", "url": "https://example.com/attach/2", "message_id": "100", "part": "3"},
    ],
}


@patch("foi_cli.cli.WDTKClient")
@patch("foi_cli.cli.Cache")
def test_attachments_json_output(mock_cache_cls, mock_client_cls):
    mock_client_cls.return_value = MagicMock()
    mock_cache_cls.return_value = MagicMock()

    with patch("foi_cli.browser.list_attachments", return_value=_SAMPLE_ATTACHMENTS_RESULT):
        runner = CliRunner()
        result = runner.invoke(cli, ["attachments", "test_request"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["total_attachments"] == 2
    assert data["attachments"][0]["filename"] == "data.xlsx"


@patch("foi_cli.cli.WDTKClient")
@patch("foi_cli.cli.Cache")
def test_attachments_summary_output(mock_cache_cls, mock_client_cls):
    mock_client_cls.return_value = MagicMock()
    mock_cache_cls.return_value = MagicMock()

    with patch("foi_cli.browser.list_attachments", return_value=_SAMPLE_ATTACHMENTS_RESULT):
        runner = CliRunner()
        result = runner.invoke(cli, ["attachments", "test_request", "--format", "summary"])
    assert result.exit_code == 0
    assert "test_request" in result.output
    assert "data.xlsx" in result.output
    assert "Message 100" in result.output


@patch("foi_cli.cli.WDTKClient")
@patch("foi_cli.cli.Cache")
def test_attachments_csv_output(mock_cache_cls, mock_client_cls):
    mock_client_cls.return_value = MagicMock()
    mock_cache_cls.return_value = MagicMock()

    with patch("foi_cli.browser.list_attachments", return_value=_SAMPLE_ATTACHMENTS_RESULT):
        runner = CliRunner()
        result = runner.invoke(cli, ["attachments", "test_request", "--format", "csv"])
    assert result.exit_code == 0
    assert "filename" in result.output  # header
    assert "data.xlsx" in result.output
    assert ".xlsx" in result.output


@patch("foi_cli.cli.WDTKClient")
@patch("foi_cli.cli.Cache")
def test_attachments_passes_filters(mock_cache_cls, mock_client_cls):
    mock_client_cls.return_value = MagicMock()
    mock_cache_cls.return_value = MagicMock()

    with patch("foi_cli.browser.list_attachments", return_value=_SAMPLE_ATTACHMENTS_RESULT) as mock_list:
        runner = CliRunner()
        result = runner.invoke(cli, ["attachments", "test_request", "--ext", "xlsx", "--skip-images"])
    assert result.exit_code == 0
    _, kwargs = mock_list.call_args
    assert kwargs["extensions"] == {"xlsx"}
    assert kwargs["skip_images"] is True


@patch("foi_cli.cli.WDTKClient")
@patch("foi_cli.cli.Cache")
def test_attachments_missing_playwright(mock_cache_cls, mock_client_cls):
    mock_client_cls.return_value = MagicMock()
    mock_cache_cls.return_value = MagicMock()

    with patch(
        "foi_cli.browser.list_attachments",
        side_effect=ModuleNotFoundError("No module named 'playwright'"),
    ):
        runner = CliRunner()
        result = runner.invoke(cli, ["attachments", "some_request"])
    assert result.exit_code != 0
    assert "Playwright is required" in result.output
