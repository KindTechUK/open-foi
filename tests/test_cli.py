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
