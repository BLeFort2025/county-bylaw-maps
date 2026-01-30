import pandas as pd
import time
import random
import os
import requests
import urllib3
from duckduckgo_search import DDGS

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- CONFIG ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REGISTRY_PATH = os.path.join(SCRIPT_DIR, "signals", "portal_registry.csv")
REPORT_PATH = os.path.join(SCRIPT_DIR, "coverage_report_2026-01-13.csv")

# Headers to look like a real browser (prevents 403s on validation)
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

def search_minutes_url(municipality_name):
    """Searches DDG for the official minutes page."""
    query = f"{municipality_name} Ontario council minutes agendas"
    print(f"   Searching: '{query}'...")
    
    try:
        with DDGS() as ddgs:
            # Get top 3 results
            results = list(ddgs.text(query, max_results=3))
            
            for res in results:
                url = res['href']
                # Filter out garbage results
                if "facebook" in url or "youtube" in url or "wikipedia" in url:
                    continue
                
                # Verify it's reachable
                try:
                    r = requests.get(url, headers=HEADERS, timeout=5, verify=False)
                    if r.status_code == 200:
                        return url
                except:
                    continue
    except Exception as e:
        print(f"   [!] Search Error: {e}")
        time.sleep(2) # Pause on error
        
    return None

def main():
    print("--- THE SEARCH HUNTER (DDG) ---")
    
    # 1. Load Registry
    if not os.path.exists(REGISTRY_PATH):
        print(f"Registry not found at {REGISTRY_PATH}")
        return
    df = pd.read_csv(REGISTRY_PATH)
    
    # 2. Identify Targets (Errors + St. Thomas Bug + Missing)
    targets = []
    
    # Priority: Errors from report
    if os.path.exists(REPORT_PATH):
        report = pd.read_csv(REPORT_PATH)
        # Filter for ANY non-success status
        mask = ~report['status'].isin(['scanned_html', 'scanned_pdf'])
        error_munids = report[mask]['munid'].tolist()
        targets.extend(error_munids)
    
    # Secondary: Registry entries that are empty or contain "stthomas" (the bug)
    bug_mask = df['example_recent_minutes_url'].astype(str).str.contains("stthomas.civicweb", na=False)
    empty_mask = df['example_recent_minutes_url'].isna() | (df['example_recent_minutes_url'] == '')
    
    targets.extend(df[bug_mask]['munid'].tolist())
    targets.extend(df[empty_mask]['munid'].tolist())
    
    # Deduplicate
    targets = list(set(targets))
    print(f"Targeting {len(targets)} broken municipalities...")
    
    fixed_count = 0
    
    for i, munid in enumerate(targets):
        # Find row
        mask = df['munid'] == munid
        if not mask.any(): continue
        
        name = df.loc[mask, 'municipality_name'].values[0]
        
        print(f"\n[{i+1}/{len(targets)}] Fixing: {name} ({munid})")
        
        # 3. Perform Search
        new_url = search_minutes_url(name)
        
        if new_url:
            print(f"   [+] FOUND: {new_url}")
            df.loc[mask, 'minutes_listing_url'] = new_url
            df.loc[mask, 'example_recent_minutes_url'] = new_url
            fixed_count += 1
            
            # Save every 5
            if fixed_count % 5 == 0:
                df.to_csv(REGISTRY_PATH, index=False)
                print(f"   >> SAVED PROGRESS ({fixed_count} fixed)")
        else:
            print("   [-] No valid link found.")
            
        # Sleep to be polite to search engine
        time.sleep(random.uniform(1.0, 2.5))

    if fixed_count > 0:
        df.to_csv(REGISTRY_PATH, index=False)
        print(f"\nSUCCESS: Search Hunter fixed {fixed_count} municipalities!")
    else:
        print("\nNo fixes found.")

if __name__ == "__main__":
    main()