"""
3_📋_Data_Browser.py — Searchable, filterable view of the Municipal Bylaw Database.

Reads from bylaws.db (SQLite) and provides:
• Category selector (DC, Stormwater, Site Alteration, LGD, Trees, Chickens, Fences)
• Search by municipality name
• Filterable summary table
• Municipality detail panel with all categories, contacts & scanner signals
• CSV / Excel export
"""

import os, sys

# ── Path resolution (same pattern as the map pages) ──
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import streamlit as st
import pandas as pd
from db_utils import (
    get_connection, get_category_summary, get_municipalities,
    get_bylaws, get_bylaws_with_details, get_contacts, get_signals,
    get_geographic_areas, resolve_yes_no, resolve_welfare_codes,
)

# ── Page config ──
st.set_page_config(page_title="Data Browser — Municipal Bylaw Database", page_icon="📋", layout="wide")

# ── Category display names ──
CATEGORY_OPTIONS = {
    "Development Charges":    "DC",
    "Stormwater":             "STORMWATER",
    "Site Alteration & Fill": "SITE_ALT",
    "Livestock Guardian Dogs":"LGD",
    "Tree / Forest Conservation": "TREES",
    "Backyard Chickens":      "CHICKENS",
    "Fence Bylaws":           "FENCES",
    "Farm Building Permit Fees": "BLDG_FEES",
}

CATEGORY_ICONS = {
    "DC":        "🏗️",
    "STORMWATER":"🌧️",
    "SITE_ALT":  "🚧",
    "LGD":       "🐕",
    "TREES":     "🌲",
    "CHICKENS":  "🐔",
    "FENCES":    "🏡",
    "BLDG_FEES": "🏚️",
}


# ═══════════════════════════════════════════════════════════════
# Sidebar filters
# ═══════════════════════════════════════════════════════════════
st.sidebar.title("📋 Data Browser")

conn = get_connection()

# Category selector
selected_label = st.sidebar.selectbox(
    "Bylaw Category",
    list(CATEGORY_OPTIONS.keys()),
    index=0,
)
selected_cat = CATEGORY_OPTIONS[selected_label]
icon = CATEGORY_ICONS.get(selected_cat, "📋")

# Search
search_term = st.sidebar.text_input("🔍 Search municipality", "")
wording_search = st.sidebar.text_input(
    "🔤 Search Exemption Wording",
    "",
    help="Filter by statutory wording keywords (e.g. 'bunkhouse', 'farm help', 'cannabis', 'greenhouse', 'FBRN')",
)
dc_carveout_filter = "All"
if selected_cat == "DC":
    dc_carveout_filter = st.sidebar.selectbox(
        "🏠 DC Worker Housing & Carve-Outs",
        [
            "All",
            "✅ Worker Housing Explicitly Exempt",
            "❌ Worker Housing Explicitly Excluded",
            "⚠️ Worker Housing Silent (Standard Non-Res)",
            "🌿 Cannabis Mentioned / Carve-Out",
            "🌱 Greenhouses Mentioned / Carve-Out",
        ],
        index=0,
    )

sa_nfp_filter = "All"
sa_policy_filter = "All"
sa_fee_filter = "All"
if selected_cat == "SITE_ALT":
    sa_nfp_filter = st.sidebar.selectbox(
        "🚜 NFP Exemption Scope",
        [
            "All",
            "Full NFP / Fill & Grading",
            "Statutory Topsoil & Drainage Only",
            "Topsoil Removal Only",
            "Drainage Only",
            "No NFP Exemption",
        ],
        index=0,
    )
    sa_policy_filter = st.sidebar.selectbox(
        "🚧 Site Alteration Provisions",
        [
            "All",
            "✅ Drainage Act Exempt",
            "📋 References O. Reg. 406/19",
            "⚠️ Fill Captures Sod / Compost / Manure",
            "🔴 Fill Captures Compost or Manure",
        ],
        index=0,
    )
    sa_fee_filter = st.sidebar.selectbox(
        "💰 Excess Soil / Fill Fee Filter",
        [
            "All",
            "✅ Verified Fee Schedules Only",
            "💵 Charges Per-m³ Volumetric Rate",
            "🟢 Farm Exempt ($0) / Waiver",
            "⚖️ Volume-Capped or Reduced Farm Tier",
            "🚫 Out-of-Municipality Fill Ban",
        ],
        index=0,
    )

bf_view_filter = "All"
bf_feature_filter = "All"
if selected_cat == "BLDG_FEES":
    bf_view_filter = st.sidebar.selectbox(
        "🏚️ Audit / Jurisdiction Filter",
        [
            "Verified Only (Pilot & Audited)",
            "Dedicated Farm Tiers Only",
            "Urban / No Farm Tier (ICI)",
            "Upper Tier (Shared & Local)",
            "All 444 Municipalities",
        ],
        index=0,
    )
    bf_feature_filter = st.sidebar.selectbox(
        "⚙️ Fee Structure Highlights",
        [
            "All",
            "🐄 Splits Livestock vs. Shed Rates",
            "📘 2024 OBC Group G Split",
            "⚠️ High Minimum Floor (≥ $1,000)",
            "🤝 County / Shared Building Authority",
        ],
        index=0,
    )

# Geographic area filter
areas = get_geographic_areas(conn)
selected_area = st.sidebar.selectbox("🗺️ Geographic Area", ["All"] + areas, index=0)

# Exemption status filter
status_filter = st.sidebar.selectbox(
    "🏷️ Exemption Status", ["All", "Yes", "Partial", "No", "N/A", "NOT KNOWN"], index=0
)


# ═══════════════════════════════════════════════════════════════
# Main content
# ═══════════════════════════════════════════════════════════════
st.title(f"{icon} {selected_label}")
st.caption("Browse municipal bylaw data from the OFA database")

# Load category summary
# Load category summary
df = get_category_summary(conn, selected_cat)

def _classify_dc_worker_housing(row):
    w = str(row.get("exemption_wording") or "").lower()
    prog = str(row.get("progress_label") or "").upper()
    status = str(row.get("exemption_status") or "").strip().upper()
    is_yes = status in ("1", "YES", "Y", "TRUE")
    is_no = status in ("2", "NO", "N", "FALSE")

    excl_patterns = (
        "excluding on-farm bunk houses",
        "excluding bunk houses",
        "excludes: (a) bunk house",
        "excluding on-farm worker bunkhouses",
        "is excluded from the farm building exemption",
        "does not include facilities for the permanent or temporary housing of persons employed on the lot",
        "excludes bunk houses",
        "including farm labour residences",
    )
    incl_patterns = (
        "bunk house",
        "bunkhouse",
        "farm help",
        "farm helphouse",
        "seasonal agricultural labourer",
        "accommodation for full-time farm labour",
        "on-farm site farm accommodations",
    )
    if any(p in w for p in excl_patterns):
        return "❌ Explicitly Excluded"
    if any(p in w for p in incl_patterns):
        return "✅ Explicitly Exempt"
    if "NO BY-LAW" in prog or "NO BYLAW" in prog:
        return "No DC Bylaw"
    if is_yes:
        return "⚠️ Silent (Standard Non-Res)"
    if is_no:
        return "No Farm Exemption"
    return "—"

if selected_cat == "DC":
    df["_dc_worker_housing"] = df.apply(_classify_dc_worker_housing, axis=1)

# ── Apply filters ──
if search_term:
    df = df[df["name"].str.contains(search_term, case=False, na=False)]
if selected_area != "All":
    df = df[df["geographic_area"] == selected_area]
if status_filter != "All":
    df = df[df["exemption_status"] == status_filter]
if wording_search and "exemption_wording" in df.columns:
    df = df[df["exemption_wording"].fillna("").str.contains(wording_search, case=False, na=False)]
if selected_cat == "DC" and dc_carveout_filter != "All":
    if dc_carveout_filter == "✅ Worker Housing Explicitly Exempt":
        df = df[df["_dc_worker_housing"] == "✅ Explicitly Exempt"]
    elif dc_carveout_filter == "❌ Worker Housing Explicitly Excluded":
        df = df[df["_dc_worker_housing"] == "❌ Explicitly Excluded"]
    elif dc_carveout_filter == "⚠️ Worker Housing Silent (Standard Non-Res)":
        df = df[df["_dc_worker_housing"] == "⚠️ Silent (Standard Non-Res)"]
    elif dc_carveout_filter == "🌿 Cannabis Mentioned / Carve-Out":
        df = df[df["exemption_wording"].fillna("").str.contains("cannabis|marijuana|marihuana", case=False, regex=True)]
    elif dc_carveout_filter == "🌱 Greenhouses Mentioned / Carve-Out":
        df = df[df["exemption_wording"].fillna("").str.contains("greenhouse", case=False, regex=True)]
if selected_cat == "SITE_ALT":
    if sa_nfp_filter != "All" and "nfp_exemption_scope" in df.columns:
        df = df[df["nfp_exemption_scope"].fillna("").str.strip() == sa_nfp_filter]
    if sa_policy_filter != "All":
        if sa_policy_filter == "✅ Drainage Act Exempt" and "drainage_act_exempt" in df.columns:
            df = df[df["drainage_act_exempt"].fillna("").str.strip().str.upper().isin(["YES", "1", "TRUE"])]
        elif sa_policy_filter == "📋 References O. Reg. 406/19" and "excess_soil_reg_406_19" in df.columns:
            df = df[df["excess_soil_reg_406_19"].fillna("").str.strip().str.upper().isin(["YES", "1", "TRUE"])]
        elif sa_policy_filter == "⚠️ Fill Captures Sod / Compost / Manure" and "fill_captures_ag_materials" in df.columns:
            df = df[df["fill_captures_ag_materials"].fillna("").isin(["Sod", "Compost or Manure", "Sod + Compost/Manure"])]
        elif sa_policy_filter == "🔴 Fill Captures Compost or Manure" and "fill_captures_ag_materials" in df.columns:
            df = df[df["fill_captures_ag_materials"].fillna("").isin(["Compost or Manure", "Sod + Compost/Manure"])]
    if sa_fee_filter != "All":
        _fvs = df["fee_verification_status"].fillna("").astype(str) if "fee_verification_status" in df.columns else pd.Series("", index=df.index)
        _ags = df["ag_import_fee_status"].fillna("").astype(str) if "ag_import_fee_status" in df.columns else pd.Series("", index=df.index)
        if sa_fee_filter == "✅ Verified Fee Schedules Only":
            df = df[_fvs.str.startswith("Verified")]
        elif sa_fee_filter == "💵 Charges Per-m³ Volumetric Rate" and "per_m3_rate" in df.columns:
            _pm3 = pd.to_numeric(df["per_m3_rate"], errors="coerce")
            df = df[_pm3.notna() & _pm3.gt(0)]
        elif sa_fee_filter == "🟢 Farm Exempt ($0) / Waiver":
            df = df[_ags.isin(["Exempt ($0)", "Waiver Available ($0 App Fee)"])]
        elif sa_fee_filter == "⚖️ Volume-Capped or Reduced Farm Tier":
            df = df[_ags.isin(["Exempt up to Volume Cap", "Reduced Farm Tier"])]
        elif sa_fee_filter == "🚫 Out-of-Municipality Fill Ban" and "out_of_muni_fill_ban" in df.columns:
            df = df[df["out_of_muni_fill_ban"].fillna("").astype(str).str.strip().str.lower().isin(["yes", "restricted"])]

if selected_cat == "BLDG_FEES":
    vs_s = df["verification_status"].fillna("").astype(str) if "verification_status" in df.columns else pd.Series("", index=df.index)
    hft_s = df["has_farm_tier"].fillna("").astype(str) if "has_farm_tier" in df.columns else pd.Series("", index=df.index)
    if bf_view_filter == "Verified Only (Pilot & Audited)":
        df = df[vs_s.ne("Pending") & vs_s.ne("")]
    elif bf_view_filter == "Dedicated Farm Tiers Only":
        df = df[hft_s.str.strip().str.lower().eq("yes")]
    elif bf_view_filter == "Urban / No Farm Tier (ICI)":
        df = df[hft_s.str.strip().str.lower().str.startswith("no")]
    elif bf_view_filter == "Upper Tier (Shared & Local)":
        df = df[df["municipal_status"].fillna("").eq("Upper Tier")]

    if bf_feature_filter == "🐄 Splits Livestock vs. Shed Rates":
        rl = pd.to_numeric(df.get("rate_per_sqft_livestock"), errors="coerce")
        ro = pd.to_numeric(df.get("rate_per_sqft_other_farm"), errors="coerce")
        df = df[rl.notna() & ro.notna() & (rl - ro).abs().gt(0.001)]
    elif bf_feature_filter == "📘 2024 OBC Group G Split":
        df = df[df["has_obc_group_g_split"].fillna("").astype(str).str.strip().str.lower().eq("yes")]
    elif bf_feature_filter == "⚠️ High Minimum Floor (≥ $1,000)":
        mf = pd.to_numeric(df.get("min_fee"), errors="coerce")
        df = df[mf.notna() & mf.ge(1000)]
    elif bf_feature_filter == "🤝 County / Shared Building Authority":
        sa_col = df["shared_authority"].fillna("").astype(str)
        df = df[sa_col.str.contains("County|Joint|Shared", case=False, na=False)]

# ── Metrics row ──
total = len(df)
has_expiry = len(df[df["expiry_date"].notna() & (df["expiry_date"] != "")])

# Calculate how many have a bylaw in place
def _has_bylaw(name, prog):
    name = str(name).strip().upper()
    prog = str(prog).strip().upper()
    if "NO BY" in prog or "NO BY-LAW" in prog: return False
    if name in ('', 'NONE', 'NAN', 'UNKNOWN', 'N/A', 'NO BY-LAW', ''): return False
    return True

has_bylaw_count = int(df.apply(lambda r: _has_bylaw(r.get('bylaw_name'), r.get('progress_label')), axis=1).sum())


# Category-specific metric labels and counts
partial_count = int((df["exemption_status"] == "Partial").sum()) if "exemption_status" in df.columns else 0
if selected_cat == "LGD":
    yes_label, no_label = "✅ Defines Farm Dogs", "❌ No Definition"
    # Count from combined LGD + HD definition columns (matches map logic)
    _resolve_yn = lambda v: str(v).strip().upper() in ("1", "YES", "Y", "TRUE")
    lgd_yes = df["has_lgd_definition"].apply(_resolve_yn) if "has_lgd_definition" in df.columns else pd.Series(False, index=df.index)
    hd_yes = df["has_herding_def"].apply(_resolve_yn) if "has_herding_def" in df.columns else pd.Series(False, index=df.index)
    combined = lgd_yes | hd_yes
    yes_count = int(combined.sum())
    no_count = total - yes_count
    na_count = 0
else:
    yes_label = "✅ Yes (Full NFP)" if selected_cat == "SITE_ALT" else "✅ Yes (Exemption)"
    no_label = "❌ No (Exemption)"
    yes_count = len(df[df["exemption_status"] == "Yes"])
    no_count = len(df[df["exemption_status"] == "No"])
    na_count = len(df[df["exemption_status"].isin(["N/A", "NOT KNOWN"])])

if selected_cat == "BLDG_FEES":
    _est_10k_b = pd.to_numeric(df.get("est_10000_barn"), errors="coerce").dropna()
    _est_10k_s = pd.to_numeric(df.get("est_10000_shed"), errors="coerce").dropna()
    _est_2500 = pd.to_numeric(df.get("est_2500_shed"), errors="coerce").dropna()
    _farm_tiers = int((df.get("has_farm_tier", pd.Series(dtype=str)).fillna("").astype(str).str.strip().str.lower() == "yes").sum())
    _urban_ici = int(df.get("has_farm_tier", pd.Series(dtype=str)).fillna("").astype(str).str.strip().str.lower().str.startswith("no").sum())
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Municipalities Shown", total)
    c2.metric("✅ Dedicated Farm Tier", _farm_tiers)
    c3.metric("🐄 Median 10k Barn", f"${_est_10k_b.median():,.0f}" if len(_est_10k_b) else "—")
    c4.metric("🚜 Median 10k Shed", f"${_est_10k_s.median():,.0f}" if len(_est_10k_s) else "—")
    c5.metric("🔧 Median 2.5k Shed", f"${_est_2500.median():,.0f}" if len(_est_2500) else "—")
    c6.metric("🏙️ Urban / No Farm Tier", _urban_ici)
elif selected_cat == "SITE_ALT" or partial_count > 0:
    col1, col1a, col2, colp, col3, col4, col5 = st.columns(7)
    col1.metric("Total Shown", total)
    col1a.metric("🏛️ Has Bylaw", has_bylaw_count)
    col2.metric(yes_label, yes_count)
    colp.metric("⚠️ Partial (Statutory)", partial_count)
    col3.metric(no_label, no_count)
    col4.metric("❓ N/A / Unknown", na_count)
    col5.metric("📅 Has Expiry Date", has_expiry)
    if selected_cat == "SITE_ALT" and "fee_verification_status" in df.columns:
        _sa_ver = int(df["fee_verification_status"].fillna("").astype(str).str.startswith("Verified").sum())
        _sa_m3 = pd.to_numeric(df.get("per_m3_rate"), errors="coerce").dropna()
        _sa_15k = pd.to_numeric(df.get("est_fee_15000_m3"), errors="coerce").dropna()
        if _sa_ver > 0:
            _parts = [f"💰 **Verified Fee Schedules:** {_sa_ver}"]
            if len(_sa_m3):
                _parts.append(f"**Per-m³ Rates:** {len(_sa_m3)} (median \\${_sa_m3.median():.2f}/m³)")
            if len(_sa_15k):
                _parts.append(f"**Median 15,000 m³ Farm Est.:** \\${_sa_15k.median():,.0f}")
            st.caption("  •  ".join(_parts))
else:
    col1, col1a, col2, col3, col4, col5 = st.columns(6)
    col1.metric("Total Shown", total)
    col1a.metric("🏛️ Has Bylaw", has_bylaw_count)
    col2.metric(yes_label, yes_count)
    col3.metric(no_label, no_count)
    col4.metric("❓ N/A / Unknown", na_count)
    col5.metric("📅 Has Expiry Date", has_expiry)

st.divider()

# ── Category-specific detail columns to show in the table ──
CATEGORY_DETAIL_COLS = {
    "LGD": {
        "_lgd_hd_combined":     "LGD/HD Working Dog Def.",
        "lgd_definition":       "LGD Definition Text",
        "herding_definition":   "Herding Definition Text",
        "exempt_license_fees":  "Exempt License Fees",
        "collar_tag_req":       "Collar/Tag Required",
        "barking_restrictions": "Barking Restrictions",
        "exempt_barking":       "Exempt from Barking",
        "dog_limit":            "Dog Limit",
    },
    "FENCES": {
        "has_fence_bylaw":              "Has Fence Bylaw",
        "applies_all_lands":            "Applies to All Lands",
        "replaces_lfa":                 "Replaces Line Fences Act",
        "security_fencing_exemption":   "Security Fencing Exemption",
        "electrified_fencing_exemption":"Electrified Fencing Exemption",
        "equal_apportionment":          "Equal Apportionment",
        "fence_notes":                  "Notes",
    },
    "DC": {
        "has_dc":              "Has DC Bylaw",
        "_dc_worker_housing":  "Worker Housing Treatment",
        "fees_bylaw_name":  "Fees Bylaw",
        "fees_enacted":     "Fees Enacted",
        "fees_expiry":      "Fees Expiry",
    },
    "STORMWATER": {
        "charge_type":      "Charge Type",
        "fee_calculation":  "Fee Calculation",
    },
    "SITE_ALT": {
        "farm_exemption":             "Farm Exempt. (Detail)",
        "nfp_exemption_scope":        "NFP Exemption Scope",
        "drainage_act_exempt":        "Drainage Act Exempt",
        "excess_soil_reg_406_19":     "O. Reg. 406/19",
        "fill_captures_ag_materials": "Fill Captures Ag Materials",
        "fee_verification_status":    "Fee Audit Status",
        "fee_year":                   "Fee Year",
        "ag_import_fee_status":       "Ag Import Fee Status",
        "ag_exempt_volume_cap_m3":    "Ag Exempt Cap (m³)",
        "out_of_muni_fill_ban":       "Out-of-Muni Fill Ban",
        "fee_pricing_model":          "Fee Pricing Model",
        "per_m3_rate":                "Rate ($/m³)",
        "est_fee_500_m3":             "Est. 500 m³",
        "est_fee_5000_m3":            "Est. 5k m³",
        "est_fee_15000_m3":           "Est. 15k m³",
        "fees_bylaw_name":            "Fees Bylaw",
        "fees_bylaw_link":            "Fees Bylaw Link",
        "security_deposit_terms":     "Security / Deposit",
        "peer_review_recovery":       "Peer Review Recovery",
        "fee_formula_notes":          "Fee Formula Notes",
        "special_provision":          "Special Provision",
        "guidelines_wording":         "Guidelines Wording",
        "exception_wording":          "Exception Wording",
    },
    "TREES": {
        "farm_exemption":               "Farm Exempt. (Detail)",
        "farming_exception_wording":    "Exception Wording",
    },
    "CHICKENS": {
        "can_keep":             "Can Keep Chickens",
        "chicken_limit":        "Chicken Limit",
        "roosters_allowed":     "Roosters Allowed",
        "licence_required":     "Licence Required",
        "welfare_requirements": "Welfare Requirements",
    },
    "BLDG_FEES": {
        "verification_status":      "Audit Status",
        "fee_year":                 "Fee Year",
        "shared_authority":         "Building Authority",
        "pricing_model":            "Pricing Model",
        "rate_per_sqft_livestock":  "Barn $/ft²",
        "rate_per_sqft_other_farm": "Shed $/ft²",
        "min_fee":                  "Min Fee",
        "est_2500_shed":            "Est. 2.5k Shed",
        "est_10000_barn":           "Est. 10k Barn",
        "est_10000_shed":           "Est. 10k Shed",
        "est_20000_barn":           "Est. 20k Barn",
        "silo_grain_bin_fee":       "Silo / Grain Bin",
        "manure_storage_fee":       "Manure Storage",
        "has_obc_group_g_split":    "2024 OBC Grp G",
        "formula_notes":            "Verified Formula Notes",
    },
}

# Fields that should be resolved from integer codes to Yes/No labels
YES_NO_DETAIL_FIELDS = {
    "has_lgd_definition", "has_herding_def", "exempt_license_fees",
    "collar_tag_req", "barking_restrictions", "exempt_barking",
    "_lgd_hd_combined",
    "has_fence_bylaw", "applies_all_lands", "replaces_lfa",
    "security_fencing_exemption", "electrified_fencing_exemption",
    "equal_apportionment", "has_dc", "farm_exemption", "can_keep",
    "roosters_allowed", "licence_required",
    "special_provision", "drainage_act_exempt", "excess_soil_reg_406_19",
}

# ── Build display columns ──
base_cols = ["name", "municipal_status", "geographic_area",
             "exemption_status", "bylaw_name", "date_enacted",
             "expiry_date", "expiry_notes", "progress_label", "exemption_wording", "bylaw_link"]

detail_map = CATEGORY_DETAIL_COLS.get(selected_cat, {})

# Resolve Yes/No codes in detail columns
def _resolve_detail_value(val):
    """Resolve integer codes AND text Yes/No/TRUE/FALSE to consistent labels."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return "N/A"
    s = str(val).strip().upper()
    if s in ("1", "YES", "Y", "TRUE"):
        return "Yes"
    if s in ("PARTIAL",):
        return "Partial"
    if s in ("2", "NO", "N", "FALSE"):
        return "No"
    if s in ("3", "NOT KNOWN", "UNKNOWN", "TBD"):
        return "NOT KNOWN"
    if s in ("4", "N/A", "NA", "", "NONE"):
        return "N/A"
    if s in ("5",):
        return "No explicit exemption found"
    return str(val)  # Keep original text for free-text fields

for raw_col in detail_map.keys():
    if raw_col in df.columns and raw_col in YES_NO_DETAIL_FIELDS:
        df[raw_col] = df[raw_col].apply(_resolve_detail_value)

# Compute combined LGD/HD Working Dog Definition column for LGD category
if selected_cat == "LGD":
    if "has_lgd_definition" in df.columns and "has_herding_def" in df.columns:
        # Resolve the raw columns first
        lgd_resolved = df["has_lgd_definition"].apply(_resolve_detail_value)
        hd_resolved = df["has_herding_def"].apply(_resolve_detail_value)
        df["_lgd_hd_combined"] = lgd_resolved.where(
            lgd_resolved.eq("Yes"), hd_resolved
        )
    elif "has_lgd_definition" in df.columns:
        df["_lgd_hd_combined"] = df["has_lgd_definition"].apply(_resolve_detail_value)
    else:
        df["_lgd_hd_combined"] = "N/A"

display_cols = [c for c in base_cols if c in df.columns]

# Insert detail columns after exemption_status (position 4)
detail_cols_to_show = [c for c in detail_map.keys() if c in df.columns]
insert_pos = display_cols.index("bylaw_name") if "bylaw_name" in display_cols else len(display_cols)
for i, dc in enumerate(detail_cols_to_show):
    display_cols.insert(insert_pos + i, dc)

rename_map = {
    "name": "Municipality",
    "municipal_status": "Tier",
    "geographic_area": "County / Region",
    "exemption_status": "Farm Exemption",
    "bylaw_name": "Bylaw Name",
    "date_enacted": "Enacted",
    "expiry_date": "Expires",
    "expiry_notes": "Expiry Notes",
    "progress_label": "Progress",
    "exemption_wording": "Exemption Wording",
    "bylaw_link": "Bylaw Link",
}
# Add detail column renames
rename_map.update(detail_map)

display_df = df[display_cols].rename(columns=rename_map).reset_index(drop=True)

if selected_cat == "BLDG_FEES":
    for _c in ("Min Fee", "Est. 2.5k Shed", "Est. 10k Barn", "Est. 10k Shed", "Est. 20k Barn"):
        if _c in display_df.columns:
            display_df[_c] = pd.to_numeric(display_df[_c], errors="coerce").map(
                lambda v: f"${v:,.0f}" if pd.notna(v) else "—"
            )
    for _c in ("Barn $/ft²", "Shed $/ft²"):
        if _c in display_df.columns:
            display_df[_c] = pd.to_numeric(display_df[_c], errors="coerce").map(
                lambda v: f"${v:.3f}".rstrip("0").ljust(5, "0") if pd.notna(v) else "—"
            )
    if "Fee Year" in display_df.columns:
        display_df["Fee Year"] = pd.to_numeric(display_df["Fee Year"], errors="coerce").map(
            lambda v: str(int(v)) if pd.notna(v) else "—"
        )

if selected_cat == "SITE_ALT":
    for _c in ("Est. 500 m³", "Est. 5k m³", "Est. 15k m³"):
        if _c in display_df.columns:
            display_df[_c] = pd.to_numeric(display_df[_c], errors="coerce").map(
                lambda v: f"${v:,.0f}" if pd.notna(v) else "—"
            )
    if "Rate ($/m³)" in display_df.columns:
        display_df["Rate ($/m³)"] = pd.to_numeric(display_df["Rate ($/m³)"], errors="coerce").map(
            lambda v: f"${v:,.2f}/m³" if pd.notna(v) else "—"
        )
    if "Ag Exempt Cap (m³)" in display_df.columns:
        display_df["Ag Exempt Cap (m³)"] = pd.to_numeric(display_df["Ag Exempt Cap (m³)"], errors="coerce").map(
            lambda v: f"{v:,.0f} m³" if pd.notna(v) else "—"
        )
    if "Fee Year" in display_df.columns:
        display_df["Fee Year"] = pd.to_numeric(display_df["Fee Year"], errors="coerce").map(
            lambda v: str(int(v)) if pd.notna(v) else "—"
        )

# Clean up NaN/None values to display as "—" instead of "nan"
display_df = display_df.fillna("—")
display_df = display_df.replace({"nan": "—", "None": "—", "none": "—", "": "—"})

# ── Data table ──
st.subheader(f"📊 {selected_label} — {total} Municipalities")

# Highlight function for exemption status and Yes/No fields
def highlight_status(val):
    v = str(val).strip()
    if v in ("Yes", "✅ Explicitly Exempt", "Full NFP / Fill & Grading", "None Flagged", "Exempt ($0)"):
        return "background-color: #d4edda; color: #155724"
    elif v in ("No", "❌ Explicitly Excluded", "No Farm Exemption", "No NFP Exemption", "Sod + Compost/Manure", "Compost or Manure", "Standard Commercial Rate"):
        return "background-color: #f8d7da; color: #721c24"
    elif v in ("Partial", "N/A", "NOT KNOWN", "⚠️ Silent (Standard Non-Res)", "Statutory Topsoil & Drainage Only", "Topsoil Removal Only", "Drainage Only", "Sod", "Exempt up to Volume Cap", "Reduced Farm Tier", "Waiver Available ($0 App Fee)", "Restricted"):
        return "background-color: #fff3cd; color: #856404"
    return ""

# Apply highlighting to Farm Exemption and all Yes/No detail columns
highlight_cols = [
    "Farm Exemption",
    "Worker Housing Treatment",
    "NFP Exemption Scope",
    "Fill Captures Ag Materials",
    "Ag Import Fee Status",
]
for raw_col, nice_name in detail_map.items():
    if raw_col in YES_NO_DETAIL_FIELDS and nice_name in display_df.columns:
        highlight_cols.append(nice_name)
subset = [c for c in highlight_cols if c in display_df.columns]

if hasattr(display_df.style, "map"):
    styled = display_df.style.map(highlight_status, subset=subset)
else:
    styled = display_df.style.applymap(highlight_status, subset=subset)

st.dataframe(
    styled, 
    use_container_width=True, 
    height=500,
    column_config={
        "Bylaw Link": st.column_config.LinkColumn("Bylaw Link"),
        "Fees Bylaw Link": st.column_config.LinkColumn("Fees Bylaw Link"),
    }
)

# ── Export ──
st.sidebar.divider()
st.sidebar.subheader("📥 Export")
csv_data = display_df.to_csv(index=False).encode("utf-8")
st.sidebar.download_button(
    label=f"Download {selected_label} CSV",
    data=csv_data,
    file_name=f"bylaw_data_{selected_cat.lower()}.csv",
    mime="text/csv",
)


# ═══════════════════════════════════════════════════════════════
# Municipality Detail Panel
# ═══════════════════════════════════════════════════════════════
st.divider()
st.subheader("🔎 Municipality Detail")

muni_names = sorted(df["name"].unique().tolist())
if muni_names:
    selected_muni = st.selectbox("Select a municipality to view details", muni_names)

    # Find the municipality ID
    muni_row = conn.execute(
        "SELECT * FROM municipalities WHERE name = ?", (selected_muni,)
    ).fetchone()

    if muni_row:
        muni_id = muni_row["id"]

        # ── Info columns ──
        info_col1, info_col2 = st.columns(2)
        with info_col1:
            st.markdown(f"**Municipality:** {muni_row['name']}")
            st.markdown(f"**Status:** {muni_row['municipal_status'] or '—'}")
            st.markdown(f"**Region:** {muni_row['geographic_area'] or '—'}")
            st.markdown(f"**Zone:** {muni_row['zone'] or '—'}")
            if muni_row["website"]:
                st.markdown(f"**Website:** [{muni_row['website']}]({muni_row['website']})")
            if muni_row["bylaw_page_link"]:
                st.markdown(f"**By-law Directory:** [{muni_row['bylaw_page_link']}]({muni_row['bylaw_page_link']})")
        with info_col2:
            st.markdown(f"**Contact:** {muni_row['contact_name'] or '—'}")
            st.markdown(f"**Position:** {muni_row['contact_position'] or '—'}")
            st.markdown(f"**Email:** {muni_row['clerk_email'] or '—'}")
            st.markdown(f"**Phone:** {muni_row['clerk_phone'] or '—'}")

        # ── All bylaws for this municipality ──
        st.markdown("---")
        st.markdown("#### All Bylaw Categories")

        all_bylaws = get_bylaws(conn, muni_id)

        for _, brow in all_bylaws.iterrows():
            cat = brow["category"]
            cat_icon = CATEGORY_ICONS.get(cat, "📋")
            cat_name = next((k for k, v in CATEGORY_OPTIONS.items() if v == cat), cat)
            status = resolve_yes_no(brow["exemption_status"])

            # Status badge
            if status == "Yes":
                badge = "✅"
            elif status == "Partial":
                badge = "⚠️"
            elif status == "No":
                badge = "❌"
            else:
                badge = "❓"

            with st.expander(f"{cat_icon} {cat_name}  {badge} {status}", expanded=(cat == selected_cat)):
                detail_col1, detail_col2 = st.columns(2)
                with detail_col1:
                    st.markdown(f"**Bylaw:** {brow['bylaw_name'] or '—'}")
                    st.markdown(f"**Enacted:** {brow['date_enacted'] or '—'}")
                    st.markdown(f"**Expires:** {brow['expiry_date'] or '—'}")
                    if brow["expiry_notes"]:
                        st.markdown(f"**Expiry Notes:** {brow['expiry_notes']}")
                with detail_col2:
                    st.markdown(f"**Farm Exemption:** {status}")
                    st.markdown(f"**Progress:** {brow['progress_label'] or '—'}")
                    if brow["bylaw_link"]:
                        st.markdown(f"[🔗 View Bylaw]({brow['bylaw_link']})")

                wording = brow["exemption_wording"]
                if pd.notna(wording) and str(wording).strip():
                    st.markdown("**Exemption Wording:**")
                    st.info(str(wording)[:2000])

                notes = brow["other_notes"]
                if pd.notna(notes) and str(notes).strip():
                    st.markdown("**Notes:**")
                    st.caption(str(notes)[:300])

                # Category-specific details
                _, detail_df = get_bylaws_with_details(conn, muni_id, cat)
                if not detail_df.empty:
                    detail_row = detail_df.iloc[0]
                    extra_fields = []
                    for col_name in detail_df.columns:
                        if col_name in ("id", "bylaw_id", "calc_spec_json", "fee_calc_spec_json"):
                            continue
                        val = detail_row[col_name]
                        if val and str(val).strip():
                            nice_name = col_name.replace("_", " ").title()
                            if col_name == "welfare_requirements":
                                resolved = resolve_welfare_codes(val)
                            elif str(val) in ("1","2","3","4","5"):
                                resolved = resolve_yes_no(val)
                            else:
                                resolved = val
                            extra_fields.append((nice_name, resolved))
                    if extra_fields:
                        st.markdown("**Category Details:**")
                        for fn, fv in extra_fields:
                            fv_display = str(fv)[:200] if fv else "—"
                            st.markdown(f"- **{fn}:** {fv_display}")

        # ── Contacts ──
        contacts_df = get_contacts(conn, muni_id)
        if not contacts_df.empty:
            st.markdown("---")
            st.markdown("#### 📞 Municipal Contacts (AMCTO Directory)")
            contact_display = contacts_df[["title", "first_name", "last_name", "email", "phone", "department"]].copy()
            contact_display.columns = ["Title", "First Name", "Last Name", "Email", "Phone", "Department"]
            st.dataframe(contact_display, use_container_width=True, hide_index=True)

        # ── Scanner signals ──
        signals_df = get_signals(conn, muni_id, days=365)
        if not signals_df.empty:
            st.markdown("---")
            st.markdown("#### 🛰️ Scanner Intelligence Signals")
            for _, sig in signals_df.iterrows():
                st.markdown(f"**{sig['trigger_keyword']}** ({sig['category']}) — {sig['discovered_date']}")
                if sig["snippet"]:
                    st.caption(sig["snippet"][:300])
                if sig["evidence_url"]:
                    st.markdown(f"[Source]({sig['evidence_url']})")
else:
    st.info("No municipalities match your filters. Try adjusting the search or filters.")

conn.close()
