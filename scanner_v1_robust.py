import pandas as pd
import requests
import os
import datetime
import urllib3
import io
import warnings
import sys

# --- 1. SETUP & IMPORTS ---
try:
    import pdfplumber
    PDF_SUPPORT = True
except ImportError:
    PDF_SUPPORT = False
    print("WARNING: 'pdfplumber' library not found. PDF documents will be skipped.")

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
warnings.simplefilter("ignore")

# --- 2. SMART CONFIGURATION ---
# Get the folder where THIS script is located (The Repo Root)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = SCRIPT_DIR  # We are already in the root

# Define paths relative to the Repo Root
REGISTRY_PATH = os.path.join(REPO_ROOT, "signals", "portal_registry.csv")
OUTPUT_DIR = os.path.join(REPO_ROOT, "signals")

# --- 3. CATEGORY & KEYWORD DEFINITIONS ---
KEYWORD_CONFIG = {
    "DC": [
        "Development Charges Background Study", "DC Background Study",
        "Development Charges Update Study", "Draft Development Charges By-law",
        "Proposed Development Charges By-law", "Passage of Development Charges By-law",
        "Statutory Public Meeting regarding Development Charges",
        "Notice of Public Meeting regarding Development Charges",
        "Development Charges Public Meeting", "Agricultural Exemption Review",
        "Farm Building Exemption", "Bona Fide Farm", "More Homes Built Faster Act",
        "Community Benefits Charge", "Bill 185", "Comprehensive Zoning Bylaw"
    ],
    "STORMWATER": [
        "Stormwater Rate Study", "Stormwater Utility Feasibility",
        "Impervious Area Charge", "Runoff Management Fee",
        "Drainage Master Plan", "Stormwater User Fee",
        "Stormwater Funding Model"
    ],
    "SITE_ALT": [
        "Site Alteration Bylaw", "Fill Bylaw", "Topsoil Preservation", 
        "Topsoil Removal", "Dumping of Fill", "Large Scale Fill Agreement", 
        "Commercial Fill Operation"
    ],
    "TREES": [
        "Tree Cutting Bylaw", "Private Tree Protection", 
        "Woodland Conservation Bylaw", "Forest Conservation Bylaw", 
        "Tree Canopy Strategy", "Significant Woodland Review", 
        "Stop Work Order - Trees"
    ],
    "CHICKENS": [
        "Backyard Hens", "Urban Hens Pilot", "Backyard Poultry", 
        "Keeping of Animals Bylaw", "Chicken Coop Regulations",
        "Council" # <--- TEMPORARY TEST KEYWORD (Remove later)
    ],
    "LGD": [
        "Animal Control Bylaw Review", "Dog Control Bylaw", 
        "Kennel By-law", "Livestock Guardian Dog", 
        "Working Dog Exemption", "Dog Licensing Fee Review"
    ],
    "FENCES": [
        "Fence Bylaw", "Division Fence", "Line Fences Act", 
        "Cost of Division Fences"
    ]
}

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

# --- 4. HELPER FUNCTIONS ---

def check_keywords(text):
    """Returns (keyword, category) if found."""
    if not text: return None, None
    text_lower = text.lower()
    for cat, phrases in KEYWORD_CONFIG.items():
        for p in phrases:
            if p.lower() in text_lower:
                return p, cat
    return None, None

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
        trigger, category = check_keywords(text_content)
        if trigger:
            snippet = text_content[:300].replace('\n', ' ').replace('\r', '')
            candidate = {
                'munid': munid,
                'name': name,
                'found_url': target_url,
                'found_date': datetime.date.today(),
                'snippet': snippet,
                'trigger_keyword': trigger,
                'category': category,
                'keywords_detected': True
            }
            return candidate, coverage
                
    except Exception as e:
        coverage['status'] = 'error'
        coverage['error'] = str(e)
    
    return None, coverage

def main():
    print(f"--- STARTING SCANNER V1 (Updated Categories) ---")
    print(f"Script Location: {SCRIPT_DIR}")
    print(f"Registry Path: {REGISTRY_PATH}")
    
    # 1. Load Registry
    if not os.path.exists(REGISTRY_PATH):
        print(f"ERROR: Registry file not found at {REGISTRY_PATH}")
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
        if index % 25 == 0:
            print(f"  Processing {index}/{len(df)}...")
            
        cand, cov = scan_municipality(row)
        coverage_log.append(cov)
        
        if cand:
            candidates.append(cand)
            print(f"  [!] HIT: {row['municipality_name']} -> {cand['category']} ({cand['trigger_keyword']})")

    # 3. Save Results
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    today_str = datetime.date.today().strftime('%Y-%m-%d')
    
    cov_path = os.path.join(OUTPUT_DIR, f"coverage_report_{today_str}.csv")
    pd.DataFrame(coverage_log).to_csv(cov_path, index=False)
    
    if candidates:
        cand_path = os.path.join(OUTPUT_DIR, f"candidates_minutes_{today_str}.csv")
        pd.DataFrame(candidates).to_csv(cand_path, index=False)
        print(f"\nSUCCESS: Found {len(candidates)} candidates.")
    else:
        print("\nScan complete. No keyword hits found.")

if __name__ == "__main__":
    main()