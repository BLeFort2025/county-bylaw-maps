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

from ofa_content import get_content_for_label, BYLAW_GROUP_FOR_LABEL
from letter_engine import (
    resolve_municipality_id, get_recipient_email,
    fill_letter_template, letter_to_plain_text,
    generate_mailto_link, build_email_subject, build_fields,
    log_advocacy_action, get_advocacy_stats, build_cover_email_body
)
from db_utils import get_connection
from bldg_fees_calc import evaluate_bldg_fee, fee_cost_tier_rgba
from site_alt_fees_calc import evaluate_site_alt_fee

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
    return sorted([c for c in df.columns if c.strip().endswith(" Status") and c.strip() != "Municipal Status"])


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
    """Map a YES/PARTIAL/NO/N/A style status string to an RGBA colour."""
    s = (s or "").strip().upper()
    if s == "YES":
        return [0, 128, 0, 160]  # green
    if s == "PARTIAL":
        return [236, 168, 66, 180]  # OFA Tulip Tree amber (statutory-only / partial)
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
    """Loads signals from the database scanner_signals table and signals.csv (90-day window)."""
    frames = []

    # 1. Load from database scanner_signals table
    try:
        conn = get_connection()
        db_df = pd.read_sql_query(
            """
            SELECT m.name AS munid, s.signal_type, s.discovered_date,
                   s.trigger_keyword, s.category, s.snippet,
                   s.ai_summary, s.ai_confidence, s.evidence_url
            FROM scanner_signals s
            LEFT JOIN municipalities m ON m.id = s.municipality_id
            """,
            conn.conn,
        )
        conn.close()
        if not db_df.empty:
            frames.append(db_df)
    except Exception:
        pass

    # 2. Load from signals/signals.csv fallback/supplement
    sig_path = os.path.join(HERE, "signals", "signals.csv")
    if os.path.exists(sig_path):
        try:
            csv_df = pd.read_csv(sig_path)
            if not csv_df.empty:
                frames.append(csv_df)
        except Exception:
            pass

    if not frames:
        return {}

    try:
        df = pd.concat(frames, ignore_index=True)

        # --- RECENCY FILTER (90 DAYS) ---
        if "discovered_date" in df.columns:
            df["_dt"] = pd.to_datetime(df["discovered_date"], errors="coerce")
            cutoff = pd.Timestamp.now() - pd.Timedelta(days=90)
            df = df[df["_dt"].isna() | (df["_dt"] >= cutoff)].drop(columns=["_dt"])

        # Deduplicate across DB and CSV
        df["_canon"] = df["munid"].astype(str).apply(canon_name)
        dedup_cols = [c for c in ["_canon", "category", "trigger_keyword", "evidence_url"] if c in df.columns]
        if dedup_cols:
            df = df.drop_duplicates(subset=dedup_cols, keep="first")

        # MULTI-CATEGORY SUPPORT: Store as List of Dicts per municipality
        signals_map = {}
        for _, row in df.iterrows():
            cname = row["_canon"]
            if not cname:
                continue
            if cname not in signals_map:
                signals_map[cname] = []
            signals_map[cname].append(row.drop(labels=["_canon"], errors="ignore").to_dict())
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
        "bylaw_name": "Bylaw Name Site Alteration",
        "bylaw_link": "Link to site alteration & fill bylaw",
        "enacted": "Date Bylaw Enacted4 (Regional)",
        "expiry": "Expiry date 4",
    },
    # Livestock Guardian Dogs — combined LGD + HD definition, plus individual provisions
    "LGD/HD Working Dog Definition": {
        "bylaw_name": "Bylaw Name LGD",
        "bylaw_link": "Livestock Guardian Dog bylaw link",
        "enacted": "Date Bylaw Enacted 5 (Regional)",
        "expiry": "Expiry Date 5",
    },
    "LGD and HD Exempt from License Fees": {
        "bylaw_name": "Bylaw Name LGD",
        "bylaw_link": "Livestock Guardian Dog bylaw link",
        "enacted": "Date Bylaw Enacted 5 (Regional)",
        "expiry": "Expiry Date 5",
    },
    "LGD and HD Collar and Tag Requirements": {
        "bylaw_name": "Bylaw Name LGD",
        "bylaw_link": "Livestock Guardian Dog bylaw link",
        "enacted": "Date Bylaw Enacted 5 (Regional)",
        "expiry": "Expiry Date 5",
    },
    "LGD and HD Exempt from Barking Restrictions": {
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
        "bylaw_name": "Bylaw Name Fence",
        "bylaw_link": "Link to Fence Bylaw",
        "enacted": "Date Bylaw Enacted 8",
        "expiry": "",
    },
    "Farm Exemption for Electrified fencing prohibitions": {
        "bylaw_name": "Bylaw Name Fence",
        "bylaw_link": "Link to Fence Bylaw",
        "enacted": "Date Bylaw Enacted 8",
        "expiry": "",
    },
    # Farm building permit fees
    "Farm Building Permit Fees": {
        "bylaw_name": "Bylaw Name Building Fees",
        "bylaw_link": "Link to Building Fees Bylaw",
        "enacted": "Date Bylaw Enacted 9",
        "expiry": "Expiry Date 9",
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
    "LGD/HD Working Dog Definition": "LGD",
    "LGD and HD Exempt from License Fees": "LGD",
    "LGD and HD Collar and Tag Requirements": "LGD",
    "LGD and HD Exempt from Barking Restrictions": "LGD",
    "Farm Exemption for Security fencing prohibitions": "FENCES",
    "Farm Exemption for Electrified fencing prohibitions": "FENCES",
    "Farm Building Permit Fees": "BLDG_FEES",
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
    enacted_col = meta.get("enacted", "")
    bylaw_name_col = meta.get("bylaw_name", "")
    link_col = meta.get("bylaw_link", "")

    expiry_raw = _safe_series(gdf, expiry_col).fillna("").astype(str).str.strip()
    enacted_raw = _safe_series(gdf, enacted_col).fillna("").astype(str).str.strip()
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
    has_bylaw = bylaw_name.ne("")
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
    gdf["__ENACTED__"] = enacted_raw
    gdf["__SIGNAL__"] = signal
    gdf["__BYLAW_NAME__"] = bylaw_name
    gdf["__BYLAW_LINK__"] = bylaw_link
    gdf["__LINE_COLOR__"] = line_color

    return gdf


@st.cache_data(ttl=300)
def load_data(path: str):
    """Load, reproject and lightly simplify the lower-tier map data.

    Returns:
        gdf: GeoDataFrame with the needed columns (status + metadata + geometry)
        status_cols: list of "... Status" columns
        name_field: chosen municipality name column
    """
    gdf = gpd.read_parquet(path)
    try:
        from build_maps_v2_rollup_metadata import overlay_live_lower
        gdf = overlay_live_lower(gdf)
    except Exception:
        pass

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
        r"^BF ",
    ]
    for c in gdf.columns:
        if c == geom_col or c == name_field or c in status_cols:
            continue
        if any(re.search(p, c) for p in patterns):
            meta_cols.append(c)

    keep_cols = set(status_cols + [name_field, geom_col] + meta_cols)
    gdf = gdf[list(keep_cols)].copy()

    # Light geometry simplification to cut JSON size and drawing time.
    gdf[geom_col] = gdf[geom_col].simplify(tolerance=0.00025, preserve_topology=True)

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
is_bldg_fees = (selected_label == "Farm Building Permit Fees")
is_site_alt = (selected_label == "Farm Exemption for SA")

# Site Alteration & Excess Soil: Interactive Topsoil Import Estimator controls
sa_volume_m3 = 15000
if is_site_alt:
    st.sidebar.markdown("---")
    st.sidebar.subheader("🧮 Topsoil Import Fee Estimator")
    sa_volume_m3 = st.sidebar.slider(
        "Imported Clean Topsoil Volume (m³)",
        min_value=500,
        max_value=25000,
        value=15000,
        step=500,
        help="Estimates municipal Site Alteration permit fees live for verified fee schedules (e.g., 14,000–15,000 m³ large farm topsoil import).",
    )

# Farm Building Permit Fees: Interactive Estimator & Cost-Tier controls
bf_bldg_type = "🐄 Livestock Barn"
bf_sqft = 10000
bf_tier_filter = "All"
bf_audited_only = False
if is_bldg_fees:
    st.sidebar.markdown("---")
    st.sidebar.subheader("🧮 Permit Cost Estimator")
    bf_bldg_type = st.sidebar.radio(
        "Structure Type",
        ["🐄 Livestock Barn", "🚜 Equipment / Drive Shed"],
        index=0,
        help="Switch between Livestock Barn and Non-Livestock Equipment / Drive Shed rates where municipalities charge separate tiers.",
    )
    bf_sqft = st.sidebar.slider(
        "Building Footprint (sq. ft.)",
        min_value=1500,
        max_value=30000,
        value=10000,
        step=500,
        help="Recomputes exact municipal fees live (including base fees, high minimum floors, and 2024 OBC Group G / stepped brackets).",
    )
    bf_tier_filter = st.sidebar.selectbox(
        "Cost Tier Filter",
        [
            "All",
            "Low (< $0.28/ft²)",
            "Moderate ($0.28–$0.37/ft²)",
            "High ($0.37–$0.48/ft²)",
            "Very High (≥ $0.48/ft²)",
            "Valuation-Based ($/$1k)",
            "Urban / No Farm Tier (ICI)",
            "Not Published Online",
            "Pending Audit",
        ],
        index=0,
    )
    bf_audited_only = st.sidebar.checkbox("Show audited municipalities only", value=False)
    status_filter = "All"
    signal_filter = "All"
else:
    # Split filters: Status vs Expiry alerts (signals)
    status_filter = st.sidebar.selectbox("Status", ["All", "YES", "PARTIAL", "NO", "N/A"], index=0)
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

# Compute fill colours (fill is driven by Status, or live Cost Tier for BLDG_FEES)
if is_bldg_fees:
    _is_live = (bf_bldg_type == "🐄 Livestock Barn")
    _bf_nums, _bf_disp, _bf_eff, _bf_tiers, _bf_colors = [], [], [], [], []
    _bf_years, _bf_models, _bf_auths = [], [], []
    for _, _row in gdf_all.iterrows():
        _payload = {
            "has_farm_tier": _row.get("BF Has Farm Tier", ""),
            "base_fee": _row.get("BF Base Fee", ""),
            "min_fee": _row.get("BF Min Fee", ""),
            "rate_per_sqft_livestock": _row.get("BF Rate Livestock", ""),
            "rate_per_sqft_other_farm": _row.get("BF Rate Other Farm", ""),
            "flat_fee": _row.get("BF Flat Fee", ""),
            "value_rate_per_1000": _row.get("BF Value Rate Per 1000", ""),
            "calc_spec_json": _row.get("BF Calc Spec JSON", ""),
        }
        _est = evaluate_bldg_fee(_payload, bf_sqft, is_livestock=_is_live)
        _vs = str(_row.get("BF Verification Status", "") or "")
        _hft = str(_row.get("BF Has Farm Tier", "") or "")
        _pm = str(_row.get("BF Pricing Model", "") or "")
        _rgba, _tier = fee_cost_tier_rgba(_est, bf_sqft, _vs, _hft, _pm)
        _bf_nums.append(_est)
        _bf_disp.append(f"${_est:,.0f}" if _est is not None else _tier)
        _bf_eff.append(f"${_est / bf_sqft:.3f}/ft²" if _est is not None else "—")
        _bf_tiers.append(_tier)
        _bf_colors.append(_rgba)
        _fy_raw = str(_row.get("BF Fee Year", "") or "").strip()
        _bf_years.append(_fy_raw.split(".")[0] if _fy_raw and _fy_raw.lower() != "nan" else "—")
        _bf_models.append(_pm or "—")
        _bf_auths.append(str(_row.get("BF Shared Authority", "") or "").strip() or "Municipal")
    gdf_all["__BF_EST_NUM__"] = _bf_nums
    gdf_all["__BF_EST_DISPLAY__"] = _bf_disp
    gdf_all["__BF_EFF_RATE__"] = _bf_eff
    gdf_all["__BF_TIER__"] = _bf_tiers
    gdf_all["__BF_YEAR__"] = _bf_years
    gdf_all["__BF_MODEL__"] = _bf_models
    gdf_all["__BF_AUTH__"] = _bf_auths
    gdf_all["__COLOR__"] = _bf_colors
else:
    gdf_all["__COLOR__"] = gdf_all["__STATUS__"].apply(status_color)

if is_site_alt:
    _sa_est_disp, _sa_ag_status_disp = [], []
    for _, _row in gdf_all.iterrows():
        _sa_pay = {
            "fee_verification_status": _row.get("SA Fee Verification Status", ""),
            "ag_import_fee_status": _row.get("SA Ag Import Fee Status", ""),
            "ag_exempt_volume_cap_m3": _row.get("SA Ag Exempt Volume Cap m3", ""),
            "fee_pricing_model": _row.get("SA Fee Pricing Model", ""),
            "base_fee_small": _row.get("SA Base Fee Small", ""),
            "base_fee_large": _row.get("SA Base Fee Large", ""),
            "per_m3_rate": _row.get("SA Per m3 Rate", ""),
            "fee_calc_spec_json": _row.get("SA Fee Calc Spec JSON", ""),
        }
        _sa_val = evaluate_site_alt_fee(_sa_pay, sa_volume_m3)
        _sa_fvs = str(_row.get("SA Fee Verification Status", "") or "").strip()
        _sa_ags = str(_row.get("SA Ag Import Fee Status", "") or "").strip()
        _sa_pm = str(_row.get("SA Fee Pricing Model", "") or "").strip()
        if _sa_val is not None:
            _sa_est_disp.append(f"${_sa_val:,.0f}")
        elif "hectare" in _sa_pm.lower():
            _sa_est_disp.append("Area-Based ($/ha)")
        elif "no bylaw" in _sa_fvs.lower() or "no bylaw" in _sa_ags.lower():
            _sa_est_disp.append("No Bylaw ($0)")
        elif _sa_fvs.lower().startswith("verified"):
            _sa_est_disp.append("Capped / Non-Volumetric")
        elif _sa_fvs:
            _sa_est_disp.append(_sa_fvs)
        else:
            _sa_est_disp.append("Pending Fee Audit")
        _sa_ag_status_disp.append(_sa_ags or "—")
    gdf_all["__SA_FEE_DISPLAY__"] = _sa_est_disp
    gdf_all["__SA_AG_FEE_STATUS__"] = _sa_ag_status_disp

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

if is_bldg_fees:
    if bf_tier_filter != "All":
        match_mask &= gdf_all["__BF_TIER__"].eq(bf_tier_filter)
    if bf_audited_only:
        match_mask &= gdf_all["__BF_TIER__"].ne("Pending Audit")
else:
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
if is_bldg_fees:
    _valid_bf = gdf_match[gdf_match["__BF_EST_NUM__"].notna()].copy()
    _n_farm = len(_valid_bf)
    _n_urban = int(gdf_match["__BF_TIER__"].eq("Urban / No Farm Tier (ICI)").sum())
    _n_pending = int(gdf_match["__BF_TIER__"].eq("Pending Audit").sum())
    _type_short = "Livestock Barn" if bf_bldg_type == "🐄 Livestock Barn" else "Drive Shed"
    if _n_farm > 0:
        _min_val = float(_valid_bf["__BF_EST_NUM__"].min())
        _med_val = float(_valid_bf["__BF_EST_NUM__"].median())
        _max_val = float(_valid_bf["__BF_EST_NUM__"].max())
        _spread = f"{(_max_val / _min_val):.1f}×" if _min_val > 0 else "—"
        _min_names = sorted(_valid_bf.loc[_valid_bf["__BF_EST_NUM__"] == _min_val, name_field].astype(str).tolist())
        _max_names = sorted(_valid_bf.loc[_valid_bf["__BF_EST_NUM__"] == _max_val, name_field].astype(str).tolist())
        c1, c2, c3, c4, c5, c6 = st.columns(6)
        c1.metric("Audited Farm Tiers", f"{_n_farm}")
        c2.metric(f"Lowest ({bf_sqft:,} ft²)", f"${_min_val:,.0f}", ", ".join(_min_names[:2]), delta_color="off")
        c3.metric(f"Median {_type_short}", f"${_med_val:,.0f}", f"${_med_val/bf_sqft:.2f}/ft²", delta_color="off")
        c4.metric(f"Highest ({bf_sqft:,} ft²)", f"${_max_val:,.0f}", ", ".join(_max_names[:2]), delta_color="off")
        c5.metric("Cost Spread", _spread)
        c6.metric("Urban / Pending", f"{_n_urban} / {_n_pending}")
    else:
        st.info("No audited area-based farm schedules match the current filter.")
    st.caption(
        f"Showing **{bf_sqft:,} sq. ft. {_type_short}** estimates ({len(gdf_match)} of {len(gdf_all)} municipalities).  "
        "Cost tier legend: 🟩 Low (< $0.28/ft²) • 🟦 Moderate ($0.28–$0.37/ft²) • 🟨 High ($0.37–$0.48/ft²) • "
        "🟥 Very High (≥ $0.48/ft²) • ⬛ Valuation ($/$1k) • ⬜ Urban / ICI • 🟫 Pending / Offline"
    )
else:
    counts = gdf_match["__STATUS__"].value_counts()
    yes = int(counts.get("YES", 0))
    partial = int(counts.get("PARTIAL", 0))
    no = int(counts.get("NO", 0))
    na = int(counts.get("N/A", 0))

    sig_counts = gdf_match["__SIGNAL__"].value_counts()
    expiring = int(sig_counts.get("Expiring soon", 0))
    expired = int(sig_counts.get("Expired", 0))
    unknown = int(sig_counts.get("Expiry unknown", 0))

    if partial > 0 or selected_label == "Farm Exemption for SA":
        c1, cp, c2, c3, c4, c5, c6 = st.columns(7)
        c1.metric("YES (Full)", f"{yes}")
        cp.metric("PARTIAL", f"{partial}")
        c2.metric("NO", f"{no}")
        c3.metric("N/A", f"{na}")
        c4.metric("Expiring soon", f"{expiring}")
        c5.metric("Expired", f"{expired}")
        c6.metric("Expiry unknown", f"{unknown}")
    else:
        c1, c2, c3, c4, c5, c6 = st.columns(6)
        c1.metric("YES", f"{yes}")
        c2.metric("NO", f"{no}")
        c3.metric("N/A", f"{na}")
        c4.metric("Expiring soon", f"{expiring}")
        c5.metric("Expired", f"{expired}")
        c6.metric("Expiry unknown", f"{unknown}")

    fill_legend = (
        "Fill legend: 🟩 YES (Full NFP) • 🟨 PARTIAL (Statutory Topsoil/Drainage Only) • 🟥 NO • ⬜ N/A  •  "
        if (partial > 0 or selected_label == "Farm Exemption for SA")
        else ""
    )
    st.caption(
        f"Matches: {len(gdf_match)} of {len(gdf_all)} municipalities.  {fill_legend}"
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
prop_cols = [
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
if is_bldg_fees:
    prop_cols = [
        name_field,
        "__BF_EST_DISPLAY__",
        "__BF_EFF_RATE__",
        "__BF_TIER__",
        "__BF_MODEL__",
        "__BF_YEAR__",
        "__BF_AUTH__",
        "__COLOR__",
        "__BYLAW_NAME__",
        "__BYLAW_LINK__",
        "__BORDER_COLOR__",
        "__LINE_WIDTH__",
        geom_col,
    ]
elif is_site_alt:
    prop_cols = [
        name_field,
        "__STATUS__",
        "__SA_AG_FEE_STATUS__",
        "__SA_FEE_DISPLAY__",
        "__COLOR__",
        "__EXPIRY__",
        "__SIGNAL__",
        "__BYLAW_NAME__",
        "__BYLAW_LINK__",
        "__BORDER_COLOR__",
        "__LINE_WIDTH__",
        geom_col,
    ]
props_df = gdf_view[prop_cols].copy()

# Create GeoJSON from the VIEW
geojson = json.loads(props_df.to_json())

# ---------- Map ----------
layer = pdk.Layer(
    "GeoJsonLayer",
    geojson,
    pickable=True,
    opacity=0.65 if is_bldg_fees else 0.5,
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

_tooltip_text = (
    (
        f"{{{name_field}}}\n"
        f"{bf_sqft:,} ft² {'Livestock Barn' if bf_bldg_type == '🐄 Livestock Barn' else 'Drive Shed'}: {{__BF_EST_DISPLAY__}} ({{__BF_EFF_RATE__}})\n"
        "Cost Tier: {__BF_TIER__}\n"
        "Model: {__BF_MODEL__} | Year: {__BF_YEAR__}\n"
        "Authority: {__BF_AUTH__}\n"
        "By-law: {__BYLAW_NAME__}"
    )
    if is_bldg_fees
    else (
        f"{{{name_field}}}\n"
        "Status: {__STATUS__}\n"
        "Ag Import Fee Status: {__SA_AG_FEE_STATUS__}\n"
        f"Est. Permit Fee ({sa_volume_m3:,} m³): {{__SA_FEE_DISPLAY__}}\n"
        "Expiry: {__EXPIRY__}\n"
        "Bylaw: {__BYLAW_NAME__}"
    )
    if is_site_alt
    else (
        f"{{{name_field}}}\n"
        "Status: {__STATUS__}\n"
        "Expiry: {__EXPIRY__}\n"
        "Signal: {__SIGNAL__}\n"
        "Bylaw: {__BYLAW_NAME__}\n"
        "Link: {__BYLAW_LINK__}"
    )
)

# ---------- Map with Selection (DIAGNOSTIC MODE) ----------
# We enable selection on the map to update the sidebar
event = st.pydeck_chart(
    pdk.Deck(
        layers=[layer],
        initial_view_state=view_state,
        map_style="light",
        tooltip={"text": _tooltip_text},
    ),
    on_select="rerun",  # Forces the app to reload immediately on click
    selection_mode="single-object",
    height=720,
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
    if is_bldg_fees:
        _r_pay = {
            "has_farm_tier": r.get("BF Has Farm Tier", ""),
            "base_fee": r.get("BF Base Fee", ""),
            "min_fee": r.get("BF Min Fee", ""),
            "rate_per_sqft_livestock": r.get("BF Rate Livestock", ""),
            "rate_per_sqft_other_farm": r.get("BF Rate Other Farm", ""),
            "flat_fee": r.get("BF Flat Fee", ""),
            "value_rate_per_1000": r.get("BF Value Rate Per 1000", ""),
            "calc_spec_json": r.get("BF Calc Spec JSON", ""),
        }
        _est_live = evaluate_bldg_fee(_r_pay, bf_sqft, is_livestock=True)
        _est_shed = evaluate_bldg_fee(_r_pay, bf_sqft, is_livestock=False)
        st.sidebar.markdown(f"**Audit Status:** {str(r.get('BF Verification Status', '') or 'Pending')} ({r.get('__BF_YEAR__', '—')})")
        st.sidebar.markdown(f"**Cost Tier:** {r.get('__BF_TIER__', '—')}")
        if _est_live is not None or _est_shed is not None:
            _sc1, _sc2 = st.sidebar.columns(2)
            _sc1.metric(f"🐄 {bf_sqft:,} ft² Barn", f"${_est_live:,.0f}" if _est_live is not None else "—")
            _sc2.metric(f"🚜 {bf_sqft:,} ft² Shed", f"${_est_shed:,.0f}" if _est_shed is not None else "—")
        st.sidebar.markdown(f"**Pricing Model:** {r.get('__BF_MODEL__', '—')}")
        st.sidebar.markdown(f"**Authority:** {r.get('__BF_AUTH__', 'Municipal')}")
        if str(r.get("BF Silo Grain Bin Fee", "") or "").strip():
            st.sidebar.markdown(f"**Silo / Grain Bin:** {r.get('BF Silo Grain Bin Fee')}")
        if str(r.get("BF Manure Storage Fee", "") or "").strip():
            st.sidebar.markdown(f"**Manure Storage:** {r.get('BF Manure Storage Fee')}")
        if str(r.get("BF Greenhouse Tarp Fee", "") or "").strip():
            st.sidebar.markdown(f"**Greenhouse / Tarp:** {r.get('BF Greenhouse Tarp Fee')}")
        if str(r.get("BF Refundable Deposit", "") or "").strip():
            st.sidebar.markdown(f"**Deposit / Surcharges:** {r.get('BF Refundable Deposit')}")
        if str(r.get("BF Formula Notes", "") or "").strip():
            st.sidebar.info(str(r.get("BF Formula Notes")))
    else:
        st.sidebar.markdown(f"**Status:** {str(r.get('__STATUS__', 'N/A') or 'N/A')}")
        st.sidebar.markdown(f"**Expiry signal:** {str(r.get('__SIGNAL__', '') or '').strip() or '—'}")
        if is_site_alt:
            _sa_fvs = str(r.get("SA Fee Verification Status", "") or "").strip()
            _sa_fy = str(r.get("SA Fee Year", "") or "").strip().split(".")[0]
            _sa_ags = str(r.get("SA Ag Import Fee Status", "") or "").strip()
            _sa_pm = str(r.get("SA Fee Pricing Model", "") or "").strip()
            _sa_rate = str(r.get("SA Per m3 Rate", "") or "").strip()
            _sa_cap = str(r.get("SA Ag Exempt Volume Cap m3", "") or "").strip()
            _sa_ban = str(r.get("SA Out-of-Muni Fill Ban", "") or "").strip()
            _sa_fbn = str(r.get("SA Fees Bylaw Name", "") or "").strip()
            _sa_fbl = str(r.get("SA Fees Bylaw Link", "") or "").strip()
            _sa_sec = str(r.get("SA Security Deposit Terms", "") or "").strip()
            _sa_peer = str(r.get("SA Peer Review Recovery", "") or "").strip()
            _sa_fn = str(r.get("SA Fee Formula Notes", "") or "").strip()
            if _sa_fvs and _sa_fvs != "N/A (No Bylaw)":
                st.sidebar.markdown("---")
                st.sidebar.markdown(f"**💰 Excess Soil / Fill Fees** ({_sa_fvs}{f' · {_sa_fy}' if _sa_fy and _sa_fy.lower() != 'nan' else ''})")
                if _sa_ags:
                    st.sidebar.markdown(f"**Ag Import Fee Status:** {_sa_ags}")
                st.sidebar.metric(f"Est. Permit Fee ({sa_volume_m3:,} m³)", str(r.get("__SA_FEE_DISPLAY__", "—")))
                if _sa_pm:
                    st.sidebar.markdown(f"**Fee Pricing Model:** {_sa_pm}")
                if _sa_rate and _sa_rate.lower() != "nan":
                    try:
                        st.sidebar.markdown(f"**Volumetric Rate:** ${float(_sa_rate):,.2f}/m³")
                    except Exception:
                        pass
                if _sa_cap and _sa_cap.lower() != "nan":
                    try:
                        st.sidebar.markdown(f"**Ag Exempt Cap:** {float(_sa_cap):,.0f} m³")
                    except Exception:
                        pass
                if _sa_ban and _sa_ban.lower() not in ("", "unknown"):
                    st.sidebar.markdown(f"**Out-of-Muni Fill Ban:** {_sa_ban}")
                if _sa_fbn:
                    st.sidebar.markdown(f"**Fees By-law:** [{_sa_fbn}]({_sa_fbl})" if _sa_fbl else f"**Fees By-law:** {_sa_fbn}")
                if _sa_sec:
                    st.sidebar.markdown(f"**Security / Deposit:** {_sa_sec}")
                if _sa_peer:
                    st.sidebar.markdown(f"**Peer Review / Testing:** {_sa_peer}")
                if _sa_fn:
                    st.sidebar.info(_sa_fn)

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

# ---------- OFA position + template letter + advocacy panel ----------
content = get_content_for_label(selected_label)

if content is not None:
    st.subheader(content.title)
    st.markdown(content.body_md)

    if content.letter_path:
        template_path = os.path.join(HERE, content.letter_path)
        if os.path.exists(template_path):
            with open(template_path, "rb") as f:
                st.download_button(
                    label="📄 Download blank template letter (.docx)",
                    data=f,
                    file_name=os.path.basename(template_path),
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )

            # ── Advocacy Letter Panel (only for municipalities WITHOUT an exemption) ──
            muni_status = ""
            if len(detail_row) == 1:
                muni_status = str(detail_row.iloc[0].get("__STATUS__", "") or "").strip().upper()

            if muni_status == "YES":
                st.success(
                    f"✅ **{selected_muni}** already has a farm exemption for this bylaw. "
                    "No advocacy letter needed!"
                )
            elif muni_status in ("NO", "PARTIAL", "NOT KNOWN", ""):
                if muni_status == "PARTIAL":
                    st.warning(
                        f"⚠️ **{selected_muni}** currently provides only a **Partial** exemption "
                        "(e.g. mandatory *Municipal Act* topsoil removal / Drainage Act carve-outs only — "
                        "farm fill placement and grade alterations may still require a permit). "
                        "You can send an advocacy letter below requesting a full Normal Farm Practice exemption."
                    )
                with st.expander("✉️ Send Personalized Advocacy Letter", expanded=False):
                    st.markdown(
                        "Fill in your details below to generate a **personalized advocacy letter** "
                        "addressed to this municipality's clerk office. You can preview, download the "
                        "editable Word document, and open it directly in your email client."
                    )

                    # Persist user details in session state across municipality changes
                    if "advocacy_name" not in st.session_state:
                        st.session_state["advocacy_name"] = ""
                    if "advocacy_title" not in st.session_state:
                        st.session_state["advocacy_title"] = ""
                    if "advocacy_federation" not in st.session_state:
                        st.session_state["advocacy_federation"] = ""
                    if "advocacy_email" not in st.session_state:
                        st.session_state["advocacy_email"] = ""
                    if "advocacy_phone" not in st.session_state:
                        st.session_state["advocacy_phone"] = ""

                    col_a, col_b = st.columns(2)
                    with col_a:
                        adv_name = st.text_input("Your Name *", value=st.session_state["advocacy_name"],
                                                 key="adv_name_input", placeholder="e.g., John Smith")
                        adv_title = st.text_input("Your Title / Position *", value=st.session_state["advocacy_title"],
                                                  key="adv_title_input", placeholder="e.g., President")
                        adv_federation = st.text_input("Organization / Affiliation (e.g., County Federation, Commodity Group, OFA Member) *",
                                                       value=st.session_state["advocacy_federation"],
                                                       key="adv_fed_input", placeholder="e.g., Huron County Federation of Agriculture")
                    with col_b:
                        adv_email = st.text_input("Your Contact Email (optional)",
                                                  value=st.session_state["advocacy_email"],
                                                  key="adv_email_input", placeholder="e.g., john@example.com")
                        adv_phone = st.text_input("Your Contact Phone (optional)",
                                                  value=st.session_state["advocacy_phone"],
                                                  key="adv_phone_input", placeholder="e.g., (519) 555-1234")

                    # Save to session state
                    st.session_state["advocacy_name"] = adv_name
                    st.session_state["advocacy_title"] = adv_title
                    st.session_state["advocacy_federation"] = adv_federation
                    st.session_state["advocacy_email"] = adv_email
                    st.session_state["advocacy_phone"] = adv_phone

                    # Build contact info string
                    contact_parts = []
                    if adv_email:
                        contact_parts.append(adv_email)
                    if adv_phone:
                        contact_parts.append(adv_phone)
                    contact_info = " | ".join(contact_parts) if contact_parts else ""

                    # Auto-populated municipality info
                    st.markdown("---")
                    muni_display = str(selected_muni)
                    bylaw_group = BYLAW_GROUP_FOR_LABEL.get(selected_label, selected_label)

                    # Resolve recipient from database
                    recipient_info = {"email": None, "contact_name": None}
                    muni_id = None
                    try:
                        db_conn = get_connection()
                        muni_id = resolve_municipality_id(db_conn, muni_display)
                        if muni_id:
                            recipient_info = get_recipient_email(db_conn, muni_id, muni_display)
                        db_conn.close()
                    except Exception:
                        pass

                    # Show auto-populated info
                    info_col1, info_col2 = st.columns(2)
                    with info_col1:
                        st.markdown(f"**Municipality:** {muni_display}")
                        st.markdown(f"**Bylaw Topic:** {bylaw_group}")
                    with info_col2:
                        if recipient_info["email"]:
                            st.markdown(f"**Recipient:** {recipient_info['email']}")
                        else:
                            st.warning("⚠️ No clerk email found in database for this municipality.")
                            manual_email = st.text_input("Enter recipient email manually:",
                                                         key="manual_recipient_email",
                                                         placeholder="e.g., clerk@municipality.ca")
                            if manual_email:
                                recipient_info["email"] = manual_email

                    # Get the bylaw name from the current detail row
                    detail_bylaw_name = ""
                    if len(detail_row) == 1:
                        raw_bylaw = str(detail_row.iloc[0].get("__BYLAW_NAME__", "") or "").strip()
                        # Remove any parenthetical notes e.g. "(amended by...)" to sound more natural in letters
                        detail_bylaw_name = re.sub(r'\s*\(.*?\)', '', raw_bylaw).strip()

                    # Validation
                    required_filled = all([adv_name.strip(), adv_title.strip(), adv_federation.strip()])

                    if not required_filled:
                        st.info("Please fill in all required fields (*) above to generate your letter.")
                    else:
                        # Build the template fields
                        fields = build_fields(
                            sender_name=adv_name,
                            sender_title=adv_title,
                            county_federation=adv_federation,
                            contact_info=contact_info,
                            municipality_name=muni_display,
                            bylaw_name=detail_bylaw_name,
                            address=recipient_info.get("address", ""),
                        )

                        # ── Preview ──
                        if st.button("👁️ Preview Letter", key="preview_letter_btn"):
                            preview_text = letter_to_plain_text(template_path, fields)
                            st.session_state["letter_preview"] = preview_text

                        if st.session_state.get("letter_preview"):
                            st.markdown("---")
                            st.markdown("**Letter Preview:**")
                            st.text_area("Letter preview", value=st.session_state["letter_preview"],
                                         height=400, disabled=True, key="preview_area",
                                         label_visibility="collapsed")

                        # ── Download personalized .docx ──
                        st.markdown("---")
                        personalized_doc = fill_letter_template(template_path, fields)
                        safe_muni = re.sub(r'[^\w\s-]', '', muni_display).strip().replace(' ', '_')
                        doc_filename = f"Advocacy_Letter_{safe_muni}_{bylaw_group.replace(' ', '_')}.docx"

                        if st.download_button(
                            label="📥 Download Personalized Letter (.docx)",
                            data=personalized_doc,
                            file_name=doc_filename,
                            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                            key="download_personalized_letter",
                        ):
                            try:
                                log_conn = get_connection()
                                log_advocacy_action(
                                    log_conn, muni_id, muni_display, bylaw_group,
                                    recipient_info.get("email"), adv_name, adv_federation,
                                    "letter_downloaded"
                                )
                                log_conn.close()
                            except Exception:
                                pass
                        st.caption("This Word document is fully editable — make any customizations before sending.")

                        # ── Open in Email Client (mailto:) ──
                        if recipient_info["email"]:
                            st.markdown("---")
                            st.warning(
                                "⚠️ **IMPORTANT:** Browser security prevents automatically attaching files to emails. "
                                "When the email draft opens, you **MUST manually attach the downloaded `.docx` file** before sending.",
                                icon="⚠️"
                            )
                            
                            subject = build_email_subject(muni_display, bylaw_group)
                            cover_body_text = build_cover_email_body(
                                adv_name, adv_title, adv_federation, muni_display, bylaw_group
                            )
                            mailto_url = generate_mailto_link(recipient_info["email"], subject, cover_body_text)

                            if st.download_button(
                                label="📧 Generate Letter & Open Email Draft",
                                data=personalized_doc,
                                file_name=doc_filename,
                                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                key="mailto_btn"
                            ):
                                try:
                                    log_conn = get_connection()
                                    log_advocacy_action(
                                        log_conn, muni_id, muni_display, bylaw_group,
                                        recipient_info["email"], adv_name, adv_federation,
                                        "mailto_opened"
                                    )
                                    log_conn.close()
                                except Exception:
                                    pass
                                st.markdown(
                                    f'<meta http-equiv="refresh" content="0;url={mailto_url}">',
                                    unsafe_allow_html=True,
                                )
                                st.success(f"Opening email to {recipient_info['email']}... Don't forget to attach the document!")
                            
                            st.caption(
                                f"**Recipient:** {recipient_info['email']}  \n"
                                "This will open your default email client (Outlook, Gmail, etc.) with the "
                                "letter pre-filled. **Remember to attach the downloaded .docx file** for "
                                "the clerk's records."
                            )
                        else:
                            st.warning(
                                "No recipient email available. Please download the letter and send it manually."
                            )

                    # ── Usage Stats ──
                    st.markdown("---")
                    st.markdown("#### 📊 Advocacy Tool Usage")
                    try:
                        stats_conn = get_connection()
                        stats = get_advocacy_stats(stats_conn)
                        stats_conn.close()

                        if stats["total_actions"] == 0:
                            st.caption("No advocacy letters have been generated yet. Be the first!")
                        else:
                            sc1, sc2, sc3 = st.columns(3)
                            sc1.metric("Letters Generated", stats["total_downloads"])
                            sc2.metric("Emails Opened", stats["total_emails"])
                            sc3.metric("Municipalities Contacted", stats["municipalities_contacted"])

                            if stats["by_municipality"]:
                                import pandas as _pd
                                muni_df = _pd.DataFrame(stats["by_municipality"])
                                muni_df.columns = ["Municipality", "Letters"]
                                st.dataframe(muni_df, use_container_width=True, hide_index=True)

                            if stats["recent"]:
                                with st.expander("Recent activity", expanded=False):
                                    recent_df = _pd.DataFrame(stats["recent"])
                                    st.dataframe(recent_df, use_container_width=True, hide_index=True)
                    except Exception:
                        st.caption("Usage tracking will appear here after your first letter.")

            else:
                st.info(
                    f"ℹ️ **{selected_muni}** has a status of **N/A** for this bylaw category. "
                    "This means the bylaw is not applicable to this municipality, so no advocacy letter is needed."
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
    if is_bldg_fees:
        _tbl_cols = [
            name_field, "__BF_TIER__", "__BF_EST_DISPLAY__", "__BF_EFF_RATE__",
            "__BF_YEAR__", "__BF_MODEL__", "__BF_AUTH__",
            "BF Rate Livestock", "BF Rate Other Farm",
            "BF Est 2500 Shed", "BF Est 10000 Barn", "BF Est 10000 Shed", "BF Est 20000 Barn",
            "__BYLAW_NAME__", "__BYLAW_LINK__",
        ]
        _avail = [c for c in _tbl_cols if c in gdf_match.columns]
        table = gdf_match[_avail].copy()
        table = table.rename(
            columns={
                name_field: "Municipality",
                "__BF_TIER__": "Cost Tier",
                "__BF_EST_DISPLAY__": f"Est. ({bf_sqft:,} ft²)",
                "__BF_EFF_RATE__": "Eff. $/ft²",
                "__BF_YEAR__": "Year",
                "__BF_MODEL__": "Pricing Model",
                "__BF_AUTH__": "Authority",
                "BF Rate Livestock": "Barn $/ft²",
                "BF Rate Other Farm": "Shed $/ft²",
                "BF Est 2500 Shed": "2.5k Shed",
                "BF Est 10000 Barn": "10k Barn",
                "BF Est 10000 Shed": "10k Shed",
                "BF Est 20000 Barn": "20k Barn",
                "__BYLAW_NAME__": "Bylaw",
                "__BYLAW_LINK__": "Bylaw Link",
            }
        )
    elif is_site_alt:
        _sa_cols = [
            name_field, "__STATUS__", "SA Fee Verification Status", "SA Ag Import Fee Status",
            "__SA_FEE_DISPLAY__", "SA Per m3 Rate", "SA Ag Exempt Volume Cap m3",
            "SA Out-of-Muni Fill Ban", "SA Fee Pricing Model",
            "SA Est Fee 500 m3", "SA Est Fee 5000 m3", "SA Est Fee 15000 m3",
            "SA Fees Bylaw Name", "SA Fees Bylaw Link",
            "__BYLAW_NAME__", "__BYLAW_LINK__",
        ]
        _avail = [c for c in _sa_cols if c in gdf_match.columns]
        table = gdf_match[_avail].copy().rename(
            columns={
                name_field: "Municipality",
                "__STATUS__": "Farm Exemption",
                "SA Fee Verification Status": "Fee Audit Status",
                "SA Ag Import Fee Status": "Ag Import Fee Status",
                "__SA_FEE_DISPLAY__": f"Est. ({sa_volume_m3:,} m³)",
                "SA Per m3 Rate": "Rate ($/m³)",
                "SA Ag Exempt Volume Cap m3": "Ag Exempt Cap (m³)",
                "SA Out-of-Muni Fill Ban": "Out-of-Muni Ban",
                "SA Fee Pricing Model": "Pricing Model",
                "SA Est Fee 500 m3": "500 m³ Est.",
                "SA Est Fee 5000 m3": "5k m³ Est.",
                "SA Est Fee 15000 m3": "15k m³ Est.",
                "SA Fees Bylaw Name": "Fees Bylaw",
                "SA Fees Bylaw Link": "Fees Bylaw Link",
                "__BYLAW_NAME__": "Site Alt. Bylaw",
                "__BYLAW_LINK__": "Site Alt. Link",
            }
        )
    else:
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
        file_name=(
            "farm_building_fees_map_results.csv" if is_bldg_fees
            else "site_alteration_fees_map_results.csv" if is_site_alt
            else "bylaw_map_results.csv"
        ),
        mime="text/csv",
    )
