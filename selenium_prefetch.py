"""
selenium_prefetch.py — Pre-fetch document text from JS-rendered municipal portals.

Runs LOCALLY via Selenium to extract text from portals that the cloud-based
HTTP scanner cannot read (CivicWeb, eScribe, Laserfiche, Legistar, etc).

The output CSV is committed to Git so the Streamlit Intelligence Scanner
can use it as a "Stage 2" cache — applying keyword matching against
pre-fetched text without needing Selenium on the cloud.

Usage:
    python selenium_prefetch.py                 # All JS portals (~294 municipalities)
    python selenium_prefetch.py --limit 10      # Test with first 10 only
    python selenium_prefetch.py --portal escribe # Only eScribe portals

This script is called automatically by run_weekly_scan.bat.
"""

import os
import sys
import time
import re
import argparse
import datetime
import pandas as pd
import urllib.parse
from io import BytesIO
from bs4 import BeautifulSoup

try:
    import pdfplumber
    import requests
except ImportError:
    print("Missing requirements: pip install pdfplumber requests bs4")
    sys.exit(1)

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- CONFIG ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REGISTRY_PATH = os.path.join(SCRIPT_DIR, "signals", "portal_registry.csv")
OUTPUT_PATH = os.path.join(SCRIPT_DIR, "signals", "cached_portal_docs.csv")

# Portal types that require Selenium (JS rendering)
JS_PORTAL_TYPES = {"civicweb", "escribe", "(escribe)", "granicus_legistar"}

# Maximum text length to store per document (controls CSV file size)
MAX_TEXT_LENGTH = 15000  # ~15KB per doc, keeps total CSV under 15MB

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


def setup_driver():
    """Configure headless Chrome optimized for fast page loads."""
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--log-level=3")
    options.page_load_strategy = "eager"
    options.add_argument(f"user-agent={HEADERS['User-Agent']}")

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()), options=options
    )
    driver.set_page_load_timeout(45)
    return driver


def extract_pdf_text(url, max_pages=30):
    """Download and extract text from a PDF URL without saving to disk."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15, verify=False)
        if resp.status_code == 200 and len(resp.content) > 500:
            with pdfplumber.open(BytesIO(resp.content)) as pdf:
                text = ""
                for page in pdf.pages[:max_pages]:
                    extracted = page.extract_text()
                    if extracted:
                        text += extracted + "\n"
                return text.strip()
    except Exception:
        pass
    return ""


def find_document_links(driver, soup, base_url):
    """Spider the page for document links (PDFs, meeting pages, FileStream downloads)."""
    links = []
    seen = set()

    for a in soup.find_all("a", href=True):
        href = a["href"]
        text = a.get_text().strip().lower()
        full_url = urllib.parse.urljoin(base_url, href)

        if href.startswith("javascript:") or href == "#":
            continue
        if full_url in seen:
            continue

        # Is this a document link?
        is_doc = (
            full_url.lower().endswith(".pdf") or
            "FileStream" in href or
            "View.ashx" in href or
            "ElectronicFile" in href
        )

        # Is this a meeting page link?
        is_meeting = (
            "Meeting.aspx" in href or
            any(w in text for w in ["regular council", "council meeting", "regular meeting",
                                    "special council", "committee of the whole",
                                    "agenda", "minutes"])
        )

        if is_doc or is_meeting:
            links.append(full_url)
            seen.add(full_url)

    return links[:5]  # Limit to 5 most recent


def extract_date_from_text(text):
    """Try to extract a date from link text or URL for sorting."""
    months = {
        'january': 1, 'february': 2, 'march': 3, 'april': 4,
        'may': 5, 'june': 6, 'july': 7, 'august': 8,
        'september': 9, 'october': 10, 'november': 11, 'december': 12
    }
    text_lower = text.lower()
    for m_name, m_num in months.items():
        match = re.search(rf'{m_name}\s+(\d{{1,2}}),?\s*(\d{{4}})', text_lower)
        if match:
            try:
                return datetime.date(int(match.group(2)), m_num, int(match.group(1)))
            except ValueError:
                pass

    match = re.search(r'(\d{4})[-/](\d{1,2})[-/](\d{1,2})', text_lower)
    if match:
        try:
            return datetime.date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except ValueError:
            pass
    return None


def prefetch_single_muni(driver, row):
    """Pre-fetch document text from a single municipality's portal.

    Returns a list of dicts with the extracted text, or empty list if nothing found.
    """
    name = row.get("municipality_name", "Unknown")
    portal_type = str(row.get("portal_type", "unknown"))
    listing_url = row.get("minutes_listing_url", "")

    if pd.isna(listing_url) or not str(listing_url).strip():
        return []

    listing_url = str(listing_url).strip()
    results = []

    try:
        # Step 1: Load the listing page with Selenium (JS renders)
        driver.get(listing_url)
        time.sleep(4)  # Wait for JS to render

        soup = BeautifulSoup(driver.page_source, "html.parser")

        # Step 2: Find document links
        doc_links = find_document_links(driver, soup, listing_url)

        # If no sub-links found, scan the listing page itself
        if not doc_links:
            page_text = driver.find_element("tag name", "body").text
            if page_text and len(page_text.strip()) > 100:
                results.append({
                    "municipality_name": name,
                    "portal_type": portal_type,
                    "doc_url": listing_url,
                    "doc_text": page_text[:MAX_TEXT_LENGTH],
                    "doc_type": "html_listing",
                    "fetch_date": datetime.date.today().isoformat(),
                })
            return results

        # Step 3: Extract text from each document link (up to 3)
        for doc_url in doc_links[:3]:
            doc_text = ""
            doc_type = ""

            if doc_url.lower().endswith(".pdf") or "FileStream" in doc_url or "ElectronicFile" in doc_url:
                # Direct PDF download — don't need Selenium
                doc_text = extract_pdf_text(doc_url)
                doc_type = "pdf"
            else:
                # HTML page — load with Selenium
                try:
                    driver.get(doc_url)
                    time.sleep(2)
                    doc_text = driver.find_element("tag name", "body").text
                    doc_type = "html"
                except Exception:
                    continue

            if doc_text and len(doc_text.strip()) > 50:
                results.append({
                    "municipality_name": name,
                    "portal_type": portal_type,
                    "doc_url": doc_url,
                    "doc_text": doc_text[:MAX_TEXT_LENGTH],
                    "doc_type": doc_type,
                    "fetch_date": datetime.date.today().isoformat(),
                })

    except Exception as e:
        print(f"    ERROR: {str(e)[:80]}")

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Pre-fetch document text from JS-rendered municipal portals."
    )
    parser.add_argument(
        "--portal", choices=["escribe", "civicweb", "all"], default="all",
        help="Filter by portal type (default: all JS portals)"
    )
    parser.add_argument(
        "--limit", type=int, default=0,
        help="Limit number of municipalities to process (0 = all)"
    )
    args = parser.parse_args()

    print("=" * 60)
    print("  SELENIUM PRE-FETCH: Caching JS Portal Documents")
    print("=" * 60)

    if not os.path.exists(REGISTRY_PATH):
        print(f"ERROR: Registry not found at {REGISTRY_PATH}")
        sys.exit(1)

    df = pd.read_csv(REGISTRY_PATH)

    # Filter to JS-rendered portals only
    if args.portal == "escribe":
        targets = df[df["portal_type"].str.lower().isin({"escribe", "(escribe)"})]
    elif args.portal == "civicweb":
        targets = df[df["portal_type"].str.lower() == "civicweb"]
    else:
        targets = df[df["portal_type"].str.lower().isin(JS_PORTAL_TYPES)]

    if args.limit > 0:
        targets = targets.head(args.limit)

    total = len(targets)
    print(f"Targeting {total} JS-rendered portals for pre-fetch.")
    print(f"Output: {OUTPUT_PATH}")
    print()

    driver = setup_driver()
    all_results = []
    success = 0
    failed = 0

    try:
        for count, (idx, row) in enumerate(targets.iterrows(), 1):
            name = row["municipality_name"]
            portal = str(row.get("portal_type", "?"))
            print(f"[{count}/{total}] {name} ({portal})...", end=" ", flush=True)

            docs = prefetch_single_muni(driver, row)

            # Retry once if the first attempt failed
            if not docs:
                time.sleep(5)
                docs = prefetch_single_muni(driver, row)

            # Detect browser crash and restart if needed
            if not docs:
                try:
                    driver.title  # Quick health check
                except Exception:
                    print("(browser crashed, restarting)...", end=" ", flush=True)
                    try:
                        driver.quit()
                    except Exception:
                        pass
                    driver = setup_driver()

            if docs:
                all_results.extend(docs)
                success += 1
                print(f"OK ({len(docs)} doc{'s' if len(docs) != 1 else ''})")
            else:
                failed += 1
                print("-- no docs found")

    except KeyboardInterrupt:
        print("\nInterrupted by user. Saving partial results...")
    finally:
        driver.quit()

    # Save results
    if all_results:
        out_df = pd.DataFrame(all_results)
        out_df.to_csv(OUTPUT_PATH, index=False)
        print(f"\n{'=' * 60}")
        print(f"  PRE-FETCH COMPLETE")
        print(f"  Municipalities with docs: {success}/{total}")
        print(f"  Total documents cached:   {len(all_results)}")
        print(f"  Failed/no docs:           {failed}")
        print(f"  Output: {OUTPUT_PATH}")
        print(f"  File size: {os.path.getsize(OUTPUT_PATH) / 1024 / 1024:.1f} MB")
        print(f"{'=' * 60}")
    else:
        print(f"\nNo documents were found. ({failed} failed)")


if __name__ == "__main__":
    main()
