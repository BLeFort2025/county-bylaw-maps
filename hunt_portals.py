import pandas as pd
import requests
from bs4 import BeautifulSoup
import os
import re
import urllib3
import time

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- CONFIG ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REGISTRY_PATH = os.path.join(SCRIPT_DIR, "signals", "portal_registry.csv")
REPORT_PATH = os.path.join(SCRIPT_DIR, "coverage_report_2026-01-13.csv") # Reads your latest report

# Headers to look like a real browser
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5'
}

# Keywords to look for in links
GOLDEN_KEYWORDS = ["civicweb", "escribemeetings", "siretechnologies", "agendasonline"]
SILVER_KEYWORDS = ["minutes", "agenda", "council meetings", "calendar"]

def get_homepage_candidates(name):
    """Generates likely homepage URLs for a municipality."""
    # Clean name: "AUGUSTA TP" -> "augusta"
    clean = re.sub(r'\s+(TP|M|C|T|V)$', '', name, flags=re.IGNORECASE).strip().lower()
    clean_nospace = clean.replace(" ", "")
    clean_hyphen = clean.replace(" ", "-")
    
    domains = [
        f"https://www.{clean_nospace}.ca",
        f"https://www.{clean_nospace}.on.ca",
        f"https://www.{clean_hyphen}.ca",
        f"https://www.{clean_hyphen}.on.ca",
        f"https://{clean_nospace}.ca",
        f"https://{clean_nospace}.on.ca",
        # Specific patterns
        f"https://www.townof{clean_nospace}.ca",
        f"https://www.municipalityof{clean_nospace}.ca",
        f"https://www.township.{clean_nospace}.on.ca"
    ]
    return domains

def hunt_for_portal(munid, name):
    print(f"\n[HUNTING] {name} ({munid})...")
    candidates = get_homepage_candidates(name)
    
    for url in candidates:
        try:
            # Short timeout to fail fast
            r = requests.get(url, headers=HEADERS, timeout=4, verify=False)
            if r.status_code == 200:
                print(f"  -> Connected to homepage: {url}")
                # Search for the golden link
                soup = BeautifulSoup(r.text, 'html.parser')
                
                # Strategy 1: Look for external portals (CivicWeb/Escribe)
                for link in soup.find_all('a', href=True):
                    href = link['href']
                    # Fix relative links
                    if href.startswith("/"):
                        href = url.rstrip("/") + href
                        
                    # Check Golden Keywords
                    if any(k in href.lower() for k in GOLDEN_KEYWORDS):
                        print(f"  [!!!] JACKPOT: Found Portal Link: {href}")
                        return href
                
                # Strategy 2: Look for internal "Minutes" pages
                for link in soup.find_all('a', href=True):
                    href = link['href']
                    text = link.get_text().lower()
                    
                    if any(k in text for k in SILVER_KEYWORDS):
                        # Filter out junk
                        if "contact" in href or "mailto" in href: continue
                        
                        # Fix relative
                        if href.startswith("/"):
                            href = url.rstrip("/") + href
                        elif not href.startswith("http"):
                            continue
                            
                        print(f"  [+] Found Minutes Page: {href}")
                        return href
                        
        except Exception:
            continue
            
    print("  [-] No portal found.")
    return None

def main():
    print("--- THE PORTAL HUNTER ---")
    
    # Load Registry
    if not os.path.exists(REGISTRY_PATH):
        print("Registry not found.")
        return
    df = pd.read_csv(REGISTRY_PATH)
    
    # Load Errors from Report
    targets = []
    if os.path.exists(REPORT_PATH):
        report = pd.read_csv(REPORT_PATH)
        # Target errors OR 'no_url_in_registry'
        mask = (report['status'] == 'error') | (report['status'] == 'no_url_in_registry')
        targets = report[mask]['munid'].tolist()
    else:
        print("Coverage report not found. Scanning ALL missing URL entries.")
        targets = df[df['example_recent_minutes_url'].isna()]['munid'].tolist()

    print(f"Targeting {len(targets)} broken municipalities...")
    
    fixed_count = 0
    
    for munid in targets:
        # Find row in registry
        mask = df['munid'] == munid
        if not mask.any(): continue
        
        name = df.loc[mask, 'municipality_name'].values[0]
        
        # Hunt!
        new_url = hunt_for_portal(munid, name)
        
        if new_url:
            df.loc[mask, 'minutes_listing_url'] = new_url
            df.loc[mask, 'example_recent_minutes_url'] = new_url
            fixed_count += 1
            
            # Save every 5 finds so we don't lose progress
            if fixed_count % 5 == 0:
                df.to_csv(REGISTRY_PATH, index=False)
                print(f"  >> SAVED PROGRESS ({fixed_count} fixed)")

    if fixed_count > 0:
        df.to_csv(REGISTRY_PATH, index=False)
        print(f"\nSUCCESS: Hunter found {fixed_count} new portals!")
    else:
        print("\nNo new portals found.")

if __name__ == "__main__":
    main()