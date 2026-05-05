"""Output formatting: JSON, CSV, summary text, and file export."""

import csv
import io
import json
import sys
from pathlib import Path

from foi_cli.models import SearchResult


def format_json(result: SearchResult) -> str:
    return result.model_dump_json(indent=2)


def format_summary(result: SearchResult) -> str:
    lines = [f"Found {result.total_requests} requests ({result.total_events} events, {result.pages_fetched} pages)\n"]
    for i, req in enumerate(result.requests, 1):
        lines.append(f"  {i}. {req.title}")
        lines.append(f"     Authority: {req.authority} | Status: {req.status} | Days: {req.total_days}")
        lines.append(f"     {req.url}")
        lines.append("")
    return "\n".join(lines)


def format_csv(result: SearchResult) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "title", "url_title", "url", "authority", "authority_url_name",
        "requester", "status", "created_at", "updated_at", "total_days", "event_count",
    ])
    for req in result.requests:
        writer.writerow([
            req.title, req.url_title, req.url, req.authority, req.authority_url_name,
            req.requester, req.status, req.created_at, req.updated_at, req.total_days,
            len(req.events),
        ])
    return buf.getvalue()


def format_authorities_csv(csv_text: str) -> str:
    return csv_text


def format_authorities_json(csv_text: str) -> str:
    reader = csv.DictReader(io.StringIO(csv_text))
    rows = list(reader)
    return json.dumps(rows, indent=2)


def write_output(content: str, output_path: str | None = None) -> None:
    if output_path:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    else:
        sys.stdout.write(content)
        if not content.endswith("\n"):
            sys.stdout.write("\n")


def detect_format_from_path(path: str) -> str:
    suffix = Path(path).suffix.lower()
    return {".csv": "csv", ".json": "json", ".txt": "summary"}.get(suffix, "json")
