"""
lgd_audit_scanner.py — Province-Wide LGD Bylaw Accuracy Audit

Scans all 414 lower/single-tier municipalities to:
  1. Validate stored bylaw links (live vs broken)
  2. Confirm bylaw name matches the linked document
  3. Search for LGD-relevant keywords in bylaws
  4. Spider municipal websites for newer animal control bylaws
  5. Classify each municipality into a triage bucket

Output: signals/lgd_audit_YYYY-MM-DD.csv

Usage:
  python lgd_audit_scanner.py              # Full scan (414 municipalities)
  python lgd_audit_scanner.py --test 10    # Test mode (first N municipalities)
"""

import pandas as pd
import requests
import os
import sys
import datetime
import urllib3
import io
import re
import sqlite3
import argparse
import time
from urllib.parse import urljoin, urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed

# Import shared config
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shared_config import REGION_MAPPING, get_region, extract_readable_snippet

try:
    import pdfplumber
    PDF_SUPPORT = True
except ImportError:
    PDF_SUPPORT = False

try:
    from bs4 import BeautifulSoup
    BS4_SUPPORT = True
except ImportError:
    BS4_SUPPORT = False

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Fix Windows terminal encoding for emoji output
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

# ── Paths ──
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(SCRIPT_DIR, "bylaws.db")
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "signals")

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                  'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

# ── LGD-specific keywords ──
LGD_PRIMARY_KEYWORDS = [
    "livestock guardian", "guardian dog", "herding dog", "working dog",
    "farm dog", "livestock guard dog", "livestock protection dog",
    "guardian animal", "lgd",
]

LGD_SECONDARY_PATTERNS = [
    # These use regex to find proximity matches
    r'dog\s+limit.*(?:agricult|farm)',
    r'(?:agricult|farm).*dog\s+limit',
    r'kennel\s+(?:exempt|licen).*farm',
    r'farm.*kennel\s+(?:exempt|licen)',
    r'exempt.*(?:licen|fee).*(?:guard|herd|farm)',
    r'(?:guard|herd|farm).*exempt.*(?:licen|fee)',
]

# Keywords to search on municipal websites for animal control bylaws
ANIMAL_BYLAW_SEARCH_TERMS = [
    "animal control", "dog bylaw", "animal bylaw", "responsible pet",
    "dog control", "dog licensing", "animal care",
]


# ── Text extraction ──

def extract_text_from_pdf(pdf_bytes):
    """Extract text from PDF bytes using pdfplumber."""
    if not PDF_SUPPORT:
        return ""
    text = ""
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages[:40]:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
    except Exception as e:
        return f"[PDF Error: {e}]"
    return text


def fetch_and_extract_text(url, timeout=15):
    """Download a URL and extract text. Returns (text, is_pdf, http_status)."""
    try:
        response = requests.get(url, headers=HEADERS, timeout=timeout, verify=False)
        status = response.status_code
        if status != 200:
            return "", False, status

        content_type = response.headers.get('Content-Type', '').lower()

        if 'pdf' in content_type or url.lower().endswith('.pdf'):
            text = extract_text_from_pdf(response.content)
            return text, True, status
        else:
            if BS4_SUPPORT:
                soup = BeautifulSoup(response.text, "html.parser")
                for tag in soup(["script", "style", "nav", "header", "footer"]):
                    tag.decompose()
                text = soup.get_text(separator=" ", strip=True)
                return text, False, status
            return response.text, False, status
    except requests.exceptions.Timeout:
        return "", False, -1  # Timeout
    except Exception:
        return "", False, -2  # Other error


def spider_website_for_bylaws(website_url, max_links=3):
    """Spider a municipal website looking for animal control bylaw links.

    Returns a list of (url, link_text) tuples for promising bylaw pages.
    """
    if not website_url or not BS4_SUPPORT:
        return []

    # Normalize the website URL
    if not website_url.startswith("http"):
        website_url = "https://" + website_url

    results = []
    try:
        resp = requests.get(website_url, headers=HEADERS, timeout=12, verify=False)
        if resp.status_code != 200:
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        links = soup.find_all("a", href=True)

        for link in links:
            href = link["href"]
            text = link.get_text().strip().lower()
            full_url = urljoin(website_url, href)

            # Look for bylaw-related links
            if any(term in text for term in ANIMAL_BYLAW_SEARCH_TERMS):
                results.append((full_url, link.get_text().strip()))
            elif any(term in href.lower() for term in ["animal", "dog-bylaw", "pet-owner"]):
                results.append((full_url, link.get_text().strip()))

        # De-duplicate
        seen = set()
        unique = []
        for url, text in results:
            if url not in seen:
                unique.append((url, text))
                seen.add(url)
        return unique[:max_links]

    except Exception:
        return []


# ── Classification logic ──

def check_lgd_keywords(text):
    """Search text for LGD-relevant keywords.

    Returns (found_keywords, snippets) — lists of matched terms and evidence snippets.
    """
    if not text or len(text.strip()) < 50:
        return [], []

    text_lower = text.lower()
    found = []
    snippets = []

    # Primary keyword search (exact phrase, word-boundary)
    for keyword in LGD_PRIMARY_KEYWORDS:
        pattern = r'\b' + re.escape(keyword) + r'\b'
        if re.search(pattern, text_lower):
            found.append(keyword)
            snippet = extract_readable_snippet(text, keyword, window=200)
            if snippet:
                snippets.append(snippet)

    # Secondary pattern search (regex proximity)
    for pattern in LGD_SECONDARY_PATTERNS:
        match = re.search(pattern, text_lower)
        if match:
            matched_text = match.group(0)
            if matched_text not in found:
                found.append(f"[pattern: {matched_text[:60]}]")
                start = max(0, match.start() - 100)
                end = min(len(text), match.end() + 100)
                snippets.append(f"...{text[start:end]}...")

    return found, snippets


def check_bylaw_name_match(text, bylaw_name):
    """Check if the stored bylaw name/number appears in the document text.

    Tries exact match first, then a cleaned/fuzzy match.
    """
    if not text or not bylaw_name:
        return False, "no_data"

    text_lower = text.lower()
    name_lower = bylaw_name.lower().strip()

    # Exact match
    if name_lower in text_lower:
        return True, "exact"

    # Extract just the bylaw number (e.g., "2022-008" from "BY-LAW 2022-008")
    num_match = re.search(r'(\d{2,4}[-/]\d{1,4})', bylaw_name)
    if num_match:
        bylaw_num = num_match.group(1)
        if bylaw_num in text:
            return True, "number_match"

    # Try without hyphens/spaces
    cleaned = re.sub(r'[\s\-/]', '', name_lower)
    text_cleaned = re.sub(r'[\s\-/]', '', text_lower)
    if cleaned in text_cleaned:
        return True, "fuzzy"

    return False, "no_match"


def detect_newer_bylaw(text, recorded_date_enacted):
    """Look for signs of a newer bylaw in the document text.

    Returns (is_newer_found, evidence_text).
    """
    if not text:
        return False, ""

    # Look for "repealed", "replaced", "superseded" language
    repeal_patterns = [
        r'repeal(?:s|ed|ing)',
        r'replac(?:es|ed|ing)',
        r'supersed(?:es|ed|ing)',
        r'revok(?:es|ed|ing)',
    ]

    for pattern in repeal_patterns:
        match = re.search(pattern, text.lower())
        if match:
            start = max(0, match.start() - 80)
            end = min(len(text), match.end() + 80)
            return True, text[start:end].strip()

    # Look for enacted dates newer than our record
    if recorded_date_enacted:
        try:
            recorded = datetime.date.fromisoformat(str(recorded_date_enacted)[:10])
            # Find year patterns in the text
            year_matches = re.findall(r'(?:enacted|passed|adopted|approved)\s+.*?(\d{4})', text.lower())
            for year_str in year_matches:
                year = int(year_str)
                if year > recorded.year:
                    return True, f"Found reference to {year} enactment (our record: {recorded.year})"
        except (ValueError, TypeError):
            pass

    return False, ""


# ── Main audit function per municipality ──

def audit_single_muni(row):
    """Audit a single municipality's LGD bylaw status.

    Args:
        row: dict with keys from the database query

    Returns:
        dict with audit results
    """
    name = row["name"]
    county = row.get("geographic_area", "Unknown")
    tier = row.get("municipal_status", "Unknown")
    progress = row.get("progress_label", "")
    bylaw_name = row.get("bylaw_name", "")
    bylaw_link = row.get("bylaw_link", "")
    date_enacted = row.get("date_enacted", "")
    website = row.get("website", "")
    has_lgd_def = row.get("has_lgd_definition", "")

    region = get_region(county, name)

    result = {
        "Municipality": name,
        "County": county,
        "Tier": tier,
        "Region": region,
        "DB Status": progress or "NULL",
        "DB Bylaw Name": bylaw_name or "",
        "DB Date Enacted": date_enacted or "",
        "DB Has LGD Def": has_lgd_def or "",
        "Audit Result": "",
        "Link Status": "",
        "Bylaw Name Match": "",
        "LGD Keywords Found": "",
        "Snippet": "",
        "Source URL": bylaw_link or "",
        "Website Bylaw Links Found": "",
        "Notes": "",
    }

    has_bylaw = progress in ("COMPLETE", "COMPLETE - FARM FRIENDLY")
    link_clean = str(bylaw_link).strip() if bylaw_link and str(bylaw_link) != "nan" else ""

    # ── Step 1: Check stored bylaw link ──
    doc_text = ""
    if link_clean:
        doc_text, is_pdf, http_status = fetch_and_extract_text(link_clean)

        if http_status == -1:
            result["Link Status"] = "TIMEOUT"
        elif http_status == -2:
            result["Link Status"] = "ERROR"
        elif http_status == 200:
            result["Link Status"] = "200 OK"
        else:
            result["Link Status"] = f"HTTP {http_status}"
    else:
        result["Link Status"] = "NO LINK"

    # ── Step 2: Check bylaw name match ──
    if doc_text and bylaw_name:
        match_found, match_type = check_bylaw_name_match(doc_text, bylaw_name)
        result["Bylaw Name Match"] = f"YES ({match_type})" if match_found else "NO"
    elif not bylaw_name:
        result["Bylaw Name Match"] = "N/A (no name in DB)"

    # ── Step 3: Search for LGD keywords ──
    lgd_found, lgd_snippets = check_lgd_keywords(doc_text) if doc_text else ([], [])
    if lgd_found:
        result["LGD Keywords Found"] = "; ".join(lgd_found[:5])
        result["Snippet"] = lgd_snippets[0][:500] if lgd_snippets else ""

    # ── Step 4: Check for newer bylaw ──
    newer_found, newer_evidence = detect_newer_bylaw(doc_text, date_enacted) if doc_text else (False, "")

    # ── Step 5: Spider municipal website for current animal control bylaw ──
    website_links = []
    if website:
        website_links = spider_website_for_bylaws(website)
        if website_links:
            result["Website Bylaw Links Found"] = "; ".join([f"{t} ({u[:80]})" for u, t in website_links[:3]])

    # ── Step 6: Classification ──
    if has_bylaw:
        # Municipality currently marked as having an LGD bylaw
        if result["Link Status"] == "200 OK":
            if result["Bylaw Name Match"].startswith("YES"):
                if newer_found:
                    result["Audit Result"] = "OUTDATED"
                    result["Notes"] = f"Newer bylaw detected: {newer_evidence[:200]}"
                else:
                    result["Audit Result"] = "CURRENT"
                    result["Notes"] = "Link live, bylaw name confirmed in document"
            else:
                result["Audit Result"] = "NEEDS REVIEW"
                result["Notes"] = "Link live but bylaw name not found in document — may have been replaced"
        elif result["Link Status"] in ("TIMEOUT", "ERROR"):
            result["Audit Result"] = "LINK BROKEN"
            result["Notes"] = "Cannot verify — link timed out or errored"
        elif result["Link Status"] == "NO LINK":
            result["Audit Result"] = "NEEDS REVIEW"
            result["Notes"] = "No bylaw link stored in database"
        else:
            result["Audit Result"] = "LINK BROKEN"
            result["Notes"] = f"HTTP {result['Link Status']} — link may be dead"
    else:
        # Municipality currently marked as NO BY-LAW IN PLACE
        if lgd_found:
            result["Audit Result"] = "NEW LGD PROVISIONS"
            result["Notes"] = f"LGD keywords found in bylaw: {'; '.join(lgd_found[:3])}"
        elif link_clean and result["Link Status"] == "200 OK":
            result["Audit Result"] = "NO LGD PROVISIONS"
            result["Notes"] = "Has animal control bylaw but no LGD-specific provisions found"
        elif link_clean and result["Link Status"] != "200 OK":
            result["Audit Result"] = "NEEDS REVIEW"
            result["Notes"] = "Had a bylaw link but it's now broken — may have been replaced"
        elif not link_clean and not website_links:
            result["Audit Result"] = "NO ANIMAL CONTROL BYLAW"
            result["Notes"] = "No bylaw link and no animal control bylaw found on website"
        elif not link_clean and website_links:
            result["Audit Result"] = "NEEDS REVIEW"
            result["Notes"] = "No bylaw link in DB but animal-related links found on website"
        else:
            result["Audit Result"] = "NEEDS REVIEW"
            result["Notes"] = "Insufficient data to classify"

    return result


# ── Main ──

def main():
    parser = argparse.ArgumentParser(description="LGD Bylaw Accuracy Audit Scanner")
    parser.add_argument("--test", type=int, default=0,
                        help="Test mode: only scan first N municipalities")
    args = parser.parse_args()

    print("=" * 70)
    print("  LGD BYLAW ACCURACY AUDIT SCANNER")
    print(f"  Date: {datetime.date.today().isoformat()}")
    print("=" * 70)

    if not os.path.exists(DB_PATH):
        print(f"ERROR: Database not found at {DB_PATH}")
        return

    # ── Load data from SQLite ──
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    query = """
        SELECT m.name, m.geographic_area, m.municipal_status, m.website,
               b.progress_label, b.bylaw_name, b.bylaw_link, b.date_enacted,
               b.date_last_updated,
               d.has_lgd_definition, d.lgd_definition,
               d.has_herding_def, d.herding_definition,
               d.exempt_license_fees, d.collar_tag_req,
               d.barking_restrictions, d.exempt_barking, d.dog_limit
        FROM municipalities m
        JOIN bylaws b ON b.municipality_id = m.id AND b.category = 'LGD'
        LEFT JOIN details_lgd d ON d.bylaw_id = b.id
        WHERE m.municipal_status != 'Upper Tier'
        ORDER BY m.name
    """

    rows = [dict(r) for r in conn.execute(query).fetchall()]
    conn.close()

    if args.test > 0:
        # In test mode, grab a mix of WITH and WITHOUT bylaws
        with_bylaw = [r for r in rows if r["progress_label"] in ("COMPLETE", "COMPLETE - FARM FRIENDLY")]
        without_bylaw = [r for r in rows if r["progress_label"] not in ("COMPLETE", "COMPLETE - FARM FRIENDLY")]
        test_rows = with_bylaw[:min(args.test // 2, len(with_bylaw))] + \
                    without_bylaw[:min(args.test // 2, len(without_bylaw))]
        rows = test_rows[:args.test]
        print(f"\n  TEST MODE: Scanning {len(rows)} municipalities")

    total = len(rows)
    with_bylaw_count = sum(1 for r in rows if r["progress_label"] in ("COMPLETE", "COMPLETE - FARM FRIENDLY"))
    without_count = total - with_bylaw_count

    print(f"\n  Scope: {total} lower/single-tier municipalities")
    print(f"    WITH LGD bylaw:    {with_bylaw_count}")
    print(f"    WITHOUT provisions: {without_count}")
    print(f"    Threads: 20 concurrent")
    print(f"    PDF support: {'YES' if PDF_SUPPORT else 'NO'}")
    print(f"    HTML parser: {'YES' if BS4_SUPPORT else 'NO'}")
    print("-" * 70)

    # ── Concurrent scan ──
    results = []
    completed = 0
    start_time = time.time()

    # Track live counts per classification
    counts = {}

    with ThreadPoolExecutor(max_workers=20) as executor:
        future_to_name = {}
        for row in rows:
            future = executor.submit(audit_single_muni, row)
            future_to_name[future] = row["name"]

        for future in as_completed(future_to_name):
            completed += 1
            muni_name = future_to_name[future]

            try:
                result = future.result(timeout=90)
                results.append(result)

                classification = result["Audit Result"]
                counts[classification] = counts.get(classification, 0) + 1

                # Print notable findings immediately
                if classification in ("OUTDATED", "NEW LGD PROVISIONS", "LINK BROKEN"):
                    icon = {"OUTDATED": "🔄", "NEW LGD PROVISIONS": "🆕", "LINK BROKEN": "❌"}.get(classification, "⚠️")
                    print(f"  {icon} [{completed}/{total}] {muni_name}: {classification}")
                    if result.get("Notes"):
                        print(f"     └─ {result['Notes'][:120]}")
                elif completed % 25 == 0:
                    elapsed = time.time() - start_time
                    rate = completed / elapsed if elapsed > 0 else 0
                    eta = (total - completed) / rate if rate > 0 else 0
                    print(f"  ⏳ Progress: {completed}/{total} ({rate:.1f}/sec, ~{eta:.0f}s remaining)")

            except Exception as e:
                results.append({
                    "Municipality": muni_name,
                    "Audit Result": "ERROR",
                    "Notes": str(e)[:200],
                })
                completed += 1

    elapsed = time.time() - start_time

    # ── Summary ──
    print("\n" + "=" * 70)
    print("  AUDIT COMPLETE")
    print(f"  Scanned {total} municipalities in {elapsed:.1f} seconds")
    print("=" * 70)
    print("\n  Classification Summary:")
    for classification in ["CURRENT", "OUTDATED", "NEW LGD PROVISIONS", "NO LGD PROVISIONS",
                           "NO ANIMAL CONTROL BYLAW", "LINK BROKEN", "NEEDS REVIEW", "ERROR"]:
        count = counts.get(classification, 0)
        if count > 0:
            icon = {
                "CURRENT": "✅", "OUTDATED": "🔄", "NEW LGD PROVISIONS": "🆕",
                "NO LGD PROVISIONS": "⚪", "NO ANIMAL CONTROL BYLAW": "🚫",
                "LINK BROKEN": "❌", "NEEDS REVIEW": "⚠️", "ERROR": "💥",
            }.get(classification, "❓")
            pct = count / total * 100
            print(f"    {icon} {classification:30s} {count:4d}  ({pct:.1f}%)")

    # ── Save CSV ──
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output_file = os.path.join(OUTPUT_DIR, f"lgd_audit_{datetime.date.today().isoformat()}.csv")
    df = pd.DataFrame(results)

    # Order columns
    col_order = [
        "Municipality", "County", "Tier", "Region",
        "DB Status", "DB Bylaw Name", "DB Date Enacted", "DB Has LGD Def",
        "Audit Result", "Link Status", "Bylaw Name Match",
        "LGD Keywords Found", "Snippet", "Source URL",
        "Website Bylaw Links Found", "Notes",
    ]
    existing_cols = [c for c in col_order if c in df.columns]
    df = df[existing_cols]

    df.to_csv(output_file, index=False, encoding="utf-8-sig")
    print(f"\n  📄 Report saved to: {output_file}")

    # ── Highlight actionable items ──
    outdated = df[df["Audit Result"] == "OUTDATED"]
    new_lgd = df[df["Audit Result"] == "NEW LGD PROVISIONS"]
    broken = df[df["Audit Result"] == "LINK BROKEN"]
    review = df[df["Audit Result"] == "NEEDS REVIEW"]

    if not outdated.empty:
        print(f"\n  🔄 OUTDATED ({len(outdated)} municipalities need data refresh):")
        for _, r in outdated.iterrows():
            print(f"     - {r['Municipality']} ({r['County']}): {r['Notes'][:100]}")

    if not new_lgd.empty:
        print(f"\n  🆕 NEW LGD PROVISIONS ({len(new_lgd)} municipalities have new LGD language):")
        for _, r in new_lgd.iterrows():
            print(f"     - {r['Municipality']} ({r['County']}): {r['LGD Keywords Found'][:80]}")

    if not broken.empty:
        print(f"\n  ❌ LINK BROKEN ({len(broken)} municipalities need link repair):")
        for _, r in broken.head(10).iterrows():
            print(f"     - {r['Municipality']} ({r['County']}): {r['Link Status']}")
        if len(broken) > 10:
            print(f"     ... and {len(broken) - 10} more (see CSV)")

    if not review.empty:
        print(f"\n  ⚠️ NEEDS REVIEW ({len(review)} municipalities need manual investigation)")

    print("\n  Done! Review the CSV report and action the flagged municipalities.")


if __name__ == "__main__":
    main()
