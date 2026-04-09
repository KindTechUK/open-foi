"""Playwright-based fetcher for full FOI request content and attachments."""

import json
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

BASE_URL = "https://www.whatdotheyknow.com"


def fetch_request(
    url_title: str,
    output_dir: str = "./foi-data",
    download_attachments: bool = True,
) -> dict:
    """Fetch full content and attachments for a single FOI request.

    Uses Playwright headless Chromium to bypass Cloudflare.
    Returns dict with correspondence and attachment paths.
    """
    from playwright.sync_api import sync_playwright

    request_url = f"{BASE_URL}/request/{url_title}"
    request_dir = Path(output_dir) / url_title
    request_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        logger.info("Navigating to %s", request_url)
        page.goto(request_url, wait_until="networkidle")

        # Extract correspondence
        correspondence = _extract_correspondence(page)

        # Extract attachment links
        attachment_links = _extract_attachment_links(page, url_title)

        # Download attachments
        downloaded = []
        if download_attachments and attachment_links:
            attachments_dir = request_dir / "attachments"
            attachments_dir.mkdir(exist_ok=True)
            for link in attachment_links:
                try:
                    local_path = _download_attachment(page, link, attachments_dir)
                    downloaded.append(str(local_path))
                    logger.info("Downloaded: %s", local_path.name)
                except Exception as e:
                    logger.warning("Failed to download %s: %s", link["url"], e)

        browser.close()

    # Save correspondence
    corr_path = request_dir / "correspondence.json"
    corr_path.write_text(json.dumps(correspondence, indent=2, default=str))

    result = {
        "url_title": url_title,
        "url": request_url,
        "output_dir": str(request_dir),
        "correspondence": correspondence,
        "attachments_downloaded": downloaded,
    }
    return result


def _extract_correspondence(page) -> list[dict]:
    """Extract all messages from the request page."""
    messages = []

    # Outgoing messages (requests/follow-ups from user)
    for el in page.query_selector_all(".outgoing.correspondence"):
        msg = _parse_message_block(el, direction="outgoing")
        if msg:
            messages.append(msg)

    # Incoming messages (responses from authority)
    for el in page.query_selector_all(".incoming.correspondence"):
        msg = _parse_message_block(el, direction="incoming")
        if msg:
            messages.append(msg)

    messages.sort(key=lambda m: m.get("date", ""))
    return messages


def _parse_message_block(el, direction: str) -> dict | None:
    """Parse a single correspondence block from the page."""
    try:
        # Get the message header/metadata
        header_el = el.query_selector(".correspondence_header, .event_header")
        header_text = header_el.inner_text().strip() if header_el else ""

        # Get the message body
        body_el = el.query_selector(".correspondence_text, .outgoing .correspondence_text")
        body_text = body_el.inner_text().strip() if body_el else ""

        # Try to extract date
        date_el = el.query_selector("time, .date")
        date = date_el.get_attribute("datetime") if date_el else ""

        # Extract message ID from the element's ID attribute
        el_id = el.get_attribute("id") or ""
        msg_id_match = re.search(r"(incoming|outgoing)-(\d+)", el_id)
        msg_id = msg_id_match.group(0) if msg_id_match else el_id

        return {
            "id": msg_id,
            "direction": direction,
            "date": date,
            "header": header_text,
            "body": body_text,
        }
    except Exception as e:
        logger.warning("Failed to parse message block: %s", e)
        return None


def _extract_attachment_links(page, url_title: str) -> list[dict]:
    """Find all attachment download links on the page."""
    links = []
    for a in page.query_selector_all("a[href*='/attach/']"):
        href = a.get_attribute("href") or ""
        text = a.inner_text().strip()
        if "/attach/html/" in href:
            continue  # Skip HTML preview links
        if href:
            full_url = href if href.startswith("http") else f"{BASE_URL}{href}"
            links.append({"url": full_url, "filename": text or _filename_from_url(href)})
    return links


def _filename_from_url(url: str) -> str:
    """Extract filename from attachment URL path."""
    parts = url.rstrip("/").split("/")
    return parts[-1] if parts else "attachment"


def _download_attachment(page, link: dict, attachments_dir: Path) -> Path:
    """Download a single attachment using the browser context."""
    response = page.request.get(link["url"])
    filename = _sanitize_filename(link["filename"])
    # Prepend a disambiguator from the URL (message_id + part)
    url_parts = link["url"].split("/")
    prefix = ""
    for i, part in enumerate(url_parts):
        if part == "response" and i + 1 < len(url_parts):
            msg_id = url_parts[i + 1]
        if part == "attach" and i + 1 < len(url_parts):
            attach_part = url_parts[i + 1]
            prefix = f"response_{msg_id}_{attach_part}_"
            break

    filepath = attachments_dir / f"{prefix}{filename}"
    filepath.write_bytes(response.body())
    return filepath


def _sanitize_filename(name: str) -> str:
    """Remove problematic characters from filename."""
    return re.sub(r'[<>:"/\\|?*]', "_", name).strip(". ")


def fetch_batch(
    url_titles: list[str],
    output_dir: str = "./foi-data",
    download_attachments: bool = True,
) -> list[dict]:
    """Fetch multiple requests sequentially."""
    results = []
    for i, url_title in enumerate(url_titles, 1):
        logger.info("Fetching %d/%d: %s", i, len(url_titles), url_title)
        try:
            result = fetch_request(url_title, output_dir, download_attachments)
            results.append(result)
        except Exception as e:
            logger.error("Failed to fetch %s: %s", url_title, e)
            results.append({"url_title": url_title, "error": str(e)})
    return results
