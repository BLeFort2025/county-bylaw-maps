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

col1.metric("Total Shown", total)
col2.metric("✅ Yes (Exemption)", yes_count)
col3.metric("❌ No (Exemption)", no_count)
col4.metric("❓ N/A / Unknown", na_count)
col5.metric("📅 Has Expiry Date", has_expiry)

st.divider()

# ── Display columns (clean up for display) ──
display_cols = ["name", "municipal_status", "geographic_area",
                "exemption_status", "bylaw_name", "date_enacted",
                "expiry_date", "expiry_notes", "progress_label"]

# Filter to only existing columns
display_cols = [c for c in display_cols if c in df.columns]

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

display_df = df[display_cols].rename(columns=rename_map).reset_index(drop=True)

# ── Data table ──
st.subheader(f"📊 {selected_label} — {total} Municipalities")

# Highlight function for exemption status
def highlight_status(val):
    if val == "Yes":
        return "background-color: #d4edda; color: #155724"
    elif val == "No":
        return "background-color: #f8d7da; color: #721c24"
    elif val in ("N/A", "NOT KNOWN"):
        return "background-color: #fff3cd; color: #856404"
    return ""

styled = display_df.style.applymap(highlight_status, subset=["Farm Exemption"] if "Farm Exemption" in display_df.columns else [])
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

                if brow["exemption_wording"]:
                    st.markdown("**Exemption Wording:**")
                    st.info(brow["exemption_wording"][:500])

                if brow["other_notes"]:
                    st.markdown("**Notes:**")
                    st.caption(brow["other_notes"][:300])

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
