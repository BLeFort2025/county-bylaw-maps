"""
migrate_access_to_sqlite.py — One-time migration from Access to SQLite.

Reads the Microsoft Access database, normalises the wide 145-column table
into the relational schema defined in db_schema.py, and populates bylaws.db.

Usage:  python migrate_access_to_sqlite.py
"""

import os
import re
import sqlite3
import datetime
import pyodbc
import pandas as pd
from db_schema import create_database, DB_PATH, CATEGORIES

# ── Paths ──
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ACCESS_PATH = (
    r"C:\Users\ben.lefort\OneDrive - Ontario Federation of Agriculture"
    r"\Desktop\Municipal Bylaw Database\Data Pulls\Scripts"
    r"\All Scripts Aug 2024\Municipal Bylaw Database Dec 2025.accdb"
)
SIGNALS_CSV = os.path.join(SCRIPT_DIR, "signals", "signals.csv")


# ═══════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════

def strip_html(text):
    """Remove HTML tags and decode common entities."""
    if text is None:
        return None
    s = str(text)
    if not s.strip():
        return None
    # Remove script / style
    s = re.sub(r"<script[^>]*>.*?</script>", " ", s, flags=re.DOTALL | re.IGNORECASE)
    s = re.sub(r"<style[^>]*>.*?</style>", " ", s, flags=re.DOTALL | re.IGNORECASE)
    # Strip tags
    s = re.sub(r"<[^>]+>", " ", s)
    # Decode entities
    s = s.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    s = s.replace("&nbsp;", " ").replace("&quot;", '"')
    s = s.replace("\u00a0", " ")
    # Collapse whitespace
    s = re.sub(r"\s+", " ", s).strip()
    return s if s else None


def clean_link(text):
    """Strip Access hyperlink delimiters '#' from URLs."""
    if text is None:
        return None
    s = str(text).strip().strip("#").strip()
    return s if s else None


def safe_date(val):
    """Convert a datetime value to ISO date string, or None."""
    if val is None:
        return None
    if isinstance(val, datetime.datetime):
        return val.strftime("%Y-%m-%d")
    s = str(val).strip()
    if not s or s.lower() == "null":
        return None
    # Try parsing common formats
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return s  # return as-is if unparseable


def safe_str(val):
    """Convert a value to a clean string, or None."""
    if val is None:
        return None
    s = str(val).strip()
    return s if s and s.lower() != "null" else None


def safe_int(val):
    """Convert to int or None."""
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def resolve_lookup(code, lookup_map):
    """Resolve an integer lookup code to its display value."""
    if code is None:
        return None
    return lookup_map.get(int(code) if isinstance(code, (int, float)) else code, safe_str(code))


# ═══════════════════════════════════════════════════════════════
# Lookup loaders
# ═══════════════════════════════════════════════════════════════

def load_lookups(cursor):
    """Load all Access lookup tables into dicts."""
    lookups = {}

    lookup_tables = {
        "Yes/No":               "List - Yes/No",
        "Progress":             "List 2 - Progress Field",
        "Stormwater Charge":    "List 3 - Stormwater Charge Type",
        "Hoop House Zoning":    "List 4 - Hoop House Zoning Type",
        "HH Building Permit":   "List 5 - HH Building Permit",
        "LGD Collar":           "List 6 - LDG Collar Needs",
        "Tree Farm Exemption":  "List 7 - Tree Cutting Farm Exemption",
        "HH Dev Charge":        "List 8 - HH Development Charge",
        "Backyard Chickens":    "List 9 - Backyard Chickens",
        "Chicken Welfare":      "List 10 - Chicken Welfare Req",
        "Tree Exceptions":      "List 11 - Tree Conservation Exceptions",
    }

    for key, tbl in lookup_tables.items():
        cursor.execute(f"SELECT * FROM [{tbl}]")
        cols = [c[0] for c in cursor.description]
        id_col = cols[0]
        val_col = cols[1] if len(cols) > 1 else cols[0]
        mapping = {}
        for row in cursor.fetchall():
            mapping[row[0]] = row[1] if len(row) > 1 else str(row[0])
        lookups[key] = mapping

    return lookups


# ═══════════════════════════════════════════════════════════════
# Main migration
# ═══════════════════════════════════════════════════════════════

def migrate():
    print("=" * 60)
    print("ACCESS → SQLite MIGRATION")
    print("=" * 60)

    # ── Connect to Access ──
    conn_str = r"DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};DBQ=" + ACCESS_PATH
    acc = pyodbc.connect(conn_str)
    acc_cursor = acc.cursor()
    print(f"✓ Connected to Access: {os.path.basename(ACCESS_PATH)}")

    # ── Load lookups ──
    lookups = load_lookups(acc_cursor)
    print(f"✓ Loaded {len(lookups)} lookup tables")

    # ── Create SQLite ──
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)  # fresh start
    db = create_database(DB_PATH)
    print(f"✓ Created SQLite: {os.path.basename(DB_PATH)}")

    # ── 1. Insert lookup values ──
    for lookup_name, mapping in lookups.items():
        for code, display in mapping.items():
            display_val = display if display is not None else f"(code {code})"
            db.execute(
                "INSERT INTO lookup_values (lookup_table, code, display_value) VALUES (?, ?, ?)",
                (lookup_name, code, display_val)
            )
    db.commit()
    print(f"✓ Inserted {sum(len(m) for m in lookups.values())} lookup values")

    # ── 2. Load & insert provincial acts + category descriptions ──
    desc_tables = {
        "DC":        ("tbl_1DC_Description", "tbl_1DC_ProvLaws"),
        "STORMWATER":("tbl_2SW_Description", "tbl_2SW_ProvActs"),
        "SITE_ALT":  ("tbl_4SA_Description", "tbl_4SA_ProvActs"),
        "LGD":       ("tbl_5LGD_Description","tbl_5LGD_ProvActs"),
        "TREES":     ("tbl_6FC_Description", "tbl_6FC_ProvActs"),
        "CHICKENS":  ("tbl_7BC_Description", "tbl_7BC_ProvActs"),
    }

    for cat, (desc_tbl, prov_tbl) in desc_tables.items():
        # Description
        try:
            acc_cursor.execute(f"SELECT * FROM [{desc_tbl}]")
            cols = [c[0] for c in acc_cursor.description]
            for row in acc_cursor.fetchall():
                db.execute(
                    "INSERT INTO category_descriptions (category, description, reason_for_interest, general_notes) VALUES (?, ?, ?, ?)",
                    (cat,
                     safe_str(row[1]) if len(row) > 1 else None,
                     safe_str(row[2]) if len(row) > 2 else None,
                     safe_str(row[3]) if len(row) > 3 else None)
                )
        except Exception as e:
            print(f"  Warning: {desc_tbl}: {e}")

        # Provincial acts
        try:
            acc_cursor.execute(f"SELECT * FROM [{prov_tbl}]")
            for row in acc_cursor.fetchall():
                db.execute(
                    "INSERT INTO provincial_acts (category, act_name, notes, date_enacted) VALUES (?, ?, ?, ?)",
                    (cat,
                     safe_str(row[1]) if len(row) > 1 else None,
                     strip_html(row[2]) if len(row) > 2 else None,
                     safe_date(row[3]) if len(row) > 3 else None)
                )
        except Exception as e:
            print(f"  Warning: {prov_tbl}: {e}")

    db.commit()
    print("✓ Inserted category descriptions and provincial acts")

    # ── 3. Main migration: 444 municipalities ──
    acc_cursor.execute("SELECT * FROM [1 - Municpal Bylaw Database]")
    columns = [c[0] for c in acc_cursor.description]
    rows = acc_cursor.fetchall()
    print(f"\n  Processing {len(rows)} municipalities...")

    muni_count = 0
    bylaw_count = 0

    for row in rows:
        # Build a dict for easy column access
        r = dict(zip(columns, row))

        # ── Insert municipality ──
        db.execute("""
            INSERT INTO municipalities
            (lookup_key, name, municipal_status, geographic_area, zone,
             website, bylaw_page_link, staff_directory_link,
             contact_position, contact_name, clerk_email, clerk_phone,
             progress_overall, progress_notes, lookup_test, export_html)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            safe_str(r.get("LOOKUP")),
            safe_str(r.get("Municipality")),
            safe_str(r.get("Municipal status")),
            safe_str(r.get("Geographic Area ")),  # Note: trailing space in Access
            r.get("ZONE"),
            clean_link(r.get("Website")),
            clean_link(r.get("Bylaw Page Link")),
            clean_link(r.get("Staff Directory Link")),
            safe_str(r.get("Contact Position")),
            safe_str(r.get("Contact Name")),
            safe_str(r.get("Clerk Email")),
            safe_str(r.get("Clerk Phone")),
            safe_int(r.get("MUNICIPALITY PROGRESS")),
            safe_str(r.get("PROGRESS NOTES")),
            safe_str(r.get("LOOKUP TEST")),
            safe_str(r.get("EXPORT")),
        ))
        muni_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        muni_count += 1

        # ── Insert bylaws for each category ──

        # --- 1. Development Charges ---
        db.execute("""
            INSERT INTO bylaws (municipality_id, category, progress, progress_label,
                bylaw_name, bylaw_link, date_enacted, expiry_date, expiry_notes,
                other_notes, date_last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            muni_id, "DC",
            safe_int(r.get("Progress 1")),
            resolve_lookup(r.get("Progress 1"), lookups["Progress"]),
            safe_str(r.get("Bylaw Name 1")),
            clean_link(r.get("Link to DC Bylaw")),
            safe_date(r.get("Date Bylaw Enacted (Regional)")),
            safe_date(r.get("Expiry Date")),
            safe_str(r.get("Expiry Notes")),
            strip_html(r.get("Other Notes 1")),
            safe_date(r.get("Date Last Updated 1")),
        ))
        dc_bylaw_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        bylaw_count += 1

        db.execute("INSERT INTO bylaw_exemptions (bylaw_id, exemption_status, exemption_wording) VALUES (?, ?, ?)", (
            dc_bylaw_id,
            resolve_lookup(r.get("Farm Exemption for Development Charges"), lookups["Yes/No"]),
            strip_html(r.get("Wording of exemption")),
        ))

        db.execute("""
            INSERT INTO details_dc (bylaw_id, has_dc, fees_bylaw_name, fees_bylaw_link,
                fees_enacted, fees_expiry, fees_expiry_notes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            dc_bylaw_id,
            resolve_lookup(r.get("Municipality Has Development Charges?"), lookups["Yes/No"]),
            safe_str(r.get("Fees/Charges Bylaw 1-2")),
            clean_link(r.get("Link to Bylaw 1-2")),
            safe_date(r.get("Date Bylaw Enacted 1-2")),
            safe_date(r.get("Expiry Date 1-2")),
            safe_str(r.get("Expiry Notes 1-2")),
        ))

        # --- 2. Stormwater ---
        db.execute("""
            INSERT INTO bylaws (municipality_id, category, progress, progress_label,
                bylaw_name, bylaw_link, date_enacted, expiry_date, expiry_notes,
                other_notes, date_last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            muni_id, "STORMWATER",
            safe_int(r.get("Progress 2")),
            resolve_lookup(r.get("Progress 2"), lookups["Progress"]),
            safe_str(r.get("Bylaw Name 2")),
            clean_link(r.get("Link to Storm Water bylaw")),
            safe_date(r.get("Date Bylaw Enacted2 (Regional)")),
            safe_date(r.get("Expiry date2")),
            safe_str(r.get("Expiry Notes 2")),
            strip_html(r.get("Other Notes 2")),
            safe_date(r.get("Date Last Updated 2")),
        ))
        sw_bylaw_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        bylaw_count += 1

        db.execute("INSERT INTO bylaw_exemptions (bylaw_id, exemption_status, exemption_wording) VALUES (?, ?, ?)", (
            sw_bylaw_id,
            resolve_lookup(r.get("Farm Exemption for Stormwater Charges"), lookups["Yes/No"]),
            strip_html(r.get("How Stormwater Fees are Calculated")),
        ))

        db.execute("INSERT INTO details_stormwater (bylaw_id, charge_type, fee_calculation) VALUES (?, ?, ?)", (
            sw_bylaw_id,
            resolve_lookup(r.get("Type Of Charge"), lookups["Stormwater Charge"]),
            strip_html(r.get("How Stormwater Fees are Calculated")),
        ))

        # --- 4. Site Alteration (skipping 3 = Hoop Houses) ---
        db.execute("""
            INSERT INTO bylaws (municipality_id, category, progress, progress_label,
                bylaw_name, bylaw_name_2, bylaw_link, bylaw_link_2,
                date_enacted, expiry_date, expiry_notes,
                other_notes, date_last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            muni_id, "SITE_ALT",
            safe_int(r.get("Progress 4")),
            resolve_lookup(r.get("Progress 4"), lookups["Progress"]),
            safe_str(r.get("Bylaw Name 4-1")),
            safe_str(r.get("Bylaw Name 4-2")),
            clean_link(r.get("Link to site alteration & fill bylaw")),
            clean_link(r.get("Link to Bylaw 4-2")),
            safe_date(r.get("Date Bylaw Enacted4 (Regional)")),
            safe_date(r.get("Expiry date 4")),
            safe_str(r.get("Expiry Notes 4")),
            strip_html(r.get("Other Notes 4")),
            safe_date(r.get("Date Last Updated 4")),
        ))
        sa_bylaw_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        bylaw_count += 1

        db.execute("INSERT INTO bylaw_exemptions (bylaw_id, exemption_status, exemption_wording) VALUES (?, ?, ?)", (
            sa_bylaw_id,
            resolve_lookup(r.get("Farm Exemption for bylaw"), lookups["Yes/No"]),
            strip_html(r.get("Site Alteration Guidelines Wording")),
        ))

        db.execute("""
            INSERT INTO details_site_alt (bylaw_id, farm_exemption, special_provision,
                guidelines_wording, exception_wording)
            VALUES (?, ?, ?, ?, ?)
        """, (
            sa_bylaw_id,
            resolve_lookup(r.get("Farm Exemption for bylaw"), lookups["Yes/No"]),
            resolve_lookup(r.get("Special Provision for Farm Land?"), lookups["Yes/No"]),
            strip_html(r.get("Site Alteration Guidelines Wording")),
            strip_html(r.get("Exception Wording")),
        ))

        # --- 5. Livestock Guardian Dogs ---
        db.execute("""
            INSERT INTO bylaws (municipality_id, category, progress, progress_label,
                bylaw_name, bylaw_link, date_enacted, expiry_date, expiry_notes,
                other_notes, date_last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            muni_id, "LGD",
            safe_int(r.get("Progress 5")),
            resolve_lookup(r.get("Progress 5"), lookups["Progress"]),
            safe_str(r.get("Bylaw Name 5")),
            clean_link(r.get("Livestock Guardian Dog bylaw link")),
            safe_date(r.get("Date Bylaw Enacted 5 (Regional)")),
            safe_date(r.get("Expiry Date 5")),
            safe_str(r.get("Expiry Notes 5")),
            strip_html(r.get("Other Notes 5")),
            safe_date(r.get("Date Last Updated 5")),
        ))
        lgd_bylaw_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        bylaw_count += 1

        # LGD doesn't have a simple "exemption" — it has multiple yes/no fields
        db.execute("INSERT INTO bylaw_exemptions (bylaw_id, exemption_status, exemption_wording) VALUES (?, ?, ?)", (
            lgd_bylaw_id,
            resolve_lookup(r.get("Has Livestock Guardian dog Definition"), lookups["Yes/No"]),
            strip_html(r.get("LDG - Definition")),
        ))

        db.execute("""
            INSERT INTO details_lgd (bylaw_id, has_lgd_definition, lgd_definition,
                has_herding_def, herding_definition, exempt_license_fees,
                collar_tag_req, barking_restrictions, exempt_barking, dog_limit)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            lgd_bylaw_id,
            resolve_lookup(r.get("Has Livestock Guardian dog Definition"), lookups["Yes/No"]),
            strip_html(r.get("LDG - Definition")),
            resolve_lookup(r.get("Herding Dog Definition Exists"), lookups["Yes/No"]),
            strip_html(r.get("Herding Dog - Definition")),
            resolve_lookup(r.get("LDG and HD exempt from license fees"), lookups["Yes/No"]),
            resolve_lookup(r.get("LDG and HD Collar and tag requirements"), lookups["Yes/No"]),
            resolve_lookup(r.get("Municipal barking restrictions"), lookups["Yes/No"]),
            resolve_lookup(r.get("LDG and HD Exempt from barking restrictions"), lookups["Yes/No"]),
            strip_html(r.get("Dog Limit")),
        ))

        # --- 6. Trees / Forest Conservation ---
        db.execute("""
            INSERT INTO bylaws (municipality_id, category, progress, progress_label,
                bylaw_name, bylaw_name_2, bylaw_link, bylaw_link_2,
                date_enacted, expiry_date, expiry_notes,
                other_notes, date_last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            muni_id, "TREES",
            safe_int(r.get("Progress 6")),
            resolve_lookup(r.get("Progress 6"), lookups["Progress"]),
            safe_str(r.get("Bylaw Name 6-1")),
            safe_str(r.get("Bylaw Name 6-2")),
            clean_link(r.get("Tree Cutting Bylaw Link")),
            clean_link(r.get("Bylaw Link (2)")),
            safe_date(r.get("Date Bylaw Enacted 6 (Regional)")),
            safe_date(r.get("Expiry Date 6")),
            safe_str(r.get("Expiry Notes 6")),
            strip_html(r.get("Other Notes 6")),
            safe_date(r.get("Date Last Updated 6")),
        ))
        tree_bylaw_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        bylaw_count += 1

        db.execute("INSERT INTO bylaw_exemptions (bylaw_id, exemption_status, exemption_wording) VALUES (?, ?, ?)", (
            tree_bylaw_id,
            resolve_lookup(r.get("Farm Exemption - Tree Cutting Bylaw"), lookups["Yes/No"]),
            strip_html(r.get("Tree Cutting Bylaw Wording")),
        ))

        db.execute("""
            INSERT INTO details_trees (bylaw_id, farm_exemption, bylaw_wording,
                farming_exception_wording, list_of_exceptions)
            VALUES (?, ?, ?, ?, ?)
        """, (
            tree_bylaw_id,
            resolve_lookup(r.get("Farm Exemption - Tree Cutting Bylaw"), lookups["Yes/No"]),
            strip_html(r.get("Tree Cutting Bylaw Wording")),
            strip_html(r.get("Farming Exception Wording")),
            strip_html(r.get("List of Exceptions")),
        ))

        # --- 7. Backyard Chickens ---
        db.execute("""
            INSERT INTO bylaws (municipality_id, category, progress, progress_label,
                bylaw_name, bylaw_link, date_enacted, expiry_date, expiry_notes,
                other_notes, date_last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            muni_id, "CHICKENS",
            safe_int(r.get("Progress 7")),
            resolve_lookup(r.get("Progress 7"), lookups["Progress"]),
            safe_str(r.get("Bylaw Name 7")),
            clean_link(r.get("Backyard Chicken Bylaw Link")),
            safe_date(r.get("Date Bylaw Enacted 7 (Regional)")),
            safe_date(r.get("Expiry Date 7")),
            safe_str(r.get("Expiry Notes 7")),
            strip_html(r.get("Other Notes 7")),
            safe_date(r.get("Date Last Updated 7")),
        ))
        chk_bylaw_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        bylaw_count += 1

        db.execute("INSERT INTO bylaw_exemptions (bylaw_id, exemption_status, exemption_wording) VALUES (?, ?, ?)", (
            chk_bylaw_id,
            resolve_lookup(r.get("Can you Keep Backyard Chickens"), lookups["Backyard Chickens"]),
            strip_html(r.get("Flock/Chicken/Hen Definition")),
        ))

        db.execute("""
            INSERT INTO details_chickens (bylaw_id, can_keep, definition,
                chicken_limit, roosters_allowed, licence_required, welfare_requirements)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            chk_bylaw_id,
            resolve_lookup(r.get("Can you Keep Backyard Chickens"), lookups["Backyard Chickens"]),
            strip_html(r.get("Flock/Chicken/Hen Definition")),
            strip_html(r.get("Backyard Chicken Limit")),
            resolve_lookup(r.get("Roosters Allowed"), lookups["Yes/No"]),
            resolve_lookup(r.get("Licence Required"), lookups["Yes/No"]),
            resolve_lookup(r.get("Welfare Requirements"), lookups.get("Chicken Welfare", {})),
        ))

        # --- 8. Fences ---
        db.execute("""
            INSERT INTO bylaws (municipality_id, category, progress, progress_label,
                bylaw_name, bylaw_link, date_enacted, expiry_date, expiry_notes,
                other_notes, date_last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            muni_id, "FENCES",
            safe_int(r.get("Bylaw Progress 8")),
            resolve_lookup(r.get("Bylaw Progress 8"), lookups["Progress"]),
            safe_str(r.get("Bylaw Name 8")),
            clean_link(r.get("Link to Fence Bylaw")),
            safe_date(r.get("Date Bylaw Enacted 8")),
            safe_date(r.get("Expiry Date 8")),
            safe_str(r.get("Expiry Notes 8")),
            strip_html(r.get("Other notes about the fence bylaw")),
            safe_date(r.get("Date Bylaw Last Updated 8")),
        ))
        fence_bylaw_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        bylaw_count += 1

        db.execute("INSERT INTO bylaw_exemptions (bylaw_id, exemption_status, exemption_wording) VALUES (?, ?, ?)", (
            fence_bylaw_id,
            safe_str(r.get("Municipality Has Fence Bylaw")),
            strip_html(r.get("Other notes about the fence bylaw")),
        ))

        db.execute("""
            INSERT INTO details_fences (bylaw_id, has_fence_bylaw, applies_all_lands,
                replaces_lfa, security_fencing_exemption, electrified_fencing_exemption,
                equal_apportionment, apportionment_bylaw, fence_notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            fence_bylaw_id,
            safe_str(r.get("Municipality Has Fence Bylaw")),
            safe_str(r.get("Does the fence bylaw apply to all lands")),
            safe_str(r.get("Does the fence bylaw replace the Line Fence Act in its entirely")),
            safe_str(r.get("Farm Exemption for Security fencing prohibitions")),
            safe_str(r.get("Farm Exemption for Electrified fencing prohibitions")),
            safe_str(r.get("Equal apportionment of fencing costs between neighbours")),
            safe_str(r.get("Please list the cost apportionment bylaw number")),
            strip_html(r.get("Other notes about the fence bylaw")),
        ))

    db.commit()
    print(f"✓ Inserted {muni_count} municipalities, {bylaw_count} bylaw records")

    # ── 4. AMCTO Contacts ──
    acc_cursor.execute("SELECT * FROM [2 - AMCTO_OMD_ExportData]")
    cols = [c[0] for c in acc_cursor.description]
    contact_count = 0
    for row in acc_cursor.fetchall():
        cr = dict(zip(cols, row))
        db.execute("""
            INSERT INTO contacts (lookup_key, contact_type, title, department,
                first_name, last_name, email, phone,
                address_1, address_2, city, postal, fax,
                municipal_email, municipal_phone, website,
                households, population)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            safe_str(cr.get("LOOKUP")),
            safe_str(cr.get("Type")),
            safe_str(cr.get("Member Title")),
            safe_str(cr.get("Department")),
            safe_str(cr.get("First Name")),
            safe_str(cr.get("Last Name")),
            safe_str(cr.get("Email")),
            safe_str(cr.get("Member Phone")),
            safe_str(cr.get("Address 1")),
            safe_str(cr.get("Address 2")),
            safe_str(cr.get("City")),
            safe_str(cr.get("Postal")),
            safe_str(cr.get("Primary Municipal Fax")),
            safe_str(cr.get("Primary Municipal Email")),
            safe_str(cr.get("Primary Municipal Phone")),
            safe_str(cr.get("Website")),
            safe_int(cr.get("Households")),
            safe_int(cr.get("Population")),
        ))
        contact_count += 1
    db.commit()
    print(f"✓ Inserted {contact_count} contacts")

    # ── 5. Link contacts to municipalities ──
    db.execute("""
        UPDATE contacts SET municipality_id = (
            SELECT m.id FROM municipalities m WHERE m.lookup_key = contacts.lookup_key
        ) WHERE lookup_key IS NOT NULL
    """)
    linked = db.execute("SELECT COUNT(*) FROM contacts WHERE municipality_id IS NOT NULL").fetchone()[0]
    db.commit()
    print(f"✓ Linked {linked}/{contact_count} contacts to municipalities")

    # ── 6. Import scanner signals ──
    if os.path.exists(SIGNALS_CSV):
        try:
            sig_df = pd.read_csv(SIGNALS_CSV)
            sig_count = 0
            for _, s in sig_df.iterrows():
                db.execute("""
                    INSERT INTO scanner_signals (munid_raw, signal_type, discovered_date,
                        trigger_keyword, category, snippet, evidence_url)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    safe_str(s.get("munid")),
                    safe_str(s.get("signal_type", "scanner_hit")),
                    safe_str(s.get("discovered_date")),
                    safe_str(s.get("trigger_keyword")),
                    safe_str(s.get("category")),
                    safe_str(s.get("snippet")),
                    safe_str(s.get("evidence_url")),
                ))
                sig_count += 1
            db.commit()
            print(f"✓ Imported {sig_count} scanner signals")
        except Exception as e:
            print(f"  Warning: signals import: {e}")
    else:
        print("  Skipped signals (no signals.csv found)")

    # ═══════════════════════════════════════════════════════════
    # VALIDATION
    # ═══════════════════════════════════════════════════════════
    print("\n" + "=" * 60)
    print("VALIDATION")
    print("=" * 60)

    checks = [
        ("municipalities",     444),
        ("bylaws",             444 * 7),  # 7 categories × 444 munis
        ("bylaw_exemptions",   444 * 7),
        ("contacts",           7238),
    ]

    all_pass = True
    for table, expected in checks:
        actual = db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        status = "✓" if actual == expected else "✗"
        if actual != expected:
            all_pass = False
        print(f"  {status} {table}: {actual} rows (expected {expected})")

    # Detail tables
    for tbl in ["details_dc", "details_stormwater", "details_site_alt",
                "details_lgd", "details_trees", "details_chickens", "details_fences"]:
        actual = db.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
        status = "✓" if actual == 444 else "✗"
        if actual != 444:
            all_pass = False
        print(f"  {status} {tbl}: {actual} rows (expected 444)")

    # Spot checks
    print("\n  Spot checks:")
    for name in ["Augusta", "Aurora", "Toronto"]:
        row = db.execute("""
            SELECT m.name, b.category, be.exemption_status
            FROM municipalities m
            JOIN bylaws b ON b.municipality_id = m.id
            JOIN bylaw_exemptions be ON be.bylaw_id = b.id
            WHERE m.name = ? AND b.category = 'DC'
        """, (name,)).fetchone()
        if row:
            print(f"    {row[0]} DC exemption: {row[2]}")
        else:
            print(f"    {name}: NOT FOUND")

    print("\n" + ("✓ ALL CHECKS PASSED" if all_pass else "✗ SOME CHECKS FAILED"))
    print(f"\nDatabase saved to: {DB_PATH}")
    print(f"Size: {os.path.getsize(DB_PATH) / 1024:.0f} KB")

    acc.close()
    db.close()


if __name__ == "__main__":
    migrate()
