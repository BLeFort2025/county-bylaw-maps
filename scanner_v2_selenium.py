import pandas as pd
import os
import datetime
import time
import glob
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

# --- CONFIG ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REGISTRY_PATH = os.path.join(SCRIPT_DIR, "signals", "portal_registry.csv")
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "signals")

KEYWORDS = [
    # The "Early Warning" - Council is opening the bylaw
    "Development Charges Background Study",
    "DC Background Study",
    "Development Charges Update Study",
    
    # The "Active Legislation" - A new law is being written
    "Draft Development Charges By-law",
    "Proposed Development Charges By-law",
    
    # The "Process" - Public input is being sought (mandatory legal step)
    "Statutory Public Meeting regarding Development Charges",
    "Notice of Public Meeting regarding Development Charges",
    
    # The "Specific Threat" - Explicit review of your interest
    "Agricultural Exemption Review"
]

def find_latest_report():
    """Automatically finds the most recent coverage report."""
    # Look in 'signals' folder first, then root
    search_paths = [
        os.path.join(SCRIPT_DIR, "signals", "coverage_report_*.csv"),
        os.path.join(SCRIPT_DIR, "coverage_report_*.csv")
    ]
    
    found_files = []
    for p in search_paths:
        found_files.extend(glob.glob(p))
    
    if not found_files:
        return None
    
    # Sort by name (which includes date) to get the latest
    return sorted(found_files)[-1]

def setup_driver():
    """Configures a headless Chrome browser."""
    options = Options()
    options.add_argument("--headless=new") 
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    return driver

def check_keywords(text):
    if not text: return None
    text_lower = text.lower()
    for k in KEYWORDS:
        if k.lower() in text_lower:
            return k
    return None

def scan_with_selenium(driver, row):
    munid = row['munid']
    name = row['municipality_name']
    url = row.get('example_recent_minutes_url', '')

    coverage = {
        'munid': munid,
        'name': name,
        'scan_date': datetime.date.today(),
        'status': 'skipped',
        'error': '',
        'target_url': url
    }

    if pd.isna(url) or str(url).strip() == '':
        coverage['status'] = 'no_url'
        return None, coverage

    try:
        driver.get(url)
        # Wait for Javascript to load
        time.sleep(3)
        
        page_text = driver.find_element("tag name", "body").text
        
        coverage['status'] = 'scanned_selenium'
        
        trigger = check_keywords(page_text)
        if trigger:
            candidate = {
                'munid': munid,
                'name': name,
                'found_url': url,
                'found_date': datetime.date.today(),
                'snippet': page_text[:300].replace('\n', ' '),
                'trigger_keyword': trigger, # <--- NEW
                'keywords_detected': True
            }
            return candidate, coverage

    except Exception as e:
        coverage['status'] = 'error'
        coverage['error'] = str(e)

    return None, coverage

def main():
    print("--- STARTING SELENIUM SCANNER (TARGETING FAILURES) ---")
    
    # 1. Find Report
    report_path = find_latest_report()
    if not report_path:
        print("ERROR: No previous coverage report found.")
        print("Please run 'python scanner_v1_robust.py' first.")
        return
        
    print(f"Using report: {os.path.basename(report_path)}")
    report = pd.read_csv(report_path)
    
    # 2. Identify Targets (Failures only)
    targets = report[~report['status'].isin(['scanned_html', 'scanned_pdf'])]
    
    if targets.empty:
        print("No failures found to retry!")
        return

    # Merge with registry
    if not os.path.exists(REGISTRY_PATH):
        # Try finding it in root if not in signals
        alt_path = os.path.join(SCRIPT_DIR, "portal_registry.csv")
        if os.path.exists(alt_path):
            reg = pd.read_csv(alt_path)
        else:
            print("ERROR: Registry not found.")
            return
    else:
        reg = pd.read_csv(REGISTRY_PATH)
        
    target_data = reg[reg['munid'].isin(targets['munid'])]
    
    print(f"Targeting {len(target_data)} municipalities...")
    
    # 3. Start Scanning
    driver = setup_driver()
    candidates = []
    
    try:
        for index, row in target_data.iterrows():
            print(f"Scanning: {row['municipality_name']}...", end="\r")
            cand, cov = scan_with_selenium(driver, row)
            
            if cand:
                candidates.append(cand)
                print(f"  [!] HIT: {row['municipality_name']}                         ")
    except KeyboardInterrupt:
        print("\nStopping scan...")
    finally:
        driver.quit()

    # 4. Save Results
    today_str = datetime.date.today().strftime('%Y-%m-%d')
    if candidates:
        cand_path = os.path.join(OUTPUT_DIR, f"candidates_selenium_{today_str}.csv")
        pd.DataFrame(candidates).to_csv(cand_path, index=False)
        print(f"\nSUCCESS: Selenium found {len(candidates)} NEW candidates.")
        print(f"Saved to: {cand_path}")
    else:
        print("\nScan complete. No new hits found.")

if __name__ == "__main__":
    main()