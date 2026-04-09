"""Playwright-based fetcher for full FOI request content and attachments.

Uses headless Chromium with stealth configuration to bypass Cloudflare.
"""

import json
import logging
import re
import time
from pathlib import Path

logger = logging.getLogger(__name__)

BASE_URL = "https://www.whatdotheyknow.com"

_CHROME_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)
_LAUNCH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--no-sandbox",
]
_VIEWPORT = {"width": 1920, "height": 1080}
_WEBDRIVER_INIT_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', {
    get: () => undefined,
});
"""


def _create_stealth_context(playwright):
    """Launch stealth Chromium browser and return (browser, context)."""
    browser = playwright.chromium.launch(headless=True, args=_LAUNCH_ARGS)
    context = browser.new_context(
        user_agent=_CHROME_USER_AGENT,
        viewport=_VIEWPORT,
        locale="en-US",
    )
    context.add_init_script(_WEBDRIVER_INIT_SCRIPT)
    return browser, context


def _prepare_page(page, url_title: str) -> None:
    """Navigate to request page and expand all content."""
    url = f"{BASE_URL}/request/{url_title}?unfold=1"
    logger.info("Navigating to %s", url)
    page.goto(url, wait_until="domcontentloaded")
    page.wait_for_selector(".correspondence", timeout=15000)

    # Expand collapsed messages
    collapsed = page.query_selector_all("div.correspondence.collapsed")
    for el in collapsed:
        header = el.query_selector(".correspondence__header")
        if header:
            header.click()
            page.wait_for_timeout(200)

    # Click all "show more attachments" buttons
    show_more = page.query_selector_all(".attachments__show-more")
    for btn in show_more:
        btn.click()
        page.wait_for_timeout(200)


def _extract_correspondence(page) -> list[dict]:
    """Extract all correspondence messages from the page."""
    messages = []
    for el in page.query_selector_all("div.correspondence"):
        classes = el.get_attribute("class") or ""
        if "outgoing" in classes:
            direction = "outgoing"
        elif "incoming" in classes:
            direction = "incoming"
        else:
            continue
        msg = _parse_message_block(el, direction)
        if msg:
            messages.append(msg)
    return messages


def _parse_message_block(el, direction: str) -> dict | None:
    """Parse a single correspondence block into a message dict."""
    try:
        el_id = el.get_attribute("id") or ""
        msg_id_match = re.search(r"(incoming|outgoing)-(\d+)", el_id)
        msg_id = msg_id_match.group(0) if msg_id_match else el_id

        author_el = el.query_selector(".correspondence__header__author")
        author = author_el.inner_text().strip() if author_el else ""

        date_el = el.query_selector(".correspondence__header__date")
        date = ""
        if date_el:
            time_el = date_el.query_selector("time")
            if time_el:
                date = time_el.get_attribute("datetime") or ""
            if not date:
                date = date_el.inner_text().strip()

        body_el = el.query_selector(".correspondence_text")
        body = body_el.inner_text().strip() if body_el else ""

        # Per-message attachments
        attachments = []
        for a in el.query_selector_all("a[href*='/attach/']"):
            href = a.get_attribute("href") or ""
            if "/attach/html/" in href or not href:
                continue
            full_url = href if href.startswith("http") else f"{BASE_URL}{href}"
            if "cookie_passthrough" not in full_url:
                sep = "&" if "?" in full_url else "?"
                full_url += f"{sep}cookie_passthrough=1"
            text = a.inner_text().strip()
            msg_id_from_url, part = _parse_attachment_url(full_url)
            attachments.append({
                "url": full_url,
                "filename": text or _filename_from_url(href),
                "message_id": msg_id_from_url,
                "part": part,
            })

        return {
            "id": msg_id,
            "direction": direction,
            "author": author,
            "date": date,
            "body": body,
            "attachments": attachments,
        }
    except Exception as e:
        logger.warning("Failed to parse message block: %s", e)
        return None


def _parse_attachment_url(url: str) -> tuple[str, str]:
    """Extract message_id and part number from attachment URL."""
    parts = url.split("/")
    msg_id = ""
    part = ""
    for i, segment in enumerate(parts):
        if segment == "response" and i + 1 < len(parts):
            msg_id = parts[i + 1]
        if segment == "attach" and i + 1 < len(parts):
            part = parts[i + 1]
            break
    return msg_id, part


def _extract_all_attachment_links(page) -> list[dict]:
    """Find all non-HTML attachment download links on the page."""
    links = []
    seen = set()
    for a in page.query_selector_all("a[href*='/attach/']"):
        href = a.get_attribute("href") or ""
        if "/attach/html/" in href or not href:
            continue
        full_url = href if href.startswith("http") else f"{BASE_URL}{href}"
        if "cookie_passthrough" not in full_url:
            sep = "&" if "?" in full_url else "?"
            full_url += f"{sep}cookie_passthrough=1"
        # Deduplicate by base URL (without query params)
        base = full_url.split("?")[0]
        if base in seen:
            continue
        seen.add(base)
        text = a.inner_text().strip()
        msg_id, part = _parse_attachment_url(full_url)
        links.append({
            "url": full_url,
            "filename": text or _filename_from_url(href),
            "message_id": msg_id,
            "part": part,
        })
    return links


def _filename_from_url(url: str) -> str:
    """Extract filename from attachment URL path."""
    # Strip query params first
    path = url.split("?")[0]
    parts = path.rstrip("/").split("/")
    return parts[-1] if parts else "attachment"


def _sanitize_filename(name: str) -> str:
    """Remove problematic characters from filename."""
    return re.sub(r'[<>:"/\\|?*]', "_", name).strip(". ")


def _download_attachment(page, link: dict, attachments_dir: Path) -> Path:
    """Download a single attachment using the browser context's cookies."""
    response = page.request.get(link["url"])
    if not response.ok:
        raise RuntimeError(f"HTTP {response.status} downloading {link['url']}")
    content_type = response.headers.get("content-type", "")
    if "text/html" in content_type:
        raise RuntimeError(
            f"Got HTML instead of attachment for {link['url']} "
            f"(likely Cloudflare block or error page)"
        )
    filename = _sanitize_filename(link["filename"])
    prefix = ""
    if link.get("message_id") and link.get("part"):
        prefix = f"response_{link['message_id']}_{link['part']}_"
    filepath = attachments_dir / f"{prefix}{filename}"
    filepath.write_bytes(response.body())
    return filepath


def fetch_request(
    url_title: str,
    output_dir: str = "./foi-data",
    download_attachments: bool = True,
    *,
    _context=None,
    _rate_limit: float = 0.0,
) -> dict:
    """Fetch full content and attachments for a single FOI request.

    Args:
        url_title: URL slug of the request
        output_dir: Base directory for output
        download_attachments: Whether to download attachment files
        _context: Pre-existing BrowserContext for batch reuse
        _rate_limit: Seconds to sleep before navigation (batch rate limiting)
    """
    own_browser = _context is None
    browser = None
    pw = None

    try:
        if own_browser:
            from playwright.sync_api import sync_playwright
            pw = sync_playwright().start()
            browser, context = _create_stealth_context(pw)
        else:
            context = _context

        if _rate_limit > 0:
            time.sleep(_rate_limit)

        request_dir = Path(output_dir) / url_title
        request_dir.mkdir(parents=True, exist_ok=True)

        page = context.new_page()
        try:
            _prepare_page(page, url_title)
            correspondence = _extract_correspondence(page)
            attachment_links = _extract_all_attachment_links(page)

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
        finally:
            page.close()

        corr_path = request_dir / "correspondence.json"
        corr_path.write_text(json.dumps(correspondence, indent=2, default=str))

        return {
            "url_title": url_title,
            "url": f"{BASE_URL}/request/{url_title}",
            "output_dir": str(request_dir),
            "correspondence": correspondence,
            "attachments_downloaded": downloaded,
        }
    finally:
        if own_browser:
            if browser:
                browser.close()
            if pw:
                pw.stop()


def fetch_batch(
    url_titles: list[str],
    output_dir: str = "./foi-data",
    download_attachments: bool = True,
    rate_limit: float = 2.0,
) -> list[dict]:
    """Fetch multiple FOI requests using a shared browser session."""
    from playwright.sync_api import sync_playwright

    results = []
    with sync_playwright() as pw:
        browser, context = _create_stealth_context(pw)
        try:
            for i, url_title in enumerate(url_titles):
                logger.info("Fetching %d/%d: %s", i + 1, len(url_titles), url_title)
                delay = rate_limit if i > 0 else 0.0
                try:
                    result = fetch_request(
                        url_title, output_dir, download_attachments,
                        _context=context, _rate_limit=delay,
                    )
                    results.append(result)
                except Exception as e:
                    logger.error("Failed to fetch %s: %s", url_title, e)
                    results.append({"url_title": url_title, "error": str(e)})
        finally:
            browser.close()
    return results
