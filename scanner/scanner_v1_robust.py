import pandas as pd
import requests
import os
import datetime
import urllib3
import io
import warnings
import sys

# --- 1. SETUP & IMPORTS ---
# Try importing pdfplumber for PDF text extraction
try:
    import pdfplumber
    PDF_SUPPORT = True
except ImportError:
    PDF_SUPPORT = False
    print("WARNING: 'pdfplumber' library not found. PDF documents will be skipped.")
    print("To fix: pip install pdfplumber")

# Suppress SSL warnings to keep output clean
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
warnings.simplefilter("ignore")

# --- 2. SMART CONFIGURATION ---
# This block finds the 'signals' folder no matter where you run the script from.

# Get the folder where THIS script is located (e.g., .../county-bylaw-maps/scanner)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Go up one level to the repo root (e.g., .../county-bylaw-maps)
REPO_ROOT = os.path.dirname(SCRIPT_DIR)

# Define paths relative to the Repo Root
REGISTRY_PATH = os.path.join(REPO_ROOT, "signals", "portal_registry.csv")
OUTPUT_DIR = os.path.join(REPO_ROOT, "signals")

# Fallback/Sanity Check: If REPO_ROOT looks wrong, try current directory
if not os.path.exists(REGISTRY_PATH):
    # Maybe we are already in the root?
    if os.path.exists("signals/portal_registry.csv"):
        REGISTRY_PATH = "signals/portal_registry.csv"
        OUTPUT_DIR = "signals"

KEYWORDS = [
    # --- The "Start Gun" (Background Studies) ---
    "Development Charges Background Study",
    "DC Background Study",
    "Development Charges Update Study",
    
    # --- The "Smoking Gun" (Drafting Laws) ---
    "Draft Development Charges By-law",
    "Proposed Development Charges By-law",
    "Passage of Development Charges By-law",
    
    # --- The "Public Process" (Meetings) ---
    "Statutory Public Meeting regarding Development Charges",
    "Notice of Public Meeting regarding Development Charges",
    "Development Charges Public Meeting",  # Safer catch-all
    
    # --- The "Agricultural Specific" (The Real Interest) ---
    "Agricultural Exemption Review",
    "Farm Building Exemption",
    "Bona Fide Farm",
    
    # --- The "Contextual Triggers" (Legislative Drivers) ---
    "More Homes Built Faster Act",  # Bill 23 trigger
    
    # --- NEW: High-Priority Legislative Terms ---
    "Community Benefits Charge",
    "Bill 185",
    "Comprehensive Zoning Bylaw"
]

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

# --- 3. HELPER FUNCTIONS ---

def check_keywords(text):
    """Returns True if any keyword is found in the text."""
    if not text: return None
    text_lower = text.lower()
    for k in KEYWORDS:
        if k.lower() in text_lower:
            return k # Return the specific keyword found
    return None

def extract_text_from_pdf(pdf_bytes):
    """Extracts text from PDF bytes using pdfplumber."""
    text = ""
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
    except Exception as e:
        return f"[PDF Error: {e}]"
    return text

def scan_municipality(row):
    """Downloads and scans a single municipality's minutes/agenda."""
    munid = row['munid']
    name = row['municipality_name']
    target_url = row.get('example_recent_minutes_url', None)

    coverage = {
        'munid': munid,
        'name': name,
        'scan_date': datetime.date.today(),
        'status': 'skipped',
        'error': '',
        'target_url': target_url
    }

    # Validation
    if pd.isna(target_url) or str(target_url).strip() == '':
        coverage['status'] = 'no_url_in_registry'
        return None, coverage

    try:
        # Download (Timeout 15s, verify=False for robust SSL)
        response = requests.get(target_url, headers=HEADERS, timeout=15, verify=False)
        response.raise_for_status()

        content_type = response.headers.get('Content-Type', '').lower()
        text_content = ""

        # --- PDF HANDLING ---
        if 'pdf' in content_type or str(target_url).lower().endswith('.pdf'):
            if PDF_SUPPORT:
                text_content = extract_text_from_pdf(response.content)
                coverage['status'] = 'scanned_pdf'
            else:
                coverage['status'] = 'pdf_skipped_no_lib'
        # --- HTML HANDLING ---
        else:
            text_content = response.text
            coverage['status'] = 'scanned_html'
            
        # Check Keywords
        trigger = check_keywords(text_content)
        if trigger:
            # Grab a snippet (clean up newlines for CSV safety)
            snippet = text_content[:300].replace('\n', ' ').replace('\r', '')
            candidate = {
                'munid': munid,
                'name': name,
                'found_url': target_url,
                'found_date': datetime.date.today(),
                'snippet': snippet,
                'trigger_keyword': trigger, # <--- NEW FIELD
                'keywords_detected': True
            }
            return candidate, coverage
                
    except Exception as e:
        coverage['status'] = 'error'
        coverage['error'] = str(e)
    
    return None, coverage

def main():
    print(f"--- STARTING SCANNER V2 (PDF ENABLED) ---")
    print(f"Reading Registry from: {os.path.abspath(REGISTRY_PATH)}")
    
    # 1. Load Registry
    if not os.path.exists(REGISTRY_PATH):
        print(f"ERROR: Registry file not found at {REGISTRY_PATH}")
        print("Please ensure 'portal_registry.csv' is in the 'signals' folder.")
        return
        
    try:
        df = pd.read_csv(REGISTRY_PATH)
        print(f"Loaded {len(df)} municipalities.")
    except Exception as e:
        print(f"ERROR reading CSV: {e}")
        return

    candidates = []
    coverage_log = []

    # 2. Run Scan
    print("Scanning...")
    for index, row in df.iterrows():
        # Print progress every 25 rows
        if index % 25 == 0:
            print(f"  Processing {index}/{len(df)}...")
            
        cand, cov = scan_municipality(row)
        coverage_log.append(cov)
        
        if cand:
            candidates.append(cand)
            print(f"  [!] HIT: {row['municipality_name']} ({cov['status']})")

    # 3. Save Results
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    today_str = datetime.date.today().strftime('%Y-%m-%d')
    
    # Save Coverage Report
    cov_path = os.path.join(OUTPUT_DIR, f"coverage_report_{today_str}.csv")
    pd.DataFrame(coverage_log).to_csv(cov_path, index=False)
    
    # Save Candidates File
    if candidates:
        cand_path = os.path.join(OUTPUT_DIR, f"candidates_minutes_{today_str}.csv")
        pd.DataFrame(candidates).to_csv(cand_path, index=False)
        print(f"\nSUCCESS: Found {len(candidates)} candidates.")
        print(f"Saved to: {cand_path}")
    else:
        print("\nScan complete. No keyword hits found.")
        
    print(f"Coverage report saved to: {cov_path}")

if __name__ == "__main__":
    main()