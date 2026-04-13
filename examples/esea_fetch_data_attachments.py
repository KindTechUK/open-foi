"""Fetch data-file attachments from successful ESEA hate crime FOI requests.

Reads the manifest from esea_hatecrime_2025.py, filters to requests with data responses,
fetches each page via Playwright, and downloads only attachments that look like data files
(spreadsheets, data-oriented PDFs) — skipping cover letters, images, and signatures.

Usage:
    python examples/esea_fetch_data_attachments.py
    python examples/esea_fetch_data_attachments.py --manifest results.json --output-dir ./data
    python examples/esea_fetch_data_attachments.py --dry-run     # list what would be downloaded
"""

import json
import logging
import re
import sys
import time
from pathlib import Path
from urllib.parse import unquote

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s", stream=sys.stderr)
logger = logging.getLogger(__name__)

MANIFEST_DEFAULT = Path("examples/esea_hatecrime_2025_requests.json")
OUTPUT_DEFAULT = Path("examples/esea_data")

# Statuses where a data response is expected
DATA_STATUSES = {"successful", "partially_successful"}

# --- Attachment filtering ---
# Always data files
SPREADSHEET_EXTS = {".xlsx", ".xls", ".csv", ".ods", ".tsv"}

# Always skip
SKIP_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".svg", ".tif", ".tiff"}

# Skip if filename matches these patterns (case-insensitive) — administrative docs, not data
SKIP_NAME_PATTERNS = [
    re.compile(r"response\s*letter", re.IGNORECASE),
    re.compile(r"cover\s*letter", re.IGNORECASE),
    re.compile(r"acknowledgement", re.IGNORECASE),
    re.compile(r"refusal", re.IGNORECASE),
    re.compile(r"appeals?\s*(procedure|notice|process)", re.IGNORECASE),
    re.compile(r"complaint(s)?\s*(right|procedure|process)", re.IGNORECASE),
    re.compile(r"review\s*(procedure|process|notice)", re.IGNORECASE),
    re.compile(r"internal\s*review\s*notice", re.IGNORECASE),
]


def is_data_attachment(filename: str) -> bool:
    """Decide whether an attachment filename looks like a data file.

    Returns True for spreadsheets unconditionally.
    Returns False for images unconditionally.
    For PDFs: returns True unless the filename looks like a cover/response letter.
    """
    decoded = unquote(filename)
    ext = Path(decoded).suffix.lower()

    if ext in SPREADSHEET_EXTS:
        return True
    if ext in SKIP_EXTS:
        return False
    # For all non-image, non-spreadsheet files: skip administrative docs
    for pattern in SKIP_NAME_PATTERNS:
        if pattern.search(decoded):
            return False
    return True


def load_manifest(path: Path) -> list[dict]:
    """Load request manifest and filter to statuses likely to have data."""
    data = json.loads(path.read_text())
    requests = data["requests"]
    filtered = [r for r in requests if r["status"] in DATA_STATUSES]
    logger.info(
        "Manifest: %d total requests, %d with data statuses (%s)",
        len(requests),
        len(filtered),
        ", ".join(sorted(DATA_STATUSES)),
    )
    return filtered


def fetch_attachment_links(pw, url_title: str) -> tuple[list[dict], "BrowserContext"]:
    """Open a request page with a fresh browser context and extract attachment links.

    Returns (links, context) — caller must close the context after downloading.
    A fresh context per request avoids Cloudflare session-based bot detection.
    """
    from foi_cli.browser import _create_stealth_context, _extract_all_attachment_links, BASE_URL

    browser, context = _create_stealth_context(pw)
    page = context.new_page()
    try:
        url = f"{BASE_URL}/request/{url_title}?unfold=1"
        page.goto(url, wait_until="domcontentloaded", timeout=20000)
        # Wait for page to load past Cloudflare challenge
        for _ in range(10):
            if page.query_selector(".correspondence"):
                break
            page.wait_for_timeout(1000)
        links = _extract_all_attachment_links(page)
        return links, context, browser, page
    except Exception:
        page.close()
        browser.close()
        raise


def download_file(page, link: dict, dest_dir: Path) -> Path | None:
    """Download a single attachment, falling back to browser navigation if Cloudflare blocks.

    First tries page.request.get() (fast, direct HTTP). If Cloudflare returns 403,
    falls back to a real browser navigation via expect_download which can solve
    JS challenges automatically.
    """
    filename = unquote(link["filename"])
    filename = re.sub(r'[<>:"/\\|?*]', "_", filename).strip(". ")
    dest = dest_dir / filename

    try:
        response = page.request.get(link["url"])
        if response.ok:
            dest.write_bytes(response.body())
            return dest
        logger.info("  HTTP %d via API request, trying browser download...", response.status)
    except Exception as e:
        logger.info("  API request failed (%s), trying browser download...", e)

    # Fallback: open a new page in the same context (shares Cloudflare cookies)
    # and navigate to the attachment URL. goto throws "Download is starting" which is
    # expected — expect_download captures the file.
    dl_page = page.context.new_page()
    try:
        with dl_page.expect_download(timeout=20000) as download_info:
            try:
                dl_page.goto(link["url"], timeout=20000)
            except Exception:
                pass  # "Download is starting" error is expected
        download = download_info.value
        download.save_as(str(dest))
        return dest
    except Exception as e:
        logger.warning("Browser download also failed for %s: %s", link["url"], e)
        return None
    finally:
        dl_page.close()


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Fetch ESEA hate crime data attachments")
    parser.add_argument("--manifest", "-m", type=Path, default=MANIFEST_DEFAULT)
    parser.add_argument("--output-dir", "-o", type=Path, default=OUTPUT_DEFAULT)
    parser.add_argument("--dry-run", action="store_true", help="List attachments without downloading")
    parser.add_argument("--rate-limit", type=float, default=3.0, help="Seconds between requests")
    args = parser.parse_args()

    requests = load_manifest(args.manifest)
    if not requests:
        logger.error("No requests with data statuses found in manifest")
        sys.exit(1)

    from playwright.sync_api import sync_playwright

    results = []

    with sync_playwright() as pw:
        for i, req in enumerate(requests):
            slug = req["url_title"]
            authority = req["authority"]
            logger.info("[%d/%d] %s (%s)", i + 1, len(requests), slug, authority)

            if i > 0:
                time.sleep(args.rate_limit)

            browser = None
            page = None
            try:
                links, context, browser, page = fetch_attachment_links(pw, slug)
            except Exception as e:
                logger.error("  Failed to load page: %s", e)
                results.append({"url_title": slug, "authority": authority, "error": str(e)})
                continue

            try:
                data_links = [l for l in links if is_data_attachment(l["filename"])]
                skipped = [l for l in links if not is_data_attachment(l["filename"])]

                if skipped:
                    for s in skipped:
                        logger.info("  Skipping: %s", unquote(s["filename"]))

                if not data_links:
                    logger.info("  No data attachments found (%d total attachments skipped)", len(links))
                    results.append({
                        "url_title": slug,
                        "authority": authority,
                        "attachments": [],
                        "note": f"{len(links)} attachments found but none matched data filter",
                    })
                    continue

                # Organize by authority name (sanitized)
                authority_dir = args.output_dir / re.sub(r'[<>:"/\\|?*]', "_", authority)

                if args.dry_run:
                    for link in data_links:
                        print(f"  [DRY RUN] {authority}: {unquote(link['filename'])}")
                    results.append({
                        "url_title": slug,
                        "authority": authority,
                        "attachments": [unquote(l["filename"]) for l in data_links],
                    })
                    continue

                authority_dir.mkdir(parents=True, exist_ok=True)
                downloaded = []
                for link in data_links:
                    dest = download_file(page, link, authority_dir)
                    if dest:
                        logger.info("  Downloaded: %s", dest.name)
                        downloaded.append(str(dest))

                results.append({
                    "url_title": slug,
                    "authority": authority,
                    "attachments": downloaded,
                })
            finally:
                if page:
                    page.close()
                if browser:
                    browser.close()

    # Write results manifest
    args.output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = args.output_dir / "fetch_manifest.json"
    manifest_path.write_text(json.dumps(results, indent=2) + "\n")

    # Summary
    total_files = sum(len(r.get("attachments", [])) for r in results)
    errors = sum(1 for r in results if "error" in r)
    empty = sum(1 for r in results if not r.get("attachments") and "error" not in r)
    print(f"\n{'='*60}")
    print(f"ESEA Hate Crime Data Attachments")
    print(f"{'='*60}")
    print(f"Requests processed:   {len(results)}")
    print(f"Data files {'found' if args.dry_run else 'downloaded'}:  {total_files}")
    print(f"No data attachments:  {empty}")
    print(f"Errors:               {errors}")
    if not args.dry_run:
        print(f"Output directory:     {args.output_dir}")
    print(f"Manifest:             {manifest_path}")


if __name__ == "__main__":
    main()
