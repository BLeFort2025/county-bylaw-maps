"""
refresh_registry.py — Refresh portal_registry.csv with the latest document URLs.

Runs locally via Selenium to handle ALL portals where the cloud-based
HTTP spider can't find documents (eScribe, Legistar, Laserfiche, etc).

Usage:
    python refresh_registry.py                 # Refresh all stale/missing portals
    python refresh_registry.py --portal escribe  # Only eScribe portals
    python refresh_registry.py --limit 10        # Process first 10 only (testing)
    python refresh_registry.py --all             # Refresh ALL municipalities

The default mode ("smart") refreshes any municipality where:
  - minutes_listing_url == example_recent_minutes_url (no specific doc saved), OR
  - example_recent_minutes_date is older than 30 days

This runs automatically as Step 0 in run_weekly_scan.bat.
"""

import os
import sys
import time
import re
import argparse
import datetime
import pandas as pd
import urllib.parse
from bs4 import BeautifulSoup

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REGISTRY_PATH = os.path.join(SCRIPT_DIR, "signals", "portal_registry.csv")


def setup_driver():
    """Configure headless Chrome for fast page loads."""
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--log-level=3")
    options.page_load_strategy = "eager"
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()), options=options
    )
    driver.set_page_load_timeout(30)
    return driver


def find_latest_document(driver, listing_url):
    """Universal document finder — works for any portal type.

    Uses Selenium to load the page (JS renders), then searches for
    the most recent PDF or document link. Tries multiple strategies:
      1. Direct PDF links on the page
      2. Links with meeting/minutes keywords → follow → find PDF
      3. CivicWeb filepro folder navigation
      4. eScribe meeting page navigation
    """
    try:
        driver.get(listing_url)
        time.sleep(5)  # Wait for JS to render

        soup = BeautifulSoup(driver.page_source, "html.parser")

        # ── Strategy 1: Direct PDF links on the page ──
        pdf_links = _find_pdf_links(soup, listing_url)
        if pdf_links:
            # Sort by date if possible, return the most recent
            best = _pick_most_recent(pdf_links)
            if best:
                return best

        # ── Strategy 2: Follow meeting/agenda links to find PDFs ──
        meeting_links = _find_meeting_page_links(soup, listing_url)
        for meeting_url, _ in meeting_links[:3]:  # Check top 3 meetings
            try:
                driver.get(meeting_url)
                time.sleep(3)
                meeting_soup = BeautifulSoup(driver.page_source, "html.parser")
                pdf_links = _find_pdf_links(meeting_soup, meeting_url)
                if pdf_links:
                    return _pick_most_recent(pdf_links)
            except Exception:
                continue

        # ── Strategy 3: CivicWeb folder navigation ──
        if "civicweb.net" in listing_url:
            result = _navigate_civicweb(driver, soup, listing_url)
            if result:
                return result

        # ── Strategy 4: Laserfiche folder navigation ──
        iframes = soup.find_all("iframe")
        for iframe in iframes:
            src = iframe.get("src", "")
            if src and "laserfiche" in src.lower() or "weblink" in src.lower():
                result = _navigate_laserfiche(driver, urllib.parse.urljoin(listing_url, src))
                if result:
                    return result
        # Also check if the URL itself is already Laserfiche
        if "weblink/browse.aspx" in listing_url.lower():
            result = _navigate_laserfiche(driver, listing_url)
            if result:
                return result

        return None

    except Exception as e:
        # Silencing error print out so it doesn't clutter the Auto-Healing logs
        return None


def _find_pdf_links(soup, base_url):
    """Extract all PDF and document download links from a page."""
    results = []
    for link in soup.find_all("a", href=True):
        href = link["href"]
        text = link.get_text().strip()
        full_url = urllib.parse.urljoin(base_url, href)

        if href.startswith("javascript:") or href == "#":
            continue

        is_doc = (
            full_url.lower().endswith(".pdf") or
            "FileStream" in href or
            "View.ashx" in href or
            "download" in href.lower()
        )

        if is_doc:
            date_hint = _extract_date(text + " " + full_url)
            results.append((full_url, text, date_hint))

    return results


def _find_meeting_page_links(soup, base_url):
    """Find links to individual meeting pages (not documents)."""
    results = []
    for link in soup.find_all("a", href=True):
        href = link["href"]
        text = link.get_text().strip().lower()

        if href.startswith("javascript:") or href == "#":
            continue

        # eScribe: Meeting.aspx?Id=...
        # General: links with meeting/minutes/agenda/council keywords
        is_meeting = (
            "Meeting.aspx" in href or
            any(w in text for w in ["regular council", "council meeting", "regular meeting",
                                    "special council", "committee of the whole"])
        )

        if is_meeting:
            full_url = urllib.parse.urljoin(base_url, href)
            date_hint = _extract_date(text + " " + full_url)
            results.append((full_url, text, date_hint))

    # Sort: most recent first
    dated = [(u, t, d) for u, t, d in results if d is not None]
    undated = [(u, t, d) for u, t, d in results if d is None]
    dated.sort(key=lambda x: x[2], reverse=True)
    return [(u, t) for u, t, _ in dated + undated]


def _navigate_civicweb(driver, soup, base_url):
    """Navigate CivicWeb filepro folder tree to find latest document."""
    try:
        links = soup.find_all("a", href=True)

        # Find Minutes or Documents folder
        for link in links:
            href = link["href"]
            text = link.get_text().strip().lower()
            full = urllib.parse.urljoin(base_url, href)
            if "filepro/documents" in href and ("minute" in text or "document" in text):
                driver.get(full)
                time.sleep(3)
                folder_soup = BeautifulSoup(driver.page_source, "html.parser")

                # Look for year folders — pick the latest
                year_folders = []
                for fl in folder_soup.find_all("a", href=True):
                    ft = fl.get_text().strip()
                    fh = fl["href"]
                    if ft.isdigit() and len(ft) == 4 and "filepro/documents" in fh:
                        year_folders.append((urllib.parse.urljoin(full, fh), int(ft)))

                if year_folders:
                    year_folders.sort(key=lambda x: x[1], reverse=True)
                    driver.get(year_folders[0][0])
                    time.sleep(3)
                    year_soup = BeautifulSoup(driver.page_source, "html.parser")

                    # Find FileStream download links
                    for dl in year_soup.find_all("a", href=True):
                        if "filestream" in dl["href"].lower():
                            return urllib.parse.urljoin(year_folders[0][0], dl["href"])

                # If no year folders, check for direct filestream links
                for dl in folder_soup.find_all("a", href=True):
                    if "filestream" in dl["href"].lower():
                        return urllib.parse.urljoin(full, dl["href"])

                break  # Only try the first matching folder

    except Exception:
        pass
    return None


def _navigate_laserfiche(driver, base_url):
    """Navigate Laserfiche WebLink folders to find the latest PDF.
    Transforms DocView.aspx links into ElectronicFile.aspx PDF downloads.
    """
    try:
        driver.get(base_url)
        time.sleep(5)
        soup = BeautifulSoup(driver.page_source, "html.parser")

        # Step 1: Look for Council / Minutes folder
        council_url = None
        for link in soup.find_all("a", href=True):
            href = link["href"]
            text = link.get_text().strip().lower()
            if "browse.aspx" in href.lower() and ("council" in text or "minute" in text):
                council_url = urllib.parse.urljoin(base_url, href)
                break
        
        if not council_url and "browse.aspx" in base_url.lower():
            council_url = base_url

        if council_url:
            driver.get(council_url)
            time.sleep(4)
            soup = BeautifulSoup(driver.page_source, "html.parser")

            # Step 2: Find the most recent year folder
            year_folders = []
            for link in soup.find_all("a", href=True):
                text = link.get_text().strip()
                href = link["href"]
                if "browse.aspx" in href.lower() and text.isdigit() and len(text) == 4:
                    year_folders.append((urllib.parse.urljoin(council_url, href), int(text)))
            
            if year_folders:
                year_folders.sort(key=lambda x: x[1], reverse=True)
                latest_year_url = year_folders[0][0]
                driver.get(latest_year_url)
                time.sleep(4)
                soup = BeautifulSoup(driver.page_source, "html.parser")

                # Step 3: Find highest numbered month/date folder
                date_folders = []
                for link in soup.find_all("a", href=True):
                    text = link.get_text().strip()
                    href = link["href"]
                    # Usually "12 December" or "12", so try to extract leading number
                    if "browse.aspx" in href.lower() and text:
                        match = re.match(r"^(\d+)", text)
                        if match:
                            date_folders.append((urllib.parse.urljoin(latest_year_url, href), int(match.group(1))))
                
                if date_folders:
                    date_folders.sort(key=lambda x: x[1], reverse=True)
                    latest_date_url = date_folders[0][0]
                    driver.get(latest_date_url)
                    time.sleep(4)
                    soup = BeautifulSoup(driver.page_source, "html.parser")
            
            # Step 4: Now find DocView links
            doc_links = []
            for link in soup.find_all("a", href=True):
                href = link["href"]
                text = link.get_text().strip().lower()
                if "docview.aspx" in href.lower() and ("council" in text or "minute" in text or "agenda" in text):
                    doc_links.append(urllib.parse.urljoin(driver.current_url, href))
            
            # Fallback to any DocView link if none specify council/minutes
            if not doc_links:
                for link in soup.find_all("a", href=True):
                    if "docview.aspx" in link["href"].lower():
                        doc_links.append(urllib.parse.urljoin(driver.current_url, link["href"]))

            if doc_links:
                # Convert DocView.aspx to ElectronicFile.aspx direct PDF link
                selected = doc_links[0]
                return selected.replace("DocView.aspx", "ElectronicFile.aspx").replace("docid=", "id=") # Some laserfiche use id= some docid=
                # Actually ElectronicFile uses docid= but DocView uses id=, so let's do safe replace
                
                # Best way is to construct the new URL manually
                parsed = urllib.parse.urlparse(selected)
                query = urllib.parse.parse_qs(parsed.query)
                doc_id = query.get("id", [""])[0]
                repo = query.get("repo", [""])[0]
                dbid = query.get("dbid", ["0"])[0]
                
                new_query = urllib.parse.urlencode({
                    "docid": doc_id,
                    "dbid": dbid,
                    "repo": repo
                })
                # Construct path
                new_path = parsed.path.replace("DocView.aspx", "ElectronicFile.aspx")
                return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, new_path, "", new_query, ""))
                
    except Exception as e:
        print(f" Laserfiche error: {e}")
    return None


def _extract_date(text):
    """Try to extract a date from text for sorting by recency."""
    text = text.lower()
    months = {
        'january': 1, 'february': 2, 'march': 3, 'april': 4,
        'may': 5, 'june': 6, 'july': 7, 'august': 8,
        'september': 9, 'october': 10, 'november': 11, 'december': 12
    }
    for m_name, m_num in months.items():
        match = re.search(rf'{m_name}\s+(\d{{1,2}}),?\s*(\d{{4}})', text)
        if match:
            try:
                return datetime.date(int(match.group(2)), m_num, int(match.group(1)))
            except ValueError:
                pass

    match = re.search(r'(\d{4})[-/](\d{1,2})[-/](\d{1,2})', text)
    if match:
        try:
            return datetime.date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except ValueError:
            pass
    return None


def _pick_most_recent(pdf_links):
    """From a list of (url, text, date_hint), return the most recent URL."""
    if not pdf_links:
        return None
    dated = [(u, t, d) for u, t, d in pdf_links if d is not None]
    if dated:
        dated.sort(key=lambda x: x[2], reverse=True)
        return dated[0][0]
    # No dates found — return the first link (usually most recent on the page)
    return pdf_links[0][0]


def _auto_heal_url(driver, muni_name):
    """Uses DuckDuckGo via Selenium to find the latest portal URL.
    
    Validates that search results actually belong to the target municipality
    by checking the domain/URL against the municipality name. This prevents
    false matches (e.g., stclair.civicweb.net being saved for Kingston).
    """
    # Build a set of name tokens for validation (e.g., "NORTH BAY" -> {"north", "bay"})
    name_tokens = set(muni_name.lower().replace("-", " ").split())
    # Remove common suffixes that won't appear in URLs
    name_tokens -= {"tp", "m", "c", "township", "municipality", "city", "town", "of", "and", "the"}
    # Build a slug for direct URL guessing (e.g., "North Bay" -> "northbay")
    name_slug = re.sub(r'[^a-z]', '', muni_name.lower().replace(" ", ""))
    # Also try hyphenated version (e.g., "north-bay")
    name_hyphen = re.sub(r'[^a-z-]', '', muni_name.lower().replace(" ", "-"))

    search_query = f"{muni_name} Ontario municipal council minutes agendas"
    search_url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(search_query)}"
    candidates = []
    try:
        driver.get(search_url)
        time.sleep(3)
        soup = BeautifulSoup(driver.page_source, "html.parser")
        for a in soup.find_all("a", class_="result__url", href=True):
            href = a["href"]
            if "uddg=" in href:
                decoded = urllib.parse.unquote(href.split("uddg=")[1].split("&")[0])
                candidates.append(decoded)
    except Exception:
        pass  # Silent fail for the search itself

    def _url_matches_muni(url):
        """Check if the URL plausibly belongs to this municipality."""
        url_lower = url.lower()
        # Check if the slug appears in the domain/path
        if name_slug in url_lower:
            return True
        if name_hyphen in url_lower:
            return True
        # Check if at least one significant name token appears in the URL
        for token in name_tokens:
            if len(token) >= 4 and token in url_lower:
                return True
        return False

    # Filter and prioritize: only keep URLs that match the municipality name
    validated = []
    fallback = []
    for c in candidates:
        if _url_matches_muni(c):
            if "civicweb.net" in c.lower() or "escribemeetings.com" in c.lower() or "pub-" in c.lower():
                validated.insert(0, c)
            else:
                validated.append(c)
        else:
            fallback.append(c)

    # If no validated matches, try common portal URL patterns directly
    if not validated:
        guesses = [
            f"https://pub-{name_slug}.escribemeetings.com/",
            f"https://{name_slug}.civicweb.net/Portal/",
        ]
        validated.extend(guesses)

    # Add non-portal fallbacks (municipal websites) that match the name
    for f in fallback:
        if _url_matches_muni(f):
            validated.append(f)

    # Return top 5 unique candidates
    unique = []
    for p in validated:
        if p not in unique:
            unique.append(p)
    return unique[:5]



def main():
    parser = argparse.ArgumentParser(description="Refresh portal registry with latest document URLs.")
    parser.add_argument("--portal", choices=["escribe", "legistar", "all"], default="all",
                        help="Filter by portal type")
    parser.add_argument("--limit", type=int, default=0,
                        help="Limit number of municipalities to process (0 = all)")
    parser.add_argument("--all", action="store_true",
                        help="Refresh ALL municipalities, not just stale ones")
    args = parser.parse_args()

    if not os.path.exists(REGISTRY_PATH):
        print(f"ERROR: Registry not found at {REGISTRY_PATH}")
        sys.exit(1)

    df = pd.read_csv(REGISTRY_PATH)
    print(f"Loaded {len(df)} municipalities from registry.")

    # Determine which municipalities need refreshing
    if args.all:
        targets = df.copy()
    elif args.portal == "escribe":
        targets = df[df["portal_type"].str.lower().str.contains("escribe", na=False)]
    elif args.portal == "legistar":
        targets = df[df["portal_type"].str.lower().str.contains("legistar", na=False)]
    else:
        # Smart mode: refresh any municipality that needs it
        listing = df["minutes_listing_url"].fillna("").str.strip().str.rstrip("/")
        example = df["example_recent_minutes_url"].fillna("").str.strip().str.rstrip("/")

        # Condition 1: listing URL == example URL (no specific document saved)
        same_url = listing == example

        # Condition 2: example_recent_minutes_date is older than 30 days or missing
        cutoff = (datetime.date.today() - datetime.timedelta(days=30)).isoformat()
        stale_date = df["example_recent_minutes_date"].fillna("") < cutoff

        targets = df[same_url | stale_date]

    if args.limit > 0:
        targets = targets.head(args.limit)

    print(f"Targeting {len(targets)} municipalities for URL refresh.")

    if targets.empty:
        print("No targets found. Exiting.")
        return

    driver = setup_driver()
    updated = 0
    failed = 0

    try:
        for count, (idx, row) in enumerate(targets.iterrows(), 1):
            name = row["municipality_name"]
            portal_type = str(row.get("portal_type", "unknown"))
            listing_url = row.get("minutes_listing_url", "")

            if pd.isna(listing_url) or not str(listing_url).strip():
                continue

            listing_url = str(listing_url).strip()
            print(f"[{count}/{len(targets)}] {name} ({portal_type})...", end=" ", flush=True)

            new_url = find_latest_document(driver, listing_url)

            if new_url:
                df.at[idx, "example_recent_minutes_url"] = new_url
                df.at[idx, "example_recent_minutes_date"] = datetime.date.today().isoformat()
                updated += 1
                print("OK")
            else:
                print("failed. Auto-healing...", end=" ", flush=True)
                candidates = _auto_heal_url(driver, name)
                healed = False
                for cand_url in candidates:
                    try_url = find_latest_document(driver, cand_url)
                    if try_url:
                        # Found a working URL! Update the base listing url too
                        df.at[idx, "minutes_listing_url"] = cand_url
                        df.at[idx, "example_recent_minutes_url"] = try_url
                        df.at[idx, "example_recent_minutes_date"] = datetime.date.today().isoformat()
                        updated += 1
                        healed = True
                        print("HEALED!")
                        break
                
                if not healed:
                    failed += 1
                    print("still failed")

    except KeyboardInterrupt:
        print("\nInterrupted by user.")
    finally:
        driver.quit()

    # Save updated registry
    if updated > 0:
        df.to_csv(REGISTRY_PATH, index=False)
        print(f"\n{'='*50}")
        print(f"DONE: Updated {updated} URLs ({failed} failed)")
        print(f"   Registry saved to {REGISTRY_PATH}")
    else:
        print(f"\nNo URLs were updated ({failed} failed).")


if __name__ == "__main__":
    main()
