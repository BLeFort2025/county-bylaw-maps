import pandas as pd
import requests
import os
import datetime
import urllib3
import io
import warnings
import sys
import re
from urllib.parse import urljoin
from concurrent.futures import ThreadPoolExecutor, as_completed

# Import shared config so terminal script and Streamlit UI stay in sync
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shared_config import (
    REGION_MAPPING, get_region, extract_readable_snippet,
    CUSTOM_KEYWORD_PACKS,
)

try:
    import pdfplumber
    PDF_SUPPORT = True
except ImportError:
    PDF_SUPPORT = False

import sqlite3

# REGION_MAPPING, get_region, extract_readable_snippet imported from shared_config

from bs4 import BeautifulSoup
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
warnings.simplefilter("ignore")

# Define paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REGISTRY_PATH = os.path.join(SCRIPT_DIR, "signals", "portal_registry.csv")
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "signals")

# extract_readable_snippet imported from shared_config

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

# Flatten all keyword packs into a single list for the terminal batch scan
CUSTOM_KEYWORDS = [kw for pack in CUSTOM_KEYWORD_PACKS.values() for kw in pack]

def extract_text_from_pdf(pdf_bytes):
    text = ""
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages[:30]:  # Limit pages for speed
                text += (page.extract_text() or "") + "\n"
    except Exception as e:
        return f"[PDF Error: {e}]"
    return text

def _is_recent_date(d, max_days=180):
    """Check if a date is within max_days (default: 180 days / 6 months) from today."""
    if d is None:
        return True
    today = datetime.date.today()
    return (today - d).days <= max_days

def _extract_date_from_text(text):
    text = text.lower()
    months = {
        'january': 1, 'february': 2, 'march': 3, 'april': 4,
        'may': 5, 'june': 6, 'july': 7, 'august': 8,
        'september': 9, 'october': 10, 'november': 11, 'december': 12
    }
    for m_name, m_num in months.items():
        match = re.search(rf'{m_name}\s+(\d{{1,2}}),?\s*(\d{{4}})', text)
        if match:
            try: return datetime.date(int(match.group(2)), m_num, int(match.group(1)))
            except ValueError: pass

    match = re.search(r'(\d{4})[-/](\d{1,2})[-/](\d{1,2})', text)
    if match:
        try: return datetime.date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except ValueError: pass

    match = re.search(r'(\d{4})[-/](\d{1,2})', text)
    if match:
        try: return datetime.date(int(match.group(1)), int(match.group(2)), 1)
        except ValueError: pass
    return None

def _spider_civicweb(base_url, soup, headers, max_links=4):
    try:
        links = soup.find_all("a", href=True)
        doc_folder_url = None
        for link in links:
            href = link["href"]
            text = link.get_text().strip().lower()
            full = urljoin(base_url, href)
            if "filepro/documents" in href and ("minute" in text or "agenda" in text or "council" in text):
                doc_folder_url = full
                break

        if not doc_folder_url and "filepro/documents" in base_url:
            doc_folder_url = base_url

        if not doc_folder_url: return []

        if doc_folder_url != base_url:
            resp2 = requests.get(doc_folder_url, headers=headers, timeout=12, verify=False)
            if resp2.status_code != 200: return []
            soup2 = BeautifulSoup(resp2.text, "html.parser")
        else: soup2 = soup

        files = []
        year_folders = []
        for link in soup2.find_all("a", href=True):
            href = link["href"]
            text = link.get_text().strip()
            full = urljoin(doc_folder_url, href)
            if "filestream" in href.lower():
                date_hint = _extract_date_from_text(text + " " + full)
                if not date_hint or _is_recent_date(date_hint, max_days=180):
                    files.append((full, text, date_hint))
            elif "filepro/documents" in href:
                match = re.search(r'\b(202[4-6])\b', text)
                if match:
                    year_folders.append((full, int(match.group(1))))

        if year_folders and not files:
            year_folders.sort(key=lambda x: x[1], reverse=True)
            latest_year_url = year_folders[0][0]
            resp3 = requests.get(latest_year_url, headers=headers, timeout=12, verify=False)
            if resp3.status_code == 200:
                soup3 = BeautifulSoup(resp3.text, "html.parser")
                for link in soup3.find_all("a", href=True):
                    href = link["href"]
                    text = link.get_text().strip()
                    full = urljoin(latest_year_url, href)
                    if "filestream" in href.lower():
                        date_hint = _extract_date_from_text(text + " " + full)
                        if not date_hint or _is_recent_date(date_hint, max_days=180):
                            files.append((full, text, date_hint))

        dated = [(u, t, d) for u, t, d in files if d is not None]
        undated = [(u, t, d) for u, t, d in files if d is None]
        dated.sort(key=lambda x: x[2], reverse=True)
        return [url for url, _, _ in (dated + undated)[:max_links]]
    except Exception:
        return []

def _find_recent_doc_links(listing_url, headers, max_links=4):
    try:
        resp = requests.get(listing_url, headers=headers, timeout=12, verify=False)
        if resp.status_code != 200: return []
        soup = BeautifulSoup(resp.text, "html.parser")
        links = soup.find_all("a", href=True)

        if "civicweb.net" in listing_url:
            return _spider_civicweb(listing_url, soup, headers, max_links)

        candidates = []
        seen_urls = set()
        for link in links:
            href = link["href"]
            text = link.get_text().strip()
            full_url = urljoin(listing_url, href)
            if href.startswith("javascript:") or href == "#": continue
            
            is_pdf = full_url.lower().endswith(".pdf")
            is_ashx = "View.ashx" in full_url or "FileStream" in full_url
            is_filestream = "filestream" in full_url.lower()
            has_doc_keyword = any(w in text.lower() for w in ["minute", "agenda", "council meeting", "regular meeting"])
            is_self_loop = full_url.lower().rstrip("/") == listing_url.lower().rstrip("/")
            if is_self_loop: continue

            if (is_pdf or is_ashx or is_filestream or has_doc_keyword) and full_url not in seen_urls:
                date_hint = _extract_date_from_text(text + " " + full_url)
                if date_hint and not _is_recent_date(date_hint, max_days=180):
                    continue
                candidates.append((full_url, text[:80], date_hint))
                seen_urls.add(full_url)

        dated = [(u, t, d) for u, t, d in candidates if d is not None]
        undated = [(u, t, d) for u, t, d in candidates if d is None]
        dated.sort(key=lambda x: x[2], reverse=True)
        return [url for url, _, _ in (dated + undated)[:max_links]]
    except Exception:
        return []

def _fetch_content_and_extract_text(url):
    try:
        response = requests.get(url, headers=HEADERS, timeout=12, verify=False)
        if response.status_code != 200:
            return "", False

        c_type = response.headers.get('Content-Type', '').lower()
        if 'pdf' in c_type or url.lower().endswith('.pdf'):
            if PDF_SUPPORT:
                return extract_text_from_pdf(response.content), True
            return "", True
        else:
            soup = BeautifulSoup(response.text, "html.parser")
            for tag in soup(["script", "style", "nav", "header", "footer"]):
                tag.decompose()
            return soup.get_text(separator=" ", strip=True), False
    except Exception:
        return "", False

def scan_single_muni(row):
    name = row.get('municipality_name', 'Unknown')
    county = row.get('county', 'Unknown')
    region = row.get('region', 'Unknown')
    listing_url = row.get('minutes_listing_url', None)
    fallback_url = row.get('example_recent_minutes_url', None)

    listing_clean = str(listing_url).strip().rstrip("/") if listing_url and not pd.isna(listing_url) else ""
    fallback_clean = str(fallback_url).strip().rstrip("/") if fallback_url and not pd.isna(fallback_url) else ""

    urls_to_scan = []
    found_real_docs = False
    
    try:
        # Spider the listing page
        if listing_clean:
            # Fetch up to 4 to capture recent agendas and minutes
            urls_to_scan = _find_recent_doc_links(listing_clean, HEADERS, max_links=4)
            if urls_to_scan:
                found_real_docs = True

        # Fallback if spidering fails
        if not urls_to_scan and fallback_clean:
            urls_to_scan = [fallback_clean]

        if not urls_to_scan:
            return None

        matches = []
        for url in urls_to_scan:
            text_content, is_pdf = _fetch_content_and_extract_text(url)
            
            # Skip HTML portal/listing pages to avoid false positives from menus
            if not is_pdf and not found_real_docs:
                continue

            content_lower = text_content.lower()

            for keyword in CUSTOM_KEYWORDS:
                # Use REGEX boundary to ensure we don't match "Halton" for "ALTO"
                pattern = r'\b' + re.escape(keyword.lower()) + r'\b'
                if re.search(pattern, content_lower):
                    snippet = extract_readable_snippet(text_content, keyword, window=300)
                    matches.append({
                        "Municipality": name,
                        "County / Upper Tier": county,
                        "Region": region,
                        "Date Scanned": datetime.date.today().isoformat(),
                        "Keyword Found": keyword,
                        "Context Snippet": snippet,
                        "Source URL": url
                    })
        
        # Unique the findings across all URLs to avoid duplicates of same document
        if matches:
            unique_matches = []
            seen = set()
            for m in matches:
                key = (m["Keyword Found"], m["Source URL"])
                if key not in seen:
                    unique_matches.append(m)
                    seen.add(key)
            return unique_matches
            
    except Exception:
        pass
    
    return None

def main():
    print(f"Starting fast concurrent scan for keywords: {CUSTOM_KEYWORDS}")
    
    if not os.path.exists(REGISTRY_PATH):
        print(f"ERROR: Registry file not found at {REGISTRY_PATH}")
        return
        
    df = pd.read_csv(REGISTRY_PATH)
    
    # ── Map Counties from the Database ──
    db_path = os.path.join(SCRIPT_DIR, "bylaws.db")
    county_dict = {}
    if os.path.exists(db_path):
        try:
            conn = sqlite3.connect(db_path)
            # We match by standard uppercase name or the lookup_key prefix 
            # to maximize matches with the registry's municipality_name
            db_df = pd.read_sql_query("SELECT name, geographic_area FROM municipalities", conn)
            for _, r in db_df.iterrows():
                if pd.notna(r['name']) and pd.notna(r['geographic_area']):
                    c_name = str(r['name']).upper().strip()
                    county_dict[c_name] = r['geographic_area']
            conn.close()
        except: pass

    def map_county(m_name):
        m_upper = str(m_name).upper().strip()
        if m_upper in county_dict: return county_dict[m_upper]
        
        # Fuzzy match / cleaned match
        clean_m = re.sub(r'\s+(TP|C|M)$', '', m_upper).strip()
        if clean_m in county_dict: return county_dict[clean_m]
        
        for db_name, area in county_dict.items():
            if clean_m in db_name or db_name in clean_m:
                return area
        return m_name
        
    df['county'] = df['municipality_name'].apply(map_county)
    df['region'] = df.apply(lambda row: get_region(row['county'], row['municipality_name']), axis=1)

    print(f"Loaded {len(df)} municipalities...")
    
    results = []
    total = len(df)
    completed = 0
    
    with ThreadPoolExecutor(max_workers=20) as executor:
        future_to_row = {executor.submit(scan_single_muni, row): i for i, row in df.iterrows()}
        for future in as_completed(future_to_row):
            completed += 1
            if completed % 25 == 0:
                print(f"Progress: {completed} / {total}")
            res_list = future.result()
            if res_list:
                results.extend(res_list)
                muni_name = res_list[0]['Municipality']
                found_kws = ", ".join(list(set([r['Keyword Found'] for r in res_list])))
                print(f"\n[!] HIT FOUND: {muni_name} ({found_kws})\n")

    if results:
        res_df = pd.DataFrame(results)
        output_file = os.path.join(OUTPUT_DIR, f"multi_keyword_hits_{datetime.date.today().isoformat()}.csv")
        res_df.to_csv(output_file, index=False)
        print(f"\nSUCCESS! Found {len(results)} total matches. Saved to {output_file}")
    else:
        print("\nScan complete. No mentions of your keywords were found in any recent municipality minutes.")

if __name__ == "__main__":
    main()
