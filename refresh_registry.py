"""
refresh_registry.py — Refresh portal_registry.csv with the latest document URLs.

Runs locally via Selenium to handle JS-heavy portals (eScribe, Legistar)
that the cloud-based Live Scanner can't spider with plain HTTP.

Usage:
    python refresh_registry.py              # Refresh all eScribe/Legistar portals
    python refresh_registry.py --portal escribe   # Only eScribe portals
    python refresh_registry.py --limit 10   # Process first 10 only (for testing)

This should be run periodically (e.g., weekly via Task Scheduler alongside
run_weekly_scan.bat) to keep the fallback URLs fresh.
"""

import os
import sys
import time
import argparse
import datetime
import pandas as pd
from bs4 import BeautifulSoup

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REGISTRY_PATH = os.path.join(SCRIPT_DIR, "signals", "portal_registry.csv")

# Portal types that need Selenium-based refresh
JS_PORTALS = ["escribe", "granicus_legistar", "(escribe)"]


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


def find_latest_minutes_escribe(driver, listing_url):
    """Navigate an eScribe portal to find the most recent council minutes PDF.

    eScribe portals load meeting lists via JavaScript. This function:
      1. Loads the main meetings page
      2. Waits for JS to render meeting entries
      3. Clicks into the most recent 'Council' meeting
      4. Finds the minutes/agenda PDF attachment link
    """
    try:
        driver.get(listing_url)
        time.sleep(5)  # Wait for AJAX to load meetings list

        soup = BeautifulSoup(driver.page_source, "html.parser")

        # eScribe renders meeting cards as divs with links inside
        # Look for links containing "Meeting" with dates
        meeting_links = []
        for link in soup.find_all("a", href=True):
            href = link["href"]
            text = link.get_text().strip()
            if "Meeting.aspx" in href and text:
                full_url = listing_url.rstrip("/") + "/" + href.lstrip("/")
                if "Id=" in href:
                    full_url = listing_url.split("/Meetings")[0] + "/" + href.lstrip("/")
                meeting_links.append((full_url, text))

        if not meeting_links:
            # Try finding meeting entries by class patterns
            for div in soup.find_all("div", class_=True):
                classes = " ".join(div.get("class", []))
                if "meeting" in classes.lower():
                    link = div.find("a", href=True)
                    if link:
                        href = link["href"]
                        text = link.get_text().strip()
                        base = listing_url.split("/Meetings")[0] if "/Meetings" in listing_url else listing_url.rstrip("/")
                        full_url = base + "/" + href.lstrip("/")
                        meeting_links.append((full_url, text))

        if not meeting_links:
            return None

        # Go to the first (most recent) meeting
        meeting_url = meeting_links[0][0]
        driver.get(meeting_url)
        time.sleep(4)

        # Look for PDF attachments
        soup2 = BeautifulSoup(driver.page_source, "html.parser")
        for link in soup2.find_all("a", href=True):
            href = link["href"]
            text = link.get_text().strip().lower()
            if href.lower().endswith(".pdf") or "FileStream" in href:
                if any(w in text for w in ["minute", "agenda", "package", "report"]):
                    base = meeting_url.split("/Meeting")[0] if "/Meeting" in meeting_url else meeting_url.rstrip("/")
                    return base + "/" + href.lstrip("/")

        # Fallback: return any PDF link found
        for link in soup2.find_all("a", href=True):
            href = link["href"]
            if href.lower().endswith(".pdf") or "FileStream" in href:
                base = meeting_url.split("/Meeting")[0] if "/Meeting" in meeting_url else meeting_url.rstrip("/")
                return base + "/" + href.lstrip("/")

        return None

    except Exception as e:
        print(f"    Error: {e}")
        return None


def find_latest_minutes_legistar(driver, listing_url):
    """Navigate a Legistar portal to find the most recent council minutes."""
    try:
        driver.get(listing_url)
        time.sleep(5)

        soup = BeautifulSoup(driver.page_source, "html.parser")

        # Legistar renders meeting rows in a grid/table
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if "View.ashx" in href and ("M=M" in href or "M=A" in href):
                return href if href.startswith("http") else listing_url.split("/Calendar")[0] + "/" + href.lstrip("/")

        return None

    except Exception as e:
        print(f"    Error: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(description="Refresh portal registry with latest document URLs.")
    parser.add_argument("--portal", choices=["escribe", "legistar", "all"], default="all",
                        help="Which portal types to refresh")
    parser.add_argument("--limit", type=int, default=0,
                        help="Limit number of municipalities to process (0 = all)")
    args = parser.parse_args()

    if not os.path.exists(REGISTRY_PATH):
        print(f"ERROR: Registry not found at {REGISTRY_PATH}")
        sys.exit(1)

    df = pd.read_csv(REGISTRY_PATH)
    print(f"Loaded {len(df)} municipalities from registry.")

    # Filter to target portals
    if args.portal == "escribe":
        targets = df[df["portal_type"].str.lower().str.contains("escribe", na=False)]
    elif args.portal == "legistar":
        targets = df[df["portal_type"].str.lower().str.contains("legistar", na=False)]
    else:
        targets = df[df["portal_type"].str.lower().isin([p.lower() for p in JS_PORTALS])]

    if args.limit > 0:
        targets = targets.head(args.limit)

    print(f"Targeting {len(targets)} JS-heavy portals for URL refresh.")

    if targets.empty:
        print("No targets found. Exiting.")
        return

    driver = setup_driver()
    updated = 0

    try:
        for idx, row in targets.iterrows():
            name = row["municipality_name"]
            portal_type = row["portal_type"].lower()
            listing_url = row.get("minutes_listing_url", "")

            if pd.isna(listing_url) or not str(listing_url).strip():
                continue

            listing_url = str(listing_url).strip()
            print(f"[{updated+1}/{len(targets)}] Refreshing {name} ({portal_type})...", end=" ")

            new_url = None
            if "escribe" in portal_type:
                new_url = find_latest_minutes_escribe(driver, listing_url)
            elif "legistar" in portal_type:
                new_url = find_latest_minutes_legistar(driver, listing_url)

            if new_url:
                df.at[idx, "example_recent_minutes_url"] = new_url
                df.at[idx, "example_recent_minutes_date"] = datetime.date.today().isoformat()
                updated += 1
                print(f"✅ Updated")
            else:
                print(f"⚠️ No new URL found")

    except KeyboardInterrupt:
        print("\nInterrupted by user.")
    finally:
        driver.quit()

    # Save updated registry
    if updated > 0:
        df.to_csv(REGISTRY_PATH, index=False)
        print(f"\n✅ SUCCESS: Updated {updated} URLs in portal_registry.csv")
        print(f"   Run 'git add signals/portal_registry.csv && git commit && git push' to deploy.")
    else:
        print("\nNo URLs were updated.")


if __name__ == "__main__":
    main()
