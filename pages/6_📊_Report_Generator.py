"""
6_📊_Report_Generator.py — Auto-generate OFA-branded bylaw reports.

Supports three scopes:
  - Provincial: Province-wide overview (county-level aggregations)
  - County / Region: Full detail for all municipalities in one area
  - Municipality: Deep dive on a single municipality
"""

import os
import sys
import datetime

# ── Path resolution ──
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import streamlit as st
from db_utils import get_connection, get_geographic_areas, get_municipalities

# ── Page config ──
st.set_page_config(page_title="Report Generator — Municipal Bylaw Database", page_icon="📊", layout="wide")

st.title("📊 Report Generator")
st.markdown(
    "Generate professional, OFA-branded Word documents summarizing bylaw data, "
    "exemption status, intelligence alerts, and advocacy priorities. "
    "Choose your scope below and download the report with one click."
)

st.divider()

# ── Scope selector ──
scope_choice = st.radio(
    "Report Scope",
    ["🏛️ Provincial (All Ontario)", "🗺️ County / Region", "📍 Municipality"],
    index=1,
    horizontal=True,
)

conn = get_connection()

scope_key = "provincial"
scope_value = None
scope_label = "Provincial"

if "County" in scope_choice:
    scope_key = "county"
    areas = get_geographic_areas(conn)
    scope_value = st.selectbox("Select County / Region", areas, index=0)
    scope_label = scope_value

elif "Municipality" in scope_choice:
    scope_key = "municipality"
    munis = get_municipalities(conn)
    muni_names = sorted(munis["name"].tolist())
    scope_value = st.selectbox("Select Municipality", muni_names, index=0)
    scope_label = scope_value

# ── Preview panel ──
st.divider()
st.subheader("📋 Report Preview")

if scope_key == "provincial":
    count = conn.execute("SELECT COUNT(*) FROM municipalities").fetchone()[0]
    n_counties = conn.execute(
        "SELECT COUNT(DISTINCT geographic_area) FROM municipalities"
    ).fetchone()[0]
    st.info(
        f"**Provincial report** covering **{count}** municipalities across "
        f"**{n_counties}** counties and regions."
    )
    st.caption(
        "Includes: Executive Summary · Exemption Scorecard · "
        "County-level Category Summaries (×7) · Intelligence Alerts · "
        "Advocacy Priority Matrix (Top 30) · Methodology"
    )

elif scope_key == "county":
    count = conn.execute(
        "SELECT COUNT(*) FROM municipalities WHERE geographic_area = %s",
        (scope_value,),
    ).fetchone()[0]
    st.info(f"**{scope_value}** report covering **{count}** municipalities.")
    st.caption(
        "Includes: Executive Summary · Exemption Scorecard · "
        "Municipality-level Category Tables with Detail Sub-fields (×7) · "
        "Individual Municipality Profiles · Intelligence Alerts · "
        "Advocacy Priority Matrix · Methodology"
    )

else:
    st.info(f"Detailed report for **{scope_value}**.")
    st.caption(
        "Includes: Executive Summary · All 7 Category Deep-Dives with "
        "Detail Sub-fields · Intelligence Alerts · Methodology"
    )

conn.close()

# ── Generate button ──
st.divider()

col_btn, col_spacer = st.columns([1, 3])

with col_btn:
    generate = st.button("📄 Generate Report", type="primary", use_container_width=True)

if generate:
    with st.spinner(f"Generating {scope_label} report... This may take a moment."):
        try:
            from report_generator import generate_report

            docx_buffer = generate_report(scope_key, scope_value)

            safe_name = (scope_value or "Provincial").replace(" ", "_").replace("/", "_")
            filename = f"OFA_Bylaw_Report_{safe_name}_{datetime.date.today()}.docx"

            st.success("✅ Report generated successfully!")
            st.download_button(
                label="⬇️ Download Report (.docx)",
                data=docx_buffer,
                file_name=filename,
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                type="primary",
            )
        except Exception as e:
            st.error(f"❌ Report generation failed: {e}")
            st.exception(e)

# ── User guide ──
st.divider()
with st.expander("📖 How to use the Report Generator"):
    st.markdown("""
### Report Scopes

**🏛️ Provincial** — A high-level overview of all 444 municipalities across Ontario. 
Category sections show county-level aggregation tables (how many YES/NO/N/A per county). 
The advocacy matrix highlights the top 30 most urgent municipalities province-wide.
Best for: Province-wide policy briefings, board presentations, annual reviews.

**🗺️ County / Region** — A comprehensive report for one county or regional municipality. 
Includes full municipality-level tables with all detail sub-fields, individual municipality 
profiles with contact information, and a complete advocacy priority matrix.
Best for: County federation meetings, council delegations, member communications.

**📍 Municipality** — A deep dive into a single municipality's bylaw status across all 7 
categories. Shows every available detail field and any scanner intelligence.
Best for: Pre-meeting research, targeted advocacy, clerk communications.

### Report Sections

| Section | Description |
|---|---|
| **Executive Summary** | Overview stats and 7-category exemption scorecard |
| **Category Sections** | Per-category tables with exemption status, bylaw names, dates, and detail sub-fields |
| **Municipality Profiles** | Individual profiles with contacts and bylaw status (county scope) |
| **Intelligence Alerts** | Recent scanner hits from council agendas and minutes |
| **Advocacy Priority Matrix** | Municipalities ranked by urgency with recommended actions |
| **Methodology** | Data sources, definitions, and scoring explanation |
    """)
