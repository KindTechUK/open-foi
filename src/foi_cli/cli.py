"""CLI entry point for open-foi."""

import logging
import sys

import click

from foi_cli.cache import Cache
from foi_cli.client import WDTKClient, WDTKError
from foi_cli.config import load_config
from foi_cli.output import (
    detect_format_from_path,
    format_authorities_csv,
    format_authorities_json,
    format_csv,
    format_json,
    format_summary,
    write_output,
)
from foi_cli.search import build_query, search_all


@click.group()
@click.option("--verbose", "-v", is_flag=True, help="Enable debug logging.")
@click.pass_context
def cli(ctx, verbose):
    """FOI CLI — search and fetch Freedom of Information requests from WhatDoTheyKnow."""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.WARNING,
        format="%(levelname)s: %(message)s",
        stream=sys.stderr,
    )
    ctx.ensure_object(dict)
    config = load_config()
    cache = Cache() if config.cache.enabled else None
    ctx.obj["config"] = config
    ctx.obj["cache"] = cache
    ctx.obj["client"] = WDTKClient(config=config, cache=cache)


@cli.command()
@click.argument("query")
@click.option("--status", default=None, help="Filter by latest_status (e.g., successful, rejected).")
@click.option("--authority", default=None, help="Filter by authority url_name.")
@click.option("--user", default=None, help="Filter by requester url_name.")
@click.option("--filetype", default=None, help="Filter by attachment type (e.g., pdf, xlsx).")
@click.option("--tag", default=None, help="Filter by request tag.")
@click.option("--max-pages", default=20, type=int, help="Max feed pages to fetch (default: 20).")
@click.option("--format", "fmt", type=click.Choice(["json", "summary", "csv"]), default=None, help="Output format.")
@click.option("--output", "output_path", default=None, help="Write to file (format from extension).")
@click.option("--no-cache", is_flag=True, help="Bypass cache for this request.")
@click.pass_context
def search(ctx, query, status, authority, user, filetype, tag, max_pages, fmt, output_path, no_cache):
    """Search FOI requests on WhatDoTheyKnow."""
    client: WDTKClient = ctx.obj["client"]
    if no_cache:
        client._cache = None

    full_query = build_query(query, status=status, authority=authority, user=user, filetype=filetype, tag=tag)

    try:
        result = search_all(client, full_query, max_pages=max_pages)
    except WDTKError as e:
        raise click.ClickException(str(e))

    if output_path and fmt is None:
        fmt = detect_format_from_path(output_path)
    fmt = fmt or "json"

    if fmt == "json":
        content = format_json(result)
    elif fmt == "summary":
        content = format_summary(result)
    elif fmt == "csv":
        content = format_csv(result)
    else:
        content = format_json(result)

    write_output(content, output_path)


def _parse_extensions(ext: str | None) -> set[str] | None:
    """Parse comma-separated extension string into a set."""
    if not ext:
        return None
    return {e.strip().lower().lstrip(".") for e in ext.split(",")}


@cli.command()
@click.argument("url_titles", nargs=-1, required=True)
@click.option("--output-dir", default=None, help="Base directory for fetched data (default: ./foi-data).")
@click.option("--attachments/--no-attachments", default=True, help="Download attachments.")
@click.option("--ext", default=None, help="Only download these extensions (comma-separated, e.g. xlsx,csv,pdf).")
@click.option("--skip-images", is_flag=True, help="Exclude image attachments (png, jpg, gif, etc.).")
@click.pass_context
def fetch(ctx, url_titles, output_dir, attachments, ext, skip_images):
    """Fetch full content and attachments for FOI request(s) (requires playwright).

    Pass one or more request URL titles. Multiple titles use a shared browser session.
    """
    config = ctx.obj["config"]
    output_dir = output_dir or config.fetch_output_dir
    extensions = _parse_extensions(ext)

    try:
        from foi_cli.browser import fetch_request, fetch_batch
        if len(url_titles) == 1:
            result = fetch_request(
                url_titles[0], output_dir=output_dir, download_attachments=attachments,
                extensions=extensions, skip_images=skip_images,
            )
            write_output(format_json_raw(result))
        else:
            results = fetch_batch(
                list(url_titles), output_dir=output_dir, download_attachments=attachments,
                extensions=extensions, skip_images=skip_images,
            )
            failures = [r for r in results if "error" in r]
            write_output(format_json_raw(results))
            if failures:
                raise click.ClickException(
                    f"{len(failures)}/{len(results)} requests failed. "
                    "See output for details."
                )
    except ModuleNotFoundError:
        raise click.ClickException(
            "Playwright is required for `foi fetch`.\n"
            "Install with: pip install open-foi[browser]\n"
            "Then run: playwright install chromium"
        )
    except click.ClickException:
        raise
    except Exception as e:
        raise click.ClickException(str(e))


@cli.command()
@click.argument("url_title")
@click.option("--ext", default=None, help="Only show these extensions (comma-separated, e.g. xlsx,csv,pdf).")
@click.option("--skip-images", is_flag=True, help="Exclude image attachments (png, jpg, gif, etc.).")
@click.option("--format", "fmt", type=click.Choice(["json", "summary", "csv"]), default=None, help="Output format.")
@click.option("--output", "output_path", default=None, help="Write to file (format from extension).")
@click.pass_context
def attachments(ctx, url_title, ext, skip_images, fmt, output_path):
    """List attachments for a FOI request without downloading (requires playwright)."""
    extensions = _parse_extensions(ext)

    try:
        from foi_cli.browser import list_attachments
        result = list_attachments(
            url_title, extensions=extensions, skip_images=skip_images
        )
    except ModuleNotFoundError:
        raise click.ClickException(
            "Playwright is required for `foi attachments`.\n"
            "Install with: pip install open-foi[browser]\n"
            "Then run: playwright install chromium"
        )
    except click.ClickException:
        raise
    except Exception as e:
        raise click.ClickException(str(e))

    if output_path and fmt is None:
        fmt = detect_format_from_path(output_path)
    fmt = fmt or "json"

    if fmt == "json":
        content = format_json_raw(result)
    elif fmt == "summary":
        content = _format_attachments_summary(result)
    elif fmt == "csv":
        content = _format_attachments_csv(result)
    else:
        content = format_json_raw(result)

    write_output(content, output_path)


def format_json_raw(data: dict) -> str:
    import json
    return json.dumps(data, indent=2, default=str)


def _format_attachments_summary(result: dict) -> str:
    """Format attachment list as a human-readable table grouped by message."""
    from collections import defaultdict
    from pathlib import PurePosixPath

    lines = [
        f"Attachments for: {result['url_title']}",
        f"URL: {result['url']}",
        f"Total: {result['total_attachments']}",
        "",
    ]
    by_message: dict[str, list[dict]] = defaultdict(list)
    for att in result["attachments"]:
        by_message[att.get("message_id", "unknown")].append(att)

    for msg_id, atts in by_message.items():
        lines.append(f"  Message {msg_id}:")
        for i, att in enumerate(atts, 1):
            ext = PurePosixPath(att["filename"]).suffix.lower() or "(none)"
            lines.append(f"    {i}. {att['filename']}  [{ext}]")
        lines.append("")
    return "\n".join(lines)


def _format_attachments_csv(result: dict) -> str:
    """Format attachment list as CSV."""
    import csv
    import io
    from pathlib import PurePosixPath

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["filename", "extension", "message_id", "part", "url"])
    for att in result["attachments"]:
        ext = PurePosixPath(att["filename"]).suffix.lower()
        writer.writerow([att["filename"], ext, att.get("message_id", ""), att.get("part", ""), att["url"]])
    return buf.getvalue()


@cli.command()
@click.option("--search", "search_term", default=None, help="Search authorities by name.")
@click.option("--format", "fmt", type=click.Choice(["json", "csv"]), default=None, help="Output format.")
@click.option("--output", "output_path", default=None, help="Write to file.")
@click.pass_context
def authorities(ctx, search_term, fmt, output_path):
    """List or search public authorities."""
    client: WDTKClient = ctx.obj["client"]

    try:
        csv_text = client.all_authorities_csv()
    except WDTKError as e:
        raise click.ClickException(str(e))

    if search_term:
        lines = csv_text.strip().split("\n")
        header = lines[0]
        filtered = [line for line in lines[1:] if search_term.lower() in line.lower()]
        csv_text = header + "\n" + "\n".join(filtered) + "\n"

    if output_path and fmt is None:
        fmt = detect_format_from_path(output_path)
    fmt = fmt or "json"

    if fmt == "json":
        content = format_authorities_json(csv_text)
    else:
        content = format_authorities_csv(csv_text)

    write_output(content, output_path)


@cli.group(invoke_without_command=True)
@click.pass_context
def cache(ctx):
    """Manage the local cache."""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@cache.command("clear")
@click.pass_context
def cache_clear(ctx):
    """Clear all cached data."""
    c: Cache | None = ctx.obj["cache"]
    if c is None:
        click.echo("Cache is disabled.")
        return
    count = c.clear()
    click.echo(f"Cleared {count} cached entries.")


@cache.command("stats")
@click.pass_context
def cache_stats(ctx):
    """Show cache statistics."""
    c: Cache | None = ctx.obj["cache"]
    if c is None:
        click.echo("Cache is disabled.")
        return
    import json
    stats = c.stats()
    click.echo(json.dumps(stats, indent=2))
