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
    get_geographic_areas, resolve_yes_no,
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
}

CATEGORY_ICONS = {
    "DC":        "🏗️",
    "STORMWATER":"🌧️",
    "SITE_ALT":  "🚧",
    "LGD":       "🐕",
    "TREES":     "🌲",
    "CHICKENS":  "🐔",
    "FENCES":    "🏡",
}


# ═══════════════════════════════════════════════════════════════
# Sidebar filters
# ═══════════════════════════════════════════════════════════════
st.sidebar.title("📋 Data Browser")

conn = get_connection(os.path.join(HERE, "bylaws.db"))

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

# Geographic area filter
areas = get_geographic_areas(conn)
selected_area = st.sidebar.selectbox("🗺️ Geographic Area", ["All"] + areas, index=0)

# Exemption status filter
status_filter = st.sidebar.selectbox(
    "🏷️ Exemption Status", ["All", "Yes", "No", "N/A", "NOT KNOWN"], index=0
)


# ═══════════════════════════════════════════════════════════════
# Main content
# ═══════════════════════════════════════════════════════════════
st.title(f"{icon} {selected_label}")
st.caption("Browse municipal bylaw data from the OFA database")

# Load category summary
df = get_category_summary(conn, selected_cat)

# ── Apply filters ──
if search_term:
    df = df[df["name"].str.contains(search_term, case=False, na=False)]
if selected_area != "All":
    df = df[df["geographic_area"] == selected_area]
if status_filter != "All":
    df = df[df["exemption_status"] == status_filter]

# ── Metrics row ──
col1, col2, col3, col4, col5 = st.columns(5)
total = len(df)
yes_count = len(df[df["exemption_status"] == "Yes"])
no_count = len(df[df["exemption_status"] == "No"])
na_count = len(df[df["exemption_status"].isin(["N/A", "NOT KNOWN"])])
has_expiry = len(df[df["expiry_date"].notna() & (df["expiry_date"] != "")])

# Category-specific metric labels
if selected_cat == "LGD":
    yes_label, no_label = "✅ Defines Farm Dogs", "❌ No Definition"
else:
    yes_label, no_label = "✅ Yes (Exemption)", "❌ No (Exemption)"

col1.metric("Total Shown", total)
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
        "has_dc":           "Has DC Bylaw",
        "fees_bylaw_name":  "Fees Bylaw",
        "fees_enacted":     "Fees Enacted",
        "fees_expiry":      "Fees Expiry",
    },
    "STORMWATER": {
        "charge_type":      "Charge Type",
        "fee_calculation":  "Fee Calculation",
    },
    "SITE_ALT": {
        "farm_exemption":       "Farm Exempt. (Detail)",
        "special_provision":    "Special Provision",
        "guidelines_wording":   "Guidelines Wording",
        "exception_wording":    "Exception Wording",
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
}

# Fields that should be resolved from integer codes to Yes/No labels
YES_NO_DETAIL_FIELDS = {
    "has_lgd_definition", "has_herding_def", "exempt_license_fees",
    "collar_tag_req", "barking_restrictions", "exempt_barking",
    "_lgd_hd_combined",
    "has_fence_bylaw", "applies_all_lands", "replaces_lfa",
    "security_fencing_exemption", "electrified_fencing_exemption",
    "equal_apportionment", "has_dc", "farm_exemption", "can_keep",
    "roosters_allowed", "licence_required", "welfare_requirements",
    "special_provision",
}

# ── Build display columns ──
base_cols = ["name", "municipal_status", "geographic_area",
             "exemption_status", "bylaw_name", "date_enacted",
             "expiry_date", "expiry_notes", "progress_label"]

detail_map = CATEGORY_DETAIL_COLS.get(selected_cat, {})

# Resolve Yes/No codes in detail columns
def _resolve_detail_value(val):
    """Resolve integer codes AND text Yes/No/TRUE/FALSE to consistent labels."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return "N/A"
    s = str(val).strip().upper()
    if s in ("1", "YES", "Y", "TRUE"):
        return "Yes"
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
}
# Add detail column renames
rename_map.update(detail_map)

display_df = df[display_cols].rename(columns=rename_map).reset_index(drop=True)

# Clean up NaN/None values to display as "—" instead of "nan"
display_df = display_df.fillna("—")
display_df = display_df.replace({"nan": "—", "None": "—", "none": "—", "": "—"})

# ── Data table ──
st.subheader(f"📊 {selected_label} — {total} Municipalities")

# Highlight function for exemption status and Yes/No fields
def highlight_status(val):
    v = str(val).strip()
    if v == "Yes":
        return "background-color: #d4edda; color: #155724"
    elif v == "No":
        return "background-color: #f8d7da; color: #721c24"
    elif v in ("N/A", "NOT KNOWN"):
        return "background-color: #fff3cd; color: #856404"
    return ""

# Apply highlighting to Farm Exemption and all Yes/No detail columns
highlight_cols = ["Farm Exemption"]
for raw_col, nice_name in detail_map.items():
    if raw_col in YES_NO_DETAIL_FIELDS and nice_name in display_df.columns:
        highlight_cols.append(nice_name)
subset = [c for c in highlight_cols if c in display_df.columns]

if hasattr(display_df.style, "map"):
    styled = display_df.style.map(highlight_status, subset=subset)
else:
    styled = display_df.style.applymap(highlight_status, subset=subset)
st.dataframe(styled, use_container_width=True, height=500)

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
                    st.info(str(wording)[:500])

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
                        if col_name in ("id", "bylaw_id"):
                            continue
                        val = detail_row[col_name]
                        if val and str(val).strip():
                            nice_name = col_name.replace("_", " ").title()
                            resolved = resolve_yes_no(val) if str(val) in ("1","2","3","4","5") else val
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
