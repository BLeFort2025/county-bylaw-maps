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
from bs4 import BeautifulSoup

# --- 1. SETUP & IMPORTS ---
PDF_SUPPORT = False
try:
    import fitz
    PDF_SUPPORT = True
except ImportError:
    fitz = None

try:
    import pdfplumber
    PDF_SUPPORT = True
except ImportError:
    pdfplumber = None

if not PDF_SUPPORT:
    print("WARNING: Neither 'fitz' (PyMuPDF) nor 'pdfplumber' found. PDF documents will be skipped.")

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
warnings.simplefilter("ignore")

# --- 2. SMART CONFIGURATION ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = SCRIPT_DIR

REGISTRY_PATH = os.path.join(REPO_ROOT, "signals", "portal_registry.csv")
CACHE_PATH = os.path.join(REPO_ROOT, "signals", "cached_portal_docs.csv")
OUTPUT_DIR = os.path.join(REPO_ROOT, "signals")

# --- 3. KEYWORD CONFIG (imported from shared module) ---
from shared_config import (
    KEYWORD_CONFIG,
    check_all_keywords,
    extract_snippet,
    extract_date_from_text,
    is_recent_date,
    is_valid_meeting_document,
    SOCIAL_JUNK_DOMAINS,
)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

JS_PORTAL_TYPES = {"civicweb", "escribe", "(escribe)", "granicus_legistar"}


def extract_text_from_pdf(pdf_bytes):
    """Extracts text from PDF bytes using PyMuPDF (fitz) with pdfplumber fallback."""
    if not pdf_bytes or len(pdf_bytes) < 200:
        return ""
    if fitz is not None:
        try:
            text = ""
            with fitz.open("pdf", pdf_bytes) as doc:
                for page in doc[:35]:
                    page_text = page.get_text()
                    if page_text:
                        text += page_text + "\n"
            if text.strip():
                return text
        except Exception:
            pass
    if pdfplumber is not None:
        try:
            text = ""
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                for page in pdf.pages[:35]:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
            return text
        except Exception:
            return ""
    return ""


def _find_recent_doc_links(listing_url, max_links=4):
    """Spider a municipal listing page for the most recent meeting PDFs or document links."""
    try:
        resp = requests.get(listing_url, headers=HEADERS, timeout=12, verify=False)
        if resp.status_code != 200:
            return []
        soup = BeautifulSoup(resp.text, "html.parser")
        candidates = []
        seen_urls = set()
        for link in soup.find_all("a", href=True):
            href = link["href"]
            text = link.get_text().strip()
            if href.startswith("javascript:") or href == "#":
                continue
            full_url = urljoin(listing_url, href)
            full_low = full_url.lower()
            if any(d in full_low for d in SOCIAL_JUNK_DOMAINS):
                continue
            if full_low.rstrip("/") == listing_url.lower().rstrip("/"):
                continue

            is_pdf = full_low.endswith(".pdf")
            is_doc_stream = any(k in full_low for k in ("view.ashx", "filestream", "electronicfile"))
            has_doc_kw = any(w in text.lower() for w in ("minute", "agenda", "council meeting", "regular meeting", "special council"))

            if (is_pdf or is_doc_stream or has_doc_kw) and full_url not in seen_urls:
                if not is_valid_meeting_document(full_url, text):
                    continue
                date_hint = extract_date_from_text(text + " " + full_url)
                if date_hint and not is_recent_date(date_hint, max_days=180):
                    continue
                candidates.append((full_url, date_hint))
                seen_urls.add(full_url)

        dated = [(u, d) for u, d in candidates if d is not None]
        undated = [(u, d) for u, d in candidates if d is None]
        dated.sort(key=lambda x: x[1], reverse=True)
        return [u for u, _ in (dated + undated)[:max_links]]
    except Exception:
        return []


def scan_municipality(row, cached_munis_upper):
    """Downloads and scans a single municipality's recent minutes/agendas (returning a list of candidate hits)."""
    munid = row['munid']
    name = str(row['municipality_name']).strip()
    portal_type = str(row.get('portal_type', '') or '').strip().lower()
    listing_url = str(row.get('minutes_listing_url', '') or '').strip()
    fallback_url = str(row.get('example_recent_minutes_url', '') or '').strip()
    if listing_url == 'nan':
        listing_url = ''
    if fallback_url == 'nan':
        fallback_url = ''

    coverage = {
        'munid': munid,
        'name': name,
        'scan_date': datetime.date.today(),
        'status': 'skipped',
        'error': '',
        'target_url': fallback_url or listing_url
    }

    # Skip live HTTP if this JS portal is already covered in cached_portal_docs.csv
    if portal_type in JS_PORTAL_TYPES and name.upper() in cached_munis_upper:
        coverage['status'] = 'covered_by_prefetch_cache'
        return [], coverage

    if not listing_url and not fallback_url:
        coverage['status'] = 'no_url_in_registry'
        return [], coverage

    urls_to_scan = []
    if listing_url:
        urls_to_scan = _find_recent_doc_links(listing_url, max_links=4)
    if not urls_to_scan and fallback_url and fallback_url.rstrip("/") != listing_url.rstrip("/"):
        urls_to_scan = [fallback_url]
    elif not urls_to_scan and fallback_url:
        urls_to_scan = [fallback_url]

    found_candidates = []
    seen_cats = set()

    try:
        for target_url in urls_to_scan:
            response = requests.get(target_url, headers=HEADERS, timeout=15, verify=False)
            if response.status_code != 200:
                continue

            content_type = response.headers.get('Content-Type', '').lower()
            text_content = ""

            if 'pdf' in content_type or str(target_url).lower().endswith('.pdf') or 'filestream' in str(target_url).lower():
                if PDF_SUPPORT:
                    text_content = extract_text_from_pdf(response.content)
                    if text_content and len(text_content.strip()) > 50:
                        coverage['status'] = 'scanned_pdf'
                    else:
                        continue
                else:
                    coverage['status'] = 'pdf_skipped_no_lib'
                    continue
            else:
                soup = BeautifulSoup(response.text, "html.parser")
                for tag in soup(["script", "style", "nav", "header", "footer"]):
                    tag.decompose()
                text_content = soup.get_text(separator=" ", strip=True)
                if text_content and len(text_content.strip()) > 50:
                    coverage['status'] = 'scanned_html'
                else:
                    continue

            if not is_valid_meeting_document(target_url, text_content):
                continue

            hits = check_all_keywords(text_content)
            for trigger, category in hits:
                if category not in seen_cats:
                    seen_cats.add(category)
                    snippet = extract_snippet(text_content, trigger)
                    found_candidates.append({
                        'munid': munid,
                        'name': name,
                        'found_url': target_url,
                        'found_date': datetime.date.today().isoformat(),
                        'snippet': snippet,
                        'trigger_keyword': trigger,
                        'category': category,
                        'keywords_detected': True
                    })

    except Exception as e:
        if coverage['status'] == 'skipped':
            coverage['status'] = 'error'
            coverage['error'] = str(e)

    return found_candidates, coverage


def main():
    print("--- STARTING SCANNER V1 (Multi-Doc Spider + By-law/Bylaw Matching) ---")
    print(f"Script Location: {SCRIPT_DIR}")
    print(f"Registry Path: {REGISTRY_PATH}")

    if not os.path.exists(REGISTRY_PATH):
        print(f"ERROR: Registry file not found at {REGISTRY_PATH}")
        return

    try:
        df = pd.read_csv(REGISTRY_PATH)
        print(f"Loaded {len(df)} municipalities.")
    except Exception as e:
        print(f"ERROR reading CSV: {e}")
        return

    cached_munis_upper = set()
    if os.path.exists(CACHE_PATH):
        try:
            cdf = pd.read_csv(CACHE_PATH)
            valid_c = cdf[cdf['doc_text'].fillna('').str.len() > 50]
            cached_munis_upper = set(valid_c['municipality_name'].dropna().astype(str).str.upper().str.strip())
            print(f"Pre-fetched Selenium cache covers {len(cached_munis_upper)} JS-portal municipalities.")
        except Exception:
            pass

    candidates = []
    coverage_log = []

    print("Scanning...")
    for index, row in df.iterrows():
        if index % 25 == 0:
            print(f"  Processing {index}/{len(df)}...")

        cands, cov = scan_municipality(row, cached_munis_upper)
        coverage_log.append(cov)

        for cand in cands:
            candidates.append(cand)
            print(f"  [!] HIT: {row['municipality_name']} -> {cand['category']} ({cand['trigger_keyword']})")

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    today_str = datetime.date.today().strftime('%Y-%m-%d')

    cov_path = os.path.join(OUTPUT_DIR, f"coverage_report_{today_str}.csv")
    pd.DataFrame(coverage_log).to_csv(cov_path, index=False)

    if candidates:
        cand_path = os.path.join(OUTPUT_DIR, f"candidates_minutes_{today_str}.csv")
        pd.DataFrame(candidates).to_csv(cand_path, index=False)
        print(f"\nSUCCESS: Found {len(candidates)} candidate hits.")
    else:
        print("\nScan complete. No keyword hits found in Stage 1.")


if __name__ == "__main__":
    main()