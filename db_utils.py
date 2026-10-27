"""
db_utils.py — Shared database access layer for the Municipal Bylaw Database.

All Streamlit pages and scripts import from here to interact with bylaws.db.
"""

import os
import sqlite3
import psycopg2
import psycopg2.extras
import streamlit as st
import datetime
import pandas as pd
import numpy as np

# Register numpy types to make psycopg2 compatible with pandas
psycopg2.extensions.register_adapter(np.int64, psycopg2.extensions.AsIs)
psycopg2.extensions.register_adapter(np.float64, psycopg2.extensions.AsIs)

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bylaws.db")

# Lookup map for integer-coded Yes/No fields from Access
YES_NO_LOOKUP = {
    1: "Yes", "1": "Yes",
    2: "No", "2": "No",
    3: "NOT KNOWN", "3": "NOT KNOWN",
    4: "N/A", "4": "N/A",
    5: "No explicit exemption found", "5": "No explicit exemption found",
}


class PgWrapper:
    def __init__(self, url):
        self.conn = psycopg2.connect(url)
        self.conn.autocommit = False

    def execute(self, query, params=tuple()):
        query = query.replace('[', '"').replace(']', '"')
        query = query.replace('?', '%s')
        cur = self.conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        if isinstance(params, list): params = tuple(params)
        cur.execute(query, params if params else tuple())
        return cur

    def commit(self):
        self.conn.commit()

    def close(self):
        self.conn.close()

    def cursor(self, *args, **kwargs):
        return self.conn.cursor(*args, **kwargs)


class SqliteWrapper:
    def __init__(self, path):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row

    def execute(self, query, params=tuple()):
        query = query.replace('[', '"').replace(']', '"')
        query = query.replace('%s', '?')
        cur = self.conn.cursor()
        if isinstance(params, list): params = tuple(params)
        cur.execute(query, params if params else tuple())
        return cur

    def commit(self):
        self.conn.commit()

    def close(self):
        self.conn.close()

    def cursor(self, *args, **kwargs):
        return self.conn.cursor(*args, **kwargs)


def get_connection(db_path: str = None):
    if db_path and str(db_path).endswith('.db') and os.path.exists(db_path):
        return SqliteWrapper(db_path)
    url = st.secrets.get("DATABASE_URL", "postgresql://neondb_owner:npg_gjmiS41HEeXB@ep-fancy-resonance-amthrghm.c-5.us-east-1.aws.neon.tech/neondb?sslmode=require")
    return PgWrapper(url)


def _read_sql(conn, sql, params=None):
    """Execute a SQL query via pandas using the underlying DB-API connection and appropriate placeholders."""
    raw_conn = conn.conn if hasattr(conn, "conn") else conn
    if isinstance(raw_conn, sqlite3.Connection):
        sql = sql.replace("%s", "?")
    return pd.read_sql_query(sql, raw_conn, params=params)


def resolve_yes_no(val):
    """Resolve an integer/string code to a human-readable Yes/No value."""
    if val is None:
        return "N/A"
    return YES_NO_LOOKUP.get(val, YES_NO_LOOKUP.get(str(val), str(val)))


# ── Queries ──

def get_municipalities(conn, filters=None):
    """Return a DataFrame of all municipalities, optionally filtered."""
    sql = "SELECT * FROM municipalities ORDER BY name"
    df = _read_sql(conn, sql)
    if filters:
        if 'status' in filters and filters['status']:
            df = df[df['municipal_status'] == filters['status']]
        if 'area' in filters and filters['area']:
            df = df[df['geographic_area'] == filters['area']]
        if 'search' in filters and filters['search']:
            df = df[df['name'].str.contains(filters['search'], case=False, na=False)]
    return df


def get_bylaws(conn, municipality_id=None, category=None):
    """Return bylaws with exemption info, optionally filtered."""
    sql = """
        SELECT b.*, be.exemption_status, be.exemption_wording
        FROM bylaws b
        LEFT JOIN bylaw_exemptions be ON be.bylaw_id = b.id
        WHERE 1=1
    """
    params = []
    if municipality_id:
        sql += " AND b.municipality_id = %s"
        params.append(municipality_id)
    if category:
        sql += " AND b.category = %s"
        params.append(category)
    sql += " ORDER BY b.category"
    return _read_sql(conn, sql, params=tuple(params) if params else None)


def get_bylaws_with_details(conn, municipality_id, category):
    """Return bylaw + its category-specific detail row."""
    bylaw_df = get_bylaws(conn, municipality_id, category)
    if bylaw_df.empty:
        return bylaw_df, pd.DataFrame()

    bylaw_id = int(bylaw_df.iloc[0]['id'])
    detail_table = {
        'DC': 'details_dc',
        'STORMWATER': 'details_stormwater',
        'SITE_ALT': 'details_site_alt',
        'LGD': 'details_lgd',
        'TREES': 'details_trees',
        'CHICKENS': 'details_chickens',
        'FENCES': 'details_fences',
    }.get(category)

    if detail_table:
        detail_df = _read_sql(
            conn,
            f"SELECT * FROM {detail_table} WHERE bylaw_id = %s",
            params=(bylaw_id,)
        )
    else:
        detail_df = pd.DataFrame()

    return bylaw_df, detail_df


def get_contacts(conn, municipality_id):
    """Return contacts for a municipality."""
    return _read_sql(
        conn,
        "SELECT * FROM contacts WHERE municipality_id = %s ORDER BY title",
        params=(municipality_id,)
    )


def get_signals(conn, municipality_id=None, days=90):
    """Return recent scanner signals, optionally for one municipality."""
    cutoff = (datetime.datetime.now() - datetime.timedelta(days=days)).strftime("%Y-%m-%d")
    sql = "SELECT * FROM scanner_signals WHERE discovered_date >= %s"
    params = [cutoff]
    if municipality_id:
        sql += " AND municipality_id = %s"
        params.append(municipality_id)
    sql += " ORDER BY discovered_date DESC"
    return _read_sql(conn, sql, params=tuple(params))


def get_category_summary(conn, category):
    """Return a summary DataFrame for one category across all municipalities.
    
    Joins the category-specific detail table to include all tracked fields.
    """
    detail_table = {
        'DC': 'details_dc',
        'STORMWATER': 'details_stormwater',
        'SITE_ALT': 'details_site_alt',
        'LGD': 'details_lgd',
        'TREES': 'details_trees',
        'CHICKENS': 'details_chickens',
        'FENCES': 'details_fences',
    }.get(category)

    if detail_table:
        sql = f"""
            SELECT m.id, m.name, m.municipal_status, m.geographic_area,
                   b.bylaw_name, b.date_enacted, b.expiry_date, b.expiry_notes,
                   b.progress_label, b.bylaw_link, b.other_notes,
                   be.exemption_status, be.exemption_wording,
                   d.*
            FROM municipalities m
            JOIN bylaws b ON b.municipality_id = m.id
            JOIN bylaw_exemptions be ON be.bylaw_id = b.id
            LEFT JOIN {detail_table} d ON d.bylaw_id = b.id
            WHERE b.category = %s
            ORDER BY m.name
        """
    else:
        sql = """
            SELECT m.id, m.name, m.municipal_status, m.geographic_area,
                   b.bylaw_name, b.date_enacted, b.expiry_date, b.expiry_notes,
                   b.progress_label, b.bylaw_link, b.other_notes,
                   be.exemption_status, be.exemption_wording
            FROM municipalities m
            JOIN bylaws b ON b.municipality_id = m.id
            JOIN bylaw_exemptions be ON be.bylaw_id = b.id
            WHERE b.category = %s
            ORDER BY m.name
        """
    df = _read_sql(conn, sql, params=(category,))
    # Drop duplicate columns from detail table join (id, bylaw_id)
    # PostgreSQL returns them as separate columns; keep only the first 'id' (municipality)
    if df.columns.duplicated().any():
        df = df.loc[:, ~df.columns.duplicated()]
    # Drop bylaw_id if present (internal FK, not useful for display)
    if 'bylaw_id' in df.columns:
        df = df.drop(columns=['bylaw_id'])
    # Resolve integer codes to labels
    df['exemption_status'] = df['exemption_status'].apply(resolve_yes_no)
    return df


def get_geographic_areas(conn):
    """Return a sorted list of unique geographic areas."""
    rows = conn.execute(
        "SELECT DISTINCT geographic_area FROM municipalities WHERE geographic_area IS NOT NULL ORDER BY geographic_area"
    ).fetchall()
    return [r[0] for r in rows]


def update_record(conn, table, record_id, field, new_value, user='admin'):
    """Update a single field and log the change."""
    # Get old value
    old = conn.execute(
        f'SELECT "{field}" FROM {table} WHERE id = %s', (record_id,)
    ).fetchone()
    old_value = old[0] if old else None

    # Update
    conn.execute(
        f'UPDATE {table} SET "{field}" = %s WHERE id = %s',
        (new_value, record_id)
    )

    # Audit log
    conn.execute("""
        INSERT INTO audit_log (timestamp, user_name, table_name, record_id, field_name, old_value, new_value)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, (
        datetime.datetime.now().isoformat(),
        user, table, record_id, field,
        str(old_value) if old_value is not None else None,
        str(new_value) if new_value is not None else None,
    ))
    conn.commit()


def get_audit_log(conn, limit=50):
    """Return recent audit log entries."""
    return _read_sql(
        conn,
        "SELECT * FROM audit_log ORDER BY timestamp DESC LIMIT %s",
        params=(limit,)
    )


def get_report_data(conn, scope='provincial', scope_value=None):
    """Fetch all data needed for report generation in efficient batch queries.

    Args:
        conn: SQLite or PostgreSQL wrapper connection
        scope: 'provincial', 'county', or 'municipality'
        scope_value: county name or municipality name

    Returns:
        dict with keys: municipalities, bylaws, details, contacts, signals, scope, scope_value
    """
    empty = {'municipalities': pd.DataFrame(), 'bylaws': pd.DataFrame(),
             'details': {}, 'contacts': pd.DataFrame(), 'signals': pd.DataFrame(),
             'scope': scope, 'scope_value': scope_value}

    # 1. Municipalities
    if scope == 'provincial':
        munis = _read_sql(
            conn, "SELECT * FROM municipalities ORDER BY geographic_area, name")
    elif scope == 'county':
        munis = _read_sql(
            conn,
            "SELECT * FROM municipalities WHERE geographic_area = %s ORDER BY name",
            params=(scope_value,))
    else:
        munis = _read_sql(
            conn,
            "SELECT * FROM municipalities WHERE name = %s ORDER BY name",
            params=(scope_value,))

    if munis.empty:
        return empty

    muni_ids = munis['id'].tolist()
    ph = ','.join(['%s'] * len(muni_ids))

    # 2. Bylaws + exemptions
    bylaws = _read_sql(conn, f"""
        SELECT b.*, be.exemption_status, be.exemption_wording,
               m.name as municipality_name, m.geographic_area
        FROM bylaws b
        LEFT JOIN bylaw_exemptions be ON be.bylaw_id = b.id
        LEFT JOIN municipalities m ON m.id = b.municipality_id
        WHERE b.municipality_id IN ({ph})
        ORDER BY m.name, b.category
    """, params=tuple(muni_ids))

    # 3. Details for each category
    bylaw_ids = bylaws['id'].tolist() if not bylaws.empty else []
    bph = ','.join(['%s'] * len(bylaw_ids)) if bylaw_ids else '0'

    detail_tables = {
        'DC': 'details_dc', 'STORMWATER': 'details_stormwater',
        'SITE_ALT': 'details_site_alt', 'LGD': 'details_lgd',
        'TREES': 'details_trees', 'CHICKENS': 'details_chickens',
        'FENCES': 'details_fences',
    }
    details = {}
    for cat, table in detail_tables.items():
        if bylaw_ids:
            details[cat] = _read_sql(
                conn,
                f"SELECT * FROM {table} WHERE bylaw_id IN ({bph})",
                params=tuple(bylaw_ids))
        else:
            details[cat] = pd.DataFrame()

    # 4. Contacts
    contacts = _read_sql(
        conn,
        f"SELECT * FROM contacts WHERE municipality_id IN ({ph}) ORDER BY municipality_id",
        params=tuple(muni_ids))

    # 5. Scanner signals
    signals = _read_sql(conn, f"""
        SELECT s.*, m.name as municipality_name, m.geographic_area
        FROM scanner_signals s
        LEFT JOIN municipalities m ON m.id = s.municipality_id
        WHERE s.municipality_id IN ({ph})
        ORDER BY s.discovered_date DESC
    """, params=tuple(muni_ids))

    return {
        'municipalities': munis, 'bylaws': bylaws, 'details': details,
        'contacts': contacts, 'signals': signals,
        'scope': scope, 'scope_value': scope_value,
    }


def export_map_dataframe(conn) -> pd.DataFrame:
    """Export the entire database into the wide flat structure expected by the map builder.

    Uses 8 batch queries (instead of 3,108 per-municipality queries) and exports
    column names aligned with META_BY_LABEL in the map pages.
    """
    munis = _read_sql(conn, "SELECT * FROM municipalities")

    def _fetch_cat_map(cat_code: str, detail_table: str) -> dict:
        df_cat = _read_sql(conn, f"""
            SELECT b.municipality_id, b.bylaw_name, b.bylaw_link, b.date_enacted, b.expiry_date,
                   be.exemption_status, be.exemption_wording, d.*
            FROM bylaws b
            LEFT JOIN bylaw_exemptions be ON be.bylaw_id = b.id
            LEFT JOIN {detail_table} d ON d.bylaw_id = b.id
            WHERE b.category = %s
        """, params=(cat_code,))
        if df_cat.empty:
            return {}
        if df_cat.columns.duplicated().any():
            df_cat = df_cat.loc[:, ~df_cat.columns.duplicated()]
        df_cat = df_cat.drop_duplicates(subset=["municipality_id"], keep="first")
        return {int(r["municipality_id"]): r for _, r in df_cat.iterrows()}

    dc_map    = _fetch_cat_map("DC",         "details_dc")
    sw_map    = _fetch_cat_map("STORMWATER", "details_stormwater")
    sa_map    = _fetch_cat_map("SITE_ALT",   "details_site_alt")
    lgd_map   = _fetch_cat_map("LGD",        "details_lgd")
    trees_map = _fetch_cat_map("TREES",      "details_trees")
    chk_map   = _fetch_cat_map("CHICKENS",   "details_chickens")
    fen_map   = _fetch_cat_map("FENCES",     "details_fences")

    rows = []
    for _, m in munis.iterrows():
        mid = int(m["id"])
        row = {
            "Municipality":     m["name"],
            "Municipal Status": m["municipal_status"],
            "Geographic Area":  m["geographic_area"],
            "Website":          m["website"],
        }

        # ── DC ──
        if mid in dc_map:
            d = dc_map[mid]
            row["Farm Exemption for Development Charges"] = d["exemption_status"]
            row["Wording of exemption"]                   = d["exemption_wording"]
            row["Bylaw Name Development Charges"]         = d["bylaw_name"]
            row["Link to DC Bylaw"]                       = d["bylaw_link"]
            row["Date Bylaw Enacted (Regional)"]          = d["date_enacted"]
            row["Expiry Date"]                            = d["expiry_date"]
            row["Municipality Has Development Charges?"]  = d.get("has_dc", "")

        # ── STORMWATER ──
        if mid in sw_map:
            d = sw_map[mid]
            row["Farm Exemption for Stormwater Charges"]  = d["exemption_status"]
            row["Bylaw Name Stormwater"]                  = d["bylaw_name"]
            row["Link to Storm Water bylaw"]              = d["bylaw_link"]
            row["Date Bylaw Enacted2 (Regional)"]         = d["date_enacted"]
            row["Expiry date2"]                           = d["expiry_date"]

        # ── SITE_ALT ──
        if mid in sa_map:
            d = sa_map[mid]
            row["Farm Exemption for SA"]                  = d["exemption_status"]
            row["Exception Wording"]                      = d["exemption_wording"]
            row["Bylaw Name Site Alteration"]             = d["bylaw_name"]
            row["Link to site alteration & fill bylaw"]   = d["bylaw_link"]
            row["Date Bylaw Enacted4 (Regional)"]         = d["date_enacted"]
            row["Expiry date 4"]                          = d["expiry_date"]
            row["SA Special Provision"]                   = d.get("special_provision", "")

        # ── LGD ──
        if mid in lgd_map:
            d = lgd_map[mid]
            row["Has Livestock Guardian dog Definition"]         = d.get("has_lgd_definition", "")
            row["Herding Dog Definition Exists"]                 = d.get("has_herding_def", "")
            row["LDG and HD exempt from license fees"]           = d.get("exempt_license_fees", "")
            row["LDG and HD Collar and tag requirements"]        = d.get("collar_tag_req", "")
            row["LDG and HD Exempt from barking restrictions"]   = d.get("exempt_barking", "")
            row["Bylaw Name LGD"]                                = d["bylaw_name"]
            row["Livestock Guardian Dog bylaw link"]             = d["bylaw_link"]
            row["Date Bylaw Enacted 5 (Regional)"]               = d["date_enacted"]
            row["Expiry Date 5"]                                 = d["expiry_date"]
            row["Dog limit details"]                             = d.get("dog_limit", "")

        # ── TREES ──
        if mid in trees_map:
            d = trees_map[mid]
            farm_exempt = str(d.get("farm_exemption") if pd.notna(d.get("farm_exemption")) else "")
            if not farm_exempt:
                farm_exempt = str(d.get("exemption_status") if pd.notna(d.get("exemption_status")) else "")

            except_word = str(d.get("farming_exception_wording") if pd.notna(d.get("farming_exception_wording")) else "")
            if not except_word:
                except_word = str(d.get("exemption_wording") if pd.notna(d.get("exemption_wording")) else "")

            row["Farm Exemption - Tree Cutting Bylaw"]    = farm_exempt
            row["Exception Wording_1"]                    = except_word
            row["Bylaw Name Forest Conservation"]         = d["bylaw_name"]
            row["Tree Cutting Bylaw Link"]                = d["bylaw_link"]
            row["Date Bylaw Enacted 6 (Regional)"]        = d["date_enacted"]
            row["Expiry Date 6"]                          = d["expiry_date"]

        # ── CHICKENS ──
        if mid in chk_map:
            d = chk_map[mid]
            row["Can you Keep Backyard Chickens"]         = d.get("can_keep", "")
            row["Licence Required"]                       = d.get("licence_required", "")
            row["Welfare Requirements"]                   = d.get("welfare_requirements", "")
            row["Bylaw Name Backyard Chicken"]            = d["bylaw_name"]
            row["Backyard Chicken Bylaw Link"]            = d["bylaw_link"]
            row["Date Bylaw Enacted 7 (Regional)"]        = d["date_enacted"]
            row["Expiry Date 7"]                          = d["expiry_date"]
            row["Limit on # of chickens"]                 = d.get("chicken_limit", "")
            row["Are roosters allowed"]                   = d.get("roosters_allowed", "")

        # ── FENCES ──
        if mid in fen_map:
            d = fen_map[mid]
            row["Municipality Has Fence Bylaw"]                          = d.get("has_fence_bylaw", "")
            row["Farm Exemption for Security fencing prohibitions"]      = d.get("security_fencing_exemption", "")
            row["Farm Exemption for Electrified fencing prohibitions"]   = d.get("electrified_fencing_exemption", "")
            row["Bylaw Name Fence"]                                      = d["bylaw_name"]
            row["Link to Fence Bylaw"]                                   = d["bylaw_link"]
            row["Date Bylaw Enacted 8"]                                  = d["date_enacted"]
            row["Expiry Date 8"]                                         = d["expiry_date"]

        rows.append(row)

    return pd.DataFrame(rows).fillna("")
