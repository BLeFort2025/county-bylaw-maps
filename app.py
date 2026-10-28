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
    """Compute live province-wide KPI metrics and 7-category scorecard from the database."""
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
    total_no = 0
    total_expiring = 0

    for cat_label, status_col, name_col, exp_col, desc in categories:
        st_series = df[status_col].fillna("NOT KNOWN").astype(str).str.strip().str.upper()
        yes_count = int((st_series == "YES").sum())
        no_count = int((st_series == "NO").sum())
        active_count = yes_count + no_count

        exp_raw = df[exp_col].fillna("").astype(str).str.strip() if exp_col in df.columns else pd.Series([""] * len(df))
        exp_dt = pd.to_datetime(exp_raw, errors="coerce")
        days = (exp_dt - today).dt.days
        expiring_count = int(((st_series.isin(["YES", "NO"])) & exp_dt.notna() & (days <= 540)).sum())

        rate = round((yes_count / active_count * 100), 1) if active_count > 0 else 0.0

        total_active += active_count
        total_yes += yes_count
        total_no += no_count
        total_expiring += expiring_count

        scorecard_rows.append(
            {
                "Bylaw Category": cat_label,
                "Key Provision Tracked": desc,
                "Active Bylaws": active_count,
                "✅ Farm Exempt / Permitted (YES)": yes_count,
                "❌ No Exemption / Prohibited (NO)": no_count,
                "⏳ Expiring ≤ 18 Mos / Expired": expiring_count,
                "Exemption Rate (%)": rate,
            }
        )

    # Count recent scanner signals
    signal_count = 0
    try:
        conn = get_connection()
        sig_df = pd.read_sql_query("SELECT COUNT(*) AS cnt FROM scanner_signals", conn.conn)
        conn.close()
        if not sig_df.empty:
            signal_count = int(sig_df.iloc[0]["cnt"])
    except Exception:
        pass

    return {
        "total_munis": len(df),
        "total_records": len(df) * 7,
        "total_active": total_active,
        "total_yes": total_yes,
        "total_no": total_no,
        "total_expiring": total_expiring,
        "signal_count": signal_count,
        "scorecard_df": pd.DataFrame(scorecard_rows),
    }


try:
    summary = load_executive_summary()
except Exception as e:
    summary = None

# ── Top-Level KPI Metrics ──
if summary is not None:
    st.markdown("### 📊 Province-Wide Executive Overview")
    k1, k2, k3, k4, k5 = st.columns(5)
    overall_pct = round(summary["total_yes"] / summary["total_active"] * 100, 1) if summary["total_active"] else 0.0
    k1.metric("Municipalities Tracked", f"{summary['total_munis']:,}", "414 Lower/Single · 30 Upper")
    k2.metric("Active Bylaws Mapped", f"{summary['total_active']:,}", f"{summary['total_records']:,} total category records")
    k3.metric("✅ Confirmed Exemptions (YES)", f"{summary['total_yes']:,}", f"{overall_pct}% of active bylaws")
    k4.metric("❌ Missing Exemptions (NO)", f"{summary['total_no']:,}", "Advocacy letter targets", delta_color="inverse")
    k5.metric("⏳ Expiring Within 18 Months", f"{summary['total_expiring']:,}", f"{summary['signal_count']} active scanner signals")

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
        st.markdown("#### 📋 Data Browser & Word Reports")
        st.caption(
            "Browse, search, and filter all 3,108 bylaw records and generate formatted **Provincial, County, "
            "or Municipal Word (.docx) Briefing Reports** and CSV exports."
        )
        st.page_link("pages/3_📋_Data_Browser.py", label="Open Data Browser & Reports →", icon="📋", use_container_width=True)

    with st.container(border=True):
        st.markdown("#### 📖 User Guide")
        st.caption(
            "Step-by-step documentation for OFA staff, county federations, and members on using the interactive "
            "maps, advocacy letter generator, and intelligence scanner."
        )
        st.page_link("pages/6_📖_User_Guide.py", label="Open User Guide →", icon="📖", use_container_width=True)

# ── Live 7-Category Province-Wide Scorecard ──
if summary is not None:
    st.divider()
    st.markdown("### 📋 Province-Wide Bylaw Exemption Scorecard (Live Database)")
    st.caption(
        "Counts reflect active municipal bylaws currently recorded across all 444 Ontario municipalities "
        "(including both Lower/Single-Tier and Upper-Tier jurisdictions)."
    )
    st.dataframe(
        summary["scorecard_df"],
        use_container_width=True,
        hide_index=True,
        column_config={
            "Exemption Rate (%)": st.column_config.ProgressColumn(
                "Exemption Rate (%)",
                help="Percentage of active bylaws in this category that provide a farm exemption (or permit backyard chickens).",
                format="%.1f%%",
                min_value=0,
                max_value=100,
            ),
        },
    )

st.divider()
st.caption("Built for the Ontario Federation of Agriculture · Live database & cartographic boundaries synced")
