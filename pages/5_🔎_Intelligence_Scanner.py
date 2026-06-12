import os
import sys
import datetime
import io
import time
import re
import requests
import urllib3
import urllib.parse
import sqlite3

import streamlit as st
import pandas as pd

from concurrent.futures import ThreadPoolExecutor, as_completed

# Suppress insecure request warnings for municipal sites with bad SSLs
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# PDF Support
try:
    import pdfplumber
    PDF_SUPPORT = True
except ImportError:
    PDF_SUPPORT = False

# --- Setup Paths & Imports ---
# This file is in `pages/`, so the root is one level up
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SCRIPT_DIR)
sys.path.append(ROOT_DIR)

# Import shared modules from the parent directory
from shared_config import (
    KEYWORD_CONFIG, extract_snippet, extract_readable_snippet,
    CUSTOM_KEYWORD_PACKS, REGION_MAPPING, get_region,
)
from db_utils import get_connection

# --- Page Config ---
st.set_page_config(
    page_title="Intelligence Scanner",
    page_icon="🔎",
    layout="wide"
)

st.title("🔎 Intelligence Scanner")
st.markdown("""
This tool allows OFA members and policy experts to actively search municipal council agendas and minutes. 
Use the **Live Scanner** to perform on-demand web searches for specific keywords, or use the **Historical Database** 
to see which municipalities have recently discussed established bylaw categories.
""")

# --- Data Loading Methods ---

@st.cache_data(ttl=3600)
def load_historical_signals():
    """Load the historical scanner hits from the SQLite database."""
    conn = get_connection()
    query = """
        SELECT 
            s.*,
            m.name as municipality,
            m.geographic_area as county
        FROM scanner_signals s
        LEFT JOIN municipalities m ON s.municipality_id = m.id
        ORDER BY s.discovered_date DESC
    """
    df = pd.read_sql_query(query, conn.conn)
    conn.close()
    return df

@st.cache_data(ttl=3600)
def load_registry():
    """Load the URL portal registry for live scanning."""
    registry_path = os.path.join(ROOT_DIR, "signals", "portal_registry.csv")
    if os.path.exists(registry_path):
        return pd.read_csv(registry_path)
    return pd.DataFrame()

# Path to the Selenium pre-fetched cache (generated weekly by selenium_prefetch.py)
CACHE_PATH = os.path.join(ROOT_DIR, "signals", "cached_portal_docs.csv")

@st.cache_data(ttl=3600)
def load_cached_docs():
    """Load the pre-fetched document text cache from the Selenium pre-fetch.

    This CSV is generated locally by `selenium_prefetch.py` and committed to Git.
    It contains the full text of documents from JS-rendered portals that the
    cloud-based HTTP scanner cannot read.
    """
    if os.path.exists(CACHE_PATH):
        df = pd.read_csv(CACHE_PATH)
        return df
    return pd.DataFrame()

# --- Shared Scanner Constants ---

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                  'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

# --- Live Scanner Logic ---

try:
    from bs4 import BeautifulSoup
    BS4_SUPPORT = True
except ImportError:
    BS4_SUPPORT = False

def extract_text_from_pdf(pdf_bytes):
    text = ""
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages[:30]:  # Limit pages for speed
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
    except Exception as e:
        return f"[PDF Error: {e}]"
    return text


def _extract_date_from_text(text):
    """Try to extract a date from link text or URL for sorting by recency."""
    text = text.lower()
    # Match patterns like "march 19, 2026", "2026-03-19", "march-19-2026"
    months = {
        'january': 1, 'february': 2, 'march': 3, 'april': 4,
        'may': 5, 'june': 6, 'july': 7, 'august': 8,
        'september': 9, 'october': 10, 'november': 11, 'december': 12
    }

    # "March 19, 2026" or "March 19 2026"
    for m_name, m_num in months.items():
        match = re.search(rf'{m_name}\s+(\d{{1,2}}),?\s*(\d{{4}})', text)
        if match:
            try:
                return datetime.date(int(match.group(2)), m_num, int(match.group(1)))
            except ValueError:
                pass

    # ISO-style "2026-03-19" or in URL paths "2026/03"
    match = re.search(r'(\d{4})[-/](\d{1,2})[-/](\d{1,2})', text)
    if match:
        try:
            return datetime.date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except ValueError:
            pass

    # Partial: "2026/03" (year/month only)
    match = re.search(r'(\d{4})[-/](\d{1,2})', text)
    if match:
        try:
            return datetime.date(int(match.group(1)), int(match.group(2)), 1)
        except ValueError:
            pass

    return None


def _find_recent_doc_links(listing_url, headers, max_links=4):
    """Spider a listing page to find the most recent document links.

    Includes special handling for CivicWeb portals which organize
    documents in nested folder structures (filepro/documents/{id}).
    """
    if not BS4_SUPPORT:
        return []

    try:
        resp = requests.get(listing_url, headers=headers, timeout=12, verify=False)
        if resp.status_code != 200:
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        links = soup.find_all("a", href=True)

        # ── CivicWeb special handling ──
        if "civicweb.net" in listing_url:
            return _spider_civicweb(listing_url, soup, headers, max_links)

        # ── General-purpose spider for custom HTML sites ──
        candidates = []
        seen_urls = set()
        for link in links:
            href = link["href"]
            text = link.get_text().strip()
            full_url = urllib.parse.urljoin(listing_url, href)

            # Skip javascript links, anchors, and non-document links
            if href.startswith("javascript:") or href == "#":
                continue

            # Identify document links
            is_pdf = full_url.lower().endswith(".pdf")
            is_ashx = "View.ashx" in full_url or "FileStream" in full_url
            is_filestream = "filestream" in full_url.lower()
            has_doc_keyword = any(w in text.lower() for w in
                                 ["minute", "agenda", "council meeting", "regular meeting"])

            # Skip self-referential loops
            is_self_loop = full_url.lower().rstrip("/") == listing_url.lower().rstrip("/")
            if is_self_loop:
                continue

            if (is_pdf or is_ashx or is_filestream or has_doc_keyword) and full_url not in seen_urls:
                date_hint = _extract_date_from_text(text + " " + full_url)
                candidates.append((full_url, text[:80], date_hint))
                seen_urls.add(full_url)

        # Sort: dated links first (newest first), then undated
        dated = [(u, t, d) for u, t, d in candidates if d is not None]
        undated = [(u, t, d) for u, t, d in candidates if d is None]
        dated.sort(key=lambda x: x[2], reverse=True)

        sorted_candidates = dated + undated
        return [url for url, _, _ in sorted_candidates[:max_links]]

    except Exception:
        return []


def _spider_civicweb(base_url, soup, headers, max_links=4):
    """Navigate CivicWeb filepro folder hierarchy to find recent documents."""
    try:
        links = soup.find_all("a", href=True)

        doc_folder_url = None
        for link in links:
            href = link["href"]
            text = link.get_text().strip().lower()
            full = urllib.parse.urljoin(base_url, href)
            if "filepro/documents" in href and ("minute" in text or "agenda" in text):
                doc_folder_url = full
                break

        if not doc_folder_url and "filepro/documents" in base_url:
            doc_folder_url = base_url

        if not doc_folder_url:
            return []

        if doc_folder_url != base_url:
            resp2 = requests.get(doc_folder_url, headers=headers, timeout=12, verify=False)
            if resp2.status_code != 200:
                return []
            soup2 = BeautifulSoup(resp2.text, "html.parser")
        else:
            soup2 = soup

        files = []
        year_folders = []
        for link in soup2.find_all("a", href=True):
            href = link["href"]
            text = link.get_text().strip()
            full = urllib.parse.urljoin(doc_folder_url, href)

            if "filestream" in href.lower():
                date_hint = _extract_date_from_text(text + " " + full)
                files.append((full, text, date_hint))
            elif "filepro/documents" in href and text.strip().isdigit() and len(text.strip()) == 4:
                year_folders.append((full, int(text.strip())))

        if year_folders and not files:
            year_folders.sort(key=lambda x: x[1], reverse=True)
            latest_year_url = year_folders[0][0]
            resp3 = requests.get(latest_year_url, headers=headers, timeout=12, verify=False)
            if resp3.status_code == 200:
                soup3 = BeautifulSoup(resp3.text, "html.parser")
                for link in soup3.find_all("a", href=True):
                    href = link["href"]
                    text = link.get_text().strip()
                    full = urllib.parse.urljoin(latest_year_url, href)
                    if "filestream" in href.lower():
                        date_hint = _extract_date_from_text(text + " " + full)
                        files.append((full, text, date_hint))

        dated = [(u, t, d) for u, t, d in files if d is not None]
        undated = [(u, t, d) for u, t, d in files if d is None]
        dated.sort(key=lambda x: x[2], reverse=True)

        all_sorted = dated + undated
        return [url for url, _, _ in all_sorted[:max_links]]

    except Exception:
        return []


def _fetch_and_extract_text(url, headers):
    """Download a URL and extract its text content (HTML or PDF).

    For HTML pages, strips tags and returns only visible body text
    to avoid false matches on navigation, headers, and scripts.
    Returns a tuple of (text_content, is_pdf).
    """
    try:
        response = requests.get(url, headers=headers, timeout=12, verify=False)
        if response.status_code != 200:
            return "", False

        content_type = response.headers.get('Content-Type', '').lower()

        if 'pdf' in content_type or url.lower().endswith('.pdf'):
            if PDF_SUPPORT:
                return extract_text_from_pdf(response.content), True
            return "", True
        else:
            # Strip HTML to get only visible text content
            if BS4_SUPPORT:
                soup = BeautifulSoup(response.text, "html.parser")
                for tag in soup(["script", "style", "nav", "header", "footer"]):
                    tag.decompose()
                text = soup.get_text(separator=" ", strip=True)
                return text, False
            return response.text, False
    except Exception:
        return "", False


# ──────────────────────────────────────────────────────────────────
# County enrichment from local SQLite (same logic as terminal script)
# ──────────────────────────────────────────────────────────────────
@st.cache_data(ttl=3600)
def _load_county_dict():
    """Build a name→county lookup from the local bylaws.db."""
    db_path = os.path.join(ROOT_DIR, "bylaws.db")
    county_dict = {}
    if os.path.exists(db_path):
        try:
            conn = sqlite3.connect(db_path)
            db_df = pd.read_sql_query(
                "SELECT name, geographic_area FROM municipalities", conn
            )
            for _, r in db_df.iterrows():
                if pd.notna(r['name']) and pd.notna(r['geographic_area']):
                    county_dict[str(r['name']).upper().strip()] = r['geographic_area']
            conn.close()
        except Exception:
            pass
    return county_dict


def _map_county(m_name, county_dict):
    """Resolve a municipality name to its county/upper-tier from the lookup dict."""
    m_upper = str(m_name).upper().strip()
    if m_upper in county_dict:
        return county_dict[m_upper]

    clean_m = re.sub(r'\s+(TP|C|M)$', '', m_upper).strip()
    clean_m_no_punct = re.sub(r'[^\w\s]', '', clean_m)
    if clean_m in county_dict:
        return county_dict[clean_m]

    for db_name, area in county_dict.items():
        db_name_no_punct = re.sub(r'[^\w\s]', '', db_name)
        if clean_m_no_punct in db_name_no_punct or db_name_no_punct in clean_m_no_punct:
            return area
            
    # Hard fallback for Chatham-Kent if the above still misses
    if "CHATHAM" in m_upper and "KENT" in m_upper:
        return "Chatham-Kent"
        
    return m_name


# ──────────────────────────────────────────────────────────────────
# Core scan function — scans ONE municipality for a LIST of keywords
# ──────────────────────────────────────────────────────────────────
def _scan_single_muni(row, keywords, negative_keywords=None):
    """Scan a single municipality's recent documents for multiple keywords.

    This is the function submitted to the thread pool. It:
      1. Spiders the listing page for up to 3 recent documents
      2. Downloads and extracts text from each document
      3. Tests ALL keywords with regex word boundaries
      4. Returns a dict with 'matches' (list) and 'stats' (document counts)
    """
    name = row.get('municipality_name', 'Unknown')
    county = row.get('county', 'Unknown')
    region = row.get('region', 'Unknown')
    listing_url = row.get('minutes_listing_url', None)
    fallback_url = row.get('example_recent_minutes_url', None)

    listing_clean = str(listing_url).strip().rstrip("/") if listing_url and not pd.isna(listing_url) else ""
    fallback_clean = str(fallback_url).strip().rstrip("/") if fallback_url and not pd.isna(fallback_url) else ""

    # Track document-level statistics for this municipality
    stats = {
        "docs_found": 0,       # URLs discovered by spidering
        "docs_scanned": 0,     # Documents successfully read
        "pdfs_read": 0,        # PDF documents read
        "html_read": 0,        # HTML documents read
        "no_portal": False,    # True if no listing URL or no docs found
    }

    urls_to_scan = []
    found_real_docs = False

    try:
        # Spider the listing page
        if listing_clean:
            urls_to_scan = _find_recent_doc_links(listing_clean, HEADERS, max_links=3)
            if urls_to_scan:
                found_real_docs = True

        # Fallback if spidering fails
        if not urls_to_scan and fallback_clean:
            urls_to_scan = [fallback_clean]

        if not urls_to_scan:
            stats["no_portal"] = True
            return {"matches": [], "stats": stats}

        stats["docs_found"] = len(urls_to_scan)

        matches = []
        for url in urls_to_scan:
            text_content, is_pdf = _fetch_and_extract_text(url, HEADERS)

            # Skip HTML portal/listing pages to avoid false positives from menus
            if not is_pdf and not found_real_docs:
                continue

            # Only count as "scanned" if we got meaningful text content
            if text_content and len(text_content.strip()) > 50:
                stats["docs_scanned"] += 1
                if is_pdf:
                    stats["pdfs_read"] += 1
                else:
                    stats["html_read"] += 1

            if negative_keywords:
                for n_kw in negative_keywords:
                    if n_kw.strip():
                        pattern = re.compile(re.escape(n_kw.strip()), re.IGNORECASE)
                        text_content = pattern.sub(" [IGNORED] ", text_content)

            content_lower = text_content.lower()

            # FAST EXIT: Check if ANY keyword exists before looping
            combined_pattern = re.compile(r'\b(' + '|'.join(re.escape(kw.lower()) for kw in keywords) + r')\b')
            if not combined_pattern.search(content_lower):
                continue

            for keyword in keywords:
                # Use REGEX word boundary to prevent false matches
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
                        "Source URL": url,
                        "Scan Method": "🟢 Live",
                    })

        # De-duplicate across URLs
        if matches:
            unique_matches = []
            seen = set()
            for m in matches:
                key = (m["Keyword Found"], m["Source URL"])
                if key not in seen:
                    unique_matches.append(m)
                    seen.add(key)
            return {"matches": unique_matches, "stats": stats}

    except Exception:
        pass

    return {"matches": [], "stats": stats}


def _scan_cached_docs(cached_df, registry_subset, keywords, stage1_scanned_munis, negative_keywords=None):
    """Stage 2: Search the pre-fetched Selenium cache for keyword matches.

    For any municipality that Stage 1 couldn't read (not in stage1_scanned_munis),
    this function checks the cached document text for keyword matches using the
    same regex word-boundary logic as Stage 1.

    Args:
        cached_df: DataFrame from cached_portal_docs.csv
        registry_subset: The target municipalities for this scan
        keywords: List of keywords to search for
        stage1_scanned_munis: Set of municipality names that Stage 1 already attempted

    Returns:
        (list[dict], dict): Matches list and cache stats dict.
    """
    if cached_df.empty:
        return [], {"munis_from_cache": 0, "cache_docs_searched": 0, "cache_hits": 0}

    # Get target municipality names
    target_names = set(registry_subset["municipality_name"].str.upper().tolist())

    # Filter cache to municipalities that are in our target set but NOT covered by Stage 1
    cache_muni_col = cached_df["municipality_name"].str.upper()
    relevant_cache = cached_df[
        cache_muni_col.isin(target_names) & ~cache_muni_col.isin(
            {m.upper() for m in stage1_scanned_munis}
        )
    ]

    if relevant_cache.empty:
        return [], {"munis_from_cache": 0, "cache_docs_searched": 0, "cache_hits": 0}

    matches = []
    munis_searched = set()

    for _, row in relevant_cache.iterrows():
        muni_name = row.get("municipality_name", "Unknown")
        doc_text = str(row.get("doc_text", ""))
        doc_url = str(row.get("doc_url", ""))

        if not doc_text or len(doc_text.strip()) < 50:
            continue

        if negative_keywords:
            for n_kw in negative_keywords:
                if n_kw.strip():
                    pattern = re.compile(re.escape(n_kw.strip()), re.IGNORECASE)
                    doc_text = pattern.sub(" [IGNORED] ", doc_text)

        munis_searched.add(muni_name)
        content_lower = doc_text.lower()

        # FAST EXIT: Check if ANY keyword exists before looping
        combined_pattern = re.compile(r'\b(' + '|'.join(re.escape(kw.lower()) for kw in keywords) + r')\b')
        if not combined_pattern.search(content_lower):
            continue

        # Look up county/region from the registry
        reg_match = registry_subset[
            registry_subset["municipality_name"].str.upper() == muni_name.upper()
        ]
        county = ""
        region = ""
        if not reg_match.empty:
            first = reg_match.iloc[0]
            county = first.get("county", "") if "county" in first.index else ""
            region = first.get("region", "") if "region" in first.index else ""
        if not region:
            region = get_region(muni_name)

        for keyword in keywords:
            pattern = r'\b' + re.escape(keyword.lower()) + r'\b'
            if re.search(pattern, content_lower):
                snippet = extract_readable_snippet(doc_text, keyword, window=300)
                matches.append({
                    "Municipality": muni_name,
                    "County / Upper Tier": county,
                    "Region": region,
                    "Date Scanned": datetime.date.today().isoformat(),
                    "Keyword Found": keyword,
                    "Context Snippet": snippet,
                    "Source URL": doc_url,
                    "Scan Method": "🟡 Cached",
                })

    # De-duplicate
    if matches:
        unique = []
        seen = set()
        for m in matches:
            key = (m["Keyword Found"], m["Source URL"])
            if key not in seen:
                unique.append(m)
                seen.add(key)
        matches = unique

    stats = {
        "munis_from_cache": len(munis_searched),
        "cache_docs_searched": len(relevant_cache),
        "cache_hits": len(matches),
    }
    return matches, stats


def run_live_scan(registry_subset, keywords, negative_keywords=None):

    """Execute a concurrent, multi-keyword scan over a registry subset.

    Uses a 3-thread pool (reduced from 5 to stay within Streamlit Cloud's
    ~1 GB memory limit) with Streamlit progress feedback.

    Crash-resilient design:
    - Each future.result() is wrapped in try/except with a 60-second timeout
      so a single hung municipal site cannot kill the entire scan.
    - Partial results are saved to st.session_state after every hit so that
      even if a late failure or Streamlit rerun occurs, earlier results survive.
    - A summary of timed-out/errored municipalities is displayed at the end.

    Returns:
        (pd.DataFrame, dict): Results DataFrame and aggregated scan statistics.
    """
    results = []
    errors = []
    total = len(registry_subset)
    completed = 0

    # Aggregate document-level statistics across all municipalities
    scan_stats = {
        "munis_attempted": total,
        "munis_with_docs": 0,      # Municipalities where ≥1 document was read
        "munis_no_portal": 0,      # Municipalities with no portal or no documents found
        "total_docs_found": 0,     # Total document URLs discovered by spidering
        "total_docs_scanned": 0,   # Total documents successfully read
        "total_pdfs_read": 0,      # PDF documents read
        "total_html_read": 0,      # HTML pages read
        "munis_errored": 0,        # Municipalities that timed out or threw exceptions
    }

    # Initialise session state for crash-safe partial results
    st.session_state["_scan_results_partial"] = []
    st.session_state["_scan_errors"] = []

    progress_bar = st.progress(0)
    status_text = st.empty()
    hit_container = st.container()

    with ThreadPoolExecutor(max_workers=3) as executor:
        future_to_name = {}
        for _, row in registry_subset.iterrows():
            future = executor.submit(_scan_single_muni, row, keywords, negative_keywords)
            future_to_name[future] = row.get('municipality_name', 'Unknown')

        stage1_with_docs = set()
        for future in as_completed(future_to_name):
            completed += 1
            muni_name = future_to_name[future]

            # Update progress
            progress_bar.progress(completed / total)
            status_text.text(f"Scanning... {completed} / {total} municipalities processed")

            try:
                result = future.result(timeout=60)

                # Aggregate document stats
                if result and isinstance(result, dict):
                    muni_stats = result.get("stats", {})
                    scan_stats["total_docs_found"] += muni_stats.get("docs_found", 0)
                    scan_stats["total_docs_scanned"] += muni_stats.get("docs_scanned", 0)
                    scan_stats["total_pdfs_read"] += muni_stats.get("pdfs_read", 0)
                    scan_stats["total_html_read"] += muni_stats.get("html_read", 0)

                    if muni_stats.get("no_portal"):
                        scan_stats["munis_no_portal"] += 1
                    elif muni_stats.get("docs_scanned", 0) > 0:
                        scan_stats["munis_with_docs"] += 1
                        stage1_with_docs.add(muni_name)

                    # Collect keyword matches
                    res_list = result.get("matches", [])
                    if res_list:
                        results.extend(res_list)
                        # Save partial results so they survive a crash
                        st.session_state["_scan_results_partial"] = list(results)
                        found_kws = ", ".join(list(set([r['Keyword Found'] for r in res_list])))
                        hit_container.success(f"🎯 **HIT:** {muni_name} — *{found_kws}*")

            except TimeoutError:
                errors.append(f"⏳ {muni_name} — timed out (site unresponsive)")
                scan_stats["munis_errored"] += 1
            except Exception as e:
                errors.append(f"❌ {muni_name} — {str(e)[:100]}")
                scan_stats["munis_errored"] += 1

    # Final status
    error_note = f"  ({len(errors)} failed)" if errors else ""
    status_text.text(f"✅ Scan complete — {total} municipalities processed.{error_note}")
    progress_bar.empty()

    # Show errors in a collapsed section so they don't clutter the results
    if errors:
        st.session_state["_scan_errors"] = errors
        with st.expander(f"⚠️ {len(errors)} municipality scan(s) failed — click to see details", expanded=False):
            for err in errors:
                st.caption(err)

    # Persist final results and stats in session state for recovery after reruns
    st.session_state["_scan_results_final"] = results
    st.session_state["_scan_stats"] = scan_stats

    # ── Stage 2: Search the Selenium pre-fetch cache ──
    cached_df = load_cached_docs()
    cache_matches = []
    cache_stats = {"munis_from_cache": 0, "cache_docs_searched": 0, "cache_hits": 0}

    if not cached_df.empty:
        status_text.text(f"Stage 2: Searching cached portal data ({len(cached_df)} cached docs)...")

        cache_matches, cache_stats = _scan_cached_docs(
            cached_df, registry_subset, keywords,
            stage1_with_docs, negative_keywords
        )

        if cache_matches:
            results.extend(cache_matches)
            st.session_state["_scan_results_final"] = results
            for cm in cache_matches:
                hit_container.info(f"🟡 **CACHED HIT:** {cm['Municipality']} — *{cm['Keyword Found']}*")

        status_text.text(
            f"✅ Scan complete — {total} live + {cache_stats['munis_from_cache']} cached municipalities searched.{error_note}"
        )

    scan_stats["cache_stats"] = cache_stats
    st.session_state["_scan_stats"] = scan_stats

    return pd.DataFrame(results), scan_stats


# --- UI Layout ---

tab_live, tab_history, tab_health = st.tabs(["🚀 Live Target Scanner", "📂 Historical Intelligence Database", "🩺 Portal Health Monitor"])

# ──────────────────────────────────────────────────────────────────
# TAB 3: PORTAL HEALTH MONITOR
# ──────────────────────────────────────────────────────────────────
with tab_health:
    st.markdown("### 🩺 Portal Health Monitor")
    st.markdown("""
    This monitor identifies municipalities that **have not published a readable document in the last 60 days**. 
    If a municipality is listed here, they have likely either:
    1. Changed their website portal completely (e.g., migrated to eScribe)
    2. Stopped uploading documents and switched to Video-only (YouTube)
    3. Experienced a broken link on their homepage
    
    **Action Required:** Locate their new Agendas & Minutes portal online and update the `minutes_listing_url` in your database.
    """)
    
    registry_df = pd.read_csv("signals/portal_registry.csv")
    cutoff_date = (datetime.date.today() - datetime.timedelta(days=60)).isoformat()
    
    # Fill missing dates with a very old date so they show up as stale
    registry_df["example_recent_minutes_date"] = registry_df["example_recent_minutes_date"].fillna("2000-01-01")
    
    stale_df = registry_df[registry_df["example_recent_minutes_date"] < cutoff_date].copy()
    
    if stale_df.empty:
        st.success("✅ All 444 municipal portals are healthy and reporting recent documents!")
    else:
        st.warning(f"⚠️ {len(stale_df)} municipalities have stale portals and require investigation.")
        
        # Clean up presentation
        def safe_days_stale(date_str):
            if date_str == "2000-01-01":
                return "Unknown"
            try:
                d = datetime.date.fromisoformat(str(date_str)[:10])
                return (datetime.date.today() - d).days
            except Exception:
                return "Invalid Data"
                
        stale_df["Days Stale"] = stale_df["example_recent_minutes_date"].apply(safe_days_stale)
        stale_df["Last Document Date"] = stale_df['example_recent_minutes_date'].replace("2000-01-01", "Never Scraped")
        
        display_stale = stale_df[["municipality_name", "tier", "portal_type", "Last Document Date", "Days Stale", "minutes_listing_url"]].sort_values("Last Document Date")
        
        st.dataframe(
            display_stale,
            use_container_width=True,
            column_config={
                "municipality_name": "Municipality",
                "tier": "Tier",
                "portal_type": "Tech Stack",
                "Last Document Date": "Latest Doc Date",
                "Days Stale": "Days Stale",
                "minutes_listing_url": st.column_config.LinkColumn("Current Registered Portal URL", max_chars=100)
            },
            hide_index=True
        )

# ──────────────────────────────────────────────────────────────────
# TAB 1: LIVE TARGET SCANNER  (Fast Scanner Engine)
# ──────────────────────────────────────────────────────────────────
with tab_live:
    st.header("Live Target Scanner")
    st.markdown(
        "Perform a **concurrent, multi-keyword** scan of municipal council portals. "
        "Select preset keyword packs and/or enter your own custom keywords. "
        "The engine scans the **most recent documents** per municipality using a "
        "concurrent thread pool with strict regex word-boundary matching to eliminate false positives."
    )

    # ── Crash recovery: offer partial results from interrupted scans ──
    _partial = st.session_state.get("_scan_results_partial", [])
    _final = st.session_state.get("_scan_results_final", [])
    if _partial and not _final:
        # We have partial but no final → scan was interrupted
        st.warning(
            f"⚠️ **A previous scan was interrupted.** {len(_partial)} hit(s) were saved before the interruption."
        )
        col_recover, col_discard = st.columns(2)
        with col_recover:
            recover_csv = pd.DataFrame(_partial).to_csv(index=False).encode('utf-8')
            st.download_button(
                "📥 Download recovered partial results",
                data=recover_csv,
                file_name=f"recovered_scan_{datetime.date.today().isoformat()}.csv",
                mime="text/csv",
                use_container_width=True,
            )
        with col_discard:
            if st.button("🗑️ Dismiss", use_container_width=True):
                st.session_state["_scan_results_partial"] = []
                st.rerun()

    registry_df = load_registry()

    if registry_df.empty:
        st.warning("Portal Registry not found. Live scanning is unavailable.")
    else:
        # ── Keyword Selection ──
        st.subheader("🔑 Keywords")

        kw_col1, kw_col2, kw_col3 = st.columns([1, 1, 1])

        with kw_col1:
            st.markdown("**Preset Keyword Packs**")
            selected_packs = []
            for pack_name, pack_keywords in CUSTOM_KEYWORD_PACKS.items():
                if st.checkbox(
                    f"{pack_name}",
                    help=f"Keywords: {', '.join(pack_keywords)}",
                    key=f"pack_{pack_name}"
                ):
                    selected_packs.append(pack_name)

        with kw_col2:
            st.markdown("**Custom Keywords** *(one per line)*")
            custom_kw_text = st.text_area(
                "Enter additional keywords",
                placeholder="e.g.\nSolar Farm\nGreenhouses\nAgri-Tourism",
                height=120,
                label_visibility="collapsed",
            )
            st.caption("💡 *Click outside or Ctrl+Enter to register.*")

        with kw_col3:
            st.markdown("**Negative Keywords (Exclude)**")
            negative_kw_text = st.text_area(
                "Enter negative keywords",
                placeholder="e.g.\ngreenhouse gas\nghg",
                height=120,
                label_visibility="collapsed",
            )
            st.caption("💡 *Excludes hits triggered by these exact phrases.*")

        # Build the final keyword list
        all_keywords = []
        for pack_name in selected_packs:
            all_keywords.extend(CUSTOM_KEYWORD_PACKS[pack_name])
        if custom_kw_text.strip():
            custom_kws = [kw.strip() for kw in custom_kw_text.strip().split("\n") if kw.strip()]
            all_keywords.extend(custom_kws)

        # De-duplicate (case-insensitive) while preserving order.
        # Scanning is case-insensitive, so "Greenhouses" and "greenhouses"
        # would produce identical results — we keep the first occurrence.
        seen_kw = set()
        unique_keywords = []
        removed_dupes = []
        for kw in all_keywords:
            if kw.lower() not in seen_kw:
                unique_keywords.append(kw)
                seen_kw.add(kw.lower())
            else:
                removed_dupes.append(kw)

        if unique_keywords:
            st.info(f"**{len(unique_keywords)} keyword(s) selected:** {', '.join(unique_keywords)}")
            if removed_dupes:
                st.caption(
                    f"ℹ️ {len(removed_dupes)} duplicate(s) removed (matching is case-insensitive): "
                    f"*{', '.join(removed_dupes)}*"
                )

        # Enrich registry_df with county for filtering
        county_dict = _load_county_dict()
        valid_regions = set(county_dict.values())
        registry_df['county'] = registry_df['municipality_name'].apply(
            lambda n: _map_county(n, county_dict)
        )
        unique_counties = sorted([
            str(c) for c in registry_df['county'].unique() 
            if c and str(c).strip() and str(c) in valid_regions
        ])

        st.divider()

        # ── Municipality Selection ──
        st.subheader("🏛️ Target Municipalities")

        scan_mode = st.radio(
            "Select scan scope:",
            options=["Select All — Province-Wide Scan", "Select by Region/County", "Select Specific Municipalities"],
            label_visibility="collapsed"
        )

        selected_munis = []
        if scan_mode == "Select by Region/County":
            selected_regions = st.multiselect(
                "Select Region(s) / County(s)",
                options=unique_counties,
                help="Select one or more regions to scan all municipalities within them."
            )
            if selected_regions:
                selected_munis = registry_df[registry_df['county'].isin(selected_regions)]['municipality_name'].tolist()
                st.caption(f"Selecting {len(selected_munis)} municipalities from {len(selected_regions)} region(s).")
        elif scan_mode == "Select Specific Municipalities":
            muni_options = registry_df['municipality_name'].sort_values().tolist()
            selected_munis = st.multiselect(
                "Select specific municipalities",
                options=muni_options,
                default=[],
                help="Choose individual municipalities."
            )

        select_all = (scan_mode == "Select All — Province-Wide Scan")

        st.divider()

        # ── Run Button ──
        if st.button("🚀 Launch Scan", type="primary", use_container_width=True):
            if not unique_keywords:
                st.error("⚠️ Please select at least one keyword pack or enter a custom keyword.")
            elif not select_all and not selected_munis:
                st.error("⚠️ Please select municipalities or enable a Province-Wide scan.")
            else:
                # Resolve target set
                target_df = registry_df.copy()
                if not select_all and selected_munis:
                    target_df = target_df[target_df['municipality_name'].isin(selected_munis)]

                target_df['region'] = target_df.apply(
                    lambda row: get_region(row['county'], row['municipality_name']), axis=1
                )

                unique_negative_keywords = []
                if negative_kw_text.strip():
                    unique_negative_keywords = [kw.strip() for kw in negative_kw_text.strip().split("\n") if kw.strip()]

                st.markdown(f"**Scanning {len(target_df)} municipalities for {len(unique_keywords)} keywords...**")

                live_results, scan_stats = run_live_scan(target_df, unique_keywords, unique_negative_keywords)

                # Extract cache stats
                cache_stats = scan_stats.get("cache_stats", {})
                munis_from_cache = cache_stats.get("munis_from_cache", 0)
                cache_docs = cache_stats.get("cache_docs_searched", 0)
                cache_hits = cache_stats.get("cache_hits", 0)
                total_coverage = scan_stats["munis_with_docs"] + munis_from_cache

                # ── Scan Coverage Report (always shown) ──
                st.markdown("---")
                st.subheader("📡 Scan Coverage Report")

                sc1, sc2, sc3, sc4, sc5, sc6 = st.columns(6)
                sc1.metric("Municipalities Attempted", scan_stats["munis_attempted"])
                sc2.metric("🟢 Live HTTP Scanned", scan_stats["munis_with_docs"])
                sc3.metric("🟡 From Cached Data", munis_from_cache)
                sc4.metric("Total Documents Read", scan_stats["total_docs_scanned"] + cache_docs)
                sc5.metric("❌ Errors / Timeouts", scan_stats["munis_errored"])
                sc6.metric("🚧 No Portal", scan_stats["munis_no_portal"])

                # Coverage percentage
                coverage_pct = (
                    round(total_coverage / scan_stats["munis_attempted"] * 100)
                    if scan_stats["munis_attempted"] > 0 else 0
                )
                st.progress(min(coverage_pct / 100, 1.0))
                st.caption(
                    f"**{coverage_pct}% coverage** — "
                    f"{scan_stats['munis_with_docs']} live + {munis_from_cache} cached = "
                    f"{total_coverage} municipalities with searchable documents."
                )

                # Cache freshness indicator
                cached_df_info = load_cached_docs()
                if not cached_df_info.empty and "fetch_date" in cached_df_info.columns:
                    latest_fetch = cached_df_info["fetch_date"].max()
                    st.caption(f"📅 Cached data last updated: **{latest_fetch}**")
                elif munis_from_cache == 0:
                    st.caption("📅 No cached data available — run `selenium_prefetch.py` locally to cover JS portals.")

                with st.expander("📊 Detailed scan breakdown", expanded=False):
                    st.markdown(f"""
| Metric | Count |
|---|---|
| Municipalities attempted | **{scan_stats['munis_attempted']}** |
| **Stage 1: Live HTTP** | |
| — Municipalities with ≥1 doc read | **{scan_stats['munis_with_docs']}** |
| — PDF documents read | **{scan_stats['total_pdfs_read']}** |
| — HTML pages read | **{scan_stats['total_html_read']}** |
| — Total docs scanned | **{scan_stats['total_docs_scanned']}** |
| **Stage 2: Cached Selenium** | |
| — Municipalities from cache | **{munis_from_cache}** |
| — Cached documents searched | **{cache_docs}** |
| — Hits from cache | **{cache_hits}** |
| **Errors** | |
| — No portal / no docs | **{scan_stats['munis_no_portal']}** |
| — Timed out / errored | **{scan_stats['munis_errored']}** |
                    """)

                if live_results.empty:
                    st.info("No matches found for the specified keywords in the selected municipalities.")
                else:
                    # ── Hit Metrics ──
                    st.markdown("---")
                    st.subheader("🎯 Keyword Hits")
                    m1, m2, m3, m4 = st.columns(4)
                    m1.metric("Total Hits", len(live_results))
                    m2.metric("Unique Municipalities", live_results["Municipality"].nunique())
                    m3.metric("Keywords Matched", live_results["Keyword Found"].nunique())
                    m4.metric("Regions Covered", live_results["Region"].nunique())

                    # ── Region filter for results ──
                    regions_found = sorted(live_results["Region"].unique().tolist())
                    if len(regions_found) > 1:
                        region_filter = st.multiselect(
                            "Filter results by Region",
                            options=regions_found,
                            default=regions_found,
                            key="result_region_filter"
                        )
                        display_results = live_results[live_results["Region"].isin(region_filter)]
                    else:
                        display_results = live_results

                    # ── Results Table ──
                    col_config = {
                        "Source URL": st.column_config.LinkColumn(
                            "Source URL",
                            display_text="🔗 Open Document"
                        ),
                        "Context Snippet": st.column_config.TextColumn(
                            "Context Snippet",
                            width="large"
                        ),
                    }
                    # Only add Scan Method column config if column exists
                    if "Scan Method" in display_results.columns:
                        col_config["Scan Method"] = st.column_config.TextColumn(
                            "Source", width="small"
                        )

                    st.dataframe(
                        display_results,
                        use_container_width=True,
                        hide_index=True,
                        column_config=col_config,
                    )

                    # ── CSV Download ──
                    csv = live_results.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        label="📥 Download Full Scan Report (CSV)",
                        data=csv,
                        file_name=f"multi_keyword_scan_{datetime.date.today().isoformat()}.csv",
                        mime="text/csv",
                        use_container_width=True,
                    )

# ──────────────────────────────────────────────────────────────────
# TAB 2: Historical Intelligence Database
# ──────────────────────────────────────────────────────────────────
with tab_history:
    st.header("Historical Intelligence Insights")
    
    # Query the database for the most recent signal date
    last_update = "Unknown"
    try:
        sync_conn = get_connection()
        latest = pd.read_sql_query(
            "SELECT MAX(discovered_date) as latest FROM scanner_signals",
            sync_conn.conn
        )
        sync_conn.close()
        if not latest.empty and latest.iloc[0]['latest']:
            last_update = str(latest.iloc[0]['latest'])
    except Exception:
        pass

    st.markdown("Query the master database of weekly automated scanner hits. This is the fastest way "
                "to see comprehensive reporting on established OFA bylaw categories across the province.")
    st.info(f"🤖 **Intelligence Database Last Synced:** {last_update}")
    
    hist_df = load_historical_signals()
    
    if hist_df.empty:
        st.info("No historical signals found in the database.")
    else:
        # Filters
        f_col1, f_col2, f_col3 = st.columns(3)
        
        with f_col1:
            # Geographic filter
            all_counties = sorted([c for c in hist_df['county'].dropna().unique() if c.strip()])
            selected_counties = st.multiselect("Filter by County/Region", options=all_counties)
            
        with f_col2:
            # Category filter
            categories = sorted(hist_df['category'].dropna().unique())
            selected_categories = st.multiselect("Filter by Category", options=categories)
            
        with f_col3:
            # Keyword filter (Text search)
            search_text = st.text_input("Search snippets & keywords", placeholder="e.g. exemption, fee")
            
        # Apply filters
        filtered_df = hist_df.copy()
        if selected_counties:
            filtered_df = filtered_df[filtered_df['county'].isin(selected_counties)]
        if selected_categories:
            filtered_df = filtered_df[filtered_df['category'].isin(selected_categories)]
        if search_text:
            mask = (
                filtered_df['snippet'].str.contains(search_text, case=False, na=False) |
                filtered_df['trigger_keyword'].str.contains(search_text, case=False, na=False) |
                filtered_df['municipality'].str.contains(search_text, case=False, na=False) |
                (filtered_df['ai_summary'].str.contains(search_text, case=False, na=False) if 'ai_summary' in filtered_df.columns else False)
            )
            filtered_df = filtered_df[mask]
            
        st.metric("Total Historical Hits", len(filtered_df))
        
        # Format for display
        display_cols = ['discovered_date', 'municipality', 'county', 'category']
        
        if 'ai_summary' in filtered_df.columns and not filtered_df['ai_summary'].isna().all():
            display_cols.extend(['ai_summary', 'ai_confidence'])
        else:
            display_cols.extend(['snippet', 'trigger_keyword'])
            
        display_cols.append('evidence_url')
        
        # Ensure all requested columns actually exist
        display_cols = [c for c in display_cols if c in filtered_df.columns]
        
        st.dataframe(
            filtered_df[display_cols],
            use_container_width=True,
            hide_index=True,
            column_config={
                "evidence_url": st.column_config.LinkColumn(
                    "Evidence URL",
                    display_text="🔗 Open Document"
                )
            }
        )
        
        if not filtered_df.empty:
            csv_hist = filtered_df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="Download Formatted Database Report (CSV)",
                data=csv_hist,
                file_name=f"ofa_bylaw_intelligence_{datetime.date.today().isoformat()}.csv",
                mime="text/csv"
            )

# ──────────────────────────────────────────────────────────────────
# Instructions / User Guide
# ──────────────────────────────────────────────────────────────────
st.divider()

st.markdown("""
## 📖 Guide to the Intelligence Scanner

Welcome to the **Intelligence Scanner**! This tool is your early-warning system to see exactly what local municipal councils are talking about—before it becomes a finalized bylaw. 

Because we track over 400 municipalities, hunting through hundreds of pages of council minutes is exhausting. This tool does the reading for you.

### Tab 1: Live Target Scanner (The "Search Party")
Use this tab when you hear a rumor about a **new or specific issue** popping up in a few municipalities and you want to investigate it *right now*. 
1. **Select your targets:** Choose one or a handful of municipalities you want to investigate.
2. **Type your keyword:** Type the exact phrase you are looking for (like `"Solar Storage"`, `"Eminent Domain"`, or a specific road name).
3. **Run the scan:** The system will rush out to those local websites, download their most recent council minutes, and quickly "speed read" them looking for your exact word. 
4. **Read the snippet:** If it finds your word, it will show you a small "snippet" of text so you can see exactly how it's being discussed along with a link to the original document.

### Tab 2: Historical Intelligence Database (The "Library")
Use this tab when you want a broad, immediate overview of the **7 official OFA bylaw categories** (like Development Charges, Stormwater Fees, or Backyard Chickens) across the whole province.
1. Every week, a master automated system quietly reads thousands of documents looking for official OFA agricultural bylaws and saves whatever it finds in this "library."
2. **Filter by County:** Select your county to instantly see every single official bylaw update that has hit council desks recently in your area. 
3. **Filter by Issue:** Select issues like `"Site Alteration"` to see everyone in the province who is actively proposing new fill rules.
4. **Search inside the snippets:** Use the text box to search for specific words (like `"fee"` or `"exemption"`) *inside* the evidence the automated scanner already saved. 
""")

