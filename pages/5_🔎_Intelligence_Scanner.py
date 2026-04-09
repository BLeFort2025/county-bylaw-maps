import os
import sys
import datetime
import io
import time
import requests
import urllib3
import urllib.parse

import streamlit as st
import pandas as pd

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
from shared_config import KEYWORD_CONFIG, extract_snippet
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
    import re
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


def _find_recent_doc_links(listing_url, headers, max_links=3):
    """Spider a listing page to find the most recent document links."""
    if not BS4_SUPPORT:
        return []

    try:
        resp = requests.get(listing_url, headers=headers, timeout=12, verify=False)
        if resp.status_code != 200:
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        links = soup.find_all("a", href=True)

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
            has_doc_keyword = any(w in text.lower() for w in
                                 ["minute", "agenda", "council meeting", "regular meeting"])

            if (is_pdf or is_ashx or has_doc_keyword) and full_url not in seen_urls:
                # Try to extract a date for sorting
                date_hint = _extract_date_from_text(text + " " + full_url)
                candidates.append((full_url, text[:80], date_hint))
                seen_urls.add(full_url)

        # Sort: dated links first (newest first), then undated
        dated = [(u, t, d) for u, t, d in candidates if d is not None]
        undated = [(u, t, d) for u, t, d in candidates if d is None]
        dated.sort(key=lambda x: x[2], reverse=True)

        sorted_candidates = dated + undated

        # Return just the URLs, limited to top N
        return [url for url, _, _ in sorted_candidates[:max_links]]

    except Exception:
        return []


def _fetch_and_extract_text(url, headers):
    """Download a URL and extract its text content (HTML or PDF)."""
    try:
        response = requests.get(url, headers=headers, timeout=12, verify=False)
        if response.status_code != 200:
            return ""

        content_type = response.headers.get('Content-Type', '').lower()

        if 'pdf' in content_type or url.lower().endswith('.pdf'):
            if PDF_SUPPORT:
                return extract_text_from_pdf(response.content)
            return ""
        else:
            return response.text
    except Exception:
        return ""


def run_live_scan(registry_subset, custom_keyword):
    """Executes a live HTTP/PDF scan over a subset of municipalities.

    For each municipality:
      1. Spider the listing page to find recent documents
      2. Scan the top 3 most recent documents for the keyword
      3. Fall back to the hardcoded example URL if spidering finds nothing
    """
    results = []

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                      'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

    progress_bar = st.progress(0)
    status_text = st.empty()

    total = len(registry_subset)
    kw_lower = custom_keyword.lower()

    for i, row in registry_subset.reset_index(drop=True).iterrows():
        name = row.get('municipality_name', 'Unknown')
        listing_url = row.get('minutes_listing_url', None)
        fallback_url = row.get('example_recent_minutes_url', None)

        status_text.text(f"Scanning {name} ({i+1}/{total})...")
        progress_bar.progress((i + 1) / total)

        # Step 1: Spider the listing page for recent documents
        urls_to_scan = []
        if listing_url and not pd.isna(listing_url) and str(listing_url).strip():
            urls_to_scan = _find_recent_doc_links(str(listing_url).strip(), headers, max_links=3)

        # Step 2: Fall back to the hardcoded example URL if spidering found nothing
        if not urls_to_scan:
            if fallback_url and not pd.isna(fallback_url) and str(fallback_url).strip():
                urls_to_scan = [str(fallback_url).strip()]

        if not urls_to_scan:
            continue

        # Step 3: Scan each document for the keyword
        for url in urls_to_scan:
            text_content = _fetch_and_extract_text(url, headers)

            if kw_lower in text_content.lower():
                snippet = extract_snippet(text_content, custom_keyword, window=200)
                results.append({
                    "Municipality": name,
                    "Date Scanned": datetime.date.today().isoformat(),
                    "Keyword Found": custom_keyword,
                    "Context Snippet": snippet,
                    "Source URL": url
                })
                break  # One hit per municipality is enough

    status_text.text("Scan Complete!")
    progress_bar.empty()
    return pd.DataFrame(results)

# --- UI Layout ---

tab_live, tab_history = st.tabs(["🚀 Live Target Scanner", "📂 Historical Intelligence Database"])

# ──────────────────────────────────────────────────────────────────
# TAB 1: Live Target Scanner
# ──────────────────────────────────────────────────────────────────
with tab_live:
    st.header("Live Target Scanner")
    st.markdown("Perform an immediate web scan of municipal council portals for a custom keyword. "
                "*Note: Selecting a large number of municipalities will take a few minutes.*")
    
    registry_df = load_registry()
    
    if registry_df.empty:
        st.warning("Portal Registry not found. Live scanning is unavailable.")
    else:
        col1, col2 = st.columns([2, 1])
        
        with col1:
            muni_options = registry_df['municipality_name'].sort_values().tolist()
            selected_munis = st.multiselect(
                "Select Municipalities to Scan",
                options=muni_options,
                default=[],
                help="Leave blank to scan ALL (Warning: Will take several minutes)"
            )
            
        with col2:
            custom_kw = st.text_input("Custom Keyword", placeholder="e.g. Solar Farm, Greenhouses")
            
        if st.button("Run Live Scan", type="primary"):
            if not custom_kw.strip():
                st.error("Please enter a custom keyword.")
            else:
                target_df = registry_df
                if selected_munis:
                    target_df = registry_df[registry_df['municipality_name'].isin(selected_munis)]
                
                with st.spinner(f"Initiating scan for '{custom_kw}'..."):
                    live_results = run_live_scan(target_df, custom_kw.strip())
                    
                if live_results.empty:
                    st.info("No matches found for the specified keyword in the selected municipalities.")
                else:
                    st.success(f"Found {len(live_results)} matches!")
                    st.dataframe(
                        live_results,
                        use_container_width=True,
                        hide_index=True,
                        column_config={
                            "Source URL": st.column_config.LinkColumn(
                                "Source URL",
                                display_text="🔗 Open Document"
                            )
                        }
                    )
                    
                    csv = live_results.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        label="Download Custom Scan Report (CSV)",
                        data=csv,
                        file_name=f"live_scan_{custom_kw}_{datetime.date.today().isoformat()}.csv",
                        mime="text/csv"
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

