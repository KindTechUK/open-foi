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
