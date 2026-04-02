import os
import sys
import json
import re
from datetime import date

# When running from pages/, resolve HERE to the project root (one level up)
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import geopandas as gpd
import pandas as pd
import pydeck as pdk
import streamlit as st

from ofa_content import get_content_for_label

st.set_page_config(page_title="Lower Tier Bylaw Exemptions Map", layout="wide")

LOWER_PARQUET = os.path.join(HERE, "lower_single_map_beta.parquet")

# --- Expiry-based signal tuning ---
EXPIRY_SOON_DAYS = 540  # ~18 months

# Signal priority (used once multiple signal types exist)
SIGNAL_PRIORITY = [
    "Expired",
    "Expiring soon",
    "Mentioned in minutes/agendas",
    "Expiry unknown",
]


def find_status_columns(df: pd.DataFrame) -> list[str]:
    """Return all columns that represent map-ready status fields."""
    return sorted([c for c in df.columns if c.strip().endswith(" Status")])


def pick_name_field(df: pd.DataFrame) -> str:
    """Pick a human-readable name column for municipalities."""
    for c in [
        "MUNICIPALITY",
        "Municipality",
        "NAME",
        "OFFICIAL_M",
        "MUNICIPA_8",
        "MUNICIPA_2",
        "_MUNI_NAME",
    ]:
        if c in df.columns:
            return c
    # Fallback: first column
    return df.columns[0]


def status_color(s: str) -> list[int]:
    """Map a YES/NO/N/A style status string to an RGBA colour."""
    s = (s or "").strip().upper()
    if s == "YES":
        return [0, 128, 0, 160]  # green
    if s == "NO":
        return [200, 0, 0, 160]  # red
    if s == "N/A":
        return [128, 128, 128, 160]  # gray
    return [0, 0, 160, 140]  # blue (other/blank)


def canon_name(x: str) -> str:
    """Lightweight canon used only for joining signals/metadata if needed."""
    if x is None:
        return ""
    s = str(x).replace("\u00A0", " ").strip().upper()
    s = s.replace("&", " AND ").replace("-", " ")
    s = re.sub(r"[’'`]", "", s)
    s = re.sub(r"[^A-Z0-9 /]", " ", s)
    s = s.replace("/", " ")
    s = re.sub(r"\s+", " ", s).strip()
    for p in [
        "CITY OF ",
        "TOWN OF ",
        "TOWNSHIP OF ",
        "VILLAGE OF ",
        "MUNICIPALITY OF ",
        "REGIONAL MUNICIPALITY OF ",
        "REGION OF ",
        "COUNTY OF ",
        "DISTRICT OF ",
    ]:
        if s.startswith(p):
            s = s[len(p) :].strip()
            break
    for suf in [
        " COUNTY",
        " REGION",
        " CITY",
        " TOWN",
        " TOWNSHIP",
        " VILLAGE",
        " MUNICIPALITY",
        " DISTRICT",
    ]:
        if s.endswith(suf):
            s = s[: -len(suf)].strip()
            break
    s = re.sub(r"\b(CO\.?|CNTY)\b$", "", s).strip()
    return re.sub(r"\s+", " ", s).strip()


def load_signals_data():
    """Loads signals.csv, filters for hits in the last 90 days, returns Dict[str, List[Dict]]."""
    sig_path = os.path.join(HERE, "signals", "signals.csv")

    if not os.path.exists(sig_path):
        return {}

    try:
        df = pd.read_csv(sig_path)

        # --- RECENCY FILTER (90 DAYS) ---
        if 'discovered_date' in df.columns:
            df['discovered_date'] = pd.to_datetime(df['discovered_date'])
            cutoff = pd.Timestamp.now() - pd.Timedelta(days=90)
            df = df[df['discovered_date'] > cutoff]

        # MULTI-CATEGORY SUPPORT: Store as List of Dicts per municipality
        signals_map = {}
        for _, row in df.iterrows():
            cname = canon_name(str(row['munid']))
            if cname not in signals_map:
                signals_map[cname] = []
            signals_map[cname].append(row.to_dict())
        return signals_map
    except Exception as e:
        st.error(f"Failed to load signals: {e}")
        return {}


# Map labels -> where to find bylaw metadata in the Parquet
# NOTE: keys must match the map dropdown labels exactly (status col without " Status")
META_BY_LABEL: dict[str, dict[str, str]] = {
    # Development Charges
    "Farm Exemption for Development Charges": {
        "bylaw_name": "Bylaw Name Development Charges",
        "bylaw_link": "Link to DC Bylaw",
        "enacted": "Date Bylaw Enacted (Regional)",
        "expiry": "Expiry Date",
    },
    # Stormwater
    "Farm Exemption for Stormwater Charges": {
        "bylaw_name": "Bylaw Name Stormwater",
        "bylaw_link": "Link to Storm Water bylaw",
        "enacted": "Date Bylaw Enacted2 (Regional)",
        "expiry": "Expiry date2",
    },
    # Site alteration
    "Farm Exemption for SA": {
        "bylaw_name": "Bylaw Name Sute Alteration",
        "bylaw_link": "Link to site alteration & fill bylaw",
        "enacted": "Date Bylaw Enacted4 (Regional)",
        "expiry": "Expiry date 4",
    },
    # Livestock Guardian Dogs (multiple map labels, same bylaw metadata)
    "Has Livestock Guardian dog Definition": {
        "bylaw_name": "Bylaw Name LGD",
        "bylaw_link": "Livestock Guardian Dog bylaw link",
        "enacted": "Date Bylaw Enacted 5 (Regional)",
        "expiry": "Expiry Date 5",
    },
    "LDG - Definition": {
        "bylaw_name": "Bylaw Name LGD",
        "bylaw_link": "Livestock Guardian Dog bylaw link",
        "enacted": "Date Bylaw Enacted 5 (Regional)",
        "expiry": "Expiry Date 5",
    },
    "Herding Dog Definition Exists": {
        "bylaw_name": "Bylaw Name LGD",
        "bylaw_link": "Livestock Guardian Dog bylaw link",
        "enacted": "Date Bylaw Enacted 5 (Regional)",
        "expiry": "Expiry Date 5",
    },
    "LDG and HD exempt from license fees": {
        "bylaw_name": "Bylaw Name LGD",
        "bylaw_link": "Livestock Guardian Dog bylaw link",
        "enacted": "Date Bylaw Enacted 5 (Regional)",
        "expiry": "Expiry Date 5",
    },
    "LDG and HD Collar and tag requirements": {
        "bylaw_name": "Bylaw Name LGD",
        "bylaw_link": "Livestock Guardian Dog bylaw link",
        "enacted": "Date Bylaw Enacted 5 (Regional)",
        "expiry": "Expiry Date 5",
    },
    "LDG and HD Exempt from barking restrictions": {
        "bylaw_name": "Bylaw Name LGD",
        "bylaw_link": "Livestock Guardian Dog bylaw link",
        "enacted": "Date Bylaw Enacted 5 (Regional)",
        "expiry": "Expiry Date 5",
    },
    # Backyard chickens (multiple labels, same bylaw metadata)
    "Can you Keep Backyard Chickens": {
        "bylaw_name": "Bylaw Name Backyard Chicken",
        "bylaw_link": "Backyard Chicken Bylaw Link",
        "enacted": "Date Bylaw Enacted 7 (Regional)",
        "expiry": "Expiry Date 7",
    },
    "Licence Required": {
        "bylaw_name": "Bylaw Name Backyard Chicken",
        "bylaw_link": "Backyard Chicken Bylaw Link",
        "enacted": "Date Bylaw Enacted 7 (Regional)",
        "expiry": "Expiry Date 7",
    },
    "Welfare Requirements": {
        "bylaw_name": "Bylaw Name Backyard Chicken",
        "bylaw_link": "Backyard Chicken Bylaw Link",
        "enacted": "Date Bylaw Enacted 7 (Regional)",
        "expiry": "Expiry Date 7",
    },
    # Tree cutting / forest conservation
    "Farm Exemption - Tree Cutting Bylaw": {
        "bylaw_name": "Bylaw Name Forest Conservation",
        "bylaw_link": "Tree Cutting Bylaw Link",
        "enacted": "Date Bylaw Enacted 6 (Regional)",
        "expiry": "Expiry Date 6",
    },
    # Fence (no expiry currently tracked)
    "Farm Exemption for Security fencing prohibitions": {
        "bylaw_name": "",
        "bylaw_link": "Link to Fence Bylaw",
        "enacted": "",
        "expiry": "",
    },
    "Farm Exemption for Electrified fencing prohibitions": {
        "bylaw_name": "",
        "bylaw_link": "Link to Fence Bylaw",
        "enacted": "",
        "expiry": "",
    },
}

# --- SINGLE SOURCE OF TRUTH: Map sidebar labels -> scanner categories ---
LAYER_TO_CATEGORY = {
    "Farm Exemption for Development Charges": "DC",
    "Farm Exemption for Stormwater Charges": "STORMWATER",
    "Farm Exemption for SA": "SITE_ALT",
    "Farm Exemption - Tree Cutting Bylaw": "TREES",
    "Can you Keep Backyard Chickens": "CHICKENS",
    "Licence Required": "CHICKENS",
    "Welfare Requirements": "CHICKENS",
    "Has Livestock Guardian dog Definition": "LGD",
    "LDG - Definition": "LGD",
    "Herding Dog Definition Exists": "LGD",
    "LDG and HD exempt from license fees": "LGD",
    "LDG and HD Collar and tag requirements": "LGD",
    "LDG and HD Exempt from barking restrictions": "LGD",
    "Farm Exemption for Security fencing prohibitions": "FENCES",
    "Farm Exemption for Electrified fencing prohibitions": "FENCES",
}


def _safe_series(df: pd.DataFrame, col: str) -> pd.Series:
    """Return df[col] if it exists, otherwise a blank Series of equal length."""
    if col and col in df.columns:
        return df[col]
    return pd.Series([""] * len(df), index=df.index)


def add_expiry_signal_columns(gdf: gpd.GeoDataFrame, selected_label: str) -> gpd.GeoDataFrame:
    """Add __EXPIRY__, __SIGNAL__, and __LINE_COLOR__ based on selected label metadata."""
    meta = META_BY_LABEL.get(selected_label, {})
    expiry_col = meta.get("expiry", "")
    bylaw_name_col = meta.get("bylaw_name", "")
    link_col = meta.get("bylaw_link", "")

    expiry_raw = _safe_series(gdf, expiry_col).fillna("").astype(str).str.strip()
    bylaw_name = _safe_series(gdf, bylaw_name_col).fillna("").astype(str).str.strip()
    bylaw_link = _safe_series(gdf, link_col).fillna("").astype(str).str.strip()

    expiry_dt = pd.to_datetime(expiry_raw, errors="coerce")
    today = pd.Timestamp(date.today())
    days = (expiry_dt - today).dt.days

    # Display expiry
    expiry_display = expiry_raw.copy()
    expiry_display = expiry_display.where(expiry_display.ne(""), other="N/A")
    expiry_display = expiry_display.where(expiry_dt.isna(), other=expiry_dt.dt.date.astype(str))

    # Signal logic
    signal = pd.Series([""] * len(gdf), index=gdf.index)

    has_expiry = expiry_dt.notna()
    signal.loc[has_expiry & (days < 0)] = "Expired"
    signal.loc[has_expiry & (days >= 0) & (days <= EXPIRY_SOON_DAYS)] = "Expiring soon"

    # If we expect expiry but don't have one, flag as "Expiry unknown" when a bylaw likely exists
    expects_expiry = bool(expiry_col)
    has_bylaw = bylaw_name.ne("") | bylaw_link.ne("")
    signal.loc[expects_expiry & ~has_expiry & has_bylaw] = "Expiry unknown"

    # Line colour to draw attention to signals (outline only; fill still reflects Status)
    # Only highlight "Expiring soon" and "Expired". "Expiry unknown" is tracked but not highlighted.
    def _line_color_for_signal(sig: str) -> list[int]:
        if sig == "Expiring soon":
            return [255, 165, 0, 255]  # orange
        if sig == "Expired":
            return [0, 0, 0, 255]  # black
        return [60, 60, 60, 255]  # default gray

    line_color = signal.apply(_line_color_for_signal)

    gdf["__EXPIRY__"] = expiry_display
    gdf["__SIGNAL__"] = signal
    gdf["__BYLAW_NAME__"] = bylaw_name
    gdf["__BYLAW_LINK__"] = bylaw_link
    gdf["__LINE_COLOR__"] = line_color

    return gdf


@st.cache_data
def load_data(path: str):
    """Load, reproject and lightly simplify the lower-tier map data.

    Returns:
        gdf: GeoDataFrame with the needed columns (status + metadata + geometry)
        status_cols: list of "... Status" columns
        name_field: chosen municipality name column
    """
    gdf = gpd.read_parquet(path)

    # Ensure WGS84 for pydeck
    try:
        gdf = gdf.to_crs(4326)
    except Exception:
        pass

    status_cols = find_status_columns(gdf)
    name_field = pick_name_field(gdf)

    # Keep: name + all status fields + geometry + all metadata columns that might be used in tooltips
    geom_col = gdf.geometry.name

    meta_cols = []
    patterns = [
        r"(?i)^bylaw name\b",
        r"(?i)\bexpiry\b",
        r"(?i)\blink\b",
        r"(?i)\bdate bylaw enacted\b",
        r"(?i)\bmunicipality has fence bylaw\b",
    ]
    for c in gdf.columns:
        if c == geom_col or c == name_field or c in status_cols:
            continue
        if any(re.search(p, c) for p in patterns):
            meta_cols.append(c)

    keep_cols = set(status_cols + [name_field, geom_col] + meta_cols)
    gdf = gdf[list(keep_cols)].copy()

    # Light geometry simplification to cut JSON size and drawing time.
    gdf[geom_col] = gdf[geom_col].simplify(tolerance=0.001, preserve_topology=True)

    return gdf, status_cols, name_field


# ---------- Load data ----------
try:
    base_gdf, status_cols, name_field = load_data(LOWER_PARQUET)
    
    # --- SIGNALS INTEGRATION ---
    signals_data = load_signals_data()

    def check_signal(name_val):
        return canon_name(name_val) in signals_data

    if name_field in base_gdf.columns:
        base_gdf["HAS_SIGNAL"] = base_gdf[name_field].apply(check_signal)
    else:
        base_gdf["HAS_SIGNAL"] = False
    # ---------------------------

except FileNotFoundError:
    st.error(f"Parquet not found: {LOWER_PARQUET}. Commit the file to the repo.")
    st.stop()

if not status_cols:
    st.error("No '… Status' columns found. Rebuild the data and push the new Parquet file.")
    st.stop()

# ---------- Sidebar ----------
st.sidebar.header("Filters")

display_labels = {col: col.replace(" Status", "") for col in status_cols}
label_to_col = {v: k for k, v in display_labels.items()}

selected_label = st.sidebar.selectbox("Bylaw", list(display_labels.values()), index=0)
selected_col = label_to_col[selected_label]

# Split filters: Status vs Expiry alerts (signals)
status_filter = st.sidebar.selectbox("Status", ["All", "YES", "NO", "N/A"], index=0)
signal_filter = st.sidebar.selectbox(
    "Expiry alert",
    ["All", "Expiring soon", "Expired", "Expiry unknown"],
    index=0,
)

# --- NEW: Scanner Signal Filter ---
show_scanner_hits = st.sidebar.checkbox("🚨 Filter to Scanner Signals", value=False)

# --- DOWNLOAD SCANNER RESULTS ---
if show_scanner_hits:
    st.sidebar.markdown("---")
    st.sidebar.caption("📥 **Export Scanner Results**")
    
    report_mode = st.sidebar.radio("Content:", ["Current View Only", "All Scanner Hits"], key="report_mode")
    
    if st.sidebar.button("Generate CSV Report"):
        # 1. Gather Data based on mode
        export_rows = []
        
        # Flatten the signals_data dictionary (values are lists of dicts)
        all_hits = []
        for muni_hits in signals_data.values():
            all_hits.extend(muni_hits)
            
        # Define category mapping for filtering
        # Uses module-level LAYER_TO_CATEGORY constant
            
        for hit in all_hits:
            # Filter Logic
            keep = False
            if report_mode == "All Scanner Hits":
                keep = True
            else:
                # Filter to Current View Category
                if hit.get('category') == LAYER_TO_CATEGORY.get(selected_label):
                    keep = True
            
            if keep:
                export_rows.append({
                    "Municipality": hit.get('munid'),
                    "Bylaw Category": hit.get('category'),
                    "Trigger Keyword": hit.get('trigger_keyword'),
                    "Evidence Link": hit.get('evidence_url'),
                    "Found Date": hit.get('discovered_date')
                })
        
        # 2. Convert to CSV
        if export_rows:
            df_export = pd.DataFrame(export_rows)
            csv_data = df_export.to_csv(index=False).encode('utf-8')
            
            st.sidebar.download_button(
                label="⬇️ Download CSV",
                data=csv_data,
                file_name=f"scanner_hits_{report_mode.replace(' ', '_').lower()}.csv",
                mime="text/csv"
            )
        else:
            st.sidebar.warning("No hits found for this selection.")
# ----------------------------------
display_mode = st.sidebar.selectbox(
    "Display mode",
    ["Highlight matches", "Filter to matches"],
    index=0,
)

# Search box
search_term = st.sidebar.text_input(
    f"Search {name_field}", value="", placeholder="Type part of a name…"
).strip()

# ---------- Dynamic title ----------
st.title(f"Lower Tier Bylaw Exemptions Map – {selected_label}")

# ---------- Prepare data ----------
# Work on a copy so the cached base_gdf stays clean.
gdf_all = base_gdf.copy()

gdf_all["__STATUS__"] = (
    gdf_all[selected_col]
    .fillna("")
    .astype(str)
    .str.strip()
    .str.upper()
    .replace({"UNKNOWN": "NOT KNOWN", "NA": "N/A", "NOT KNOWN": "N/A"})
)

# Compute fill colours (fill is driven by Status)
gdf_all["__COLOR__"] = gdf_all["__STATUS__"].apply(status_color)

# Add expiry + signal columns for the current selection (outlines + tooltip/sidebar metadata)
gdf_all = add_expiry_signal_columns(gdf_all, selected_label)

# --- 🚨 PATCH: SCANNER SIGNAL OVERRIDE (v2) 🚨 ---
# Trust the fuzzy matching already done by 'HAS_SIGNAL' earlier in the script
if "HAS_SIGNAL" in gdf_all.columns:
    # If the map found a signal (fuzzy match), FORCE the status to Scanner Detection
    # This overrides "Expiring Soon" or "Expiry Unknown"
    gdf_all.loc[gdf_all["HAS_SIGNAL"] == True, "__SIGNAL__"] = "Mentioned in minutes/agendas"
# -----------------------------------------------------

# ---------- Build match mask (what "filters" mean) ----------
match_mask = pd.Series(True, index=gdf_all.index)

if status_filter != "All":
    match_mask &= gdf_all["__STATUS__"].eq(status_filter)

if signal_filter != "All":
    match_mask &= gdf_all["__SIGNAL__"].eq(signal_filter)

# --- SMART SIGNAL FILTERING ---
if show_scanner_hits and "HAS_SIGNAL" in gdf_all.columns:
    # 1. Base Filter: Must have a signal
    signal_mask = gdf_all["HAS_SIGNAL"].eq(True)

    # 2. Category Filter: Match the Map Layer to the Signal Category
    # Uses module-level LAYER_TO_CATEGORY constant

    target_category = LAYER_TO_CATEGORY.get(selected_label, None)

    if target_category:
        # Check if ANY of the municipality's signals match the target category
        def signal_matches_category(muni_name):
            cname = canon_name(str(muni_name))
            hits = signals_data.get(cname, [])
            # Check if any signal in the list matches the target category
            return any(h.get('category', 'DC') == target_category for h in hits)

        category_match = gdf_all[name_field].apply(signal_matches_category)
        match_mask &= (signal_mask & category_match)
    else:
        # If viewing a layer with no scanner targets (e.g. Fences), hide signals
        match_mask &= False
# ---------------------------------

if search_term:
    match_mask &= gdf_all[name_field].astype(str).str.contains(search_term, case=False, na=False)

gdf_match = gdf_all[match_mask].copy()

# ---------- Sidebar: Municipality details ----------
st.sidebar.divider()
st.sidebar.subheader("Municipality details")

limit_muni_list = st.sidebar.checkbox("Limit list to current results", value=True)

muni_source = gdf_match if (limit_muni_list and not gdf_match.empty) else gdf_all
muni_options = sorted(muni_source[name_field].dropna().astype(str).unique().tolist())

# If filters result in 0 options, fall back to full list
if not muni_options:
    muni_options = sorted(gdf_all[name_field].dropna().astype(str).unique().tolist())

# --- CRITICAL FIX: Ensure Selected Muni is Always in Options ---
# If a user clicks a map polygon that is currently filtered out (e.g. clicking a 'NO' muni 
# while filtering for 'YES'), we must forcibly add it to the options list so the widget 
# doesn't crash or ignore the selection.
current_selection = st.session_state.get("selected_muni")
if current_selection and current_selection not in muni_options:
    muni_options.append(current_selection)
    muni_options = sorted(muni_options)
# -------------------------------------------------------------

# Keep Streamlit widget state valid if options change
if "selected_muni" not in st.session_state:
    st.session_state["selected_muni"] = muni_options[0] if muni_options else ""
elif st.session_state["selected_muni"] not in muni_options and muni_options:
    st.session_state["selected_muni"] = muni_options[0]

selected_muni = st.sidebar.selectbox("Select a municipality", options=muni_options, key="selected_muni")

# ---------- Display mode: filter vs highlight ----------
if display_mode == "Filter to matches":
    gdf_view = gdf_match.copy()
else:
    # Highlight matches but keep context: dim non-matching municipalities
    gdf_view = gdf_all.copy()

    dim_alpha = 40  # lower alpha for non-matches (keeps YES/NO/N/A colour but fades it)

    def _dim_rgba(rgba):
        if isinstance(rgba, (list, tuple)) and len(rgba) == 4:
            return [int(rgba[0]), int(rgba[1]), int(rgba[2]), dim_alpha]
        return rgba

    nonmatch_line = [200, 200, 200, 40]

    gdf_view["__COLOR__"] = [
        (rgba if is_match else _dim_rgba(rgba))
        for rgba, is_match in zip(gdf_view["__COLOR__"].tolist(), match_mask.tolist())
    ]
    gdf_view["__LINE_COLOR__"] = [
        (lc if is_match else nonmatch_line)
        for lc, is_match in zip(gdf_view["__LINE_COLOR__"].tolist(), match_mask.tolist())
    ]

# Variable line width: thicker for matches, thinner for context features
if display_mode == "Highlight matches":
    gdf_view["__LINE_WIDTH__"] = [2 if m else 1 for m in match_mask.tolist()]
else:
    gdf_view["__LINE_WIDTH__"] = 2

# ---------- Summary cards (counts reflect the matching set) ----------
counts = gdf_match["__STATUS__"].value_counts()
yes = int(counts.get("YES", 0))
no = int(counts.get("NO", 0))
na = int(counts.get("N/A", 0))

sig_counts = gdf_match["__SIGNAL__"].value_counts()
expiring = int(sig_counts.get("Expiring soon", 0))
expired = int(sig_counts.get("Expired", 0))
unknown = int(sig_counts.get("Expiry unknown", 0))

c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric("YES", f"{yes}")
c2.metric("NO", f"{no}")
c3.metric("N/A", f"{na}")
c4.metric("Expiring soon", f"{expiring}")
c5.metric("Expired", f"{expired}")
c6.metric("Expiry unknown", f"{unknown}")

st.caption(
    f"Matches: {len(gdf_match)} of {len(gdf_all)} municipalities.  "
    "Outline legend: 🟧 Expiring soon • ⬛ Expired • 🟨 Expiry unknown • ⬜ No expiry alert  •  Outline priority (if multiple signals): Expired > Expiring soon > Mentioned in minutes/agendas > Expiry unknown"
)

if gdf_match.empty:
    st.warning("No municipalities match the current filters.")

# ---------- Map data prep ----------
# --- SMART BORDER LOGIC ---
# Define Mapping for Border Logic (matches the filter logic)
# Uses module-level LAYER_TO_CATEGORY constant (defined after META_BY_LABEL)

# Determine the category for the CURRENTLY selected layer
current_map_category = LAYER_TO_CATEGORY.get(selected_label, None)

def get_border_color(row):
    sig = row.get("__SIGNAL__")
    
    # 1. Official Bylaw Status Signals (Priority High)
    if sig == "Expired":
        return [0, 0, 0, 255]         # Black
    if sig == "Expiring soon":
        return [255, 165, 0, 255]     # Orange
    if sig == "Expiry unknown":
        return [255, 255, 0, 255]     # Yellow
        
    # 2. Scanner "Minutes/Agendas" Signals (Priority Medium)
    # CRITICAL FIX: Only show Red Border if the signal matches the current map layer
    if row.get("HAS_SIGNAL") == True:
        # Look up the list of signals for this municipality
        muni_name = str(row[name_field])
        cname = canon_name(muni_name)
        
        hits = signals_data.get(cname, [])
        # Check if ANY signal in the list matches the current map category
        if any(h.get('category', 'DC') == current_map_category for h in hits):
            return [255, 69, 0, 255]      # Red-Orange
        
    # 3. Default (Priority Low)
    return [100, 100, 100, 100]       # Grey

# Apply to gdf_view so it reflects in the generated GeoJSON
gdf_view["__BORDER_COLOR__"] = gdf_view.apply(get_border_color, axis=1)

geom_col = gdf_view.geometry.name

# Add __BORDER_COLOR__ to the properties list
props_df = gdf_view[
    [
        name_field,
        "__STATUS__",
        "__COLOR__",
        "__EXPIRY__",
        "__SIGNAL__",
        "__BYLAW_NAME__",
        "__BYLAW_LINK__",
        "__BORDER_COLOR__", 
        "__LINE_WIDTH__",
        geom_col,
    ]
].copy()

# Create GeoJSON from the VIEW
geojson = json.loads(props_df.to_json())

# ---------- Map ----------
layer = pdk.Layer(
    "GeoJsonLayer",
    geojson,
    pickable=True,
    opacity=0.5,
    stroked=True,
    filled=True,
    extruded=False,
    wireframe=True,
    get_fill_color="properties.__COLOR__",
    get_line_color="properties.__BORDER_COLOR__",
    lineWidthMinPixels=2,          # <--- FIXED: Restores crisp borders
    auto_highlight=True,
)

view_state = pdk.ViewState(latitude=44.0, longitude=-80.0, zoom=5.8)

# ---------- Map with Selection (DIAGNOSTIC MODE) ----------
# We enable selection on the map to update the sidebar
event = st.pydeck_chart(
    pdk.Deck(
        layers=[layer],
        initial_view_state=view_state,
        map_style="light",
        tooltip={
            "text": (
                f"{{{name_field}}}\n"
                "Status: {__STATUS__}\n"
                "Expiry: {__EXPIRY__}\n"
                "Signal: {__SIGNAL__}\n"
                "Bylaw: {__BYLAW_NAME__}\n"
                "Link: {__BYLAW_LINK__}"
            )
        },
    ),
    on_select="rerun",  # Forces the app to reload immediately on click
    selection_mode="single-object"
)

# --- CLICK HANDLER LOGIC ---
if event.selection:
    indices = None
    objects = event.selection.get("objects")
    
    # 1. Parse the selection format (Dict vs List)
    if isinstance(objects, dict):
        indices = list(objects.keys())
    elif isinstance(objects, list) and objects:
        indices = objects 

    if indices:
        try:
            # 2. Get the index
            idx = int(list(indices)[0])
            
            # 3. Look up the municipality name
            if idx < len(gdf_view):
                clicked_muni = gdf_view.iloc[idx][name_field]
                
                # 4. Force Sidebar Update
                if st.session_state.get("selected_muni") != clicked_muni:
                    st.session_state["selected_muni"] = clicked_muni
                    st.rerun() 
                    
        except Exception as e:
            st.sidebar.error(f"Click Logic Error: {e}")
            
else:
    st.sidebar.caption("Click a municipality on the map to view details.")

# ---------- Municipality details panel (sidebar) ----------
detail_row = gdf_all[gdf_all[name_field].astype(str).eq(str(selected_muni))].head(1)
if len(detail_row) == 1:
    r = detail_row.iloc[0]

    st.sidebar.markdown(f"**Selected bylaw topic:** {selected_label}")
    st.sidebar.markdown(f"**Status:** {str(r.get('__STATUS__', 'N/A') or 'N/A')}")
    st.sidebar.markdown(f"**Expiry signal:** {str(r.get('__SIGNAL__', '') or '').strip() or '—'}")

    bylaw_name = str(r.get("__BYLAW_NAME__", "") or "").strip()
    enacted = str(r.get("__ENACTED__", "") or "").strip()
    expiry = str(r.get("__EXPIRY__", "") or "").strip()
    bylaw_link = str(r.get("__BYLAW_LINK__", "") or "").strip()

    if bylaw_name:
        st.sidebar.markdown(f"**Bylaw:** {bylaw_name}")
    if enacted and enacted != "N/A":
        st.sidebar.markdown(f"**Enacted:** {enacted}")
    if expiry and expiry != "N/A":
        st.sidebar.markdown(f"**Expiry:** {expiry}")
    if bylaw_link:
        st.sidebar.markdown(f"**Bylaw Source:** {bylaw_link}")

    # --- NEW: Contextual Signal Display (Multi-Hit Safe) ---
    cname_selected = canon_name(str(selected_muni))
    
    if 'signals_data' in locals() and cname_selected in signals_data:
        hits_list = signals_data[cname_selected] # This is now a LIST
        
        # Redefine mapping locally to ensure we find the right signal for this view
        # Uses module-level LAYER_TO_CATEGORY constant
        
        target_category = LAYER_TO_CATEGORY.get(selected_label, None)
        
        # Find the specific hit that matches the layer we are viewing
        target_hit = None
        for h in hits_list:
            if h.get('category') == target_category:
                target_hit = h
                break
        
        # If we found a hit for THIS category, display it
        if target_hit:
            evidence_url = target_hit.get('evidence_url', '')
            snippet = str(target_hit.get('snippet', '')).strip()
            
            # Clean up date format
            raw_date = str(target_hit.get('discovered_date', 'Unknown'))
            found_date = raw_date.split(" ")[0] if " " in raw_date else raw_date
            
            if evidence_url:
                st.sidebar.markdown("---")
                st.sidebar.error("🔍 **Scanner Evidence Found**")

                trigger_word = str(target_hit.get('trigger_keyword', 'General Keyword')).strip()
                st.sidebar.info(f"**Trigger:** Found **'{trigger_word}'** on {found_date}.")

                if snippet and snippet.lower() != "nan":
                    # Sanitize snippet
                    clean_snippet = snippet.replace('\r', ' ').replace('\n', ' ')
                    clean_snippet = ' '.join(clean_snippet.split())
                    clean_snippet = clean_snippet.strip()[:250]
                    st.sidebar.caption(f"**Context:** \"...{clean_snippet}...\"")

                st.sidebar.markdown(f"👉 [**View Source Document**]({evidence_url})")

# ---------- OFA position + template letter ----------
content = get_content_for_label(selected_label)

if content is not None:
    st.subheader(content.title)
    st.markdown(content.body_md)

    if content.letter_path:
        template_path = os.path.join(HERE, content.letter_path)
        if os.path.exists(template_path):
            with open(template_path, "rb") as f:
                st.download_button(
                    label="Download template letter for this bylaw (.docx)",
                    data=f,
                    file_name=os.path.basename(template_path),
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
        else:
            st.info(
                "A template letter is expected for this bylaw, but the .docx file is not present in the repository."
            )
    else:
        st.info("A template letter for this bylaw type is not currently available.")

# ---------- Legend ----------
with st.expander("Legend", expanded=False):
    st.markdown(
        "- **YES** = green  \n"
        "- **NO** = red  \n"
        "- **N/A** = gray  \n"
        "- **Other/blank** = blue  \n"
        "- **Red-Orange outline** = Mentioned in minutes/agendas (Scanner Hit) \n"
        "- **Orange outline** = expiring soon  \n"
        "- **Black outline** = expired  \n"
        "- **Yellow outline** = expiry unknown (bylaw exists)  \n"
        "- **Highlight mode** dims non-matches instead of removing them"
    )

# ---------- Results table + export ----------
with st.expander("Results (filtered) – table + export", expanded=False):
    table = gdf_match[
        [name_field, "__STATUS__", "__EXPIRY__", "__SIGNAL__", "__BYLAW_NAME__", "__BYLAW_LINK__"]
    ].copy()

    table = table.rename(
        columns={
            name_field: "Municipality",
            "__STATUS__": "Status",
            "__EXPIRY__": "Expiry",
            "__SIGNAL__": "Expiry alert",
            "__BYLAW_NAME__": "Bylaw",
            "__BYLAW_LINK__": "Bylaw link",
        }
    )

    st.dataframe(table, use_container_width=True, hide_index=True)

    csv_bytes = table.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
    st.download_button(
        "Download these results as CSV",
        data=csv_bytes,
        file_name="bylaw_map_results.csv",
        mime="text/csv",
    )
