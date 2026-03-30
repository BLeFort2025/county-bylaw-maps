import os
import sys
import datetime
import io
import time
import requests
import urllib3

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
    df = pd.read_sql_query(query, conn)
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

def extract_text_from_pdf(pdf_bytes):
    text = ""
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\\n"
    except Exception as e:
        return f"[PDF Error: {e}]"
    return text

def run_live_scan(registry_subset, custom_keyword):
    """Executes a live HTTP/PDF scan over a subset of municipalities."""
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
        url = row.get('example_recent_minutes_url', None)
        
        status_text.text(f"Scanning {name} ({i+1}/{total})...")
        progress_bar.progress((i + 1) / total)
        
        if pd.isna(url) or not str(url).strip():
            continue
            
        try:
            # 10s timeout to keep UI responsive
            response = requests.get(url, headers=headers, timeout=10, verify=False)
            if response.status_code == 200:
                content_type = response.headers.get('Content-Type', '').lower()
                text_content = ""
                
                # Extract text
                if 'pdf' in content_type or str(url).lower().endswith('.pdf'):
                    if PDF_SUPPORT:
                        text_content = extract_text_from_pdf(response.content)
                else:
                    text_content = response.text
                
                # Check Keyword
                if kw_lower in text_content.lower():
                    # Extract 200-char context window mapping against exact casing
                    snippet = extract_snippet(text_content, custom_keyword, window=200)
                    results.append({
                        "Municipality": name,
                        "Date Scanned": datetime.date.today().isoformat(),
                        "Keyword Found": custom_keyword,
                        "Context Snippet": snippet,
                        "Source URL": url
                    })
        except Exception as e:
            # Skip on timeout/SSL error during live scans
            pass
            
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
                    st.dataframe(live_results, use_container_width=True, hide_index=True)
                    
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
    
    db_path = os.path.join(ROOT_DIR, "bylaws.db")
    last_update = "Unknown"
    if os.path.exists(db_path):
        import time
        mtime = os.path.getmtime(db_path)
        last_update = datetime.datetime.fromtimestamp(mtime).strftime('%B %d, %Y at %I:%M %p')
        
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
        
        st.dataframe(filtered_df[display_cols], use_container_width=True, hide_index=True)
        
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

