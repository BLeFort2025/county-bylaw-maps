"""
app.py — Standalone Streamlit Application:
OFA Post-Election Municipal Council Outreach & Letter Generator (2026–2030 Term)

Allows County Federations of Agriculture to select their County/Region and target
Municipality, review empirical County Agricultural Profile & Survey statistics,
and generate a personalized congratulatory letter (.docx) + pre-addressed email draft
to the Municipal Clerk requesting a delegation to the newly elected Council.
"""

import os
import re
import io
import json
import zipfile
import pandas as pd
import streamlit as st

from outreach_letter_engine import (
    fmt_currency_large,
    fmt_gdp_millions,
    build_letter_sections,
    render_plain_text,
    generate_docx,
    build_email_subject,
    build_cover_email_body,
    generate_mailto_link,
)

HERE = os.path.dirname(os.path.abspath(__file__))
BUNDLE_PATH = os.path.join(HERE, "data", "outreach_data_bundle.json")

st.set_page_config(
    page_title="OFA New Council Outreach Tool",
    page_icon="🌾",
    layout="wide",
)


@st.cache_data
def load_bundle():
    if not os.path.exists(BUNDLE_PATH):
        st.error(f"Data bundle not found at {BUNDLE_PATH}. Please run `python build_outreach_data.py` first.")
        st.stop()
    with open(BUNDLE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


bundle = load_bundle()
counties_dict = bundle["counties"]
county_keys = sorted(counties_dict.keys())

# ── Header Banner ──
st.markdown(
    """
    <div style="background: linear-gradient(90deg, #1b5e20 0%, #2e7d32 100%);
                padding: 1.4rem 1.8rem; border-radius: 10px; color: white; margin-bottom: 1.2rem;">
        <h2 style="margin: 0; color: white; font-weight: 700;">
            🌾 Post-Election Municipal Council Outreach Tool (2026–2030 Term)
        </h2>
        <p style="margin: 0.4rem 0 0 0; font-size: 1.02rem; opacity: 0.95;">
            Generate a personalized letter and email to your Municipal Clerk congratulating the newly elected Council,
            sharing your County's agricultural profile, economic impact, and 2025 Farm Business Confidence Survey priorities,
            and offering an official County Federation delegation to Council.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

# ── STEP 1: Select County & Target Municipality ──
st.subheader("1️⃣ Select Your County / Region & Target Municipality")

col_sel1, col_sel2, col_sel3 = st.columns([1.3, 1.5, 1.2])

with col_sel1:
    default_idx = county_keys.index("Huron") if "Huron" in county_keys else 0
    selected_county_key = st.selectbox(
        "County / Region / District",
        options=county_keys,
        index=default_idx,
        format_func=lambda k: f"{k} ({counties_dict[k]['display_name']})",
    )

county_data = counties_dict[selected_county_key]
munis_list = county_data.get("municipalities", [])

# Sort municipalities so Upper Tier / Single Tier appear first, then Lower Tier alphabetically
status_order = {"Upper Tier": 0, "Single Tier": 1, "Lower Tier": 2}
munis_sorted = sorted(
    munis_list,
    key=lambda m: (status_order.get(m.get("municipal_status", ""), 3), m.get("name", ""))
)

def _format_muni_label(m: dict) -> str:
    st_lbl = m.get("municipal_status", "")
    nm = m.get("name", "")
    if st_lbl == "Upper Tier":
        return f"🏛️ {county_data['display_name']} — Upper-Tier Council ({nm})"
    elif st_lbl == "Single Tier":
        return f"🏛️ {nm} (Single-Tier Municipality)"
    else:
        return f"📍 {nm} (Lower-Tier Municipality)"

with col_sel2:
    selected_muni_idx = st.selectbox(
        "Target Municipality in County",
        options=list(range(len(munis_sorted))),
        format_func=lambda idx: _format_muni_label(munis_sorted[idx]),
    )
    muni_data = munis_sorted[selected_muni_idx]

# Determine Survey Scope (handle multi-federation counties and small-sample northern districts)
sub_fed_map = county_data.get("sub_federation_surveys", {})
base_survey = county_data.get("survey_2025", {})
base_n = base_survey.get("n", 0)

survey_to_use = base_survey
survey_scope_label = county_data["display_name"]

with col_sel3:
    if sub_fed_map:
        sf_options = list(sub_fed_map.keys())
        chosen_sf = st.selectbox(
            "2025 Survey Federation Filter",
            options=sf_options,
            help="This county has multiple local federations in the 2025 Farm Business Confidence Survey.",
        )
        survey_to_use = sub_fed_map[chosen_sf]
        survey_scope_label = chosen_sf
    else:
        st.markdown("**2025 Survey Sample**")
        st.caption(f"Local respondents in {county_data['display_name']}: **n = {base_n}**")

    # Small sample safeguard (< 5 respondents)
    if survey_to_use.get("n", 0) < 5:
        region_name = county_data.get("region_name", "Northern Ontario")
        reg_survey = bundle["regional_survey_2025"].get(region_name, bundle["provincial_survey_2025"])
        prov_survey = bundle["provincial_survey_2025"]
        pool_choice = st.radio(
            f"⚠️ Small local sample (n={survey_to_use.get('n', 0)}). Select survey pool:",
            options=[
                f"{region_name} Regional Pool (n={reg_survey['n']})",
                f"Ontario Provincial Pool (n={prov_survey['n']})",
                f"County Only (n={survey_to_use.get('n', 0)})",
            ],
            index=0,
        )
        if pool_choice.startswith(region_name):
            survey_to_use = reg_survey
            survey_scope_label = f"{region_name} Region"
        elif pool_choice.startswith("Ontario"):
            survey_to_use = prov_survey
            survey_scope_label = "Ontario Province-Wide"

# ── DATA OVERVIEW CARDS ──
st.markdown("---")
st.subheader(f"📊 Empirical Snapshot: {county_data['display_name']}")

cen = county_data["census_2021"]
attr = county_data["attribution"]

m1, m2, m3, m4, m5, m6 = st.columns(6)
m1.metric("Total Farms (2021 Census)", f"{cen['total_farms']:,}")
m2.metric("Total Farmland Acres", f"{cen['total_acres']:,}")
m3.metric("Gross Farm Receipts", fmt_currency_large(cen["gross_farm_receipts"]))
m4.metric(
    "Agri-Food Value Chain GDP",
    f"${attr['gdp_2025_m']/1000:.2f}B" if attr["gdp_2025_m"] >= 1000 else f"${attr['gdp_2025_m']:,.1f}M",
    help="OMAFA 2025 Economic Attribution Model (chained 2017 dollars; includes primary farm, food manufacturing, and retail).",
)
m5.metric(
    "Agri-Food Jobs Supported",
    f"{attr['jobs_latest']:,}",
    help="OMAFA Economic Attribution Model jobs across the agri-food value chain.",
)
m6.metric("2025 Survey Respondents", f"n = {survey_to_use['n']}")

with st.expander("🔍 View Detailed County Census Profile, OMAFA Economic Attribution & 2025 Survey Rankings", expanded=False):
    dcol1, dcol2, dcol3 = st.columns(3)

    with dcol1:
        st.markdown("#### 🌾 2021 Census of Agriculture")
        st.markdown(f"- **Scope:** {cen.get('census_scope_label', county_data['display_name'])}")
        st.markdown(f"- **Farms Reporting:** {cen['total_farms']:,}")
        if cen.get("total_operators"):
            st.markdown(f"- **Farm Operators:** {cen['total_operators']:,}")
        st.markdown(f"- **Total Farm Area:** {cen['total_acres']:,} acres")
        st.markdown(f"- **Area in Crops:** {cen['crop_acres']:,} acres")
        if cen.get("woodlands_wetlands_acres"):
            st.markdown(f"- **On-Farm Woodlands & Wetlands:** {cen['woodlands_wetlands_acres']:,} acres")
        st.markdown(f"- **Gross Farm Receipts:** {fmt_currency_large(cen['gross_farm_receipts'])}")
        st.markdown(f"- **Total Farm Capital:** {fmt_currency_large(cen['total_farm_capital'])}")
        if cen.get("direct_sales_farms"):
            st.markdown(f"- **Farms Selling Direct to Consumers:** {cen['direct_sales_farms']:,} farms")

        st.markdown("**Top Commodity Sectors (by Farm Count):**")
        for s in cen.get("top_sectors", []):
            st.markdown(f"1. {s['sector']}: **{s['farms']:,} farms**")

        lt_cen = muni_data.get("lower_tier_census")
        if lt_cen and lt_cen.get("total_farms") and muni_data.get("municipal_status") == "Lower Tier":
            st.info(
                f"📍 **Lower-Tier Census Data Available for {muni_data['name']}:** "
                f"{lt_cen['total_farms']:,} farms | "
                f"{lt_cen['total_acres']:,} acres | "
                f"{fmt_currency_large(lt_cen['gross_farm_receipts'])} gross receipts"
            )

    with dcol2:
        st.markdown("#### 💼 OMAFA Attribution Model")
        gdp25_md = fmt_gdp_millions(attr["gdp_2025_m"]).replace("$", r"\$")
        gdp24_md = fmt_gdp_millions(attr["gdp_2024_m"]).replace("$", r"\$")
        st.markdown(
            f"- **Region / Division:** {attr.get('cd_label', county_data['display_name'])}\n"
            f"- **2025 Agri-Food GDP:** {gdp25_md} *(chained 2017 dollars)*\n"
            f"- **2024 Agri-Food GDP:** {gdp24_md}\n"
            f"- **Agri-Food Employment:** **{attr['jobs_latest']:,} jobs** across primary agriculture, "
            f"food & beverage processing, and agri-food retail."
        )
        if attr.get("is_combined_cd"):
            st.caption(
                "ℹ️ Note: Statistics Canada and OMAFA report economic attribution for Haldimand and Norfolk "
                "together at the Haldimand-Norfolk Census Division level. The letter explicitly states this."
            )

    with dcol3:
        st.markdown(f"#### 📋 2025 Farm Business Confidence Survey ({survey_scope_label}, n={survey_to_use['n']})")
        st.markdown("**Top Farm Business Challenges:**")
        for c in survey_to_use.get("challenges", [])[:6]:
            st.markdown(f"- **{c['label']}**: {c['pct']:.0f}% ({c['count']}/{survey_to_use['n']})")
        st.markdown("**Top Helpful Policy Priorities:**")
        for p in survey_to_use.get("policy_priorities", [])[:6]:
            st.markdown(f"- **{p['label']}**: {p['pct']:.0f}% ({p['count']}/{survey_to_use['n']})")

# ── STEP 2: Sender & Recipient Details ──
st.markdown("---")
st.subheader("2️⃣ Fill In Your County Federation & Recipient Details")

# Automatically update default federation name when county changes
if st.session_state.get("_last_county_for_fed") != selected_county_key:
    st.session_state["outreach_federation"] = county_data["default_federation"]
    st.session_state["_last_county_for_fed"] = selected_county_key

for k, default_v in [
    ("outreach_name", ""),
    ("outreach_title", "President"),
    ("outreach_federation", county_data["default_federation"]),
    ("outreach_email", ""),
    ("outreach_phone", ""),
    ("outreach_custom_note", ""),
]:
    if k not in st.session_state:
        st.session_state[k] = default_v

fcol1, fcol2, fcol3 = st.columns([1.2, 1.2, 1.2])

with fcol1:
    st.markdown("**Sender Details (County Federation)**")
    sender_name = st.text_input(
        "Your Name *",
        value=st.session_state["outreach_name"],
        placeholder="e.g., Jane Doe",
    )
    sender_title = st.text_input(
        "Your Title / Position *",
        value=st.session_state["outreach_title"],
        placeholder="e.g., President, PAC Chair, or MSR",
    )
    federation_name = st.text_input(
        "County Federation Name *",
        value=st.session_state["outreach_federation"],
        placeholder="e.g., Huron County Federation of Agriculture",
    )
    uploaded_logo = st.file_uploader(
        "Upload County Federation Logo (optional)",
        type=["png", "jpg", "jpeg", "webp", "bmp"],
        help="Places your County Federation logo at the top of the generated Word (.docx) letter.",
    )
    logo_bytes = None
    logo_alignment = "Left"
    logo_width_inches = 2.0
    if uploaded_logo is not None:
        logo_bytes = uploaded_logo.getvalue()
        lcol_a, lcol_b = st.columns([1, 1.3])
        with lcol_a:
            st.image(logo_bytes, caption="Logo Preview", width=130)
        with lcol_b:
            logo_alignment = st.radio(
                "Logo Alignment",
                options=["Left", "Center", "Right"],
                index=0,
                horizontal=True,
            )
            logo_width_inches = st.slider(
                "Logo Width (inches)",
                min_value=1.0,
                max_value=3.5,
                value=2.0,
                step=0.25,
            )

with fcol2:
    st.markdown("**Sender Contact Info & Letter Options**")
    contact_email = st.text_input(
        "Your Contact Email (for delegation replies) *",
        value=st.session_state["outreach_email"],
        placeholder="e.g., president@huronfederation.ca",
    )
    contact_phone = st.text_input(
        "Your Contact Phone (optional)",
        value=st.session_state["outreach_phone"],
        placeholder="e.g., (519) 555-0199",
    )
    num_items = st.slider(
        "Number of Top Survey Challenges & Priorities to Include",
        min_value=3,
        max_value=6,
        value=4,
    )
    include_lt_stats = st.checkbox(
        "Include municipality-specific Census stats (when available for lower-tier townships)",
        value=True,
    )

with fcol3:
    st.markdown(f"**Target Municipal Clerk ({muni_data['name']})**")
    auto_email = muni_data.get("clerk_email", "")
    auto_addr = muni_data.get("address", "")
    recipient_email = st.text_input(
        "Municipal Clerk / Council Email",
        value=auto_email,
        placeholder="e.g., clerk@municipality.ca",
        help="Auto-populated from the OFA Municipal Bylaw & Contact Database. You may edit or override this address.",
    )
    recipient_address = st.text_input(
        "Municipal Mailing Address",
        value=auto_addr,
        placeholder="Optional municipal mailing address",
    )
    custom_intro_note = st.text_area(
        "Optional Custom Local Note (appended to introduction paragraph)",
        value=st.session_state["outreach_custom_note"],
        height=88,
        placeholder="Optional: e.g., mention your local Agricultural Advisory Committee or an upcoming County Federation event.",
    )

# Persist state
st.session_state["outreach_name"] = sender_name
st.session_state["outreach_title"] = sender_title
st.session_state["outreach_federation"] = federation_name
st.session_state["outreach_email"] = contact_email
st.session_state["outreach_phone"] = contact_phone
st.session_state["outreach_custom_note"] = custom_intro_note

# Apply any manual overrides to muni_data copy
muni_effective = dict(muni_data)
muni_effective["clerk_email"] = recipient_email.strip()
muni_effective["address"] = recipient_address.strip()

# Build letter sections
sections = build_letter_sections(
    county_data=county_data,
    muni_data=muni_effective,
    sender_name=sender_name,
    sender_title=sender_title,
    federation_name=federation_name,
    contact_email=contact_email,
    contact_phone=contact_phone,
    custom_intro_note=custom_intro_note,
    survey_override=survey_to_use,
    survey_scope_label=survey_scope_label,
    num_challenges=num_items,
    num_priorities=num_items,
    include_lower_tier_stats=include_lt_stats,
)

# ── STEP 3: Preview, Download .docx & Send Automated Clerk Email ──
muni_display_label = (
    county_data["display_name"]
    if muni_effective.get("municipal_status") == "Upper Tier"
    else muni_effective["name"]
)
st.markdown("---")
st.subheader(f"3️⃣ Preview & Send Letter to {muni_display_label}")

required_ok = bool(sender_name.strip() and sender_title.strip() and federation_name.strip())
if not required_ok:
    st.warning("Please enter **Your Name**, **Your Title / Position**, and **County Federation Name** above to enable downloading and emailing.")

with st.expander("👁️ Preview Full Personalized Letter Text", expanded=True):
    preview_str = render_plain_text(sections)
    st.text_area(
        "Letter Preview",
        value=preview_str,
        height=480,
        disabled=True,
        label_visibility="collapsed",
    )

# Generate Word Document in memory
docx_buffer = generate_docx(
    sections,
    logo_bytes=logo_bytes,
    logo_alignment=logo_alignment,
    logo_width_inches=logo_width_inches,
)
safe_muni = re.sub(r"[^\w\s-]", "", muni_display_label).strip().replace(" ", "_")
docx_filename = f"Congratulations_New_Council_{safe_muni}_{selected_county_key}.docx"

act_col1, act_col2, act_col3 = st.columns([1.2, 1.4, 1.4])

with act_col1:
    st.markdown("#### 📥 Step A: Download Word Letter")
    st.download_button(
        label=f"📄 Download Letter for {muni_display_label} (.docx)",
        data=docx_buffer,
        file_name=docx_filename,
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        disabled=not required_ok,
        use_container_width=True,
    )
    st.caption("Fully editable Word document (`.docx`) ready to attach or print on County Federation letterhead.")

with act_col2:
    st.markdown("#### 📧 Step B: Open Clerk Email Draft")
    if muni_effective["clerk_email"]:
        subject = build_email_subject(muni_effective["name"], federation_name)
        cover_body = build_cover_email_body(
            sender_name=sections["sender_name"],
            sender_title=sections["sender_title"],
            federation_name=sections["federation_name"],
            municipality_name=muni_effective["name"],
            county_display=county_data["display_name"],
            contact_str=sections["contact_str"],
        )
        mailto_url = generate_mailto_link(muni_effective["clerk_email"], subject, cover_body)

        if st.download_button(
            label=f"✉️ Download .docx & Open Email to {muni_effective['clerk_email']}",
            data=generate_docx(
                sections,
                logo_bytes=logo_bytes,
                logo_alignment=logo_alignment,
                logo_width_inches=logo_width_inches,
            ),
            file_name=docx_filename,
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            disabled=not required_ok,
            use_container_width=True,
            key="mailto_launch_btn",
        ):
            st.markdown(
                f'<meta http-equiv="refresh" content="0;url={mailto_url}">',
                unsafe_allow_html=True,
            )
            st.success(
                f"Opening email draft to **{muni_effective['clerk_email']}**... "
                "Remember to attach the downloaded `.docx` letter before hitting Send!"
            )
        st.caption(
            "⚠️ **Important:** Browser security prevents web apps from auto-attaching files to Outlook/Gmail. "
            "Clicking above downloads the `.docx` and opens your pre-filled email draft — simply drag the downloaded `.docx` into the email."
        )
    else:
        st.warning("No clerk email is set for this municipality. Enter an email address in Step 2 above to enable one-click email launch.")

with act_col3:
    st.markdown(f"#### 📦 Bonus: All {len(munis_sorted)} Municipalities in {selected_county_key}")
    # Build a ZIP containing personalized .docx letters for every municipality in the county + CSV directory
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        dir_rows = []
        for m_item in munis_sorted:
            m_sec = build_letter_sections(
                county_data=county_data,
                muni_data=m_item,
                sender_name=sender_name,
                sender_title=sender_title,
                federation_name=federation_name,
                contact_email=contact_email,
                contact_phone=contact_phone,
                custom_intro_note=custom_intro_note,
                survey_override=survey_to_use,
                survey_scope_label=survey_scope_label,
                num_challenges=num_items,
                num_priorities=num_items,
                include_lower_tier_stats=include_lt_stats,
            )
            m_doc = generate_docx(
                m_sec,
                logo_bytes=logo_bytes,
                logo_alignment=logo_alignment,
                logo_width_inches=logo_width_inches,
            )
            m_safe = re.sub(r"[^\w\s-]", "", m_item["name"]).strip().replace(" ", "_")
            m_fn = f"Congratulations_New_Council_{m_safe}.docx"
            zf.writestr(m_fn, m_doc.getvalue())
            dir_rows.append({
                "Municipality": m_item["name"],
                "Tier": m_item["municipal_status"],
                "Clerk Email": m_item.get("clerk_email", ""),
                "Mailing Address": m_item.get("address", ""),
                "Suggested Subject": build_email_subject(m_item["name"], federation_name),
                "Letter File": m_fn,
            })
        dir_df = pd.DataFrame(dir_rows)
        zf.writestr(f"{selected_county_key}_Clerk_Email_Directory.csv", dir_df.to_csv(index=False))
    zip_buf.seek(0)

    st.download_button(
        label=f"📦 Download All {len(munis_sorted)} County Letters (.zip)",
        data=zip_buf,
        file_name=f"{selected_county_key}_New_Council_Outreach_Package.zip",
        mime="application/zip",
        disabled=not required_ok,
        use_container_width=True,
    )
    st.caption(
        f"Generates individualized `.docx` letters for all **{len(munis_sorted)}** municipalities in {county_data['display_name']} "
        "plus a `Clerk_Email_Directory.csv`."
    )
