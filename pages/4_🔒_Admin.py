"""
4_🔒_Admin.py — Password-protected admin page for editing bylaw records.

Features:
• Password gate (SHA-256 hash comparison)
• Municipality selector with search
• Per-category edit forms with all fields
• Save with audit trail
• Change history viewer
• Bulk CSV import
"""

import os, sys, hashlib, datetime

# ── Path resolution ──
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import streamlit as st
import pandas as pd
from db_utils import (
    get_connection, get_municipalities, get_bylaws, get_bylaws_with_details,
    get_contacts, get_audit_log, update_record, resolve_yes_no,
)
from shared_config import ADMIN_PASSWORD_HASH, BYLAW_CATEGORIES

# ── Page config ──
st.set_page_config(page_title="Admin — Municipal Bylaw Database", page_icon="🔒", layout="wide")

DB_PATH = os.path.join(HERE, "bylaws.db")

# ═══════════════════════════════════════════════════════════════
# Password gate
# ═══════════════════════════════════════════════════════════════
def check_password():
    """Password gate — returns True if authenticated."""
    if "admin_authenticated" not in st.session_state:
        st.session_state.admin_authenticated = False

    if st.session_state.admin_authenticated:
        return True

    st.title("🔒 Admin Login")
    st.markdown("Enter the admin password to access editing features.")

    password = st.text_input("Password", type="password", key="admin_password_input")
    if st.button("Login", key="admin_login_btn"):
        if hashlib.sha256(password.encode()).hexdigest() == ADMIN_PASSWORD_HASH:
            st.session_state.admin_authenticated = True
            st.rerun()
        else:
            st.error("Incorrect password.")
    return False


if not check_password():
    st.stop()

# ═══════════════════════════════════════════════════════════════
# Authenticated — show admin interface
# ═══════════════════════════════════════════════════════════════
conn = get_connection(DB_PATH)

st.sidebar.title("🔒 Admin Panel")

# Logout button
if st.sidebar.button("🚪 Logout"):
    st.session_state.admin_authenticated = False
    st.rerun()

# ── Mode selector ──
admin_mode = st.sidebar.radio(
    "Mode",
    ["✏️ Edit Municipality", "📜 Change History", "📤 Bulk Import"],
    index=0,
)


# ═══════════════════════════════════════════════════════════════
# MODE: Edit Municipality
# ═══════════════════════════════════════════════════════════════
if admin_mode == "✏️ Edit Municipality":
    st.title("✏️ Edit Municipality")

    # Municipality selector
    munis = get_municipalities(conn)
    muni_names = sorted(munis["name"].tolist())
    selected_name = st.selectbox("Select Municipality", muni_names, key="edit_muni_select")

    muni_row = conn.execute(
        "SELECT * FROM municipalities WHERE name = ?", (selected_name,)
    ).fetchone()

    if not muni_row:
        st.error("Municipality not found.")
        st.stop()

    muni_id = muni_row["id"]
    st.caption(f"ID: {muni_id} · {muni_row['municipal_status']} · {muni_row['geographic_area']} · Zone {muni_row['zone']}")

    # ── Municipality info tab ──
    tab_names = ["📍 Municipality Info"] + [f"{cat_label}" for _, cat_label in BYLAW_CATEGORIES]
    tabs = st.tabs(tab_names)

    # --- Tab 0: Municipality Info ---
    with tabs[0]:
        st.subheader("📍 Municipality Information")
        with st.form("muni_info_form"):
            col1, col2 = st.columns(2)
            with col1:
                new_name = st.text_input("Municipality Name", value=muni_row["name"] or "")
                new_status = st.selectbox(
                    "Municipal Status",
                    ["Lower Tier", "Upper Tier", "Single Tier"],
                    index=["Lower Tier", "Upper Tier", "Single Tier"].index(muni_row["municipal_status"]) if muni_row["municipal_status"] in ["Lower Tier", "Upper Tier", "Single Tier"] else 0,
                )
                new_area = st.text_input("Geographic Area", value=muni_row["geographic_area"] or "")
                new_zone = st.number_input("Zone", value=float(muni_row["zone"] or 0), step=1.0)
            with col2:
                new_website = st.text_input("Website", value=muni_row["website"] or "")
                new_contact = st.text_input("Contact Name", value=muni_row["contact_name"] or "")
                new_position = st.text_input("Contact Position", value=muni_row["contact_position"] or "")
                new_email = st.text_input("Clerk Email", value=muni_row["clerk_email"] or "")
                new_phone = st.text_input("Clerk Phone", value=muni_row["clerk_phone"] or "")

            if st.form_submit_button("💾 Save Municipality Info"):
                fields = {
                    "name": new_name,
                    "municipal_status": new_status,
                    "geographic_area": new_area,
                    "zone": new_zone,
                    "website": new_website,
                    "contact_name": new_contact,
                    "contact_position": new_position,
                    "clerk_email": new_email,
                    "clerk_phone": new_phone,
                }
                for field, value in fields.items():
                    old = muni_row[field]
                    if str(value) != str(old or ""):
                        update_record(conn, "municipalities", muni_id, field, value)
                st.success(f"✅ Saved municipality info for {new_name}")
                st.rerun()

    # --- Tabs 1-7: Bylaw categories ---
    EXEMPTION_OPTIONS = ["Yes", "No", "NOT KNOWN", "N/A",
                         "No explicit exemption found", ""]

    for i, (cat_code, cat_label) in enumerate(BYLAW_CATEGORIES):
        with tabs[i + 1]:
            st.subheader(f"{cat_label}")

            bylaw_df, detail_df = get_bylaws_with_details(conn, muni_id, cat_code)

            if bylaw_df.empty:
                st.warning(f"No bylaw record found for {cat_label}.")
                continue

            brow = bylaw_df.iloc[0]
            bylaw_id = brow["id"]

            with st.form(f"bylaw_form_{cat_code}_{muni_id}"):
                col1, col2 = st.columns(2)

                with col1:
                    new_bylaw_name = st.text_input("Bylaw Name", value=brow["bylaw_name"] or "", key=f"bn_{cat_code}_{muni_id}")
                    new_bylaw_link = st.text_input("Bylaw Link", value=brow["bylaw_link"] or "", key=f"bl_{cat_code}_{muni_id}")
                    new_enacted = st.text_input("Date Enacted (YYYY-MM-DD)", value=brow["date_enacted"] or "", key=f"de_{cat_code}_{muni_id}")
                    new_expiry = st.text_input("Expiry Date (YYYY-MM-DD)", value=brow["expiry_date"] or "", key=f"ed_{cat_code}_{muni_id}")
                    new_expiry_notes = st.text_input("Expiry Notes", value=brow["expiry_notes"] or "", key=f"en_{cat_code}_{muni_id}")

                with col2:
                    # Exemption status
                    current_status = resolve_yes_no(brow["exemption_status"])
                    try:
                        status_idx = EXEMPTION_OPTIONS.index(current_status)
                    except ValueError:
                        status_idx = len(EXEMPTION_OPTIONS) - 1
                    new_exemption = st.selectbox(
                        "Farm Exemption Status", EXEMPTION_OPTIONS,
                        index=status_idx, key=f"es_{cat_code}_{muni_id}"
                    )
                    new_wording = st.text_area(
                        "Exemption Wording / Notes",
                        value=brow["exemption_wording"] or "",
                        height=120, key=f"ew_{cat_code}_{muni_id}"
                    )
                    new_other = st.text_area(
                        "Other Notes",
                        value=brow["other_notes"] or "",
                        height=80, key=f"on_{cat_code}_{muni_id}"
                    )

                    # Progress
                    progress_opts = ["", "COMPLETE", "COMMUNICATION NEEDED",
                                     "AWAITING RESPONSE", "IN PROGRESS",
                                     "NO BY-LAW IN PLACE", "NOT STARTED"]
                    current_progress = brow["progress_label"] or ""
                    try:
                        prog_idx = progress_opts.index(current_progress)
                    except ValueError:
                        prog_idx = 0
                    new_progress = st.selectbox(
                        "Progress", progress_opts,
                        index=prog_idx, key=f"pr_{cat_code}_{muni_id}"
                    )

                # Category-specific fields
                st.markdown("---")
                st.markdown("**Category-Specific Details**")

                detail_updates = {}

                if cat_code == "DC" and not detail_df.empty:
                    drow = detail_df.iloc[0]
                    dc1, dc2 = st.columns(2)
                    with dc1:
                        detail_updates["has_dc"] = st.selectbox(
                            "Municipality Has DC?",
                            ["", "Yes", "No", "NOT KNOWN"],
                            index=["", "Yes", "No", "NOT KNOWN"].index(resolve_yes_no(drow["has_dc"])) if resolve_yes_no(drow["has_dc"]) in ["", "Yes", "No", "NOT KNOWN"] else 0,
                            key=f"hdc_{cat_code}_{muni_id}"
                        )
                    with dc2:
                        detail_updates["fees_bylaw_name"] = st.text_input(
                            "Fees/Charges Bylaw", value=drow["fees_bylaw_name"] or "", key=f"fbn_{cat_code}_{muni_id}")

                elif cat_code == "STORMWATER" and not detail_df.empty:
                    drow = detail_df.iloc[0]
                    detail_updates["charge_type"] = st.text_input(
                        "Charge Type", value=drow["charge_type"] or "", key=f"ct_{cat_code}_{muni_id}")
                    detail_updates["fee_calculation"] = st.text_area(
                        "Fee Calculation", value=drow["fee_calculation"] or "", height=80, key=f"fc_{cat_code}_{muni_id}")

                elif cat_code == "SITE_ALT" and not detail_df.empty:
                    drow = detail_df.iloc[0]
                    sa1, sa2 = st.columns(2)
                    with sa1:
                        _fe_opts = ["", "Yes", "No", "NOT KNOWN"]
                        _fe_val = resolve_yes_no(drow["farm_exemption"])
                        _fe_idx = _fe_opts.index(_fe_val) if _fe_val in _fe_opts else 0
                        detail_updates["farm_exemption"] = st.selectbox(
                            "Farm Exemption", _fe_opts,
                            index=_fe_idx, key=f"sfe_{cat_code}_{muni_id}")
                        _sp_val = resolve_yes_no(drow["special_provision"])
                        _sp_idx = _fe_opts.index(_sp_val) if _sp_val in _fe_opts else 0
                        detail_updates["special_provision"] = st.selectbox(
                            "Special Provision for Farm Land?", _fe_opts,
                            index=_sp_idx, key=f"sp_{cat_code}_{muni_id}")
                    with sa2:
                        detail_updates["guidelines_wording"] = st.text_area(
                            "Guidelines Wording", value=drow["guidelines_wording"] or "", height=80, key=f"gw_{cat_code}_{muni_id}")
                        detail_updates["exception_wording"] = st.text_area(
                            "Exception Wording", value=drow["exception_wording"] or "", height=80, key=f"exw_{cat_code}_{muni_id}")

                elif cat_code == "LGD" and not detail_df.empty:
                    drow = detail_df.iloc[0]
                    lgd1, lgd2 = st.columns(2)
                    yn_opts = ["", "Yes", "No", "NOT KNOWN"]
                    with lgd1:
                        detail_updates["has_lgd_definition"] = st.selectbox("Has LGD Definition?", yn_opts, key=f"hld_{cat_code}_{muni_id}")
                        detail_updates["lgd_definition"] = st.text_area("LGD Definition", value=drow["lgd_definition"] or "", height=80, key=f"ldd_{cat_code}_{muni_id}")
                        detail_updates["has_herding_def"] = st.selectbox("Has Herding Dog Def?", yn_opts, key=f"hhd_{cat_code}_{muni_id}")
                        detail_updates["herding_definition"] = st.text_area("Herding Dog Definition", value=drow["herding_definition"] or "", height=80, key=f"hdd_{cat_code}_{muni_id}")
                    with lgd2:
                        detail_updates["exempt_license_fees"] = st.selectbox("Exempt from License Fees?", yn_opts, key=f"elf_{cat_code}_{muni_id}")
                        detail_updates["collar_tag_req"] = st.selectbox("Collar/Tag Required?", yn_opts, key=f"ctr_{cat_code}_{muni_id}")
                        detail_updates["barking_restrictions"] = st.selectbox("Barking Restrictions?", yn_opts, key=f"br_{cat_code}_{muni_id}")
                        detail_updates["exempt_barking"] = st.selectbox("Exempt from Barking?", yn_opts, key=f"eb_{cat_code}_{muni_id}")
                        detail_updates["dog_limit"] = st.text_input("Dog Limit", value=drow["dog_limit"] or "", key=f"dl_{cat_code}_{muni_id}")

                elif cat_code == "TREES" and not detail_df.empty:
                    drow = detail_df.iloc[0]
                    detail_updates["farm_exemption"] = st.selectbox("Farm Exemption?", ["", "Yes", "No", "NOT KNOWN"], key=f"tfe_{cat_code}_{muni_id}")
                    detail_updates["bylaw_wording"] = st.text_area("Bylaw Wording", value=drow["bylaw_wording"] or "", height=80, key=f"tw_{cat_code}_{muni_id}")
                    detail_updates["farming_exception_wording"] = st.text_area("Farming Exception Wording", value=drow["farming_exception_wording"] or "", height=80, key=f"few_{cat_code}_{muni_id}")

                elif cat_code == "CHICKENS" and not detail_df.empty:
                    drow = detail_df.iloc[0]
                    ch1, ch2 = st.columns(2)
                    with ch1:
                        detail_updates["can_keep"] = st.selectbox("Can Keep Chickens?", ["", "Yes", "No", "NOT KNOWN", "No explicit exemption found"], key=f"ck_{cat_code}_{muni_id}")
                        detail_updates["definition"] = st.text_area("Definition", value=drow["definition"] or "", height=60, key=f"cd_{cat_code}_{muni_id}")
                        detail_updates["chicken_limit"] = st.text_input("Chicken Limit", value=drow["chicken_limit"] or "", key=f"cl_{cat_code}_{muni_id}")
                    with ch2:
                        detail_updates["roosters_allowed"] = st.selectbox("Roosters Allowed?", ["", "Yes", "No", "NOT KNOWN"], key=f"ra_{cat_code}_{muni_id}")
                        detail_updates["licence_required"] = st.selectbox("Licence Required?", ["", "Yes", "No", "NOT KNOWN"], key=f"lr_{cat_code}_{muni_id}")
                        detail_updates["welfare_requirements"] = st.text_area("Welfare Requirements", value=drow["welfare_requirements"] or "" if isinstance(drow["welfare_requirements"], str) else "", height=60, key=f"wr_{cat_code}_{muni_id}")

                elif cat_code == "FENCES" and not detail_df.empty:
                    drow = detail_df.iloc[0]
                    yn_opts = ["", "YES", "NO", "N/A"]
                    f1, f2 = st.columns(2)
                    with f1:
                        detail_updates["has_fence_bylaw"] = st.selectbox("Has Fence Bylaw?", yn_opts, key=f"hfb_{cat_code}_{muni_id}")
                        detail_updates["applies_all_lands"] = st.selectbox("Applies to All Lands?", yn_opts, key=f"aal_{cat_code}_{muni_id}")
                        detail_updates["replaces_lfa"] = st.selectbox("Replaces Line Fences Act?", yn_opts, key=f"rlf_{cat_code}_{muni_id}")
                    with f2:
                        detail_updates["security_fencing_exemption"] = st.selectbox("Security Fencing Exemption?", yn_opts, key=f"sfe2_{cat_code}_{muni_id}")
                        detail_updates["electrified_fencing_exemption"] = st.selectbox("Electrified Fencing Exemption?", yn_opts, key=f"efe_{cat_code}_{muni_id}")
                        detail_updates["equal_apportionment"] = st.selectbox("Equal Apportionment?", yn_opts, key=f"ea_{cat_code}_{muni_id}")

                # Submit button
                if st.form_submit_button(f"💾 Save {cat_label}"):
                    # Save bylaw fields
                    bylaw_fields = {
                        "bylaw_name": new_bylaw_name,
                        "bylaw_link": new_bylaw_link,
                        "date_enacted": new_enacted,
                        "expiry_date": new_expiry,
                        "expiry_notes": new_expiry_notes,
                        "progress_label": new_progress,
                        "other_notes": new_other,
                    }
                    for field, value in bylaw_fields.items():
                        old = brow[field]
                        if str(value or "") != str(old or ""):
                            update_record(conn, "bylaws", bylaw_id, field, value or None)

                    # Save exemption
                    exemption_row = conn.execute(
                        "SELECT * FROM bylaw_exemptions WHERE bylaw_id = ?", (bylaw_id,)
                    ).fetchone()
                    if exemption_row:
                        ex_id = exemption_row["id"]
                        if new_exemption != resolve_yes_no(exemption_row["exemption_status"]):
                            update_record(conn, "bylaw_exemptions", ex_id, "exemption_status", new_exemption)
                        if (new_wording or "") != (exemption_row["exemption_wording"] or ""):
                            update_record(conn, "bylaw_exemptions", ex_id, "exemption_wording", new_wording or None)

                    # Save category details
                    if detail_updates and not detail_df.empty:
                        detail_id = detail_df.iloc[0]["id"]
                        detail_table = {
                            "DC": "details_dc", "STORMWATER": "details_stormwater",
                            "SITE_ALT": "details_site_alt", "LGD": "details_lgd",
                            "TREES": "details_trees", "CHICKENS": "details_chickens",
                            "FENCES": "details_fences",
                        }[cat_code]
                        for field, value in detail_updates.items():
                            if value is not None and value != "":
                                update_record(conn, detail_table, detail_id, field, value)

                    st.success(f"✅ Saved {cat_label} for {selected_name}")
                    st.rerun()


# ═══════════════════════════════════════════════════════════════
# MODE: Change History
# ═══════════════════════════════════════════════════════════════
elif admin_mode == "📜 Change History":
    st.title("📜 Change History")
    st.caption("Recent edits to the database, newest first.")

    limit = st.slider("Number of entries", 10, 200, 50)
    audit_df = get_audit_log(conn, limit)

    if audit_df.empty:
        st.info("No changes have been recorded yet.")
    else:
        display_df = audit_df[["timestamp", "user_name", "table_name", "record_id",
                                "field_name", "old_value", "new_value"]].copy()
        display_df.columns = ["Timestamp", "User", "Table", "Record ID",
                              "Field", "Old Value", "New Value"]
        st.dataframe(display_df, use_container_width=True, hide_index=True)

        # Export
        csv = display_df.to_csv(index=False).encode("utf-8")
        st.download_button("📥 Download Change History CSV", csv,
                          "change_history.csv", "text/csv")


# ═══════════════════════════════════════════════════════════════
# MODE: Bulk Import
# ═══════════════════════════════════════════════════════════════
elif admin_mode == "📤 Bulk Import":
    st.title("📤 Bulk CSV Import")
    st.markdown("""
    Upload a CSV to update multiple records at once. The CSV must have these columns:
    - **municipality_name** — must match an existing municipality
    - **category** — one of: DC, STORMWATER, SITE_ALT, LGD, TREES, CHICKENS, FENCES
    - **field** — the field to update (e.g., `bylaw_name`, `exemption_status`, `expiry_date`)
    - **value** — the new value
    """)

    uploaded = st.file_uploader("Choose a CSV file", type=["csv"])
    if uploaded:
        import_df = pd.read_csv(uploaded)
        st.dataframe(import_df, use_container_width=True)

        required_cols = {"municipality_name", "category", "field", "value"}
        if not required_cols.issubset(set(import_df.columns)):
            st.error(f"CSV must have columns: {required_cols}")
        else:
            st.info(f"Ready to apply {len(import_df)} updates.")
            if st.button("🚀 Apply Import"):
                success = 0
                errors = []
                for _, row in import_df.iterrows():
                    # Find municipality
                    muni = conn.execute(
                        "SELECT id FROM municipalities WHERE name = ?",
                        (row["municipality_name"],)
                    ).fetchone()
                    if not muni:
                        errors.append(f"Municipality not found: {row['municipality_name']}")
                        continue

                    # Find bylaw
                    bylaw = conn.execute(
                        "SELECT id FROM bylaws WHERE municipality_id = ? AND category = ?",
                        (muni["id"], row["category"])
                    ).fetchone()
                    if not bylaw:
                        errors.append(f"Bylaw not found: {row['municipality_name']} / {row['category']}")
                        continue

                    # Determine target table
                    field = row["field"]
                    if field in ("exemption_status", "exemption_wording"):
                        ex = conn.execute(
                            "SELECT id FROM bylaw_exemptions WHERE bylaw_id = ?",
                            (bylaw["id"],)
                        ).fetchone()
                        if ex:
                            update_record(conn, "bylaw_exemptions", ex["id"], field, row["value"])
                            success += 1
                    elif field in ("bylaw_name", "bylaw_link", "date_enacted",
                                   "expiry_date", "expiry_notes", "other_notes", "progress_label"):
                        update_record(conn, "bylaws", bylaw["id"], field, row["value"])
                        success += 1
                    else:
                        errors.append(f"Unknown field: {field}")

                st.success(f"✅ Applied {success} updates successfully.")
                if errors:
                    st.warning(f"⚠️ {len(errors)} errors:")
                    for e in errors[:20]:
                        st.caption(e)

conn.close()
