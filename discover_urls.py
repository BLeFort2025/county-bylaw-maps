import pandas as pd
import requests
import os
import urllib3
import re

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- CONFIG ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REGISTRY_PATH = os.path.join(SCRIPT_DIR, "signals", "portal_registry.csv")
REPORT_PATH = os.path.join(SCRIPT_DIR, "coverage_report_2026-01-13.csv")

# Common patterns for Ontario municipal portals
# {clean} = name with spaces removed, lowercase
# {clean_hyphen} = name with spaces replaced by hyphens
PATTERNS = [
    "https://{clean}.civicweb.net/Portal/",
    "https://pub-{clean}.escribemeetings.com/",
    "https://pub-{clean_hyphen}.escribemeetings.com/",
    "https://{clean}.ca/council/minutes",
    "https://{clean}.ca/town-hall/council-meetings",
    "https://{clean}.com/council/minutes-agendas/"
]

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

def clean_name(name):
    # Remove "TP", "M", "C" suffixes and clean up
    name = re.sub(r'\s+(TP|M|C|T|V)$', '', name, flags=re.IGNORECASE)
    return name.strip().lower()

def check_url(url):
    try:
        response = requests.get(url, headers=HEADERS, timeout=5, verify=False)
        if response.status_code == 200:
            # simple check to make sure it's not a generic "parked domain" page
            if "council" in response.text.lower() or "agenda" in response.text.lower() or "civicweb" in url or "escribe" in url:
                return True
    except:
        pass
    return False

def main():
    print("--- AUTOMATED URL DISCOVERY TOOL ---")
    
    # 1. Load Registry
    if not os.path.exists(REGISTRY_PATH):
        print("Error: Registry not found.")
        return
    df = pd.read_csv(REGISTRY_PATH)
    
    # 2. Identify Targets (Errors + Missing)
    # If we have a coverage report, prioritize errors from there
    targets = []
    
    # Check for empty URLs in registry
    missing_mask = df['example_recent_minutes_url'].isna() | (df['example_recent_minutes_url'] == '')
    targets.extend(df[missing_mask]['munid'].tolist())
    
    # If report exists, add errors
    if os.path.exists(REPORT_PATH):
        report = pd.read_csv(REPORT_PATH)
        error_munids = report[report['status'] == 'error']['munid'].tolist()
        targets.extend(error_munids)
    
    targets = list(set(targets)) # Unique list
    print(f"Targeting {len(targets)} municipalities with missing or broken URLs...")
    
    fixed_count = 0
    
    for munid in targets:
        # Get current row index
        idx = df.index[df['munid'] == munid].tolist()
        if not idx: continue
        idx = idx[0]
        
        raw_name = df.at[idx, 'municipality_name']
        base_name = clean_name(str(raw_name))
        
        print(f"Scanning: {raw_name}...", end="\r")
        
        found_url = None
        
        # Generate variations
        variations = {
            "clean": base_name.replace(" ", ""),
            "clean_hyphen": base_name.replace(" ", "-")
        }
        
        for pattern in PATTERNS:
            test_url = pattern.format(**variations)
            if check_url(test_url):
                print(f"  [+] FOUND: {munid} -> {test_url}")
                found_url = test_url
                break # Stop after first success
        
        if found_url:
            df.at[idx, 'minutes_listing_url'] = found_url
            df.at[idx, 'example_recent_minutes_url'] = found_url
            fixed_count += 1
            
            # Save progressively every 5 finds
            if fixed_count % 5 == 0:
                df.to_csv(REGISTRY_PATH, index=False)
                print(f"  (Saved progress: {fixed_count} fixed)")

    # Final Save
    if fixed_count > 0:
        df.to_csv(REGISTRY_PATH, index=False)
        print(f"\nSUCCESS: Automated Discovery fixed {fixed_count} municipalities!")
    else:
        print("\nNo new URLs discovered using standard patterns.")

if __name__ == "__main__":
    main()