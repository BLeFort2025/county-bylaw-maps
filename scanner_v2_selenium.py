import pandas as pd
import os
import datetime
import time
import glob
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

# --- CONFIG ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REGISTRY_PATH = os.path.join(SCRIPT_DIR, "signals", "portal_registry.csv")
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "signals")
CACHE_PATH = os.path.join(OUTPUT_DIR, "cached_portal_docs.csv")

# --- KEYWORD CONFIG (imported from shared module) ---
from shared_config import (
    KEYWORD_CONFIG,
    check_all_keywords,
    extract_snippet,
    is_valid_meeting_document,
    classify_meeting_doc,
    merge_docs_into_cache,
)
from selenium_prefetch import prefetch_single_muni, select_best_portal_url


def find_latest_report():
    """Automatically finds the most recent coverage report."""
    search_paths = [
        os.path.join(SCRIPT_DIR, "signals", "coverage_report_*.csv"),
        os.path.join(SCRIPT_DIR, "coverage_report_*.csv")
    ]
    found_files = []
    for p in search_paths:
        found_files.extend(glob.glob(p))
    if not found_files:
        return None
    return sorted(found_files)[-1]


def setup_driver():
    """Configures a headless Chrome browser via Selenium 4 Selenium Manager."""
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--log-level=3")
    options.page_load_strategy = "eager"
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(45)
    return driver


def scan_with_selenium(driver, row):
    """Spider and scan a failed municipality's portal with Selenium, returning a list of candidate hits."""
    munid = row['munid']
    name = row['municipality_name']
    url = select_best_portal_url(row)

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
        return [], coverage, []

    found_candidates = []
    fetched_docs = []
    seen_cats = set()

    try:
        docs = prefetch_single_muni(driver, row)
        if docs:
            coverage['status'] = 'scanned_selenium'
            for doc in docs:
                doc_text = str(doc.get("doc_text", "") or "")
                doc_url = str(doc.get("doc_url", url) or url)
                if not is_valid_meeting_document(doc_url, doc_text):
                    continue
                fetched_docs.append({
                    'municipality_name': name,
                    'portal_type': str(row.get('portal_type', '') or 'selenium'),
                    'doc_url': doc_url,
                    'doc_text': doc_text[:25000],
                    'doc_type': str(doc.get('doc_type') or classify_meeting_doc(doc_url, doc_text)),
                    'fetch_date': datetime.date.today().isoformat(),
                })
                for trigger, category in check_all_keywords(doc_text):
                    if category not in seen_cats:
                        seen_cats.add(category)
                        found_candidates.append({
                            'munid': munid,
                            'name': name,
                            'found_url': doc_url,
                            'found_date': datetime.date.today().isoformat(),
                            'snippet': extract_snippet(doc_text, trigger),
                            'trigger_keyword': trigger,
                            'category': category,
                            'keywords_detected': True
                        })
        else:
            cur_u = (driver.current_url or "").lower()
            if cur_u.startswith("chrome-error://") or cur_u in ("", "about:blank"):
                coverage['status'] = 'error'
                coverage['error'] = f"Navigation failed ({cur_u or 'about:blank'})"
                return found_candidates, coverage, fetched_docs
            page_text = driver.find_element("tag name", "body").text
            coverage['status'] = 'scanned_selenium'
            if is_valid_meeting_document(url, page_text):
                for trigger, category in check_all_keywords(page_text):
                    if category not in seen_cats:
                        seen_cats.add(category)
                        found_candidates.append({
                            'munid': munid,
                            'name': name,
                            'found_url': url,
                            'found_date': datetime.date.today().isoformat(),
                            'snippet': extract_snippet(page_text, trigger),
                            'trigger_keyword': trigger,
                            'category': category,
                            'keywords_detected': True
                        })
    except Exception as e:
        coverage['status'] = 'error'
        coverage['error'] = str(e)

    return found_candidates, coverage


def main():
    print("--- STARTING SELENIUM SCANNER (TARGETING STAGE 1 FAILURES) ---")

    report_path = find_latest_report()
    if not report_path:
        print("ERROR: No previous coverage report found.")
        print("Please run 'python scanner_v1_robust.py' first.")
        return

    print(f"Using report: {os.path.basename(report_path)}")
    report = pd.read_csv(report_path)

    # Identify Targets (Failures only — skip those already scanned or covered by prefetch cache)
    targets = report[~report['status'].isin(['scanned_html', 'scanned_pdf', 'covered_by_prefetch_cache'])]

    if targets.empty:
        print("No failures found to retry!")
        return

    if not os.path.exists(REGISTRY_PATH):
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

    driver = setup_driver()
    candidates = []
    all_fetched_docs = []

    try:
        total_targets = len(target_data)
        for count, (_, row) in enumerate(target_data.iterrows(), 1):
            ptype = str(row.get('portal_type', '?') or '?')
            print(f"[{count}/{total_targets}] Scanning {row['municipality_name']} ({ptype})...", end=" ", flush=True)
            cands, cov, fdocs = scan_with_selenium(driver, row)
            if fdocs:
                all_fetched_docs.extend(fdocs)
            if cov['status'] == 'error':
                err_short = str(cov.get('error', '')).replace('\n', ' ')[:80]
                print(f"FAILED ({err_short})", flush=True)
            elif cands:
                print(f"OK ({len(cands)} hit{'s' if len(cands) != 1 else ''})", flush=True)
            else:
                print("OK (no hits)", flush=True)
            for cand in cands:
                candidates.append(cand)
                print(f"  [!] HIT: {row['municipality_name']} -> {cand['category']} ({cand['trigger_keyword']})", flush=True)
    except KeyboardInterrupt:
        print("\nStopping scan...")
    finally:
        driver.quit()

    if all_fetched_docs:
        total_cached = merge_docs_into_cache(all_fetched_docs, CACHE_PATH)
        print(f"Unified council text cache updated: +{len(all_fetched_docs)} Selenium retry docs -> {total_cached} total docs")

    today_str = datetime.date.today().strftime('%Y-%m-%d')
    if candidates:
        cand_path = os.path.join(OUTPUT_DIR, f"candidates_selenium_{today_str}.csv")
        pd.DataFrame(candidates).to_csv(cand_path, index=False)
        print(f"\nSUCCESS: Selenium found {len(candidates)} NEW candidate hits.")
        print(f"Saved to: {cand_path}")
    else:
        print("\nScan complete. No new hits found.")


if __name__ == "__main__":
    main()