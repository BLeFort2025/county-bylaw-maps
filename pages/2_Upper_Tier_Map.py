import os
import sys
import json
import re
from datetime import date

# When running from pages/, resolve HERE to the project root (one level up)
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import streamlit as st
import geopandas as gpd
import pydeck as pdk
import pandas as pd

from ofa_content import get_content_for_label, BYLAW_GROUP_FOR_LABEL
from letter_engine import (
    resolve_municipality_id, get_recipient_email,
    fill_letter_template, letter_to_plain_text,
    generate_mailto_link, build_email_subject, build_fields,
    log_advocacy_action, get_advocacy_stats, build_cover_email_body
)
from db_utils import get_connection
from bldg_fees_calc import evaluate_bldg_fee, fee_cost_tier_rgba
from site_alt_fees_calc import site_alt_fee_tier_rgba

st.set_page_config(page_title="Upper Tier Bylaw Exemptions Map", layout="wide")

UPPER_PARQUET = os.path.join(HERE, "upper_single_map_beta.parquet")

# --- Expiry-based signal tuning ---
EXPIRY_SOON_DAYS = 540  # ~18 months

# Signal priority (used once multiple signal types exist)
SIGNAL_PRIORITY = [
    "Expired",
    "Expiring soon",
    "Mentioned in minutes/agendas",
    "Expiry unknown",
]


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
        # Filter to recent signals only (90 days)
        if "discovered_date" in df.columns:
            df["_dt"] = pd.to_datetime(df["discovered_date"], errors="coerce")
            cutoff = pd.Timestamp.now() - pd.Timedelta(days=90)
            df = df[df["_dt"].isna() | (df["_dt"] >= cutoff)].drop(columns=["_dt"])

        df["_canon"] = df["munid"].astype(str).apply(canon_name)
        dedup_cols = [c for c in ["_canon", "category", "trigger_keyword", "evidence_url"] if c in df.columns]
        if dedup_cols:
            df = df.drop_duplicates(subset=dedup_cols, keep="first")

        signals_map = {}
        for _, row in df.iterrows():
            cname = row["_canon"]
            if not cname:
                continue
            if cname not in signals_map:
                signals_map[cname] = []
            signals_map[cname].append(row.drop(labels=["_canon"], errors="ignore").to_dict())
        return signals_map
    except Exception:
        return {}

@st.cache_data(ttl=300)
def load_parquet(path):
    gdf = gpd.read_parquet(path)
    try:
        from build_maps_v2_rollup_metadata import overlay_live_upper
        gdf = overlay_live_upper(gdf)
    except Exception:
        pass
    try:
        gdf = gdf.to_crs(4326)
    except Exception:
        pass
    return gdf


NON_LAYER_STATUS_COLS = {
    "Municipal Status",
    "BF Verification Status",
    "SA Fee Verification Status",
    "SA Ag Import Fee Status",
}


def find_status_columns(df: pd.DataFrame) -> list[str]:
    return sorted([
        c for c in df.columns
        if c.strip().endswith(" Status") and c.strip() not in NON_LAYER_STATUS_COLS
    ])


def pick_name_field(df: pd.DataFrame) -> str:
    for c in ["MUNICIPALITY", "Municipality", "NAME", "OFFICIAL_M", "_UPPER_NAME"]:
        if c in df.columns:
            return c
    return df.columns[0]


def status_color(s: str) -> list[int]:
    s = (s or "").strip().upper()
    if s == "YES":
        return [0, 128, 0, 160]
    if s == "PARTIAL":
        return [236, 168, 66, 180]
    if s == "NO":
        return [200, 0, 0, 160]
    if s == "N/A":
        return [128, 128, 128, 160]
    return [0, 0, 160, 140]


# Same label->metadata mapping as lower map.
# IMPORTANT: Upper-tier parquet may not contain these fields unless build_maps.py is updated
# to aggregate them. The code below degrades gracefully (shows N/A).
META_BY_LABEL: dict[str, dict[str, str]] = {
    "Farm Exemption for Development Charges": {
        "bylaw_name": "Bylaw Name Development Charges",
        "bylaw_link": "Link to DC Bylaw",
        "enacted": "Date Bylaw Enacted (Regional)",
        "expiry": "Expiry Date",
    },
    "Farm Exemption for Stormwater Charges": {
        "bylaw_name": "Bylaw Name Stormwater",
        "bylaw_link": "Link to Storm Water bylaw",
        "enacted": "Date Bylaw Enacted2 (Regional)",
        "expiry": "Expiry date2",
    },
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
    "Farm Exemption - Tree Cutting Bylaw": {
        "bylaw_name": "Bylaw Name Forest Conservation",
        "bylaw_link": "Tree Cutting Bylaw Link",
        "enacted": "Date Bylaw Enacted 6 (Regional)",
        "expiry": "Expiry Date 6",
    },
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
    "Has Livestock Guardian dog Definition": "LGD",
    "LGD/HD Working Dog Definition": "LGD",
    "LGD and HD Exempt from License Fees": "LGD",
    "LGD and HD Collar and Tag Requirements": "LGD",
    "LGD and HD Exempt from Barking Restrictions": "LGD",
    "Farm Exemption for Security fencing prohibitions": "FENCES",
    "Farm Exemption for Electrified fencing prohibitions": "FENCES",
    "Farm Building Permit Fees": "BLDG_FEES",
}

def _safe_series(df: pd.DataFrame, col: str) -> pd.Series:
    if col and col in df.columns:
        return df[col]
    return pd.Series([""] * len(df), index=df.index)


def add_expiry_signal_columns(gdf: gpd.GeoDataFrame, selected_label: str, direct_only: bool = False) -> gpd.GeoDataFrame:
    meta = META_BY_LABEL.get(selected_label, {})
    suffix = "__DIRECT" if direct_only else ""
    expiry_base = meta.get("expiry", "")
    enacted_base = meta.get("enacted", "")
    bylaw_name_base = meta.get("bylaw_name", "")
    link_base = meta.get("bylaw_link", "")

    expiry_col = f"{expiry_base}{suffix}" if (expiry_base and f"{expiry_base}{suffix}" in gdf.columns) else expiry_base
    enacted_col = f"{enacted_base}{suffix}" if (enacted_base and f"{enacted_base}{suffix}" in gdf.columns) else enacted_base
    bylaw_name_col = f"{bylaw_name_base}{suffix}" if (bylaw_name_base and f"{bylaw_name_base}{suffix}" in gdf.columns) else bylaw_name_base
    link_col = f"{link_base}{suffix}" if (link_base and f"{link_base}{suffix}" in gdf.columns) else link_base

    expiry_raw = _safe_series(gdf, expiry_col).fillna("").astype(str).str.strip()
    enacted_raw = _safe_series(gdf, enacted_col).fillna("").astype(str).str.strip()
    bylaw_name = _safe_series(gdf, bylaw_name_col).fillna("").astype(str).str.strip()
    bylaw_link = _safe_series(gdf, link_col).fillna("").astype(str).str.strip()

    expiry_dt = pd.to_datetime(expiry_raw, errors="coerce")
    today = pd.Timestamp(date.today())
    days = (expiry_dt - today).dt.days

    expiry_display = expiry_raw.where(expiry_raw.ne(""), other="N/A")
    expiry_display = expiry_display.where(expiry_dt.isna(), other=expiry_dt.dt.date.astype(str))

    signal = pd.Series([""] * len(gdf), index=gdf.index)
    has_expiry = expiry_dt.notna()
    signal.loc[has_expiry & (days < 0)] = "Expired"
    signal.loc[has_expiry & (days >= 0) & (days <= EXPIRY_SOON_DAYS)] = "Expiring soon"

    expects_expiry = bool(expiry_base)
    has_bylaw = bylaw_name.ne("")
    signal.loc[expects_expiry & ~has_expiry & has_bylaw] = "Expiry unknown"

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


# ---------- Load data ----------
try:
    gdf = load_parquet(UPPER_PARQUET)

except FileNotFoundError:
    st.error(f"Parquet not found: {UPPER_PARQUET}. Commit the file to the repo.")
    st.stop()

status_cols = find_status_columns(gdf)
if not status_cols:
    st.error("No ‘… Status’ columns found. Rebuild with build_maps.py and push the new Parquet.")
    st.stop()

name_field = pick_name_field(gdf)

# --- SIGNALS INTEGRATION ---
signals_data = load_signals_data()
def check_signal(name_val):
    return canon_name(name_val) in signals_data

if name_field in gdf.columns:
    gdf["HAS_SIGNAL"] = gdf[name_field].apply(check_signal)
else:
    gdf["HAS_SIGNAL"] = False

# ---------- Sidebar ----------
st.sidebar.header("Filters")

display_labels = {col: col.replace(" Status", "") for col in status_cols}
label_to_col = {v: k for k, v in display_labels.items()}

selected_label = st.sidebar.selectbox("Bylaw", list(display_labels.values()), index=0)
selected_col = label_to_col[selected_label]
is_bldg_fees = (selected_label == "Farm Building Permit Fees")
is_site_alt = (selected_label == "Farm Exemption for SA")

view_mode = st.sidebar.radio(
    "Jurisdiction mode",
    ["Combined (County + Lower-Tier Rollup)", "Upper-Tier / Regional Bylaws Only"],
    index=0,
    help=(
        "Combined shows the county rollup across local municipalities (median 10,000 ft² benchmark for Farm Building Fees). "
        "Upper-Tier Only shows bylaws enacted directly by the County, Region, or Single-Tier municipality (e.g., Dufferin County Building Services)."
    ),
)
direct_only = view_mode == "Upper-Tier / Regional Bylaws Only"
active_status_col = f"{selected_col}__DIRECT" if (direct_only and f"{selected_col}__DIRECT" in gdf.columns) else selected_col

bf_bldg_type = "🐄 Livestock Barn"
bf_tier_filter = "All"
sa_fee_mode = False
sa_bench_vol = 15000
sa_fee_tier_filter = "All"
if is_site_alt:
    st.sidebar.markdown("---")
    st.sidebar.subheader("🧮 Excess Soil Fee View")
    _ut_sa_mode = st.sidebar.radio(
        "Map Colouring Mode",
        ["Policy Exemption (Default)", "Excess Soil Fee Tier ($)"],
        index=0,
        key="ut_sa_map_mode",
        help="Default keeps standard YES/PARTIAL/NO exemption colours. Switch to view county/single-tier fee tiers.",
    )
    sa_fee_mode = (_ut_sa_mode == "Excess Soil Fee Tier ($)")
    if sa_fee_mode:
        _ut_sa_vol = st.sidebar.radio(
            "Benchmark Volume",
            ["500 m³ (~50 loads)", "5,000 m³ (~500 loads)", "15,000 m³ (~1,500 loads)"],
            index=2,
            key="ut_sa_vol",
        )
        sa_bench_vol = {"500 m³ (~50 loads)": 500, "5,000 m³ (~500 loads)": 5000, "15,000 m³ (~1,500 loads)": 15000}[_ut_sa_vol]
        sa_fee_tier_filter = st.sidebar.selectbox(
            "Excess Soil Fee Tier Filter",
            [
                "All",
                "Farm Exempt ($0)",
                "Waiver ($0 App Fee)",
                "Low (< $1.00/m³)",
                "Moderate ($1.00–$1.99/m³)",
                "High (≥ $2.00/m³)",
                "Area-Based ($/ha)",
                "Capped / Non-Volumetric",
                "Cost Recovery Only",
                "Not Published Online",
                "No Site Alt. By-law",
            ],
            index=0,
        )

if is_bldg_fees:
    bf_bldg_type = st.sidebar.radio(
        "Structure Type (10,000 sq. ft. Benchmark)",
        ["🐄 Livestock Barn", "🚜 Equipment / Drive Shed"],
        index=0,
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
            "Local Jurisdiction (Lower Tier)",
            "Pending Audit",
        ],
        index=0,
    )
    status_filter = "All"
    signal_filter = "All"
elif sa_fee_mode:
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
filter_signals = st.sidebar.checkbox("🚨 Filter to Scanner Signals", value=False)
display_mode = st.sidebar.selectbox(
    "Display mode",
    ["Highlight matches", "Filter to matches"],
    index=0,
)

search_term = st.sidebar.text_input(f"Search {name_field}", value="", placeholder="Type part of a name…").strip()

# ---------- Dynamic title ----------
st.title(f"Upper Tier Bylaw Exemptions Map – {selected_label}")

# ---------- Prepare data ----------
gdf_all = gdf.copy()

gdf_all["__STATUS__"] = (
    gdf_all[active_status_col]
    .fillna("")
    .astype(str)
    .str.strip()
    .str.upper()
    .replace({"UNKNOWN": "NOT KNOWN", "NA": "N/A", "NOT KNOWN": "N/A"})
)

if is_bldg_fees:
    _sfx = "__DIRECT" if direct_only else ""
    _est_col = ("BF Est 10000 Barn" if bf_bldg_type == "🐄 Livestock Barn" else "BF Est 10000 Shed") + _sfx
    if _est_col not in gdf_all.columns:
        _est_col = "BF Est 10000 Barn" if bf_bldg_type == "🐄 Livestock Barn" else "BF Est 10000 Shed"
    _vs_col = f"BF Verification Status{_sfx}" if f"BF Verification Status{_sfx}" in gdf_all.columns else "BF Verification Status"
    _hft_col = f"BF Has Farm Tier{_sfx}" if f"BF Has Farm Tier{_sfx}" in gdf_all.columns else "BF Has Farm Tier"
    _pm_col = f"BF Pricing Model{_sfx}" if f"BF Pricing Model{_sfx}" in gdf_all.columns else "BF Pricing Model"
    _auth_col = f"BF Shared Authority{_sfx}" if f"BF Shared Authority{_sfx}" in gdf_all.columns else "BF Shared Authority"
    _yr_col = f"BF Fee Year{_sfx}" if f"BF Fee Year{_sfx}" in gdf_all.columns else "BF Fee Year"
    _fn_col = f"BF Formula Notes{_sfx}" if f"BF Formula Notes{_sfx}" in gdf_all.columns else "BF Formula Notes"

    _bf_nums, _bf_disp, _bf_tiers, _bf_colors, _bf_auths, _bf_yrs = [], [], [], [], [], []
    for _, _row in gdf_all.iterrows():
        _raw_est = _row.get(_est_col, "")
        try:
            _est = float(_raw_est) if str(_raw_est).strip() not in ("", "nan", "None") else None
        except Exception:
            _est = None
        _vs = str(_row.get(_vs_col, "") or "")
        _hft = str(_row.get(_hft_col, "") or "")
        _pm = str(_row.get(_pm_col, "") or "")
        _rgba, _tier = fee_cost_tier_rgba(_est, 10000.0, _vs, _hft, _pm)
        _bf_nums.append(_est)
        _bf_disp.append(f"${_est:,.0f}" if _est is not None else _tier)
        _bf_tiers.append(_tier)
        _bf_colors.append(_rgba)
        _bf_auths.append(str(_row.get(_auth_col, "") or "").strip() or "—")
        _yr_s = str(_row.get(_yr_col, "") or "").strip()
        _bf_yrs.append(_yr_s.split(".")[0] if _yr_s and _yr_s.lower() != "nan" else "—")
    gdf_all["__BF_EST_NUM__"] = _bf_nums
    gdf_all["__BF_EST_DISPLAY__"] = _bf_disp
    gdf_all["__BF_TIER__"] = _bf_tiers
    gdf_all["__BF_AUTH__"] = _bf_auths
    gdf_all["__BF_YEAR__"] = _bf_yrs
    gdf_all["__BF_NOTES__"] = gdf_all[_fn_col].fillna("").astype(str) if _fn_col in gdf_all.columns else ""
    gdf_all["__COLOR__"] = _bf_colors
elif sa_fee_mode:
    _sfx = "__DIRECT" if direct_only else ""
    _vol_col = f"SA Est Fee {sa_bench_vol} m3{_sfx}"
    if _vol_col not in gdf_all.columns:
        _vol_col = f"SA Est Fee {sa_bench_vol} m3"
    _sa_vs_col = f"SA Fee Verification Status{_sfx}" if f"SA Fee Verification Status{_sfx}" in gdf_all.columns else "SA Fee Verification Status"
    _sa_ag_col = f"SA Ag Import Fee Status{_sfx}" if f"SA Ag Import Fee Status{_sfx}" in gdf_all.columns else "SA Ag Import Fee Status"
    _sa_pm_col = f"SA Fee Pricing Model{_sfx}" if f"SA Fee Pricing Model{_sfx}" in gdf_all.columns else "SA Fee Pricing Model"
    _sa_nums, _sa_disp, _sa_tiers, _sa_colors = [], [], [], []
    for _, _row in gdf_all.iterrows():
        _raw_v = _row.get(_vol_col, "")
        try:
            _v = float(_raw_v) if str(_raw_v).strip() not in ("", "nan", "None") else None
        except Exception:
            _v = None
        _fvs = str(_row.get(_sa_vs_col, "") or "")
        _ags = str(_row.get(_sa_ag_col, "") or "")
        _pm = str(_row.get(_sa_pm_col, "") or "")
        _rgba, _tier = site_alt_fee_tier_rgba(_v, float(sa_bench_vol), _fvs, _ags, _pm)
        _sa_nums.append(_v)
        _sa_disp.append(f"${_v:,.0f}" if _v is not None else _tier)
        _sa_tiers.append(_tier)
        _sa_colors.append(_rgba)
    gdf_all["__SA_FEE_NUM__"] = _sa_nums
    gdf_all["__SA_FEE_DISPLAY__"] = _sa_disp
    gdf_all["__SA_FEE_TIER__"] = _sa_tiers
    gdf_all["__COLOR__"] = _sa_colors
else:
    gdf_all["__COLOR__"] = gdf_all["__STATUS__"].apply(status_color)
gdf_all = add_expiry_signal_columns(gdf_all, selected_label, direct_only=direct_only)

# ---------- Build match mask ----------
match_mask = pd.Series(True, index=gdf_all.index)

if is_bldg_fees:
    if bf_tier_filter != "All":
        match_mask &= gdf_all["__BF_TIER__"].eq(bf_tier_filter)
elif sa_fee_mode:
    if sa_fee_tier_filter != "All":
        match_mask &= gdf_all["__SA_FEE_TIER__"].eq(sa_fee_tier_filter)
else:
    if status_filter != "All":
        match_mask &= gdf_all["__STATUS__"].eq(status_filter)

    if signal_filter != "All":
        match_mask &= gdf_all["__SIGNAL__"].eq(signal_filter)

if search_term:
    match_mask &= gdf_all[name_field].astype(str).str.contains(search_term, case=False, na=False)

# --- Scanner Signal Filter ---
if filter_signals:
    signal_mask = gdf_all["HAS_SIGNAL"].eq(True)
    target_category = LAYER_TO_CATEGORY.get(selected_label, None)
    if target_category and signals_data:
        cat_mask = pd.Series(False, index=gdf_all.index)
        for i, row in gdf_all.iterrows():
            cname = canon_name(str(row[name_field]))
            if cname in signals_data:
                if any(h.get('category') == target_category for h in signals_data[cname]):
                    cat_mask.loc[i] = True
        match_mask &= cat_mask
    else:
        match_mask &= signal_mask

gdf_match = gdf_all[match_mask].copy()

# ---------- Sidebar: Municipality details ----------
st.sidebar.divider()
st.sidebar.subheader("Municipality details")

limit_muni_list = st.sidebar.checkbox("Limit list to current results", value=True)

muni_source = gdf_match if (limit_muni_list and not gdf_match.empty) else gdf_all
muni_options = sorted(muni_source[name_field].dropna().astype(str).unique().tolist())

if not muni_options:
    muni_options = sorted(gdf_all[name_field].dropna().astype(str).unique().tolist())

if "selected_upper_muni" not in st.session_state:
    st.session_state["selected_upper_muni"] = muni_options[0] if muni_options else ""
elif st.session_state["selected_upper_muni"] not in muni_options and muni_options:
    st.session_state["selected_upper_muni"] = muni_options[0]

selected_muni = st.sidebar.selectbox("Select a municipality", options=muni_options, key="selected_upper_muni")

# ---------- Display mode: filter vs highlight ----------
if display_mode == "Filter to matches":
    gdf_view = gdf_match.copy()
else:
    gdf_view = gdf_all.copy()

    dim_alpha = 40

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

if display_mode == "Highlight matches":
    gdf_view["__LINE_WIDTH__"] = [2 if m else 1 for m in match_mask.tolist()]
else:
    gdf_view["__LINE_WIDTH__"] = 2

# ---------- Summary cards (counts reflect the matching set) ----------
if is_bldg_fees:
    _valid_bf = gdf_match[gdf_match["__BF_EST_NUM__"].notna()]
    _n_farm = len(_valid_bf)
    _n_local = int(gdf_match["__BF_TIER__"].eq("Local Jurisdiction (Lower Tier)").sum())
    _n_urban = int(gdf_match["__BF_TIER__"].eq("Urban / No Farm Tier (ICI)").sum())
    _n_pend = int(gdf_match["__BF_TIER__"].eq("Pending Audit").sum())
    _mode_lbl = "Direct Upper/Single Tier" if direct_only else "County Median Rollup"
    _t_lbl = "10k Barn" if bf_bldg_type == "🐄 Livestock Barn" else "10k Shed"
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric(f"Audited ({_mode_lbl})", f"{_n_farm}")
    c2.metric(f"Lowest {_t_lbl}", f"${_valid_bf['__BF_EST_NUM__'].min():,.0f}" if _n_farm else "—")
    c3.metric(f"Median {_t_lbl}", f"${_valid_bf['__BF_EST_NUM__'].median():,.0f}" if _n_farm else "—")
    c4.metric(f"Highest {_t_lbl}", f"${_valid_bf['__BF_EST_NUM__'].max():,.0f}" if _n_farm else "—")
    c5.metric("Local / Urban / Pending", f"{_n_local} / {_n_urban} / {_n_pend}")
    st.caption(
        f"Showing **{bf_bldg_type.split(' ', 1)[1]} (10,000 ft²)** — {_mode_lbl}.  "
        r"Legend: 🟩 Low (< \$0.28/ft²) • 🟦 Moderate (\$0.28–\$0.37/ft²) • 🟨 High (\$0.37–\$0.48/ft²) • "
        r"🟥 Very High (≥ \$0.48/ft²) • ⬜ Local Jurisdiction / Urban ICI • 🟫 Pending"
    )
elif sa_fee_mode:
    _sa_active = gdf_match[gdf_match["__SA_FEE_TIER__"] != "No Site Alt. By-law"]
    _sa_paid = _sa_active[_sa_active["__SA_FEE_NUM__"].notna() & (_sa_active["__SA_FEE_NUM__"] > 0)]
    _sa_ex = int(_sa_active["__SA_FEE_TIER__"].isin(["Farm Exempt ($0)", "Waiver ($0 App Fee)"]).sum())
    _mode_lbl = "Direct Upper/Single Tier" if direct_only else "County Lower-Tier Median"
    c1, c2, c3, c4 = st.columns(4)
    c1.metric(f"Active ({_mode_lbl})", f"{len(_sa_active)}")
    c2.metric("Farm Exempt ($0)", f"{_sa_ex}")
    c3.metric(f"Paid ({sa_bench_vol:,} m³)", f"{len(_sa_paid)}")
    c4.metric("Median Paid Fee", f"${_sa_paid['__SA_FEE_NUM__'].median():,.0f}" if len(_sa_paid) else "—")
    st.caption(
        f"Showing **{sa_bench_vol:,} m³ (~{sa_bench_vol // 10:,} loads)** Excess Soil fee tiers — {_mode_lbl}.  "
        r"Legend: 🟩 Farm Exempt (\$0) • 🟦 Low (< \$1/m³) • 🟨 Moderate (\$1–\$1.99/m³) • 🟥 High (≥ \$2/m³) • ⬛ Area (\$/ha) • ⬜ No Bylaw"
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

# ---------- Map ----------
# COLOR LOGIC: Priority-based borders
def get_border_color(row):
    sig = row.get("__SIGNAL__")
    if sig == "Expired":
        return [0, 0, 0, 255]         # Black
    if sig == "Expiring soon":
        return [255, 165, 0, 255]     # Orange
    if sig == "Expiry unknown":
        return [255, 255, 0, 255]     # Yellow
    # Category-aware scanner signal border
    if row.get("HAS_SIGNAL") == True:
        cname = canon_name(str(row.get(name_field, "")))
        if cname in signals_data:
            current_map_category = LAYER_TO_CATEGORY.get(selected_label, None)
            if current_map_category:
                if any(h.get('category') == current_map_category for h in signals_data[cname]):
                    return [255, 69, 0, 255]   # Red-Orange (matches current layer)
            else:
                return [255, 69, 0, 255]       # Red-Orange (no category filter)
    return [100, 100, 100, 100]       # Grey

gdf_view["__BORDER_COLOR__"] = gdf_view.apply(get_border_color, axis=1)

geom_col = gdf_view.geometry.name
if is_bldg_fees:
    props_df = gdf_view[[name_field, "__BF_EST_DISPLAY__", "__BF_TIER__", "__BF_AUTH__", "__BF_YEAR__", "__COLOR__", "__BYLAW_NAME__", "__BYLAW_LINK__", "__BORDER_COLOR__", "__LINE_WIDTH__", geom_col]].copy()
elif sa_fee_mode:
    props_df = gdf_view[[name_field, "__STATUS__", "__SA_FEE_DISPLAY__", "__SA_FEE_TIER__", "__COLOR__", "__BYLAW_NAME__", "__BYLAW_LINK__", "__BORDER_COLOR__", "__LINE_WIDTH__", geom_col]].copy()
else:
    props_df = gdf_view[[name_field, "__STATUS__", "__COLOR__", "__EXPIRY__", "__SIGNAL__", "__BYLAW_NAME__", "__BYLAW_LINK__", "__BORDER_COLOR__", "__LINE_WIDTH__", geom_col]].copy()
geojson = json.loads(props_df.to_json())

layer = pdk.Layer(
    "GeoJsonLayer",
    geojson,
    pickable=True,
    opacity=0.65 if (is_bldg_fees or sa_fee_mode) else 0.5,
    stroked=True,
    filled=True,
    extruded=False,
    wireframe=True,
    get_fill_color="properties.__COLOR__",
    get_line_color="properties.__BORDER_COLOR__",
    lineWidthMinPixels=2,          # <--- Crisp borders
    auto_highlight=True,
)

view_state = pdk.ViewState(latitude=44.0, longitude=-80.0, zoom=5.8)

_upper_tip = (
    (
        f"{{{name_field}}}\n"
        f"{'Direct' if direct_only else 'Median'} 10,000 ft² {'Barn' if bf_bldg_type == '🐄 Livestock Barn' else 'Shed'}: {{__BF_EST_DISPLAY__}}\n"
        "Cost Tier: {__BF_TIER__}\n"
        "Authority: {__BF_AUTH__} | Year: {__BF_YEAR__}\n"
        "By-law: {__BYLAW_NAME__}"
    )
    if is_bldg_fees
    else (
        f"{{{name_field}}}\n"
        "Farm Exemption: {__STATUS__}\n"
        f"{'Direct' if direct_only else 'Median'} {sa_bench_vol:,} m³ Fee: {{__SA_FEE_DISPLAY__}}\n"
        "Fee Tier: {__SA_FEE_TIER__}\n"
        "By-law: {__BYLAW_NAME__}"
    )
    if sa_fee_mode
    else (
        f"{{{name_field}}}\n"
        "Status: {__STATUS__}\n"
        "Expiry: {__EXPIRY__}\n"
        "Signal: {__SIGNAL__}\n"
        "Bylaw: {__BYLAW_NAME__}\n"
        "Link: {__BYLAW_LINK__}"
    )
)

event = st.pydeck_chart(
    height=720,
    on_select="rerun",
    selection_mode="single-object",
    pydeck_obj=pdk.Deck(
        layers=[layer],
        initial_view_state=view_state,
        map_style="light",
        tooltip={"text": _upper_tip},
    ),
)

# --- CLICK HANDLER LOGIC ---
if event.selection:
    indices = None
    objects = event.selection.get("objects")

    if isinstance(objects, dict):
        indices = list(objects.keys())
    elif isinstance(objects, list) and objects:
        indices = objects

    if indices:
        try:
            idx = int(list(indices)[0])
            if idx < len(gdf_view):
                clicked_muni = gdf_view.iloc[idx][name_field]
                if st.session_state.get("selected_upper_muni") != clicked_muni:
                    st.session_state["selected_upper_muni"] = clicked_muni
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
        st.sidebar.markdown(f"**Cost Tier:** {str(r.get('__BF_TIER__', '—')).replace('$', chr(92) + '$')}")
        st.sidebar.markdown(f"**{'Direct' if direct_only else 'Median'} 10,000 ft² {'Barn' if bf_bldg_type == '🐄 Livestock Barn' else 'Shed'}:** {str(r.get('__BF_EST_DISPLAY__', '—')).replace('$', chr(92) + '$')}")
        st.sidebar.markdown(f"**Authority:** {r.get('__BF_AUTH__', '—')}")
        st.sidebar.markdown(f"**Fee Year:** {r.get('__BF_YEAR__', '—')}")
        if str(r.get("__BF_NOTES__", "") or "").strip():
            st.sidebar.info(str(r.get("__BF_NOTES__")).replace("$", r"\$"))
    else:
        st.sidebar.markdown(f"**Status:** {str(r.get('__STATUS__', 'N/A') or 'N/A')}")
        st.sidebar.markdown(f"**Expiry signal:** {str(r.get('__SIGNAL__', '') or '').strip() or '—'}")
        if is_site_alt:
            _sfx = "__DIRECT" if direct_only else ""
            _sa_fvs = str(r.get(f"SA Fee Verification Status{_sfx}", "") or "").strip()
            _sa_rate = str(r.get(f"SA Per m3 Rate{_sfx}", "") or "").strip()
            _sa_5k = str(r.get(f"SA Est Fee 5000 m3{_sfx}", "") or "").strip()
            _sa_15k = str(r.get(f"SA Est Fee 15000 m3{_sfx}", "") or "").strip()
            _sa_fbn = str(r.get(f"SA Fees Bylaw Name{_sfx}", "") or "").strip()
            _sa_fbl = str(r.get(f"SA Fees Bylaw Link{_sfx}", "") or "").strip()
            if _sa_fvs and _sa_fvs != "N/A (No Bylaw)":
                st.sidebar.markdown("---")
                _scope_lbl = "Direct" if direct_only else "Lower-Tier Median"
                st.sidebar.markdown(f"**💰 Excess Soil / Fill Fees** ({_sa_fvs})")
                if _sa_rate and _sa_rate.lower() != "nan":
                    try:
                        st.sidebar.markdown(f"**{_scope_lbl} Rate:** ${float(_sa_rate):,.2f}/m³")
                    except Exception:
                        pass
                if _sa_5k and _sa_5k.lower() != "nan":
                    try:
                        st.sidebar.markdown(f"**{_scope_lbl} 5,000 m³ Est.:** ${float(_sa_5k):,.0f}")
                    except Exception:
                        pass
                if _sa_15k and _sa_15k.lower() != "nan":
                    try:
                        st.sidebar.markdown(f"**{_scope_lbl} 15,000 m³ Est.:** ${float(_sa_15k):,.0f}")
                    except Exception:
                        pass
                if _sa_fbn:
                    st.sidebar.markdown(f"**Fees By-law:** [{_sa_fbn}]({_sa_fbl})" if _sa_fbl else f"**Fees By-law:** {_sa_fbn}")

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
        st.sidebar.markdown(f"**Source:** {bylaw_link}")

    # --- Scanner Evidence Panel ---
    cname_selected = canon_name(str(selected_muni))
    if cname_selected in signals_data:
        hits_list = signals_data[cname_selected]
        target_category = LAYER_TO_CATEGORY.get(selected_label, None)
        
        target_hit = None
        if target_category:
            for h in hits_list:
                if h.get('category') == target_category:
                    target_hit = h
                    break
        if target_hit is None and hits_list:
            target_hit = hits_list[0]
        
        if target_hit:
            st.sidebar.divider()
            st.sidebar.markdown("### 🚨 Scanner Evidence Found")
            trigger = target_hit.get('trigger_keyword', 'N/A')
            date_found = str(target_hit.get('discovered_date', 'N/A')).split(" ")[0]
            snippet = target_hit.get('snippet', '')
            url = target_hit.get('evidence_url', '')
            
            st.sidebar.markdown(f"**Trigger word:** `{trigger}`")
            st.sidebar.markdown(f"**Date found:** {date_found}")
            if snippet:
                st.sidebar.info(f"**Context:** _{snippet[:300]}..._" if len(str(snippet)) > 300 else f"**Context:** _{snippet}_")
            if url:
                st.sidebar.markdown(f"[View Source Document]({url})")

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
            upper_muni_status = ""
            if len(detail_row) == 1:
                upper_muni_status = str(detail_row.iloc[0].get("__STATUS__", "") or "").strip().upper()

            if upper_muni_status == "YES":
                st.success(
                    f"✅ **{selected_muni}** already has a farm exemption for this bylaw. "
                    "No advocacy letter needed!"
                )
            elif upper_muni_status in ("NO", "PARTIAL", "NOT KNOWN", ""):
                if upper_muni_status == "PARTIAL":
                    st.warning(
                        f"⚠️ **{selected_muni}** currently shows a **Partial** exemption "
                        "(mandatory *Municipal Act* topsoil removal / Drainage Act carve-outs only — "
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
                    for _key in ["advocacy_name", "advocacy_title", "advocacy_federation",
                                 "advocacy_email", "advocacy_phone"]:
                        if _key not in st.session_state:
                            st.session_state[_key] = ""

                    col_a, col_b = st.columns(2)
                    with col_a:
                        adv_name = st.text_input("Your Name *", value=st.session_state["advocacy_name"],
                                                 key="upper_adv_name", placeholder="e.g., John Smith")
                        adv_title = st.text_input("Your Title / Position *", value=st.session_state["advocacy_title"],
                                                  key="upper_adv_title", placeholder="e.g., President")
                        adv_federation = st.text_input("Organization / Affiliation (e.g., County Federation, Commodity Group, OFA Member) *",
                                                       value=st.session_state["advocacy_federation"],
                                                       key="upper_adv_fed_input", placeholder="e.g., Huron County Federation of Agriculture")
                    with col_b:
                        adv_email = st.text_input("Your Contact Email (optional)",
                                                  value=st.session_state["advocacy_email"],
                                                  key="upper_adv_email", placeholder="e.g., john@example.com")
                        adv_phone = st.text_input("Your Contact Phone (optional)",
                                                  value=st.session_state["advocacy_phone"],
                                                  key="upper_adv_phone", placeholder="e.g., (519) 555-1234")

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
                                                         key="upper_manual_email",
                                                         placeholder="e.g., clerk@municipality.ca")
                            if manual_email:
                                recipient_info["email"] = manual_email

                    # Get the bylaw name from the sidebar detail row
                    upper_detail_row = gdf_all[gdf_all[name_field].astype(str).eq(str(selected_muni))].head(1)
                    detail_bylaw_name = ""
                    if len(upper_detail_row) == 1:
                        raw_bylaw = str(upper_detail_row.iloc[0].get("__BYLAW_NAME__", "") or "").strip()
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
                        if st.button("👁️ Preview Letter", key="upper_preview_btn"):
                            preview_text = letter_to_plain_text(template_path, fields)
                            st.session_state["upper_letter_preview"] = preview_text

                        if st.session_state.get("upper_letter_preview"):
                            st.markdown("---")
                            st.markdown("**Letter Preview:**")
                            st.text_area("Letter preview", value=st.session_state["upper_letter_preview"],
                                         height=400, disabled=True, key="upper_preview_area",
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
                            key="upper_dl_letter",
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
                                key="upper_mailto_btn"
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

# --- Export Scanner Results ---
st.sidebar.divider()
st.sidebar.subheader("🚨 Export Scanner Results")
report_mode = st.sidebar.radio("Content:", ["Current View Only", "All Scanner Hits"], key="upper_report_mode")
if st.sidebar.button("Generate CSV Report", key="upper_csv_btn"):
    all_hits = []
    for cname, muni_hits in signals_data.items():
        all_hits.extend(muni_hits)
    
    filtered_hits = []
    for hit in all_hits:
        keep = False
        if report_mode == "All Scanner Hits":
            keep = True
        else:
            if hit.get('category') == LAYER_TO_CATEGORY.get(selected_label):
                keep = True
        if keep:
            filtered_hits.append(hit)
    
    if filtered_hits:
        export_df = pd.DataFrame(filtered_hits)
        csv_bytes = export_df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
        st.sidebar.download_button(
            f"⬇️ Download {len(filtered_hits)} Scanner Results",
            data=csv_bytes,
            file_name="scanner_results_upper.csv",
            mime="text/csv",
            key="upper_scanner_dl"
        )
    else:
        st.sidebar.info("No scanner results match the current view.")

# ---------- Legend ----------
with st.expander("Legend", expanded=False):
    if is_bldg_fees:
        st.markdown(
            "- **Sage Green** = Low (< `$0.28/ft²` eff.)  \n"
            "- **Bluewood-Teal** = Moderate (`$0.28–$0.37/ft²` eff.)  \n"
            "- **OFA Gold** = High (`$0.37–$0.48/ft²` eff.)  \n"
            "- **OFA Crimson** = Very High (`≥ $0.48/ft²` eff.)  \n"
            "- **Deep Slate** = Valuation-Based (`$/$1,000` CV)  \n"
            "- **Warm/Steel Gray** = Local Jurisdiction (Lower Tier) / Urban ICI  \n"
            "- **Highlight mode** dims non-matches instead of removing them"
        )
    elif sa_fee_mode:
        st.markdown(
            "- **Sage Green** = Farm Exempt (`$0`) or `$0` Waiver  \n"
            "- **Bluewood-Teal** = Low (`< $1.00/m³` eff.)  \n"
            "- **OFA Gold** = Moderate (`$1.00–$1.99/m³` eff.)  \n"
            "- **OFA Crimson** = High (`≥ $2.00/m³` eff.)  \n"
            "- **Deep Slate** = Area-Based (`$/ha`) or Cost Recovery Only  \n"
            "- **Warm Gray** = No Site Alteration By-law  \n"
            "- **Highlight mode** dims non-matches instead of removing them"
        )
    else:
        st.markdown(
            "- **YES** = green  \n"
            "- **PARTIAL** = amber (statutory minimum only, e.g. Site Alteration)  \n"
            "- **NO** = red  \n"
            "- **N/A** = gray  \n"
            "- **Other/blank** = blue  \n"
            "- **Orange outline** = expiring soon  \n"
            "- **Black outline** = expired  \n"
            "- **Yellow outline** = expiry unknown (bylaw exists)  \n"
            "- **Red-orange outline** = mentioned in recent council minutes/agendas  \n"
            "- **Highlight mode** dims non-matches instead of removing them"
        )

# ---------- Results table + export ----------
with st.expander("Results (filtered) – table + export", expanded=False):
    if is_bldg_fees:
        _ut_cols = [name_field, "__BF_TIER__", "__BF_EST_DISPLAY__", "__BF_YEAR__", "__BF_AUTH__", "__BYLAW_NAME__", "__BYLAW_LINK__"]
        table = gdf_match[[c for c in _ut_cols if c in gdf_match.columns]].copy()
        table = table.rename(
            columns={
                name_field: "County / Single Tier",
                "__BF_TIER__": "Cost Tier",
                "__BF_EST_DISPLAY__": f"{'Direct' if direct_only else 'Median'} 10k {'Barn' if bf_bldg_type == '🐄 Livestock Barn' else 'Shed'}",
                "__BF_YEAR__": "Year",
                "__BF_AUTH__": "Authority",
                "__BYLAW_NAME__": "Bylaw",
                "__BYLAW_LINK__": "Bylaw Link",
            }
        )
    elif is_site_alt:
        _sfx = "__DIRECT" if direct_only else ""
        _sa_ut_cols = [
            name_field, "__STATUS__",
            f"SA Fee Verification Status{_sfx}",
            f"SA Per m3 Rate{_sfx}",
            f"SA Est Fee 500 m3{_sfx}",
            f"SA Est Fee 5000 m3{_sfx}",
            f"SA Est Fee 15000 m3{_sfx}",
            "__BYLAW_NAME__", "__BYLAW_LINK__",
        ]
        table = gdf_match[[c for c in _sa_ut_cols if c in gdf_match.columns]].copy().rename(
            columns={
                name_field: "County / Single Tier",
                "__STATUS__": "Farm Exemption",
                f"SA Fee Verification Status{_sfx}": "Fee Audit Status",
                f"SA Per m3 Rate{_sfx}": f"{'Direct' if direct_only else 'Median'} $/m³",
                f"SA Est Fee 500 m3{_sfx}": f"{'Direct' if direct_only else 'Median'} 500 m³",
                f"SA Est Fee 5000 m3{_sfx}": f"{'Direct' if direct_only else 'Median'} 5k m³",
                f"SA Est Fee 15000 m3{_sfx}": f"{'Direct' if direct_only else 'Median'} 15k m³",
                "__BYLAW_NAME__": "Bylaw",
                "__BYLAW_LINK__": "Bylaw Link",
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
            "farm_building_fees_upper_results.csv" if is_bldg_fees
            else "site_alteration_fees_upper_results.csv" if is_site_alt
            else "bylaw_map_results_upper.csv"
        ),
        mime="text/csv",
    )
