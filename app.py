import os
from datetime import date
import pandas as pd
import streamlit as st

from db_utils import get_connection
from build_maps_v2_rollup_metadata import _load_live_df

st.set_page_config(
    page_title="Ontario Municipal Bylaw Database",
    page_icon="🏛️",
    layout="wide",
)

st.title("🏛️ Ontario Municipal Bylaw Database")
st.subheader("Ontario Federation of Agriculture – Municipal Policy & Intelligence Engine")

st.markdown(
    "Welcome to the **Ontario Municipal Bylaw Database & Interactive Map**. "
    "This platform tracks agricultural exemptions, bylaw expiry timelines, council agenda intelligence, "
    "and municipal clerk contacts across **all 444 Ontario municipalities** (414 Lower/Single-Tier and 30 Upper-Tier Counties & Regions)."
)


@st.cache_data(ttl=300)
def load_executive_summary():
    """Compute live province-wide KPI metrics and 8-category scorecard from the database."""
    df, _ = _load_live_df()
    today = pd.Timestamp(date.today())

    categories = [
        (
            "Development Charges",
            "Farm Exemption for Development Charges Status",
            "Bylaw Name Development Charges",
            "Expiry Date",
            "Farm building / bona fide farm exemption",
        ),
        (
            "Stormwater Charges",
            "Farm Exemption for Stormwater Charges Status",
            "Bylaw Name Stormwater",
            "Expiry date2",
            "Agricultural land / farm exemption",
        ),
        (
            "Site Alteration & Fill",
            "Farm Exemption for SA Status",
            "Bylaw Name Site Alteration",
            "Expiry date 4",
            "Normal farm practice exemption",
        ),
        (
            "Livestock Guardian & Herding Dogs",
            "LGD/HD Working Dog Definition Status",
            "Bylaw Name LGD",
            "Expiry Date 5",
            "Working dog definition & exemptions",
        ),
        (
            "Tree / Forest Conservation",
            "Farm Exemption - Tree Cutting Bylaw Status",
            "Bylaw Name Forest Conservation",
            "Expiry Date 6",
            "Agricultural / normal farm practice exemption",
        ),
        (
            "Backyard Chickens",
            "Can you Keep Backyard Chickens Status",
            "Bylaw Name Backyard Chicken",
            "Expiry Date 7",
            "Backyard hens permitted under bylaw",
        ),
        (
            "Fence Bylaws (Security / Electrified)",
            "Farm Exemption for Electrified fencing prohibitions Status",
            "Bylaw Name Fence",
            "Expiry Date 8",
            "Farm exemption for electrified/security fencing",
        ),
    ]

    scorecard_rows = []
    total_active = 0
    total_yes = 0
    total_partial = 0
    total_no = 0
    total_expiring = 0

    for cat_label, status_col, name_col, exp_col, desc in categories:
        st_series = df[status_col].fillna("NOT KNOWN").astype(str).str.strip().str.upper()
        yes_count = int((st_series == "YES").sum())
        partial_count = int((st_series == "PARTIAL").sum())
        no_count = int((st_series == "NO").sum())
        active_count = yes_count + partial_count + no_count

        exp_raw = df[exp_col].fillna("").astype(str).str.strip() if exp_col in df.columns else pd.Series([""] * len(df))
        exp_dt = pd.to_datetime(exp_raw, errors="coerce")
        days = (exp_dt - today).dt.days
        expiring_count = int(((st_series.isin(["YES", "PARTIAL", "NO"])) & exp_dt.notna() & (days <= 540)).sum())

        rate = round((yes_count / active_count * 100), 1) if active_count > 0 else 0.0

        total_active += active_count
        total_yes += yes_count
        total_partial += partial_count
        total_no += no_count
        total_expiring += expiring_count

        scorecard_rows.append(
            {
                "Category": cat_label,
                "Key Provision": desc,
                "Active": active_count,
                "Full (YES)": yes_count,
                "Partial": partial_count,
                "No Exemp.": no_count,
                "Expiring": expiring_count,
                "Exemption Rate": rate,
            }
        )

    # Count recent scanner signals & live fee intelligence snapshots
    signal_count = 0
    bf_snap = {"audited": 0, "farm_tiers": 0, "med_10k_barn": None, "med_2500_shed": None}
    dc_snap = {"audited": 0, "active_dc": 0, "charged_barn": 0, "charged_gh": 0, "charged_can": 0, "med_barn": None}
    sa_snap = {"active_bylaws": 0, "verified": 0, "exempt_zero": 0, "per_m3_cnt": 0, "med_15k": None, "bans": 0}
    try:
        conn = get_connection()
        sig_df = pd.read_sql_query("SELECT COUNT(*) AS cnt FROM scanner_signals", conn.conn)
        if not sig_df.empty:
            signal_count = int(sig_df.iloc[0]["cnt"])

        bf_df = pd.read_sql_query(
            """
            SELECT d.verification_status, d.has_farm_tier, d.est_10000_barn, d.est_2500_shed
            FROM details_bldg_fees d
            """,
            conn.conn,
        )
        if not bf_df.empty:
            _bf_vs = bf_df["verification_status"].fillna("Pending").astype(str)
            bf_snap["audited"] = int((_bf_vs != "Pending").sum())
            bf_snap["farm_tiers"] = int(bf_df["has_farm_tier"].fillna("").astype(str).str.strip().str.lower().eq("yes").sum())
            _b10 = pd.to_numeric(bf_df["est_10000_barn"], errors="coerce").dropna()
            _s25 = pd.to_numeric(bf_df["est_2500_shed"], errors="coerce").dropna()
            bf_snap["med_10k_barn"] = float(_b10.median()) if len(_b10) else None
            bf_snap["med_2500_shed"] = float(_s25.median()) if len(_s25) else None

        dc_df = pd.read_sql_query(
            """
            SELECT d.dc_rate_verification_status, d.est_dc_10k_barn_rural,
                   d.est_dc_1ac_greenhouse_rural, d.est_dc_10k_cannabis_rural
            FROM details_dc d
            """,
            conn.conn,
        )
        if not dc_df.empty:
            _dc_vs = dc_df["dc_rate_verification_status"].fillna("Pending").astype(str)
            dc_snap["audited"] = int((_dc_vs != "Pending").sum())
            _dc_act = dc_df[~_dc_vs.isin(["Pending", "No DC By-law"])]
            dc_snap["active_dc"] = len(_dc_act)
            _db = pd.to_numeric(_dc_act["est_dc_10k_barn_rural"], errors="coerce").dropna()
            _dg = pd.to_numeric(_dc_act["est_dc_1ac_greenhouse_rural"], errors="coerce").dropna()
            _dc = pd.to_numeric(_dc_act["est_dc_10k_cannabis_rural"], errors="coerce").dropna()
            dc_snap["charged_barn"] = int((_db > 0).sum())
            dc_snap["charged_gh"] = int((_dg > 0).sum())
            dc_snap["charged_can"] = int((_dc > 0).sum())
            _db_pos = _db[_db > 0]
            dc_snap["med_barn"] = float(_db_pos.median()) if len(_db_pos) else None

        sa_df = pd.read_sql_query(
            """
            SELECT d.fee_verification_status, d.ag_import_fee_status, d.per_m3_rate,
                   d.est_fee_15000_m3, d.out_of_muni_fill_ban
            FROM details_site_alt d
            """,
            conn.conn,
        )
        if not sa_df.empty:
            _sa_vs = sa_df["fee_verification_status"].fillna("").astype(str)
            _sa_active = sa_df[~_sa_vs.str.contains("No Bylaw", case=False, na=False) & _sa_vs.ne("")]
            sa_snap["active_bylaws"] = len(_sa_active)
            sa_snap["verified"] = int(_sa_active["fee_verification_status"].fillna("").astype(str).str.startswith("Verified").sum())
            sa_snap["exempt_zero"] = int(
                _sa_active["ag_import_fee_status"].fillna("").astype(str).isin(["Exempt ($0)", "Waiver Available ($0 App Fee)"]).sum()
            )
            _m3 = pd.to_numeric(_sa_active["per_m3_rate"], errors="coerce").dropna()
            sa_snap["per_m3_cnt"] = int((_m3 > 0).sum())
            _e15 = pd.to_numeric(_sa_active["est_fee_15000_m3"], errors="coerce").dropna()
            _e15_paid = _e15[_e15 > 0]
            sa_snap["med_15k"] = float(_e15_paid.median()) if len(_e15_paid) else None
            sa_snap["bans"] = int(
                _sa_active["out_of_muni_fill_ban"].fillna("").astype(str).str.strip().str.lower().isin(["yes", "restricted"]).sum()
            )
        conn.close()
    except Exception:
        pass

    return {
        "total_munis": len(df),
        "total_records": len(df) * 8,
        "total_active": total_active,
        "total_yes": total_yes,
        "total_partial": total_partial,
        "total_no": total_no,
        "total_expiring": total_expiring,
        "signal_count": signal_count,
        "scorecard_df": pd.DataFrame(scorecard_rows),
        "bf_snap": bf_snap,
        "dc_snap": dc_snap,
        "sa_snap": sa_snap,
    }


try:
    summary = load_executive_summary()
except Exception as e:
    summary = None

# ── Top-Level KPI Metrics ──
if summary is not None:
    st.markdown("### 📊 Province-Wide Executive Overview")
    k1, k2, k3, k4, k5, k6 = st.columns(6)
    overall_pct = round(summary["total_yes"] / summary["total_active"] * 100, 1) if summary["total_active"] else 0.0
    with k1:
        st.metric("Municipalities", f"{summary['total_munis']:,}")
        st.caption("414 Lower/Single · 30 Upper")
    with k2:
        st.metric("Active Bylaws", f"{summary['total_active']:,}")
        st.caption(f"{summary['total_records']:,} category records")
    with k3:
        st.metric("Full Exempt (YES)", f"{summary['total_yes']:,}")
        st.caption(f"{overall_pct}% of active bylaws")
    with k4:
        st.metric("Partial Exempt", f"{summary['total_partial']:,}")
        st.caption("Statutory minimum only")
    with k5:
        st.metric("No Exemption (NO)", f"{summary['total_no']:,}")
        st.caption("Advocacy letter targets")
    with k6:
        st.metric("Expiring ≤ 18 Mos", f"{summary['total_expiring']:,}")
        st.caption(f"{summary['signal_count']} scanner signals")

st.divider()

# ── Quick Navigation Cards ──
st.markdown("### 🧭 Launch a Tool")
nav_c1, nav_c2, nav_c3 = st.columns(3)

with nav_c1:
    with st.container(border=True):
        st.markdown("#### 🗺️ Lower Tier Map")
        st.caption(
            "Interactive map of all **414 local and single-tier municipalities** with shoreline-clipped boundaries, "
            "expiry alerts, scanner signal borders, and 1-click personalized OFA advocacy letters."
        )
        st.page_link("pages/1_Lower_Tier_Map.py", label="Open Lower Tier Map →", icon="🗺️", use_container_width=True)

    with st.container(border=True):
        st.markdown("#### 🔎 Intelligence Scanner")
        st.caption(
            "Scan municipal council agendas and minutes across Ontario for bylaw reviews, DC background studies, "
            "and custom policy keywords, and save hits directly to the database."
        )
        st.page_link("pages/5_🔎_Intelligence_Scanner.py", label="Open Intelligence Scanner →", icon="🔎", use_container_width=True)

with nav_c2:
    with st.container(border=True):
        st.markdown("#### 🏛️ Upper Tier Map")
        st.caption(
            "Interactive map of all **38 counties, regions, and single-tier cities**. Toggle between "
            "**Combined County + Lower-Tier Rollup** and **Upper-Tier / Regional Bylaws Only**."
        )
        st.page_link("pages/2_Upper_Tier_Map.py", label="Open Upper Tier Map →", icon="🏛️", use_container_width=True)

    with st.container(border=True):
        st.markdown("#### 🔒 Admin Data Entry")
        st.caption(
            "Password-protected editor for updating municipal bylaws, exemption statuses, expiry dates, "
            "and clerk contacts with instant live synchronization to the maps and reports."
        )
        st.page_link("pages/4_🔒_Admin.py", label="Open Admin Editor →", icon="🔒", use_container_width=True)

with nav_c3:
    with st.container(border=True):
        st.markdown("#### 📋 Data Browser")
        st.caption(
            "Browse, search, and filter all 3,552 bylaw & fee records across all 444 Ontario municipalities "
            "and export custom filtered tables to CSV."
        )
        st.page_link("pages/3_📋_Data_Browser.py", label="Open Data Browser →", icon="📋", use_container_width=True)

    with st.container(border=True):
        st.markdown("#### 📊 Report Generator")
        st.caption(
            "Generate OFA-branded **Provincial, County/Regional, or Municipal Word (.docx) Briefing Reports** "
            "summarizing bylaw data, exemption statuses, and advocacy priorities."
        )
        st.page_link("pages/6_📊_Report_Generator.py", label="Open Report Generator →", icon="📊", use_container_width=True)

with st.container(border=True):
    _fc1, _fc2 = st.columns([3, 1])
    with _fc1:
        st.markdown("#### 🧮 Farm Permit, Development Charge & Soil Fee Explorer")
        st.caption(
            "Interactive **Farm Building Permit Fee**, **Agricultural Development Charges** (with Upper-Tier stacking "
            "across barns, greenhouses, cannabis, and worker housing), and **Site Alteration / Excess Soil Fee** explorer — "
            "compare county neighbours and export 1-page OFA council delegation briefs (.docx)."
        )
    with _fc2:
        st.markdown("")
        st.page_link("pages/7_🧮_Fee_Explorer.py", label="Open Fee Explorer →", icon="🧮", use_container_width=True)

# ── Live 7-Category Province-Wide Scorecard ──
if summary is not None:
    st.divider()
    st.markdown("### 📋 Province-Wide Bylaw Exemption Scorecard (Live Database)")
    st.caption(
        "Counts reflect active municipal bylaws across the 7 binary/ternary agricultural exemption categories "
        "(all 444 Ontario municipalities, Lower/Single-Tier and Upper-Tier)."
    )
    st.dataframe(
        summary["scorecard_df"],
        use_container_width=True,
        hide_index=True,
        column_config={
            "Category": st.column_config.TextColumn("Category", width="medium"),
            "Key Provision": st.column_config.TextColumn("Key Provision", width="medium"),
            "Active": st.column_config.NumberColumn("Active", width="small"),
            "Full (YES)": st.column_config.NumberColumn("YES", width="small"),
            "Partial": st.column_config.NumberColumn("Partial", width="small"),
            "No Exemp.": st.column_config.NumberColumn("NO", width="small"),
            "Expiring": st.column_config.NumberColumn("Expiring", width="small"),
            "Exemption Rate": st.column_config.ProgressColumn(
                "Exemption Rate",
                help="Percentage of active bylaws in this category that provide a full farm exemption (or permit backyard chickens).",
                format="%.1f%%",
                min_value=0,
                max_value=100,
                width="small",
            ),
        },
    )

    # ── Quantitative Farm Fee Intelligence Snapshot ──
    st.divider()
    st.markdown("### 💰 Municipal Farm Fee Intelligence Snapshot")
    st.caption(
        "Quantitative cost schedules tracked separately from binary exemptions so farmers and County Federations "
        "can benchmark real project fees without mixing incompatible metrics."
    )
    _bf_s = summary["bf_snap"]
    _dc_s = summary["dc_snap"]
    _sa_s = summary["sa_snap"]

    def _snap_kpi_html(items: list[tuple[str, str, str]]) -> str:
        cols_html = []
        for lbl, val, sub in items:
            cols_html.append(
                "<div style='flex:1; min-width:0;'>"
                f"<div style='font-size:0.78rem; color:#475569; margin-bottom:2px;'>{lbl}</div>"
                f"<div style='font-size:1.38rem; font-weight:700; color:#334B58; line-height:1.2; white-space:nowrap;'>{val}</div>"
                f"<div style='font-size:0.75rem; color:#64748B; margin-top:3px; line-height:1.25; min-height:2.5em;'>{sub}</div>"
                "</div>"
            )
        return (
            "<div style='display:flex; gap:10px; align-items:flex-start; margin:8px 0 14px 0; font-family:Arial, sans-serif;'>"
            + "".join(cols_html)
            + "</div>"
        )

    fs_col1, fs_col2, fs_col3 = st.columns(3)
    with fs_col1:
        with st.container(border=True):
            st.markdown("#### Building Permit Fees")
            st.markdown(
                _snap_kpi_html([
                    ("Audited", f"{_bf_s['audited']}/{summary['total_munis']}", f"{round(_bf_s['audited']/summary['total_munis']*100, 1)}% of ON"),
                    ("Farm Tiers", f"{_bf_s['farm_tiers']}", "Area / stepped"),
                    (
                        "Med. Barn",
                        f"${round(_bf_s['med_10k_barn']):,}" if _bf_s["med_10k_barn"] is not None else "—",
                        f"2.5k Shed: ${round(_bf_s['med_2500_shed']):,}" if _bf_s["med_2500_shed"] is not None else "10k ft² barn",
                    ),
                ]),
                unsafe_allow_html=True,
            )
            if st.button("Explore Building Permit Fees →", key="home_jump_bf", use_container_width=True):
                st.session_state["fe_jump_view"] = "Farm Building Permit Fees"
                st.switch_page("pages/7_🧮_Fee_Explorer.py")

    with fs_col2:
        with st.container(border=True):
            st.markdown("#### Agricultural Dev. Charges")
            st.markdown(
                _snap_kpi_html([
                    ("Active DCs", f"{_dc_s['active_dc']}", f"{_dc_s['audited']}/{summary['total_munis']} audited"),
                    ("Charged Barns", f"{_dc_s['charged_barn']}", f"{_dc_s['charged_gh']} GH · {_dc_s['charged_can']} Can"),
                    (
                        "Med. Barn DC",
                        f"${round(_dc_s['med_barn']):,}" if _dc_s["med_barn"] is not None else "—",
                        "Charged rural (10k)",
                    ),
                ]),
                unsafe_allow_html=True,
            )
            if st.button("Explore Dev. Charges →", key="home_jump_dc", use_container_width=True):
                st.session_state["fe_jump_view"] = "Agricultural Development Charges"
                st.switch_page("pages/7_🧮_Fee_Explorer.py")

    with fs_col3:
        with st.container(border=True):
            st.markdown("#### Site Alteration & Soil Fees")
            st.markdown(
                _snap_kpi_html([
                    ("Active Bylaws", f"{_sa_s['active_bylaws']}", f"{_sa_s['verified']} verified"),
                    ("Exempt ($0)", f"{_sa_s['exempt_zero']}", f"{_sa_s['bans']} fill bans"),
                    (
                        "Med. 15k m³",
                        f"${round(_sa_s['med_15k']):,}" if _sa_s["med_15k"] is not None else "—",
                        f"{_sa_s['per_m3_cnt']} per-m³ rates",
                    ),
                ]),
                unsafe_allow_html=True,
            )
            if st.button("Explore Excess Soil Fees →", key="home_jump_sa", use_container_width=True):
                st.session_state["fe_jump_view"] = "Site Alteration & Excess Soil Fees"
                st.switch_page("pages/7_🧮_Fee_Explorer.py")

st.divider()
st.caption("Built for the Ontario Federation of Agriculture · Live database & cartographic boundaries synced")
