"""
7_🧮_Fee_Explorer.py — Standalone OFA Farm Permit, Development Charge & Excess Soil Fee Explorer.

Provides a clean, farmer- & council-ready workspace for quantitative municipal fees
WITHOUT modifying the binary bylaw exemption map layers or existing exemption workflows:
  - View 1: Farm Building Permit Fees (BLDG_FEES) — scenarios, Bottom Line banner, cost receipt,
            county peer bars, size curve
  - View 2: Agricultural Development Charges (DC) — 4 farm building sub-types (Typical Farm,
            Commercial Greenhouse, Cannabis Production, Bunkhouse / SAWP), Rural vs. Urban servicing,
            Upper-Tier County/Region stacking, 4-tile snapshot, stacked peer chart & scaling curve
  - View 3: Site Alteration & Excess Soil Fees (SITE_ALT) — truckload presets, Bottom Line banner,
            rule vs cost split, separate refundable security box, volumetric median, volume-cliff curve
  - View 4: Side-by-Side Peer Comparator & 1-Page OFA Council Delegation Brief (.docx)
"""

from __future__ import annotations

import html
import os
import re
import sys
import datetime

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import pandas as pd
import streamlit as st

from db_utils import get_connection, get_category_summary
from bldg_fees_calc import evaluate_bldg_fee, fee_cost_tier_rgba
from dc_fees_calc import compute_stacked_dc, evaluate_dc_fee, STANDARD_DC_BENCHMARKS
from site_alt_fees_calc import evaluate_site_alt_fee, site_alt_fee_tier_rgba
from fee_charts import (
    build_peer_bar_chart,
    build_bldg_scaling_chart,
    build_site_alt_scaling_chart,
    build_dc_stacked_peer_chart,
    build_dc_scaling_chart,
)

st.set_page_config(
    page_title="Farm Fee Explorer — OFA Bylaw Database",
    page_icon="🧮",
    layout="wide",
)

# Subtle OFA Brand Guide 2025-26 CSS polish (Champagne Bottom-Line banner + Crimson accent bar)
st.markdown(
    """
    <style>
    .ofa-bottom-line {
        background-color: #EDE6DE;
        border-left: 4px solid #D7182A;
        border-radius: 4px;
        padding: 12px 16px;
        margin: 8px 0 16px 0;
        color: #1E293B;
        font-family: Arial, sans-serif;
        font-size: 0.96rem;
        line-height: 1.45;
    }
    .ofa-bottom-line strong.ofa-bl-tag {
        color: #334B58;
        text-transform: uppercase;
        font-size: 0.78rem;
        letter-spacing: 0.05em;
        margin-right: 6px;
    }
    .ofa-card-hdr {
        color: #334B58;
        font-family: Arial, sans-serif;
        font-size: 1.05rem;
        font-weight: 700;
        border-bottom: 2px solid #EDE6DE;
        padding-bottom: 6px;
        margin-bottom: 10px;
    }
    [data-testid="stMetricValue"] {
        font-size: 1.6rem !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data(ttl=300)
def load_fee_datasets() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Load BLDG_FEES, DC, and SITE_ALT summaries from the active database (SQLite or Neon PG)."""
    conn = get_connection()
    bf_df = get_category_summary(conn, "BLDG_FEES")
    dc_df = get_category_summary(conn, "DC")
    sa_df = get_category_summary(conn, "SITE_ALT")
    conn.close()
    return bf_df, dc_df, sa_df


def _clean_str(val, fallback: str = "—") -> str:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return fallback
    s = str(val).strip()
    if not s or s.lower() in ("nan", "none"):
        return fallback
    return s


def _md_safe(val, fallback: str = "—") -> str:
    """Clean a string and escape literal $ signs so Streamlit Markdown never parses them as LaTeX math."""
    return _clean_str(val, fallback=fallback).replace("$", r"\$")


def _fmt_dollars(val: float | None) -> str:
    if val is None or pd.isna(val):
        return "—"
    return f"${round(float(val)):,}"


def _valid_url(val) -> str | None:
    s = _clean_str(val, fallback="")
    if s.lower().startswith(("http://", "https://")):
        return s.split()[0]
    return None


def _fmt_year(val) -> str:
    s = _clean_str(val, fallback="")
    if not s:
        return "—"
    try:
        return str(int(float(s)))
    except Exception:
        return s


def _render_bottom_line(body_html: str) -> None:
    st.markdown(
        f'<div class="ofa-bottom-line"><strong class="ofa-bl-tag">Bottom Line</strong>{body_html}</div>',
        unsafe_allow_html=True,
    )


# ── Header ──
st.markdown(
    "<h1 style='color:#334B58; font-family:Arial, sans-serif; margin-bottom:0.15rem;'>"
    "Farm Permit, Development Charge &amp; Excess Soil Fee Explorer</h1>",
    unsafe_allow_html=True,
)
st.caption(
    "Estimate municipal farm building permits, stacked agricultural development charges, and excess soil fees — "
    "compare county neighbours against provincial medians and export 1-page OFA council delegation briefs."
)

bf_all, dc_all, sa_all = load_fee_datasets()
bf_local = bf_all[bf_all["municipal_status"].fillna("") != "Upper Tier"].copy()
dc_local = dc_all[dc_all["municipal_status"].fillna("") != "Upper Tier"].copy()
sa_local = sa_all[sa_all["municipal_status"].fillna("") != "Upper Tier"].copy()

# Lookup map for parent Upper-Tier County / Region DC schedules (matched ONLY for Lower-Tier rows)
dc_upper_by_area: dict[str, pd.Series] = {
    str(r["geographic_area"]): r
    for _, r in dc_all[dc_all["municipal_status"].fillna("") == "Upper Tier"].iterrows()
    if pd.notna(r.get("geographic_area"))
}


def _parent_upper_dc_row(muni_row: pd.Series, stack_enabled: bool) -> pd.Series | None:
    """Return parent Upper-Tier DC row ONLY when stacking is enabled and municipality is Lower Tier."""
    if not stack_enabled:
        return None
    if str(muni_row.get("municipal_status", "")).strip() != "Lower Tier":
        return None
    return dc_upper_by_area.get(str(muni_row.get("geographic_area", "")))


VIEW_OPTIONS = [
    "Farm Building Permit Fees",
    "Agricultural Development Charges",
    "Site Alteration & Excess Soil Fees",
    "Peer Comparator & Council Brief",
]

# ── Seamless deep-linking from Home Snapshot or Lower Tier Map ──
_jump_view = st.session_state.pop("fe_jump_view", None) or st.query_params.get("view", None)
_jump_muni = st.session_state.pop("fe_jump_muni", None) or st.query_params.get("muni", None)

if _jump_view:
    _jv = str(_jump_view).strip().lower()
    if "dev" in _jv or _jv == "dc" or "charge" in _jv:
        st.session_state["fe_active_view"] = VIEW_OPTIONS[1]
    elif "site" in _jv or "soil" in _jv or _jv == "sa":
        st.session_state["fe_active_view"] = VIEW_OPTIONS[2]
    elif "peer" in _jv or "compar" in _jv or "brief" in _jv:
        st.session_state["fe_active_view"] = VIEW_OPTIONS[3]
    else:
        st.session_state["fe_active_view"] = VIEW_OPTIONS[0]

if _jump_muni:
    _jm = str(_jump_muni).strip()
    st.session_state["fe_bf_area"] = "All Counties / Districts"
    st.session_state["fe_dc_area"] = "All Counties / Districts"
    st.session_state["fe_sa_area"] = "All Counties / Districts"
    if _jm in bf_local["name"].astype(str).values:
        st.session_state["fe_bf_muni"] = _jm
        st.session_state["fe_cmp_home"] = _jm
    if _jm in dc_all["name"].astype(str).values:
        _dc_active_names = set(
            dc_all.loc[dc_all["has_dc"].fillna("").astype(str).str.strip().str.lower().isin(["yes", "1"]), "name"].astype(str)
        )
        if _jm not in _dc_active_names:
            st.session_state["fe_dc_active_only"] = False
        st.session_state["fe_dc_muni"] = _jm
    if _jm in sa_local["name"].astype(str).values:
        _sa_active_names = set(
            sa_local.loc[
                ~sa_local["fee_verification_status"].fillna("").astype(str).str.contains("No Bylaw", case=False, na=False)
                & sa_local["fee_verification_status"].fillna("").astype(str).ne(""),
                "name",
            ].astype(str)
        )
        if _jm not in _sa_active_names:
            st.session_state["fe_sa_active_only"] = False
        st.session_state["fe_sa_muni"] = _jm

if "fe_active_view" not in st.session_state or st.session_state["fe_active_view"] not in VIEW_OPTIONS:
    st.session_state["fe_active_view"] = VIEW_OPTIONS[0]

if hasattr(st, "segmented_control"):
    active_view = st.segmented_control(
        "Fee Workspace",
        VIEW_OPTIONS,
        selection_mode="single",
        key="fe_active_view",
        label_visibility="collapsed",
    ) or VIEW_OPTIONS[0]
else:
    active_view = st.radio(
        "Fee Workspace",
        VIEW_OPTIONS,
        horizontal=True,
        key="fe_active_view",
        label_visibility="collapsed",
    )

st.markdown("")


def _compute_ont_med_bf(sqft: int, is_livestock: bool) -> float | None:
    vals = []
    for _, _r in bf_local.iterrows():
        if str(_r.get("name", "")) == "Moosonee":
            continue
        _v = evaluate_bldg_fee(_r, float(sqft), is_livestock=is_livestock, assumed_cost_per_sqft=None)
        if _v is not None:
            vals.append(_v)
    return float(pd.Series(vals).median()) if vals else None


def _compute_sa_medians(vol: int) -> tuple[float | None, float | None]:
    """Return (ontario_all_paid_median, ontario_volumetric_per_m3_median) at `vol`."""
    paid_all, paid_vol = [], []
    for _, _r in sa_local.iterrows():
        _v = evaluate_site_alt_fee(_r, float(vol))
        if _v is not None and _v > 0:
            paid_all.append(_v)
            _pm3 = pd.to_numeric(_r.get("per_m3_rate"), errors="coerce")
            if pd.notna(_pm3) and float(_pm3) > 0:
                paid_vol.append(_v)
    return (
        float(pd.Series(paid_all).median()) if paid_all else None,
        float(pd.Series(paid_vol).median()) if paid_vol else None,
    )


def _compute_dc_charged_median(
    building_type: str,
    service_area: str,
    stacked: bool,
    sqft: float | None = None,
    beds: int | None = None,
) -> float | None:
    """Return Ontario Charged Median ($ > 0) across local/single-tier municipalities."""
    charged = []
    for _, _r in dc_local.iterrows():
        _ut = _parent_upper_dc_row(_r, stacked)
        _res = compute_stacked_dc(_r, _ut, building_type, service_area, sqft=sqft, beds=beds)
        _tv = _res["stacked_total"]
        if _tv is not None and _tv > 0:
            charged.append(_tv)
    return float(pd.Series(charged).median()) if charged else None


def _dc_short_status(val: float | None, raw_status: str, no_dc: bool = False) -> str:
    if no_dc:
        return "No DC By-law"
    if val is not None:
        if val <= 0:
            return "Exempt ($0)"
        s = _clean_str(raw_status, "Charged")
        return s[:38] + ("…" if len(s) > 38 else "")
    s = _clean_str(raw_status, "Silent / Confirm")
    if "defer" in s.lower():
        return "Deferred"
    if "silent" in s.lower():
        return "Silent / Confirm"
    return s[:38] + ("…" if len(s) > 38 else "")


def _pretty_upper_name(val) -> str:
    s = _clean_str(val, "")
    if not s:
        return ""
    if s.endswith(", Co"):
        return s[:-4] + " County"
    if s.endswith(", R"):
        return s[:-3] + " Region"
    return s


def _dc_effective_total(ev: dict) -> tuple[float | None, bool]:
    """Return (display_total, is_partial_silent).

    Preserves empirical rigor: if both tiers are verified, returns exact sum (is_partial=False).
    If one tier is verified > $0 and the other tier is Silent, returns the verified minimum floor
    with is_partial=True (displayed with '+' and explicit silent-tier warning).
    If the only known tier is $0 while the other tier is Silent, returns (None, False) so a
    silent tier is NEVER disguised as $0 Exempt.
    """
    if ev["stacked_total"] is not None:
        return float(ev["stacked_total"]), False
    kf = ev.get("known_floor_total")
    if kf is not None and float(kf) > 0.0:
        return float(kf), True
    return None, False


# ═══════════════════════════════════════════════════════════════════════════
# VIEW 1: FARM BUILDING PERMIT FEES (BLDG_FEES)
# ═══════════════════════════════════════════════════════════════════════════
if active_view == VIEW_OPTIONS[0]:
    bf_areas = ["All Counties / Districts"] + sorted(bf_local["geographic_area"].dropna().astype(str).unique().tolist())

    if "fe_bf_area" not in st.session_state or st.session_state["fe_bf_area"] not in bf_areas:
        st.session_state["fe_bf_area"] = bf_areas[0]

    c_sel1, c_sel2, c_sel3 = st.columns([1.2, 1.5, 1.3])
    with c_sel1:
        fe_bf_area = st.selectbox("Filter by County / District", bf_areas, key="fe_bf_area")
    bf_pool = bf_local if fe_bf_area == "All Counties / Districts" else bf_local[bf_local["geographic_area"] == fe_bf_area]
    bf_muni_names = sorted(bf_pool["name"].dropna().astype(str).unique().tolist())

    if "fe_bf_muni" not in st.session_state or st.session_state["fe_bf_muni"] not in bf_muni_names:
        st.session_state["fe_bf_muni"] = "Perth East" if "Perth East" in bf_muni_names else (bf_muni_names[0] if bf_muni_names else "")

    with c_sel2:
        fe_bf_muni = st.selectbox("Select Municipality", bf_muni_names, key="fe_bf_muni")
    with c_sel3:
        fe_bf_struct = st.radio(
            "Structure Type",
            ["🐄 Livestock Barn", "🚜 Equipment / Drive Shed"],
            index=0,
            horizontal=True,
            key="fe_bf_struct",
        )
    is_live = (fe_bf_struct == "🐄 Livestock Barn")
    struct_short = "Livestock Barn" if is_live else "Equipment / Drive Shed"

    p_col1, p_col2, p_col3 = st.columns([1.8, 1.4, 1.2])
    with p_col1:
        fe_bf_preset = st.radio(
            "Farm Project Size Scenario",
            ["2,500 ft² Shed", "10,000 ft² Barn", "20,000 ft² Barn", "Custom Size"],
            index=1,
            horizontal=True,
            key="fe_bf_preset",
        )
        _preset_sqft = {"2,500 ft² Shed": 2500, "10,000 ft² Barn": 10000, "20,000 ft² Barn": 20000}
        if fe_bf_preset in _preset_sqft:
            fe_bf_sqft = _preset_sqft[fe_bf_preset]
        else:
            fe_bf_sqft = st.slider(
                "Custom Footprint (sq. ft.)",
                min_value=1500,
                max_value=30000,
                value=10000,
                step=500,
                key="fe_bf_sqft_slider",
            )
    with p_col2:
        fe_bf_val_on = st.checkbox(
            "Estimate Valuation-Based (per $1k CV) schedules",
            value=False,
            key="fe_bf_val_on",
            help="Off by default so area-based schedules and construction-value schedules are never silently mixed. Turn on to estimate valuation-only municipalities (e.g., Ottawa, French River, Wawa) using an assumed per-sq.-ft. construction cost.",
        )
        fe_bf_assumed = None
        if fe_bf_val_on:
            fe_bf_assumed = float(
                st.number_input(
                    "Assumed Construction Cost ($/ft²)",
                    min_value=20,
                    max_value=400,
                    value=100 if is_live else 55,
                    step=5,
                    key="fe_bf_assumed",
                )
            )
    with p_col3:
        fe_bf_chart_scope = st.selectbox(
            "Peer Chart Scope",
            ["Same County / District", "Provincial Lowest 15", "Provincial Highest 15 (Ag/Town)"],
            index=0,
            key="fe_bf_chart_scope",
        )

    _bf_eval_rows = []
    for _, _r in bf_local.iterrows():
        _est = evaluate_bldg_fee(_r, float(fe_bf_sqft), is_livestock=is_live, assumed_cost_per_sqft=fe_bf_assumed)
        _est_base = evaluate_bldg_fee(_r, float(fe_bf_sqft), is_livestock=is_live, assumed_cost_per_sqft=None)
        _is_val_est = (_est is not None and _est_base is None and fe_bf_assumed is not None)
        _, _tier = fee_cost_tier_rgba(
            _est, float(fe_bf_sqft),
            _clean_str(_r.get("verification_status"), ""),
            _clean_str(_r.get("has_farm_tier"), ""),
            _clean_str(_r.get("pricing_model"), ""),
        )
        _bf_eval_rows.append({
            "Municipality": str(_r["name"]),
            "County": _clean_str(_r.get("geographic_area")),
            "Fee": _est,
            "FeeBase": _est_base,
            "IsEstimate": _is_val_est,
            "Tier": _tier,
            "Model": _clean_str(_r.get("pricing_model")),
            "Year": _fmt_year(_r.get("fee_year")),
            "Authority": _clean_str(_r.get("shared_authority"), "Municipal"),
            "Status": _clean_str(_r.get("verification_status"), "Pending"),
            "Bylaw": _clean_str(_r.get("bylaw_name")),
            "Link": _valid_url(_r.get("bylaw_link")),
        })
    bf_eval_df = pd.DataFrame(_bf_eval_rows)

    _emp_prov = bf_eval_df[bf_eval_df["FeeBase"].notna() & (bf_eval_df["Municipality"] != "Moosonee")]["FeeBase"]
    ont_med_bf = float(_emp_prov.median()) if len(_emp_prov) else None

    focus_raw = bf_local[bf_local["name"] == fe_bf_muni].iloc[0]
    focus_eval = bf_eval_df[bf_eval_df["Municipality"] == fe_bf_muni].iloc[0]
    focus_county = focus_eval["County"]

    # County ranking context for Bottom Line strip
    _cnty_priced = bf_eval_df[(bf_eval_df["County"] == focus_county) & bf_eval_df["Fee"].notna()].sort_values("Fee", ascending=False).reset_index(drop=True)
    _dep_raw = _clean_str(focus_raw.get("refundable_deposit"), "")
    if pd.notna(focus_eval["Fee"]):
        _fv = float(focus_eval["Fee"])
        _eff = _fv / float(fe_bf_sqft)
        _pct_str = ""
        if ont_med_bf and ont_med_bf > 0:
            _pct = round((_fv - ont_med_bf) / ont_med_bf * 100)
            _pct_str = (
                f"<b>{abs(_pct)}% {'above' if _pct > 0 else 'below'}</b> the Ontario median ({_fmt_dollars(ont_med_bf)})"
                if _pct != 0 else f"<b>equal to</b> the Ontario median ({_fmt_dollars(ont_med_bf)})"
            )
        _rk_str = ""
        if fe_bf_muni in _cnty_priced["Municipality"].values and len(_cnty_priced) > 1:
            _pos = int(_cnty_priced.index[_cnty_priced["Municipality"] == fe_bf_muni][0]) + 1
            _rk_str = f" and <b>#{_pos} of {len(_cnty_priced)}</b> priced peers in {html.escape(focus_county)}"
        _dep_str = f" Separate deposit/surcharge: {html.escape(_dep_raw)}." if (_dep_raw and "not specified" not in _dep_raw.lower()) else ""
        _render_bottom_line(
            f"<b>{html.escape(fe_bf_muni)}</b> charges <b>{_fmt_dollars(_fv)}</b> (${_eff:.2f}/ft²) for a {fe_bf_sqft:,} ft² "
            f"{struct_short.lower()} — {_pct_str}{_rk_str}.{_dep_str}"
        )
    else:
        _render_bottom_line(
            f"<b>{html.escape(fe_bf_muni)}</b> ({html.escape(focus_county)}) is classified as <b>{html.escape(focus_eval['Tier'])}</b> "
            f"({html.escape(focus_eval['Model'])}). No direct per-sq.-ft. farm fee applies without additional assumptions."
        )

    # ── Two-Part Cost Receipt Card ──
    card_l, card_r = st.columns([1.25, 1.0])
    with card_l:
        with st.container(border=True):
            st.markdown(
                f'<div class="ofa-card-hdr">{html.escape(fe_bf_muni)} ({html.escape(focus_county)}) — Non-Refundable Permit Estimate</div>',
                unsafe_allow_html=True,
            )
            if pd.notna(focus_eval["Fee"]):
                _fv = float(focus_eval["Fee"])
                _eff = _fv / float(fe_bf_sqft)
                _m1, _m2 = st.columns(2)
                with _m1:
                    st.metric(
                        f"{fe_bf_sqft:,} ft² {struct_short}",
                        f"{_fmt_dollars(_fv)}{' (Est.)' if focus_eval['IsEstimate'] else ''}",
                    )
                    if ont_med_bf and ont_med_bf > 0:
                        _pct = round((_fv - ont_med_bf) / ont_med_bf * 100)
                        _rel = f"{abs(_pct)}% {'above' if _pct > 0 else 'below'} Ontario median (\\${round(ont_med_bf):,})" if _pct != 0 else f"Matches Ontario median (\\${round(ont_med_bf):,})"
                        st.caption(_rel)
                with _m2:
                    st.metric("Effective Rate", f"${_eff:.2f}/ft²")
                    st.caption(f"Tier: {_md_safe(focus_eval['Tier'])}")
                if focus_eval["IsEstimate"]:
                    st.caption(f"⚠️ *Estimated from valuation rate using your assumed \\${round(fe_bf_assumed):,}/ft² construction value.*")
            else:
                st.warning(
                    f"**{_md_safe(focus_eval['Tier'])}** — No direct per-sq.-ft. farm permit estimate for {fe_bf_muni}. "
                    + (
                        f"Charges by construction value (**{_md_safe(focus_eval['Model'])}**). Enable *'Estimate Valuation-Based schedules'* above to model an assumed per-sq.-ft. cost."
                        if "Valuation" in focus_eval["Tier"]
                        else f"Audit status: **{_md_safe(focus_eval['Status'])}** · Pricing model: **{_md_safe(focus_eval['Model'])}**."
                    )
                )

            st.markdown(
                f"**Pricing Model:** {_md_safe(focus_eval['Model'])}  \n"
                f"**Fee Year:** {focus_eval['Year']} · **Building Authority:** {_md_safe(focus_eval['Authority'])}  \n"
                f"**Source By-law:** "
                + (f"[{_md_safe(focus_eval['Bylaw'])}]({focus_eval['Link']})" if focus_eval["Link"] else _md_safe(focus_eval["Bylaw"]))
            )
            _fn = _clean_str(focus_raw.get("formula_notes"), "")
            if _fn:
                st.info(f"**Verified Schedule Formula:** {_md_safe(_fn)}")

    with card_r:
        with st.container(border=True):
            st.markdown(
                '<div class="ofa-card-hdr">Ancillary Farm Structures &amp; Refundable Deposits</div>',
                unsafe_allow_html=True,
            )
            st.caption("Separated from permit fees so refundable deposits and special structure rates stay transparent.")
            st.markdown(
                f"- **Silo / Grain Bin:** {_md_safe(focus_raw.get('silo_grain_bin_fee'))}  \n"
                f"- **Manure Storage:** {_md_safe(focus_raw.get('manure_storage_fee'))}  \n"
                f"- **Greenhouse / Tarp:** {_md_safe(focus_raw.get('greenhouse_tarp_fee'))}  \n"
                f"- **2024 OBC Group G Split:** {_md_safe(focus_raw.get('has_obc_group_g_split'))}"
            )
            if _dep_raw:
                st.warning(f"**Refundable Deposit / Surcharges (Separate from Permit Fee):** {_md_safe(_dep_raw)}")
            else:
                st.caption("No separate refundable building permit deposit noted in published fee schedule.")

            _alt_est = evaluate_bldg_fee(focus_raw, float(fe_bf_sqft), is_livestock=(not is_live), assumed_cost_per_sqft=fe_bf_assumed)
            if _alt_est is not None and pd.notna(focus_eval["Fee"]) and abs(float(_alt_est) - float(focus_eval["Fee"])) >= 1.0:
                _alt_lbl = "Equipment / Drive Shed" if is_live else "Livestock Barn"
                st.success(
                    f"**Separate Farm Tier:** This municipality charges **{_md_safe(_fmt_dollars(_alt_est))}** for a {fe_bf_sqft:,} ft² {_alt_lbl} "
                    f"(a **{_md_safe(_fmt_dollars(abs(float(_alt_est) - float(focus_eval['Fee']))))}** difference)."
                )

    # ── Peer Benchmark Bar Chart ──
    st.markdown("")
    if fe_bf_chart_scope == "Same County / District":
        peer_slice = bf_eval_df[bf_eval_df["County"] == focus_county].copy()
        scope_label = f"{focus_county} peers"
    elif fe_bf_chart_scope == "Provincial Lowest 15":
        _priced = bf_eval_df[bf_eval_df["Fee"].notna()].sort_values(["Fee", "Municipality"]).head(15)
        peer_slice = pd.concat([_priced, bf_eval_df[bf_eval_df["Municipality"] == fe_bf_muni]]).drop_duplicates("Municipality")
        scope_label = "Ontario's 15 lowest-fee municipalities"
    else:
        _priced = bf_eval_df[bf_eval_df["Fee"].notna() & (bf_eval_df["Municipality"] != "Moosonee")].sort_values(
            ["Fee", "Municipality"], ascending=[False, True]
        ).head(15)
        peer_slice = pd.concat([_priced, bf_eval_df[bf_eval_df["Municipality"] == fe_bf_muni]]).drop_duplicates("Municipality")
        scope_label = "Ontario's 15 highest-fee agricultural/town schedules"

    chart_ready = peer_slice[peer_slice["Fee"].notna()].copy()
    chart_ready["Detail"] = chart_ready["Model"] + " (" + chart_ready["Year"] + ")"
    non_priced_peers = peer_slice[peer_slice["Fee"].isna()].copy()

    if pd.notna(focus_eval["Fee"]) and not chart_ready.empty:
        _ranked = chart_ready.sort_values("Fee", ascending=False).reset_index(drop=True)
        _rank_pos = int(_ranked.index[_ranked["Municipality"] == fe_bf_muni][0]) + 1 if fe_bf_muni in _ranked["Municipality"].values else None
        _claim_title = (
            f"{fe_bf_muni} charges {_fmt_dollars(focus_eval['Fee'])} for a {fe_bf_sqft:,} ft² {struct_short}"
            + (f" (#{_rank_pos} highest of {len(_ranked)} in view)" if _rank_pos else "")
        )
    else:
        _claim_title = f"{fe_bf_sqft:,} ft² {struct_short} Permit Fees — {scope_label}"

    _sub = (
        f"Comparing {len(chart_ready)} priced municipalities ({scope_label}) · OFA Crimson = Selected"
        + (f" · Valuation rows estimated at ${round(fe_bf_assumed):,}/ft²" if fe_bf_assumed else " · Area / stepped / prescribed schedules only")
    )

    st.altair_chart(
        build_peer_bar_chart(
            chart_ready,
            focus_muni=fe_bf_muni,
            title=_claim_title,
            subtitle=_sub,
            median_val=ont_med_bf,
            median_label="Ontario Median",
        ),
        use_container_width=True,
    )

    if not non_priced_peers.empty:
        with st.expander(f"ℹ️ {len(non_priced_peers)} non-comparable / unposted peer(s) in {focus_county} (excluded from dollar chart to preserve scale integrity)", expanded=False):
            st.dataframe(
                non_priced_peers[["Municipality", "Tier", "Model", "Status", "Bylaw"]],
                use_container_width=True,
                hide_index=True,
            )

    _curve = build_bldg_scaling_chart(
        focus_raw,
        muni_name=fe_bf_muni,
        is_livestock=is_live,
        assumed_cost=fe_bf_assumed,
        highlight_sqft=fe_bf_sqft,
        show_obc_marker=True,
    )
    if _curve is not None:
        st.altair_chart(_curve, use_container_width=True)


# ═══════════════════════════════════════════════════════════════════════════
# VIEW 2: AGRICULTURAL DEVELOPMENT CHARGES (DC)
# ═══════════════════════════════════════════════════════════════════════════
elif active_view == VIEW_OPTIONS[1]:
    if "fe_dc_active_only" not in st.session_state:
        st.session_state["fe_dc_active_only"] = True

    _active_dc_total = int(dc_all["has_dc"].fillna("").astype(str).str.strip().str.lower().isin(["yes", "1"]).sum())
    dc_s1, dc_s2, dc_s3 = st.columns([1.15, 1.35, 1.5])
    with dc_s1:
        fe_dc_active_only = st.checkbox(
            f"Active DC By-laws only ({_active_dc_total})",
            key="fe_dc_active_only",
            help="Focuses the municipality picker on the 227 Ontario municipalities (209 Local/Single + 18 Upper Tiers) with active Development Charge by-laws. Uncheck to browse all 444 municipalities.",
        )
    dc_pool = dc_all.copy()
    if fe_dc_active_only:
        dc_pool = dc_pool[dc_pool["has_dc"].fillna("").astype(str).str.strip().str.lower().isin(["yes", "1"])]

    dc_areas = ["All Counties / Districts"] + sorted(dc_pool["geographic_area"].dropna().astype(str).unique().tolist())
    if "fe_dc_area" not in st.session_state or st.session_state["fe_dc_area"] not in dc_areas:
        st.session_state["fe_dc_area"] = dc_areas[0]
    with dc_s2:
        fe_dc_area = st.selectbox("Filter by County / District", dc_areas, key="fe_dc_area")
    if fe_dc_area != "All Counties / Districts":
        dc_pool = dc_pool[dc_pool["geographic_area"] == fe_dc_area]

    dc_muni_names = sorted(dc_pool["name"].dropna().astype(str).unique().tolist())
    if "fe_dc_muni" not in st.session_state or st.session_state["fe_dc_muni"] not in dc_muni_names:
        st.session_state["fe_dc_muni"] = "Leamington" if "Leamington" in dc_muni_names else (dc_muni_names[0] if dc_muni_names else "")
    with dc_s3:
        fe_dc_muni = st.selectbox("Select Municipality (Local, Single, or Upper Tier)", dc_muni_names, key="fe_dc_muni")

    # Controls Row 2: Building sub-type, Rural/Urban servicing, Upper-Tier stacking
    dc_c1, dc_c2, dc_c3 = st.columns([2.1, 1.15, 1.05])
    _DC_BTYPE_OPTS = {
        "🐄 Typical Farm": "typical_farm",
        "🌿 Greenhouse": "greenhouse",
        "🍃 Cannabis": "cannabis",
        "🛏️ Bunkhouse / SAWP": "bunkhouse",
    }
    with dc_c1:
        fe_dc_btype_lbl = st.radio(
            "Agricultural Building Sub-Type",
            list(_DC_BTYPE_OPTS.keys()),
            index=0,
            horizontal=True,
            key="fe_dc_btype_lbl",
        )
        fe_dc_btype = _DC_BTYPE_OPTS[fe_dc_btype_lbl]
    with dc_c2:
        fe_dc_sa_lbl = st.radio(
            "Servicing Area",
            ["Rural (Unserviced)", "Urban (Serviced)"],
            index=0,
            horizontal=True,
            key="fe_dc_sa_lbl",
        )
        fe_dc_sarea = "rural" if fe_dc_sa_lbl.startswith("Rural") else "urban"
    with dc_c3:
        st.markdown("<div style='height:22px;'></div>", unsafe_allow_html=True)
        fe_dc_stack = st.checkbox(
            "Stack Upper-Tier County / Region DC",
            value=True,
            key="fe_dc_stack",
            help="Adds the parent Upper-Tier County/Region DC on top of Lower-Tier municipal DCs (automatically skipped for Single-Tier cities and Upper-Tier standalone rows so nothing is double-counted).",
        )

    # Controls Row 3: Size presets + Chart Scope
    dc_p1, dc_p2 = st.columns([2.2, 1.2])
    with dc_p1:
        if fe_dc_btype == "greenhouse":
            _gh_pre = st.radio(
                "Greenhouse Size Scenario",
                ["0.5 Acre", "1 Acre (43,560 ft²)", "2 Acres", "5 Acres", "Custom"],
                index=1,
                horizontal=True,
                key="fe_dc_gh_pre",
            )
            _gh_map = {"0.5 Acre": 0.5, "1 Acre (43,560 ft²)": 1.0, "2 Acres": 2.0, "5 Acres": 5.0}
            if _gh_pre in _gh_map:
                _dc_acres = _gh_map[_gh_pre]
            else:
                _dc_acres = st.slider("Custom Greenhouse Area (acres)", 0.25, 10.0, 1.0, 0.25, key="fe_dc_gh_slider")
            fe_dc_sqft = _dc_acres * 43560.0
            fe_dc_beds = 0
            fe_dc_scen_txt = f"{_dc_acres:g} Acre ({round(fe_dc_sqft):,} ft²) Commercial Greenhouse"
            fe_dc_hi_val = _dc_acres
        elif fe_dc_btype == "bunkhouse":
            _bk_pre = st.radio(
                "Seasonal Worker Housing Scenario (scaled at 200 ft²/bed)",
                ["6 Beds", "10 Beds (Standard)", "20 Beds", "30 Beds", "Custom"],
                index=1,
                horizontal=True,
                key="fe_dc_bk_pre",
            )
            _bk_map = {"6 Beds": 6, "10 Beds (Standard)": 10, "20 Beds": 20, "30 Beds": 30}
            if _bk_pre in _bk_map:
                fe_dc_beds = _bk_map[_bk_pre]
            else:
                fe_dc_beds = st.slider("Custom Worker Capacity (beds)", 4, 40, 10, 2, key="fe_dc_bk_slider")
            fe_dc_sqft = float(fe_dc_beds * 200)
            fe_dc_scen_txt = f"{fe_dc_beds}-Bed ({round(fe_dc_sqft):,} ft²) Bunkhouse / SAWP Housing"
            fe_dc_hi_val = float(fe_dc_beds)
        elif fe_dc_btype == "cannabis":
            _cn_pre = st.radio(
                "Cannabis Facility Size Scenario",
                ["5,000 ft²", "10,000 ft² (Standard)", "25,000 ft²", "Custom"],
                index=1,
                horizontal=True,
                key="fe_dc_cn_pre",
            )
            _cn_map = {"5,000 ft²": 5000.0, "10,000 ft² (Standard)": 10000.0, "25,000 ft²": 25000.0}
            if _cn_pre in _cn_map:
                fe_dc_sqft = _cn_map[_cn_pre]
            else:
                fe_dc_sqft = float(st.slider("Custom Facility Area (sq. ft.)", 2000, 30000, 10000, 1000, key="fe_dc_cn_slider"))
            fe_dc_beds = 0
            fe_dc_scen_txt = f"{round(fe_dc_sqft):,} ft² Cannabis Production Facility"
            fe_dc_hi_val = fe_dc_sqft
        else:
            _tf_pre = st.radio(
                "Typical Farm Building Size Scenario",
                ["5,000 ft²", "10,000 ft² (Standard)", "20,000 ft²", "Custom"],
                index=1,
                horizontal=True,
                key="fe_dc_tf_pre",
            )
            _tf_map = {"5,000 ft²": 5000.0, "10,000 ft² (Standard)": 10000.0, "20,000 ft²": 20000.0}
            if _tf_pre in _tf_map:
                fe_dc_sqft = _tf_map[_tf_pre]
            else:
                fe_dc_sqft = float(st.slider("Custom Building Area (sq. ft.)", 2000, 30000, 10000, 1000, key="fe_dc_tf_slider"))
            fe_dc_beds = 0
            fe_dc_scen_txt = f"{round(fe_dc_sqft):,} ft² Typical Farm Building"
            fe_dc_hi_val = fe_dc_sqft

    dc_focus_raw = dc_all[dc_all["name"] == fe_dc_muni].iloc[0]
    dc_focus_status_tier = _clean_str(dc_focus_raw.get("municipal_status"), "Lower Tier")
    dc_focus_county = _clean_str(dc_focus_raw.get("geographic_area"))
    dc_is_upper_selected = dc_focus_status_tier == "Upper Tier"
    dc_ut_row = _parent_upper_dc_row(dc_focus_raw, fe_dc_stack)
    dc_ut_name = _pretty_upper_name(dc_ut_row.get("name")) if dc_ut_row is not None else ""

    with dc_p2:
        _scope_opts = (
            ["All 18 Active Upper-Tier Counties / Regions", "Provincial Top 15 Charged (Local/Single)"]
            if dc_is_upper_selected
            else [
                "Same County / District",
                "Provincial Top 15 Charged",
                "Ontario Greenhouse Belt",
                "Ontario Priced Bunkhouse / SAWP",
            ]
        )
        fe_dc_scope = st.selectbox("Peer Chart Scope", _scope_opts, index=0, key=f"fe_dc_scope_{dc_is_upper_selected}")

    # Evaluate selected municipality & Ontario Charged Median
    _dc_focus_eval = compute_stacked_dc(
        dc_focus_raw,
        dc_ut_row,
        fe_dc_btype,
        fe_dc_sarea,
        sqft=fe_dc_sqft,
        beds=fe_dc_beds,
    )
    _lt_val = _dc_focus_eval["lower_or_single"]
    _ut_val = _dc_focus_eval["upper_tier"]
    _tot_val, _tot_partial = _dc_effective_total(_dc_focus_eval)
    _silent_which = _dc_focus_eval.get("silent_tier_which")
    _focus_no_dc = str(dc_focus_raw.get("has_dc", "") or "").strip().lower() in ("no", "2")
    _ont_med_dc = _compute_dc_charged_median(fe_dc_btype, fe_dc_sarea, fe_dc_stack, sqft=fe_dc_sqft, beds=fe_dc_beds)

    _st_col_map = {
        "typical_farm": ("farm_bldg_dc_status", "exemption_wording"),
        "greenhouse": ("greenhouse_dc_status", "greenhouse_dc_notes"),
        "cannabis": ("cannabis_dc_status", "cannabis_dc_notes"),
        "bunkhouse": ("bunkhouse_dc_status", "bunkhouse_dc_notes"),
    }
    _cur_st_col, _cur_notes_col = _st_col_map[fe_dc_btype]
    _focus_sub_status = "No DC By-law" if _focus_no_dc else _clean_str(dc_focus_raw.get(_cur_st_col), "Silent / Confirm")
    _edc_str = _clean_str(dc_focus_raw.get("dc_edc_applicable"), "None noted")

    # ── Bottom Line Strip ──
    _sa_short = "rural unserviced" if fe_dc_sarea == "rural" else "urban serviced"
    if _tot_val is not None:
        if _tot_val <= 0 and not _tot_partial:
            _ut_zero_note = (
                f" (both {html.escape(fe_dc_muni)} and {html.escape(dc_ut_name)} are $0)"
                if (dc_ut_row is not None and dc_ut_name)
                else (" (no municipal DC by-law)" if _focus_no_dc else " (exempt under current DC by-law)")
            )
            _render_bottom_line(
                f"<b>{html.escape(fe_dc_muni)}</b> ({html.escape(dc_focus_county)}) charges <b>$0</b> in municipal Development Charges "
                f"for a {_sa_short} {html.escape(fe_dc_scen_txt)}{_ut_zero_note}."
            )
        elif _tot_partial:
            _known_clause = (
                f"<b>{_fmt_dollars(_lt_val)}</b> {html.escape(fe_dc_muni)} + <b>{html.escape(dc_ut_name)} Silent</b> (confirm Upper Tier)"
                if _silent_which == "upper"
                else f"<b>{html.escape(fe_dc_muni)} Silent</b> + <b>{_fmt_dollars(_ut_val)}</b> {html.escape(dc_ut_name)}"
            )
            _edc_clause = (
                f" Separate school-board EDCs also apply ({html.escape(_edc_str[:90])})."
                if _edc_str.lower().startswith("yes")
                else ""
            )
            _render_bottom_line(
                f"<b>{html.escape(fe_dc_muni)}</b> ({html.escape(dc_focus_county)}) imposes at least <b>{_fmt_dollars(_tot_val)}+</b> "
                f"({_known_clause}) for a {_sa_short} {html.escape(fe_dc_scen_txt)}.{_edc_clause}"
            )
        else:
            _stack_clause = ""
            if dc_ut_row is not None and dc_ut_name and (_ut_val or 0) > 0:
                _stack_clause = f" (<b>{_fmt_dollars(_lt_val)}</b> {html.escape(fe_dc_muni)} + <b>{_fmt_dollars(_ut_val)}</b> {html.escape(dc_ut_name)})"
            elif dc_is_upper_selected:
                _stack_clause = " (Upper-Tier standalone — member Lower-Tier DCs may stack separately)"
            _med_clause = ""
            if _ont_med_dc and _ont_med_dc > 0 and not dc_is_upper_selected:
                _pct = round((_tot_val - _ont_med_dc) / _ont_med_dc * 100)
                _med_clause = (
                    f" — <b>{abs(_pct)}% {'above' if _pct > 0 else 'below'}</b> the Ontario charged median ({_fmt_dollars(_ont_med_dc)})"
                    if _pct != 0 else f" — <b>equal to</b> the Ontario charged median ({_fmt_dollars(_ont_med_dc)})"
                )
            _edc_clause = (
                f" Separate school-board EDCs also apply ({html.escape(_edc_str[:90])})."
                if _edc_str.lower().startswith("yes")
                else ""
            )
            _render_bottom_line(
                f"<b>{html.escape(fe_dc_muni)}</b> ({html.escape(dc_focus_county)}) imposes <b>{_fmt_dollars(_tot_val)}</b>"
                f"{_stack_clause} for a {_sa_short} {html.escape(fe_dc_scen_txt)}{_med_clause}.{_edc_clause}"
            )
    else:
        _render_bottom_line(
            f"<b>{html.escape(fe_dc_muni)}</b> ({html.escape(dc_focus_county)}) is marked <b>{html.escape(_focus_sub_status)}</b> "
            f"for {html.escape(fe_dc_scen_txt)} ({_sa_short}) — silent or ambiguous by-law wording is never assumed to be $0; confirm directly with the municipal clerk."
        )

    # ── 4-Tile Cross-Sub-Type Snapshot (keeps incompatible dollar scales off a single axis) ──
    _tile_specs = [
        ("typical_farm", "🐄 Typical Farm (10k ft²)", 10000.0, 0, "farm_bldg_dc_status"),
        ("greenhouse", "🌿 Greenhouse (1 Acre)", 43560.0, 0, "greenhouse_dc_status"),
        ("cannabis", "🍃 Cannabis (10k ft²)", 10000.0, 0, "cannabis_dc_status"),
        ("bunkhouse", "🛏️ Bunkhouse (10 Beds)", 2000.0, 10, "bunkhouse_dc_status"),
    ]
    _tcols = st.columns(4)
    for _tc, (_tk, _tlbl, _tsq, _tbd, _tstcol) in zip(_tcols, _tile_specs):
        _tres = compute_stacked_dc(dc_focus_raw, dc_ut_row, _tk, fe_dc_sarea, sqft=_tsq, beds=_tbd)
        _tv, _tpart = _dc_effective_total(_tres)
        if _tv is None:
            _tdisp = "Silent"
        elif _tv <= 0 and not _tpart:
            _tdisp = "$0"
        else:
            _tdisp = f"{_fmt_dollars(_tv)}+" if _tpart else _fmt_dollars(_tv)
        _traw = _clean_str(dc_focus_raw.get(_tstcol), "Silent / Confirm")
        with _tc:
            with st.container(border=True):
                st.metric(_tlbl + (" ★" if _tk == fe_dc_btype else ""), _tdisp)
                if _tpart:
                    _sub_cap = (
                        f"LT \\${round(_tres['lower_or_single'] or 0):,} · UT silent"
                        if _tres.get("silent_tier_which") == "upper"
                        else f"UT \\${round(_tres['upper_tier'] or 0):,} · LT silent"
                    )
                elif dc_ut_row is not None and (_tres["upper_tier"] or 0) > 0 and _tv is not None:
                    _sub_cap = f"LT \\${round(_tres['lower_or_single'] or 0):,} + UT \\${round(_tres['upper_tier'] or 0):,}"
                else:
                    _sub_cap = _md_safe(_dc_short_status(_tv, _traw, no_dc=_focus_no_dc))
                st.caption(_sub_cap)

    # ── Two-Card Legal & Rate Receipt ──
    dc_l, dc_r = st.columns([1.22, 1.0])
    with dc_l:
        with st.container(border=True):
            st.markdown(
                f'<div class="ofa-card-hdr">{html.escape(fe_dc_muni)} ({html.escape(dc_focus_county)}) — Development Charge Receipt</div>',
                unsafe_allow_html=True,
            )
            if _tot_val is not None:
                if dc_ut_row is not None and dc_ut_name:
                    _m1, _m2, _m3 = st.columns(3)
                    with _m1:
                        st.metric(
                            fe_dc_muni,
                            "Silent" if _lt_val is None else ("$0" if _lt_val <= 0 else _fmt_dollars(_lt_val)),
                        )
                        st.caption("Lower-Tier Standalone")
                    with _m2:
                        st.metric(
                            dc_ut_name,
                            "Silent" if _ut_val is None else ("$0" if _ut_val <= 0 else _fmt_dollars(_ut_val)),
                        )
                        st.caption("Confirm w/ Upper Tier" if _ut_val is None else "Parent Upper-Tier")
                    with _m3:
                        _comb_val = "$0" if (_tot_val <= 0 and not _tot_partial) else f"{_fmt_dollars(_tot_val)}{'+' if _tot_partial else ''}"
                        st.metric("Combined Total", _comb_val)
                        if _tot_partial:
                            st.caption("Known min. (other tier silent)")
                        elif _tot_val > 0:
                            _unit_rate = (
                                f"${_tot_val / fe_dc_beds:,.0f}/bed" if fe_dc_btype == "bunkhouse" and fe_dc_beds > 0
                                else f"${_tot_val / fe_dc_sqft:.2f}/ft²"
                            )
                            st.caption(f"Eff. rate: {_md_safe(_unit_rate)}")
                        else:
                            st.caption("Both tiers exempt / no DC")
                else:
                    _m1, _m2 = st.columns(2)
                    with _m1:
                        st.metric(fe_dc_scen_txt, "$0" if _tot_val <= 0 else _fmt_dollars(_tot_val))
                        st.caption(f"{dc_focus_status_tier} · {fe_dc_sa_lbl}")
                    with _m2:
                        if _tot_val > 0:
                            _unit_rate = (
                                f"${_tot_val / fe_dc_beds:,.0f}/bed" if fe_dc_btype == "bunkhouse" and fe_dc_beds > 0
                                else f"${_tot_val / fe_dc_sqft:.2f}/ft²"
                            )
                            st.metric("Effective Rate", _unit_rate)
                        else:
                            st.metric("Effective Rate", "$0.00")
                        st.caption(_md_safe(_dc_short_status(_tot_val, _focus_sub_status, no_dc=_focus_no_dc)))
            else:
                st.warning(
                    f"**{_md_safe(_focus_sub_status)}** — No numeric rate published for {fe_dc_muni} "
                    f"(or its parent Upper Tier) on this sub-type. Silent / ambiguous schedules are never assumed to be \\$0."
                )

            _dc_yr = _fmt_year(dc_focus_raw.get("dc_rate_year"))
            _dc_eff = _clean_str(dc_focus_raw.get("dc_rate_effective_date"))
            _dc_ver = _clean_str(dc_focus_raw.get("dc_rate_verification_status"))
            _dc_basis = _clean_str(dc_focus_raw.get("dc_rate_service_area_basis"))
            _dc_bylaw = _clean_str(dc_focus_raw.get("bylaw_name"))
            _dc_bylaw_url = _valid_url(dc_focus_raw.get("bylaw_link"))
            _dc_pamph = _clean_str(dc_focus_raw.get("dc_rate_pamphlet_name"))
            _dc_pamph_url = _valid_url(dc_focus_raw.get("dc_rate_pamphlet_link"))

            _meta_lines = [
                f"**Audit Status:** {_md_safe(_dc_ver)} · **Rate Year:** {_dc_yr} (Eff. {_md_safe(_dc_eff)})",
                f"**Municipal Tier:** {dc_focus_status_tier} · **Service Area Basis:** {_md_safe(_dc_basis)}",
                "**Source DC By-law:** " + (f"[{_md_safe(_dc_bylaw)}]({_dc_bylaw_url})" if _dc_bylaw_url else _md_safe(_dc_bylaw)),
            ]
            if _dc_pamph != "—":
                _meta_lines.append(
                    "**Indexed Rate Pamphlet:** " + (f"[{_md_safe(_dc_pamph)}]({_dc_pamph_url})" if _dc_pamph_url else _md_safe(_dc_pamph))
                )
            if dc_ut_row is not None and dc_ut_name:
                _ut_p_nm = _clean_str(dc_ut_row.get("dc_rate_pamphlet_name") or dc_ut_row.get("bylaw_name"))
                _ut_p_url = _valid_url(dc_ut_row.get("dc_rate_pamphlet_link")) or _valid_url(dc_ut_row.get("bylaw_link"))
                _meta_lines.append(
                    f"**Parent Upper-Tier Source ({_md_safe(dc_ut_name)}):** "
                    + (f"[{_md_safe(_ut_p_nm)}]({_ut_p_url})" if _ut_p_url else _md_safe(_ut_p_nm))
                )
            st.markdown("  \n".join(_meta_lines))

            _dc_fn = _clean_str(dc_focus_raw.get("dc_rate_formula_notes"), "")
            if _dc_fn:
                st.info(f"**Verified Rate & Indexing Notes:** {_md_safe(_dc_fn)}")

    with dc_r:
        with st.container(border=True):
            st.markdown(
                f'<div class="ofa-card-hdr">Sub-Type Legal Rules, Carve-Outs &amp; Education DCs</div>',
                unsafe_allow_html=True,
            )
            st.markdown(f"**Selected Sub-Type Treatment ({fe_dc_btype_lbl}):** {_md_safe(_focus_sub_status)}")
            _sub_note_txt = _clean_str(dc_focus_raw.get(_cur_notes_col), "")
            if _sub_note_txt:
                st.info(f"**Primary-Source Wording / Basis:** {_md_safe(_sub_note_txt)}")
            elif _focus_no_dc:
                st.success(f"{fe_dc_muni} does not levy a municipal Development Charge by-law.")

            if dc_ut_row is not None and dc_ut_name:
                _ut_has = str(dc_ut_row.get("has_dc", "") or "").strip().lower() in ("yes", "1")
                _ut_st_txt = _clean_str(dc_ut_row.get(_cur_st_col), "Exempt / Silent") if _ut_has else "No Upper-Tier DC By-law"
                st.markdown(f"**Parent Upper Tier ({_md_safe(dc_ut_name)}) Treatment:** {_md_safe(_ut_st_txt)}")

            if _edc_str.lower().startswith("yes"):
                st.warning(f"**Education Development Charges (Separate School Board Levy):** {_md_safe(_edc_str)}")
            else:
                st.caption(f"**Education Development Charges (EDCs):** {_md_safe(_edc_str)}")

            st.markdown(
                "**All 4 Sub-Type Treatments:**  \n"
                f"- **Typical Farm:** {_md_safe(dc_focus_raw.get('farm_bldg_dc_status'), 'No DC' if _focus_no_dc else '—')}  \n"
                f"- **Greenhouse:** {_md_safe(dc_focus_raw.get('greenhouse_dc_status'), 'No DC' if _focus_no_dc else '—')}  \n"
                f"- **Cannabis:** {_md_safe(dc_focus_raw.get('cannabis_dc_status'), 'No DC' if _focus_no_dc else '—')}  \n"
                f"- **Bunkhouse / SAWP:** {_md_safe(dc_focus_raw.get('bunkhouse_dc_status'), 'No DC' if _focus_no_dc else '—')}"
            )

    # ── Stacked Peer Benchmark Bar Chart ──
    st.markdown("")
    _peer_base = (
        dc_all[(dc_all["municipal_status"].fillna("") == "Upper Tier") & (dc_all["has_dc"].fillna("").astype(str).str.strip().str.lower().isin(["yes", "1"]))].copy()
        if (dc_is_upper_selected and fe_dc_scope.startswith("All 18"))
        else dc_local.copy()
    )

    _dc_eval_rows = []
    for _, _r in _peer_base.iterrows():
        _ut_p = _parent_upper_dc_row(_r, fe_dc_stack)
        _ev = compute_stacked_dc(_r, _ut_p, fe_dc_btype, fe_dc_sarea, sqft=fe_dc_sqft, beds=fe_dc_beds)
        _eff_tot, _is_part = _dc_effective_total(_ev)
        _r_no_dc = str(_r.get("has_dc", "") or "").strip().lower() in ("no", "2")
        _dc_eval_rows.append(
            {
                "Municipality": str(_r["name"]),
                "County": _clean_str(_r.get("geographic_area")),
                "LowerFee": _ev["lower_or_single"],
                "UpperFee": _ev["upper_tier"] if _ut_p is not None else 0.0,
                "TotalFee": _eff_tot,
                "PartialSilent": _is_part,
                "SilentWhich": _ev.get("silent_tier_which") or "",
                "UpperName": _pretty_upper_name(_ut_p.get("name")) if _ut_p is not None else "—",
                "Status": "No DC By-law" if _r_no_dc else _clean_str(_r.get(_cur_st_col), "Silent / Confirm"),
                "Year": _fmt_year(_r.get("dc_rate_year")),
                "Detail": ("No DC By-law" if _r_no_dc else _clean_str(_r.get(_cur_st_col), "Silent / Confirm")),
                "Bylaw": _clean_str(_r.get("dc_rate_pamphlet_name") or _r.get("bylaw_name")),
            }
        )
    dc_eval_df = pd.DataFrame(_dc_eval_rows)

    if dc_is_upper_selected and fe_dc_scope.startswith("All 18"):
        dc_peer_slice = dc_eval_df.copy()
        dc_scope_lbl = "all 18 active Upper-Tier Counties & Regions"
    elif fe_dc_scope == "Same County / District":
        dc_peer_slice = dc_eval_df[dc_eval_df["County"] == dc_focus_county].copy()
        dc_scope_lbl = f"{dc_focus_county} peers"
    elif fe_dc_scope == "Ontario Greenhouse Belt":
        _gh_belt = {"Essex", "Niagara", "Chatham-Kent", "Haldimand", "Norfolk", "Elgin", "Brant"}
        dc_peer_slice = dc_eval_df[
            dc_eval_df["County"].isin(_gh_belt) & (dc_eval_df["TotalFee"].notna()) & (dc_eval_df["Status"] != "No DC By-law")
        ].sort_values(["TotalFee", "Municipality"], ascending=[False, True]).head(18)
        dc_peer_slice = pd.concat([dc_peer_slice, dc_eval_df[dc_eval_df["Municipality"] == fe_dc_muni]]).drop_duplicates("Municipality")
        dc_scope_lbl = "Ontario greenhouse-belt DC municipalities"
    elif fe_dc_scope == "Ontario Priced Bunkhouse / SAWP":
        _bk_priced = dc_eval_df[dc_eval_df["TotalFee"].notna() & (dc_eval_df["TotalFee"] > 0)].sort_values(
            ["TotalFee", "Municipality"], ascending=[False, True]
        ).head(18)
        dc_peer_slice = pd.concat([_bk_priced, dc_eval_df[dc_eval_df["Municipality"] == fe_dc_muni]]).drop_duplicates("Municipality")
        dc_scope_lbl = "Ontario municipalities charging bunkhouse / SAWP DCs"
    else:
        _top_dc = dc_eval_df[dc_eval_df["TotalFee"].notna() & (dc_eval_df["TotalFee"] > 0)].sort_values(
            ["TotalFee", "Municipality"], ascending=[False, True]
        ).head(15)
        dc_peer_slice = pd.concat([_top_dc, dc_eval_df[dc_eval_df["Municipality"] == fe_dc_muni]]).drop_duplicates("Municipality")
        dc_scope_lbl = "Ontario's 15 highest charged municipal DC schedules"

    dc_chart_df = dc_peer_slice[dc_peer_slice["TotalFee"].notna()].copy()
    dc_silent_peers = dc_peer_slice[dc_peer_slice["TotalFee"].isna()].copy()

    if _tot_val is not None and not dc_chart_df.empty:
        _ranked_dc = dc_chart_df.sort_values("TotalFee", ascending=False).reset_index(drop=True)
        _rk_dc = int(_ranked_dc.index[_ranked_dc["Municipality"] == fe_dc_muni][0]) + 1 if fe_dc_muni in _ranked_dc["Municipality"].values else None
        _val_str = "$0 (Exempt)" if (_tot_val <= 0 and not _tot_partial) else f"{_fmt_dollars(_tot_val)}{'+' if _tot_partial else ''}"
        _dc_title = (
            f"{fe_dc_muni} imposes {_val_str} for a {fe_dc_scen_txt}"
            + (f" (#{_rk_dc} of {len(_ranked_dc)} in view)" if _rk_dc and _tot_val > 0 else "")
        )
    else:
        _dc_title = f"Agricultural Development Charges ({fe_dc_scen_txt}) — {dc_scope_lbl}"

    _has_ut_bars = bool(fe_dc_stack and not dc_chart_df.empty and (dc_chart_df["UpperFee"].fillna(0) > 0).any())
    _any_plus = bool(not dc_chart_df.empty and dc_chart_df["PartialSilent"].any())
    _dc_sub = (
        f"Comparing {len(dc_chart_df)} verified peers ({dc_scope_lbl}; {fe_dc_sa_lbl})"
        + (" · Stacked: Lower/Single (Crimson/Gray) + Upper-Tier (Gold/Slate)" if _has_ut_bars else " · OFA Crimson = Selected · Green = $0 Exempt")
        + (" · '+' = one tier silent" if _any_plus else "")
    )

    st.altair_chart(
        build_dc_stacked_peer_chart(
            dc_chart_df,
            focus_muni=fe_dc_muni,
            title=_dc_title,
            subtitle=_dc_sub,
            median_val=None if dc_is_upper_selected else _ont_med_dc,
            median_label="Ontario Charged Median",
            stacked=fe_dc_stack,
        ),
        use_container_width=True,
    )

    if not dc_silent_peers.empty:
        with st.expander(
            f"ℹ️ {len(dc_silent_peers)} silent / ambiguous / unpublished peer(s) excluded from dollar chart (never coerced to \\$0)",
            expanded=False,
        ):
            st.dataframe(
                dc_silent_peers[["Municipality", "County", "Status", "Year", "Bylaw"]],
                use_container_width=True,
                hide_index=True,
            )

    _dc_curve = build_dc_scaling_chart(
        dc_focus_raw,
        dc_ut_row,
        muni_name=fe_dc_muni,
        upper_name=dc_ut_name,
        building_type=fe_dc_btype,
        service_area=fe_dc_sarea,
        stacked=fe_dc_stack,
        highlight_val=fe_dc_hi_val,
    )
    if _dc_curve is not None:
        st.markdown("<div style='height:12px;'></div>", unsafe_allow_html=True)
        st.altair_chart(_dc_curve, use_container_width=True)


# ═══════════════════════════════════════════════════════════════════════════
# VIEW 3: SITE ALTERATION & EXCESS SOIL FEES (SITE_ALT)
# ═══════════════════════════════════════════════════════════════════════════
elif active_view == VIEW_OPTIONS[2]:
    if "fe_sa_active_only" not in st.session_state:
        st.session_state["fe_sa_active_only"] = True

    sa_s1, sa_s2, sa_s3 = st.columns([1.2, 1.5, 1.3])
    with sa_s1:
        fe_sa_active_only = st.checkbox(
            "Active Site Alteration Bylaws only (132)",
            key="fe_sa_active_only",
            help="Focuses the municipality picker on the 132 municipalities that regulate site alteration / fill. Uncheck to browse all 414 local/single-tier municipalities.",
        )
    sa_pool = sa_local.copy()
    if fe_sa_active_only:
        sa_pool = sa_pool[
            ~sa_pool["fee_verification_status"].fillna("").astype(str).str.contains("No Bylaw", case=False, na=False)
            & sa_pool["fee_verification_status"].fillna("").astype(str).ne("")
        ]

    sa_areas = ["All Counties / Districts"] + sorted(sa_pool["geographic_area"].dropna().astype(str).unique().tolist())
    if "fe_sa_area" not in st.session_state or st.session_state["fe_sa_area"] not in sa_areas:
        st.session_state["fe_sa_area"] = sa_areas[0]
    with sa_s2:
        fe_sa_area = st.selectbox("Filter by County / District", sa_areas, key="fe_sa_area")
    if fe_sa_area != "All Counties / Districts":
        sa_pool = sa_pool[sa_pool["geographic_area"] == fe_sa_area]

    sa_muni_names = sorted(sa_pool["name"].dropna().astype(str).unique().tolist())
    if "fe_sa_muni" not in st.session_state or st.session_state["fe_sa_muni"] not in sa_muni_names:
        st.session_state["fe_sa_muni"] = "Clarington" if "Clarington" in sa_muni_names else (sa_muni_names[0] if sa_muni_names else "")

    with sa_s3:
        fe_sa_muni = st.selectbox("Select Municipality", sa_muni_names, key="fe_sa_muni")

    sv_c1, sv_c2 = st.columns([2.2, 1.2])
    with sv_c1:
        fe_sa_preset = st.radio(
            "Clean Topsoil / Fill Import Scenario (10 m³ ≈ 1 Tri-Axle Load)",
            ["500 m³ (~50 loads)", "5,000 m³ (~500 loads)", "15,000 m³ (~1,500 loads)", "Custom Volume"],
            index=2,
            horizontal=True,
            key="fe_sa_preset",
        )
        _sa_pmap = {"500 m³ (~50 loads)": 500, "5,000 m³ (~500 loads)": 5000, "15,000 m³ (~1,500 loads)": 15000}
        if fe_sa_preset in _sa_pmap:
            fe_sa_vol = _sa_pmap[fe_sa_preset]
        else:
            fe_sa_vol = st.slider(
                "Custom Imported Volume (m³)",
                min_value=500,
                max_value=25000,
                value=15000,
                step=500,
                key="fe_sa_vol_slider",
            )
    with sv_c2:
        fe_sa_scope = st.selectbox(
            "Peer Chart Scope",
            ["Same County / District", "Provincial Top 15 Paid Schedules", "Provincial All Volumetric (Per-m³)"],
            index=0,
            key="fe_sa_scope",
        )

    _sa_eval_rows = []
    for _, _r in sa_local.iterrows():
        _v = evaluate_site_alt_fee(_r, float(fe_sa_vol))
        _fvs = _clean_str(_r.get("fee_verification_status"), "")
        _ags = _clean_str(_r.get("ag_import_fee_status"), "")
        _pm = _clean_str(_r.get("fee_pricing_model"), "")
        _, _tier = site_alt_fee_tier_rgba(_v, float(fe_sa_vol), _fvs, _ags, _pm)
        _sa_eval_rows.append({
            "Municipality": str(_r["name"]),
            "County": _clean_str(_r.get("geographic_area")),
            "Fee": _v,
            "Tier": _tier,
            "Exemption": _clean_str(_r.get("exemption_status")),
            "NFPScope": _clean_str(_r.get("nfp_exemption_scope")),
            "AgFeeStatus": _ags or "—",
            "Model": _pm or "—",
            "PerM3": pd.to_numeric(_r.get("per_m3_rate"), errors="coerce"),
            "CapM3": pd.to_numeric(_r.get("ag_exempt_volume_cap_m3"), errors="coerce"),
            "OutBan": _clean_str(_r.get("out_of_muni_fill_ban")),
            "Status": _fvs or "Pending",
            "Year": _fmt_year(_r.get("fee_year")),
            "Bylaw": _clean_str(_r.get("fees_bylaw_name") or _r.get("bylaw_name")),
            "Link": _valid_url(_r.get("fees_bylaw_link")) or _valid_url(_r.get("bylaw_link")),
        })
    sa_eval_df = pd.DataFrame(_sa_eval_rows)

    ont_med_sa_paid, ont_med_sa_vol = _compute_sa_medians(int(fe_sa_vol))

    sa_focus_raw = sa_local[sa_local["name"] == fe_sa_muni].iloc[0]
    sa_focus_ev = sa_eval_df[sa_eval_df["Municipality"] == fe_sa_muni].iloc[0]
    sa_focus_county = sa_focus_ev["County"]

    # Bottom Line takeaway strip
    _ban_flag = str(sa_focus_ev["OutBan"]).strip().lower() in ("yes", "restricted")
    _ban_phrase = f" <b>Restricts/bans out-of-municipality fill ({html.escape(sa_focus_ev['OutBan'])})</b>." if _ban_flag else ""
    if pd.notna(sa_focus_ev["Fee"]):
        _sv = float(sa_focus_ev["Fee"])
        if _sv <= 0:
            _render_bottom_line(
                f"<b>{html.escape(fe_sa_muni)}</b> ({html.escape(sa_focus_county)}) charges <b>$0</b> ({html.escape(sa_focus_ev['AgFeeStatus'])}) "
                f"for {fe_sa_vol:,} m³ (~{fe_sa_vol // 10:,} loads) of clean farm topsoil import (Exemption: <b>{html.escape(sa_focus_ev['Exemption'])}</b>).{_ban_phrase}"
            )
        else:
            _render_bottom_line(
                f"<b>{html.escape(fe_sa_muni)}</b> ({html.escape(sa_focus_county)}) has a <b>{html.escape(sa_focus_ev['Exemption'])}</b> farm exemption "
                f"and charges an estimated <b>{_fmt_dollars(_sv)}</b> (${_sv / fe_sa_vol:.2f}/m³) non-refundable permit fee at {fe_sa_vol:,} m³ "
                f"(~{fe_sa_vol // 10:,} loads) — separate from refundable securities &amp; peer-review retainers.{_ban_phrase}"
            )
    else:
        _render_bottom_line(
            f"<b>{html.escape(fe_sa_muni)}</b> ({html.escape(sa_focus_county)}) uses <b>{html.escape(sa_focus_ev['Tier'])}</b> "
            f"({html.escape(sa_focus_ev['Model'])}; Exemption: <b>{html.escape(sa_focus_ev['Exemption'])}</b>).{_ban_phrase}"
        )

    # ── Dual-Dimension Policy Rule Strip (clean captions, zero misleading up-arrows) ──
    _ag_short_map = {
        "Standard Commercial Rate": "Commercial Rate",
        "Exempt up to Volume Cap": "Volume-Capped",
        "Waiver Available ($0 App Fee)": "$0 App Waiver",
    }
    _ag_display = _ag_short_map.get(sa_focus_ev["AgFeeStatus"], sa_focus_ev["AgFeeStatus"])
    b1, b2, b3, b4 = st.columns([1.15, 1.25, 1.0, 1.0])
    with b1:
        st.metric("Farm Exemption", sa_focus_ev["Exemption"])
        st.caption(_md_safe(sa_focus_ev["NFPScope"]))
    with b2:
        st.metric("Ag Import Fee Tier", _ag_display)
        st.caption(f"Fee Year: {sa_focus_ev['Year']}")
    with b3:
        st.metric("Ag Exempt Cap", f"{round(float(sa_focus_ev['CapM3'])):,} m³" if pd.notna(sa_focus_ev["CapM3"]) else "None / N/A")
        st.caption(f"≈ {round(float(sa_focus_ev['CapM3'])) // 10:,} loads" if pd.notna(sa_focus_ev["CapM3"]) else "See by-law wording")
    with b4:
        st.metric("Out-of-Muni Fill Ban", sa_focus_ev["OutBan"])
        st.caption(f"O. Reg. 406/19: {_md_safe(sa_focus_raw.get('excess_soil_reg_406_19'))}")

    if _ban_flag:
        st.error(
            f"🚫 **Out-of-Municipality Fill Restriction ({sa_focus_ev['OutBan']}):** "
            f"{fe_sa_muni}'s Site Alteration by-law restricts or prohibits importing excess soil originating outside municipal boundaries."
        )

    # ── Two-Stack Cost Card ──
    sc_l, sc_r = st.columns([1.2, 1.0])
    with sc_l:
        with st.container(border=True):
            st.markdown(
                f'<div class="ofa-card-hdr">Stack A — Non-Refundable Permit Fee ({fe_sa_vol:,} m³ / ~{fe_sa_vol // 10:,} loads)</div>',
                unsafe_allow_html=True,
            )
            if pd.notna(sa_focus_ev["Fee"]):
                _sv = float(sa_focus_ev["Fee"])
                if _sv <= 0:
                    st.success(f"**\\$0** — {_md_safe(sa_focus_ev['AgFeeStatus'])} at {fe_sa_vol:,} m³.")
                else:
                    _eff_m3 = _sv / float(fe_sa_vol)
                    _sm1, _sm2 = st.columns(2)
                    with _sm1:
                        st.metric(f"Est. Permit Fee ({fe_sa_vol:,} m³)", _fmt_dollars(_sv))
                        st.caption(_md_safe(sa_focus_ev["Tier"]))
                    with _sm2:
                        st.metric("Effective Volumetric Rate", f"${_eff_m3:.2f}/m³")
                        st.caption(_md_safe(sa_focus_ev["Model"]))
            else:
                st.warning(
                    f"**{_md_safe(sa_focus_ev['Tier'])}** — {fe_sa_muni} uses **{_md_safe(sa_focus_ev['Model'])}** "
                    f"(Audit status: {_md_safe(sa_focus_ev['Status'])}). Incompatible scales (e.g., per-hectare or cost-recovery) are never coerced to \\$0."
                )

            st.markdown(
                f"**Source Fees By-law:** "
                + (f"[{_md_safe(sa_focus_ev['Bylaw'])}]({sa_focus_ev['Link']})" if sa_focus_ev["Link"] else _md_safe(sa_focus_ev["Bylaw"]))
            )
            _sfn = _clean_str(sa_focus_raw.get("fee_formula_notes"), "")
            if _sfn:
                st.info(f"**Verified Schedule Formula:** {_md_safe(_sfn)}")

    with sc_r:
        with st.container(border=True):
            st.markdown(
                '<div class="ofa-card-hdr">Stack B — Refundable Securities, Road Deposits &amp; Peer Review</div>',
                unsafe_allow_html=True,
            )
            st.caption(
                "Often larger than the permit fee itself — tracked separately so refundable securities "
                "and third-party engineering retainers are never hidden or blended into permit fees."
            )
            st.warning(f"**Security / Road Damage Deposit:** {_md_safe(sa_focus_raw.get('security_deposit_terms'))}")
            st.info(f"**Peer Review & Soil Testing Cost Recovery:** {_md_safe(sa_focus_raw.get('peer_review_recovery'))}")
            st.markdown(
                f"- **Drainage Act Exempt:** {_md_safe(sa_focus_raw.get('drainage_act_exempt'))}  \n"
                f"- **Fill Definition Captures Ag Materials:** {_md_safe(sa_focus_raw.get('fill_captures_ag_materials'))}"
            )

    # ── Site Alteration Peer Chart (apples-to-apples Volumetric Median when volumetric schedules are shown) ──
    st.markdown("")
    _sa_active_all = sa_eval_df[sa_eval_df["Tier"] != "No Site Alt. By-law"].copy()
    if fe_sa_scope == "Same County / District":
        sa_peer_slice = _sa_active_all[_sa_active_all["County"] == sa_focus_county].copy()
        sa_scope_lbl = f"active Site Alteration bylaws in {sa_focus_county}"
    elif fe_sa_scope == "Provincial Top 15 Paid Schedules":
        _top = _sa_active_all[_sa_active_all["Fee"].notna() & (_sa_active_all["Fee"] > 0)].sort_values(
            ["Fee", "Municipality"], ascending=[False, True]
        ).head(15)
        sa_peer_slice = pd.concat([_top, sa_eval_df[sa_eval_df["Municipality"] == fe_sa_muni]]).drop_duplicates("Municipality")
        sa_scope_lbl = "Ontario's 15 highest paid excess-soil fee schedules"
    else:
        _vol_all = _sa_active_all[_sa_active_all["PerM3"].notna() & (_sa_active_all["PerM3"] > 0)].copy()
        sa_peer_slice = pd.concat([_vol_all, sa_eval_df[sa_eval_df["Municipality"] == fe_sa_muni]]).drop_duplicates("Municipality")
        sa_scope_lbl = "all Ontario per-m³ volumetric schedules"

    sa_chart_df = sa_peer_slice[sa_peer_slice["Fee"].notna()].copy()
    sa_chart_df["Detail"] = sa_chart_df["AgFeeStatus"] + " · " + sa_chart_df["Model"]
    sa_non_vol = sa_peer_slice[sa_peer_slice["Fee"].isna()].copy()

    # Choose apples-to-apples benchmark line: if chart contains volumetric per-m³ schedules, use ON Volumetric Median
    _has_volumetric = bool((sa_chart_df["PerM3"].notna() & (sa_chart_df["PerM3"] > 0)).any())
    if _has_volumetric and ont_med_sa_vol is not None:
        _sa_ref_val, _sa_ref_lbl = ont_med_sa_vol, "Ontario Volumetric Median"
    else:
        _sa_ref_val, _sa_ref_lbl = ont_med_sa_paid, "Ontario Paid Median"

    if pd.notna(sa_focus_ev["Fee"]):
        _sa_title = f"{fe_sa_muni} estimates {'$0 (Exempt)' if float(sa_focus_ev['Fee']) <= 0 else _fmt_dollars(sa_focus_ev['Fee'])} for {fe_sa_vol:,} m³ clean topsoil import"
    else:
        _sa_title = f"Excess Soil Permit Fees ({fe_sa_vol:,} m³ / ~{fe_sa_vol // 10:,} loads) — {sa_scope_lbl}"

    st.altair_chart(
        build_peer_bar_chart(
            sa_chart_df,
            focus_muni=fe_sa_muni,
            title=_sa_title,
            subtitle=f"Non-refundable permit fee only across {len(sa_chart_df)} comparable peers ({sa_scope_lbl}) · Green = $0 Farm Exempt",
            median_val=_sa_ref_val,
            median_label=_sa_ref_lbl,
            exempt_zero_highlight=True,
        ),
        use_container_width=True,
    )

    if not sa_non_vol.empty:
        with st.expander(f"ℹ️ {len(sa_non_vol)} non-volumetric / unposted peer(s) (Area-based $/ha, Cost Recovery, or Offline)", expanded=False):
            st.dataframe(
                sa_non_vol[["Municipality", "Exemption", "Tier", "Model", "OutBan", "Bylaw"]],
                use_container_width=True,
                hide_index=True,
            )

    _sa_curve = build_site_alt_scaling_chart(
        sa_focus_raw,
        muni_name=fe_sa_muni,
        highlight_vol=fe_sa_vol,
        exempt_cap_m3=float(sa_focus_ev["CapM3"]) if pd.notna(sa_focus_ev["CapM3"]) else None,
    )
    if _sa_curve is not None:
        st.altair_chart(_sa_curve, use_container_width=True)


# ═══════════════════════════════════════════════════════════════════════════
# VIEW 4: SIDE-BY-SIDE PEER COMPARATOR & 1-PAGE COUNCIL DELEGATION BRIEF
# ═══════════════════════════════════════════════════════════════════════════
else:
    st.markdown(
        '<div class="ofa-card-hdr" style="font-size:1.15rem;">Build a Custom Peer Comparison &amp; Council Delegation Brief</div>',
        unsafe_allow_html=True,
    )
    st.caption(
        "Pin your home municipality plus up to 8 neighbouring peers to compare Building Permit Fees, "
        "Agricultural Development Charges (with Upper-Tier stacking), Excess Soil Fees, or all three — then export an OFA-branded Word handout (.docx)."
    )

    all_local_names = sorted(bf_local["name"].dropna().astype(str).unique().tolist())
    if "fe_cmp_home" not in st.session_state or st.session_state["fe_cmp_home"] not in all_local_names:
        st.session_state["fe_cmp_home"] = "Perth East" if "Perth East" in all_local_names else all_local_names[0]
    cmp_c1, cmp_c2 = st.columns([1.2, 1.8])
    with cmp_c1:
        cmp_home = st.selectbox("Home Municipality (Spotlighted in OFA Crimson)", all_local_names, key="fe_cmp_home")
        _home_county = _clean_str(bf_local.loc[bf_local["name"] == cmp_home, "geographic_area"].iloc[0], "")
        _county_peers = sorted(
            bf_local.loc[(bf_local["geographic_area"] == _home_county) & (bf_local["name"] != cmp_home), "name"].astype(str).tolist()
        )[:6]
    with cmp_c2:
        cmp_peers = st.multiselect(
            f"Comparator Municipalities (auto-suggested from {_home_county}; max 8)",
            options=[m for m in all_local_names if m != cmp_home],
            default=_county_peers,
            max_selections=8,
            key=f"fe_cmp_peers_{cmp_home}",
        )

    cmp_topic_lbl = st.radio(
        "Comparison Topic",
        ["Building Permit Fees", "Agricultural Development Charges", "Site Alteration Soil Fees", "All Three (Full Package)"],
        index=0,
        horizontal=True,
        key="fe_cmp_topic",
    )
    cmp_topic = {
        "Building Permit Fees": "bldg_fees",
        "Agricultural Development Charges": "dc",
        "Site Alteration Soil Fees": "site_alt",
        "All Three (Full Package)": "all",
    }[cmp_topic_lbl]

    cmp_t1, cmp_t2, cmp_t3 = st.columns([1.3, 1.4, 1.3])
    with cmp_t1:
        cmp_sqft = st.select_slider(
            "Building Permit Size (ft²)",
            options=[2500, 5000, 10000, 15000, 20000],
            value=10000,
            key="fe_cmp_sqft",
            disabled=(cmp_topic not in ("bldg_fees", "all")),
        )
        cmp_is_live = st.radio(
            "Permit Building Type",
            ["🐄 Livestock Barn", "🚜 Drive Shed"],
            index=0,
            horizontal=True,
            key="fe_cmp_btype",
            disabled=(cmp_topic not in ("bldg_fees", "all")),
        ) == "🐄 Livestock Barn"
        cmp_val_on = st.checkbox(
            r"Include Valuation (per \$1k CV) at \$100/ft²",
            value=False,
            key="fe_cmp_val_on",
            disabled=(cmp_topic not in ("bldg_fees", "all")),
        )
        cmp_assumed = 100.0 if cmp_val_on else None
    with cmp_t2:
        _CMP_DC_MAP = {
            "Typical Farm (10,000 ft²)": "typical_farm",
            "Commercial Greenhouse (1 Acre)": "greenhouse",
            "Cannabis Production (10,000 ft²)": "cannabis",
            "Bunkhouse / SAWP (10 Beds)": "bunkhouse",
        }
        cmp_dc_btype_lbl = st.selectbox(
            "Development Charge Sub-Type",
            list(_CMP_DC_MAP.keys()),
            index=0,
            key="fe_cmp_dc_btype",
            disabled=(cmp_topic not in ("dc", "all")),
        )
        cmp_dc_btype = _CMP_DC_MAP[cmp_dc_btype_lbl]
        cmp_dc_sa = "rural" if st.radio(
            "DC Servicing Area",
            ["Rural (Unserviced)", "Urban (Serviced)"],
            index=0,
            horizontal=True,
            key="fe_cmp_dc_sa",
            disabled=(cmp_topic not in ("dc", "all")),
        ).startswith("Rural") else "urban"
        cmp_dc_stack = st.checkbox(
            "Stack Upper-Tier County / Region DC",
            value=True,
            key="fe_cmp_dc_stack",
            disabled=(cmp_topic not in ("dc", "all")),
        )
    with cmp_t3:
        cmp_vol = st.select_slider(
            "Topsoil Import Benchmark (m³)",
            options=[500, 2500, 5000, 10000, 15000, 20000],
            value=15000,
            key="fe_cmp_vol",
            disabled=(cmp_topic not in ("site_alt", "all")),
        )

    selected_set = [cmp_home] + cmp_peers
    st.divider()

    export_frames = []
    if cmp_topic in ("bldg_fees", "all"):
        ont_med_bf_cmp = _compute_ont_med_bf(int(cmp_sqft), cmp_is_live)
        _rows_b = []
        for nm in selected_set:
            _sub = bf_local[bf_local["name"] == nm]
            if _sub.empty:
                continue
            r = _sub.iloc[0]
            _e = evaluate_bldg_fee(r, float(cmp_sqft), is_livestock=cmp_is_live, assumed_cost_per_sqft=cmp_assumed)
            _eb = evaluate_bldg_fee(r, float(cmp_sqft), is_livestock=cmp_is_live, assumed_cost_per_sqft=None)
            _rows_b.append({
                "Municipality": nm,
                "County": _clean_str(r.get("geographic_area")),
                "Fee": _e,
                "IsEstimate": (_e is not None and _eb is None and cmp_assumed is not None),
                "Fee Display": f"{_fmt_dollars(_e)}{' (Est.)' if (_e is not None and _eb is None and cmp_assumed) else ''}" if _e is not None else _clean_str(r.get("pricing_model")),
                "Eff. $/ft²": f"${_e / cmp_sqft:.2f}/ft²" if _e is not None else "—",
                "Year": _fmt_year(r.get("fee_year")),
                "Pricing Model": _clean_str(r.get("pricing_model")),
                "Refundable Deposit": _clean_str(r.get("refundable_deposit")),
                "Bylaw Link": _valid_url(r.get("bylaw_link")) or "",
                "Detail": _clean_str(r.get("pricing_model")),
            })
        df_cmp_b = pd.DataFrame(_rows_b)
        st.altair_chart(
            build_peer_bar_chart(
                df_cmp_b[df_cmp_b["Fee"].notna()],
                focus_muni=cmp_home,
                title=f"Building Permit Fee Comparison — {cmp_sqft:,} ft² {'Livestock Barn' if cmp_is_live else 'Drive Shed'}",
                subtitle=f"{len(selected_set)} selected municipalities · OFA Crimson = {cmp_home}",
                median_val=ont_med_bf_cmp,
                median_label="Ontario Median",
            ),
            use_container_width=True,
        )
        st.dataframe(
            df_cmp_b[["Municipality", "County", "Fee Display", "Eff. $/ft²", "Year", "Pricing Model", "Refundable Deposit", "Bylaw Link"]],
            use_container_width=True,
            hide_index=True,
            column_config={"Bylaw Link": st.column_config.LinkColumn("Source PDF", display_text="Open PDF ↗")},
        )
        export_frames.append(df_cmp_b.drop(columns=["Fee", "IsEstimate", "Detail"]))

    if cmp_topic in ("dc", "all"):
        _cmp_dc_med = _compute_dc_charged_median(cmp_dc_btype, cmp_dc_sa, cmp_dc_stack)
        _cmp_st_col = {
            "typical_farm": "farm_bldg_dc_status",
            "greenhouse": "greenhouse_dc_status",
            "cannabis": "cannabis_dc_status",
            "bunkhouse": "bunkhouse_dc_status",
        }[cmp_dc_btype]
        _rows_dc = []
        for nm in selected_set:
            _sub = dc_local[dc_local["name"] == nm]
            if _sub.empty:
                continue
            r = _sub.iloc[0]
            _ut = _parent_upper_dc_row(r, cmp_dc_stack)
            _ev = compute_stacked_dc(r, _ut, cmp_dc_btype, cmp_dc_sa)
            _eff_tot, _is_part = _dc_effective_total(_ev)
            _r_nodc = str(r.get("has_dc", "") or "").strip().lower() in ("no", "2")
            _ut_nodc = (_ut is None) or (str(_ut.get("has_dc", "") or "").strip().lower() in ("no", "2"))

            def _fmt_dc_c(val, nodc=False, plus=False):
                if nodc:
                    return "$0 (No DC)"
                if val is None:
                    return "Silent / Confirm"
                if val <= 0 and not plus:
                    return "$0 (Exempt)"
                return f"{_fmt_dollars(val)}+" if plus else _fmt_dollars(val)

            _rows_dc.append({
                "Municipality": nm,
                "County": _clean_str(r.get("geographic_area")),
                "LowerFee": _ev["lower_or_single"],
                "UpperFee": _ev["upper_tier"] if _ut is not None else 0.0,
                "TotalFee": _eff_tot,
                "PartialSilent": _is_part,
                "SilentWhich": _ev.get("silent_tier_which") or "",
                "UpperName": _pretty_upper_name(_ut.get("name")) if _ut is not None else "—",
                "Lower / Single DC": _fmt_dc_c(_ev["lower_or_single"], _r_nodc),
                "Upper-Tier DC": ("—" if str(r.get("municipal_status", "")).strip() != "Lower Tier" else _fmt_dc_c(_ev["upper_tier"], _ut_nodc)),
                "Combined DC": _fmt_dc_c(_eff_tot, _r_nodc and _ut_nodc, plus=_is_part),
                "Status": "No DC By-law" if _r_nodc else _clean_str(r.get(_cmp_st_col), "Silent / Confirm"),
                "Year": _fmt_year(r.get("dc_rate_year")),
                "EDC Applies": _clean_str(r.get("dc_edc_applicable")),
                "Pamphlet Link": _valid_url(r.get("dc_rate_pamphlet_link")) or _valid_url(r.get("bylaw_link")) or "",
                "Detail": "No DC By-law" if _r_nodc else _clean_str(r.get(_cmp_st_col), "Silent / Confirm"),
            })
        df_cmp_dc = pd.DataFrame(_rows_dc)
        _dc_sa_str = "Rural Unserviced" if cmp_dc_sa == "rural" else "Urban Serviced"
        st.altair_chart(
            build_dc_stacked_peer_chart(
                df_cmp_dc[df_cmp_dc["TotalFee"].notna()],
                focus_muni=cmp_home,
                title=f"Development Charge Comparison — {cmp_dc_btype_lbl} ({_dc_sa_str})",
                subtitle=(
                    f"{len(selected_set)} selected municipalities · Stacked: Lower/Single (Crimson/Gray) + Upper-Tier (Gold/Slate)"
                    if cmp_dc_stack
                    else f"{len(selected_set)} selected municipalities · Standalone Municipal DC · OFA Crimson = {cmp_home}"
                ),
                median_val=_cmp_dc_med,
                median_label="Ontario Charged Median",
                stacked=cmp_dc_stack,
            ),
            use_container_width=True,
        )
        _dc_cols_show = (
            ["Municipality", "County", "Lower / Single DC", "Upper-Tier DC", "Combined DC", "Year", "Pamphlet Link", "Status"]
            if cmp_dc_stack
            else ["Municipality", "County", "Lower / Single DC", "Year", "Pamphlet Link", "Status", "EDC Applies"]
        )
        st.dataframe(
            df_cmp_dc[_dc_cols_show],
            use_container_width=True,
            hide_index=True,
            column_config={
                "Year": st.column_config.TextColumn("Year", width="small"),
                "Pamphlet Link": st.column_config.LinkColumn("Source PDF", display_text="Open PDF ↗", width="small"),
                "Status": st.column_config.TextColumn("Status", width="medium"),
            },
        )
        export_frames.append(df_cmp_dc[_dc_cols_show])

    if cmp_topic in ("site_alt", "all"):
        ont_med_sa_paid_c, ont_med_sa_vol_c = _compute_sa_medians(int(cmp_vol))
        _rows_s = []
        _any_vol = False
        for nm in selected_set:
            _sub = sa_local[sa_local["name"] == nm]
            if _sub.empty:
                continue
            r = _sub.iloc[0]
            _v = evaluate_site_alt_fee(r, float(cmp_vol))
            _pm3 = pd.to_numeric(r.get("per_m3_rate"), errors="coerce")
            if pd.notna(_pm3) and float(_pm3) > 0:
                _any_vol = True
            _fvs = _clean_str(r.get("fee_verification_status"))
            _pm = _clean_str(r.get("fee_pricing_model"))
            _disp = (
                ("$0 (Exempt)" if _v <= 0 else _fmt_dollars(_v))
                if _v is not None
                else ("Area-Based ($/ha)" if "hectare" in _pm.lower() else ("No Bylaw ($0)" if "no bylaw" in _fvs.lower() else _fvs))
            )
            _rows_s.append({
                "Municipality": nm,
                "County": _clean_str(r.get("geographic_area")),
                "Fee": _v,
                "Exemption": _clean_str(r.get("exemption_status")),
                "Ag Import Fee Status": _clean_str(r.get("ag_import_fee_status")),
                f"Est. ({cmp_vol:,} m³)": _disp,
                "Out-of-Muni Ban": _clean_str(r.get("out_of_muni_fill_ban")),
                "Refundable Security": _clean_str(r.get("security_deposit_terms")),
                "Bylaw Link": _valid_url(r.get("fees_bylaw_link")) or _valid_url(r.get("bylaw_link")) or "",
                "Detail": f"{_clean_str(r.get('ag_import_fee_status'))} · {_pm}",
            })
        df_cmp_s = pd.DataFrame(_rows_s)
        _ref_v = ont_med_sa_vol_c if (_any_vol and ont_med_sa_vol_c is not None) else ont_med_sa_paid_c
        _ref_l = "Ontario Volumetric Median" if (_any_vol and ont_med_sa_vol_c is not None) else "Ontario Paid Median"
        st.altair_chart(
            build_peer_bar_chart(
                df_cmp_s[df_cmp_s["Fee"].notna()],
                focus_muni=cmp_home,
                title=f"Excess Soil Permit Fee Comparison — {cmp_vol:,} m³ (~{cmp_vol // 10:,} Loads)",
                subtitle="Non-refundable permit fee only across comparable municipalities · Green = $0 Farm Exempt",
                median_val=_ref_v,
                median_label=_ref_l,
                exempt_zero_highlight=True,
            ),
            use_container_width=True,
        )
        st.dataframe(
            df_cmp_s[["Municipality", "County", "Exemption", "Ag Import Fee Status", f"Est. ({cmp_vol:,} m³)", "Out-of-Muni Ban", "Refundable Security", "Bylaw Link"]],
            use_container_width=True,
            hide_index=True,
            column_config={"Bylaw Link": st.column_config.LinkColumn("Source PDF", display_text="Open PDF ↗")},
        )
        export_frames.append(df_cmp_s.drop(columns=["Fee", "Detail"]))

    # ── Export Bar: CSV + 1-Page OFA Delegation Brief (.docx) ──
    st.markdown("---")
    ex1, ex2 = st.columns([1.2, 1.8])
    with ex1:
        if export_frames:
            _csv_out = pd.concat(export_frames, ignore_index=True).to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
            _safe_h = re.sub(r"[^\w-]+", "_", cmp_home)
            st.download_button(
                "⬇️ Download Comparison Table (CSV)",
                data=_csv_out,
                file_name=f"OFA_Fee_Comparison_{_safe_h}_{cmp_topic}.csv",
                mime="text/csv",
                use_container_width=True,
                key="fe_cmp_csv_dl",
            )
    with ex2:
        if st.button("📄 Generate 1-Page Council Delegation Brief (.docx)", type="primary", use_container_width=True, key="fe_brief_btn"):
            from report_generator import generate_fee_comparison_brief

            with st.spinner("Generating OFA-branded delegation brief..."):
                _docx_buf = generate_fee_comparison_brief(
                    focus_muni=cmp_home,
                    peer_munis=cmp_peers,
                    topic=cmp_topic,
                    bldg_sqft=int(cmp_sqft),
                    is_livestock=cmp_is_live,
                    assumed_cost_per_sqft=cmp_assumed,
                    sa_volume_m3=int(cmp_vol),
                    dc_btype=cmp_dc_btype,
                    dc_service_area=cmp_dc_sa,
                    dc_stacked=cmp_dc_stack,
                )
            _safe_h = re.sub(r"[^\w-]+", "_", cmp_home)
            st.session_state["fe_brief_bytes"] = _docx_buf.getvalue()
            st.session_state["fe_brief_fname"] = f"OFA_Council_Fee_Brief_{_safe_h}_{datetime.date.today()}.docx"

        if st.session_state.get("fe_brief_bytes"):
            st.download_button(
                f"📥 Download {st.session_state['fe_brief_fname']}",
                data=st.session_state["fe_brief_bytes"],
                file_name=st.session_state["fe_brief_fname"],
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                type="primary",
                use_container_width=True,
                key="fe_brief_dl",
            )
