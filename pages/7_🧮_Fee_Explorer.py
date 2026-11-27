"""
7_🧮_Fee_Explorer.py — Standalone OFA Farm Permit & Excess Soil Fee Explorer.

Provides a clean, farmer- & council-ready workspace for quantitative municipal fees
WITHOUT modifying the 6 binary bylaw exemption map layers or existing exemption workflows:
  - View 1: Farm Building Permit Fees (BLDG_FEES) — scenarios, Bottom Line banner, cost receipt,
            county peer bars, size curve
  - View 2: Site Alteration & Excess Soil Fees (SITE_ALT) — truckload presets, Bottom Line banner,
            rule vs cost split, separate refundable security box, volumetric median, volume-cliff curve
  - View 3: Side-by-Side Peer Comparator & 1-Page OFA Council Delegation Brief (.docx)
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
from site_alt_fees_calc import evaluate_site_alt_fee, site_alt_fee_tier_rgba
from fee_charts import (
    build_peer_bar_chart,
    build_bldg_scaling_chart,
    build_site_alt_scaling_chart,
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
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data(ttl=300)
def load_fee_datasets() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load BLDG_FEES and SITE_ALT summaries from the active database (SQLite or Neon PG)."""
    conn = get_connection()
    bf_df = get_category_summary(conn, "BLDG_FEES")
    sa_df = get_category_summary(conn, "SITE_ALT")
    conn.close()
    return bf_df, sa_df


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
    "Farm Permit &amp; Excess Soil Fee Explorer</h1>",
    unsafe_allow_html=True,
)
st.caption(
    "Estimate municipal project fees, compare county neighbours against provincial medians, "
    "and export 1-page OFA council delegation briefs — built from primary-source audited municipal by-laws."
)

bf_all, sa_all = load_fee_datasets()
bf_local = bf_all[bf_all["municipal_status"].fillna("") != "Upper Tier"].copy()
sa_local = sa_all[sa_all["municipal_status"].fillna("") != "Upper Tier"].copy()

VIEW_OPTIONS = [
    "Farm Building Permit Fees",
    "Site Alteration & Excess Soil Fees",
    "Peer Comparator & Council Brief",
]

# ── Seamless deep-linking from Home Snapshot or Lower Tier Map ──
_jump_view = st.session_state.pop("fe_jump_view", None) or st.query_params.get("view", None)
_jump_muni = st.session_state.pop("fe_jump_muni", None) or st.query_params.get("muni", None)

if _jump_view:
    _jv = str(_jump_view).strip().lower()
    if "site" in _jv or "soil" in _jv or _jv == "sa":
        st.session_state["fe_active_view"] = VIEW_OPTIONS[1]
    elif "peer" in _jv or "compar" in _jv or "brief" in _jv:
        st.session_state["fe_active_view"] = VIEW_OPTIONS[2]
    else:
        st.session_state["fe_active_view"] = VIEW_OPTIONS[0]

if _jump_muni:
    _jm = str(_jump_muni).strip()
    st.session_state["fe_bf_area"] = "All Counties / Districts"
    st.session_state["fe_sa_area"] = "All Counties / Districts"
    if _jm in bf_local["name"].astype(str).values:
        st.session_state["fe_bf_muni"] = _jm
        st.session_state["fe_cmp_home"] = _jm
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
# VIEW 2: SITE ALTERATION & EXCESS SOIL FEES (SITE_ALT)
# ═══════════════════════════════════════════════════════════════════════════
elif active_view == VIEW_OPTIONS[1]:
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
# VIEW 3: SIDE-BY-SIDE PEER COMPARATOR & 1-PAGE COUNCIL DELEGATION BRIEF
# ═══════════════════════════════════════════════════════════════════════════
else:
    st.markdown(
        '<div class="ofa-card-hdr" style="font-size:1.15rem;">Build a Custom Peer Comparison &amp; Council Delegation Brief</div>',
        unsafe_allow_html=True,
    )
    st.caption(
        "Pin your home municipality plus up to 8 neighbouring peers to compare Building Permit Fees, "
        "Excess Soil Fees, or both side-by-side — then export an OFA-branded Word handout (.docx)."
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

    cmp_t1, cmp_t2, cmp_t3 = st.columns([1.4, 1.3, 1.3])
    with cmp_t1:
        cmp_topic_lbl = st.radio(
            "Comparison Topic",
            ["Building Permit Fees", "Site Alteration Soil Fees", "Combined (Both)"],
            index=0,
            horizontal=True,
            key="fe_cmp_topic",
        )
        cmp_topic = {
            "Building Permit Fees": "bldg_fees",
            "Site Alteration Soil Fees": "site_alt",
            "Combined (Both)": "combined",
        }[cmp_topic_lbl]
    with cmp_t2:
        cmp_sqft = st.select_slider(
            "Building Benchmark Size (ft²)",
            options=[2500, 5000, 10000, 15000, 20000],
            value=10000,
            key="fe_cmp_sqft",
            disabled=(cmp_topic == "site_alt"),
        )
        cmp_is_live = st.radio(
            "Building Type",
            ["🐄 Livestock Barn", "🚜 Drive Shed"],
            index=0,
            horizontal=True,
            key="fe_cmp_btype",
            disabled=(cmp_topic == "site_alt"),
        ) == "🐄 Livestock Barn"
    with cmp_t3:
        cmp_vol = st.select_slider(
            "Topsoil Import Benchmark (m³)",
            options=[500, 2500, 5000, 10000, 15000, 20000],
            value=15000,
            key="fe_cmp_vol",
            disabled=(cmp_topic == "bldg_fees"),
        )
        cmp_val_on = st.checkbox(
            r"Include Valuation (per \$1k CV) at \$100/ft²",
            value=False,
            key="fe_cmp_val_on",
            disabled=(cmp_topic == "site_alt"),
        )
        cmp_assumed = 100.0 if cmp_val_on else None

    selected_set = [cmp_home] + cmp_peers
    st.divider()

    export_frames = []
    if cmp_topic in ("bldg_fees", "combined"):
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

    if cmp_topic in ("site_alt", "combined"):
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
