"""
db_utils.py — Shared database access layer for the Municipal Bylaw Database.

All Streamlit pages and scripts import from here to interact with bylaws.db.
"""

import os
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

def get_connection(db_path: str = None):
    url = st.secrets.get("DATABASE_URL", "postgresql://neondb_owner:npg_gjmiS41HEeXB@ep-fancy-resonance-amthrghm.c-5.us-east-1.aws.neon.tech/neondb?sslmode=require")
    return PgWrapper(url)


def resolve_yes_no(val):
    """Resolve an integer/string code to a human-readable Yes/No value."""
    if val is None:
        return "N/A"
    return YES_NO_LOOKUP.get(val, YES_NO_LOOKUP.get(str(val), str(val)))


# ── Queries ──

def get_municipalities(conn, filters=None):
    """Return a DataFrame of all municipalities, optionally filtered."""
    sql = "SELECT * FROM municipalities ORDER BY name"
    df = pd.read_sql_query(sql, conn)
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
    return pd.read_sql_query(sql, conn, params=params)


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
        detail_df = pd.read_sql_query(
            f"SELECT * FROM {detail_table} WHERE bylaw_id = %s",
            conn.conn, params=(bylaw_id,)
        )
    else:
        detail_df = pd.DataFrame()

    return bylaw_df, detail_df


def get_contacts(conn, municipality_id):
    """Return contacts for a municipality."""
    return pd.read_sql_query(
        "SELECT * FROM contacts WHERE municipality_id = %s ORDER BY title",
        conn.conn, params=(municipality_id,)
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
    return pd.read_sql_query(sql, conn.conn, params=tuple(params))


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
                   b.progress_label, b.bylaw_link,
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
                   b.progress_label, b.bylaw_link,
                   be.exemption_status, be.exemption_wording
            FROM municipalities m
            JOIN bylaws b ON b.municipality_id = m.id
            JOIN bylaw_exemptions be ON be.bylaw_id = b.id
            WHERE b.category = %s
            ORDER BY m.name
        """
    df = pd.read_sql_query(sql, conn.conn, params=(category,))
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
    return pd.read_sql_query(
        "SELECT * FROM audit_log ORDER BY timestamp DESC LIMIT %s",
        conn.conn, params=(limit,)
    )


def get_report_data(conn, scope='provincial', scope_value=None):
    """Fetch all data needed for report generation in efficient batch queries.

    Args:
        conn: SQLite connection
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
        munis = pd.read_sql_query(
            "SELECT * FROM municipalities ORDER BY geographic_area, name", conn)
    elif scope == 'county':
        munis = pd.read_sql_query(
            "SELECT * FROM municipalities WHERE geographic_area = %s ORDER BY name",
            conn.conn, params=(scope_value,))
    else:
        munis = pd.read_sql_query(
            "SELECT * FROM municipalities WHERE name = %s ORDER BY name",
            conn.conn, params=(scope_value,))

    if munis.empty:
        return empty

    muni_ids = munis['id'].tolist()
    ph = ','.join(['%s'] * len(muni_ids))

    # 2. Bylaws + exemptions
    bylaws = pd.read_sql_query(f"""
        SELECT b.*, be.exemption_status, be.exemption_wording,
               m.name as municipality_name, m.geographic_area
        FROM bylaws b
        LEFT JOIN bylaw_exemptions be ON be.bylaw_id = b.id
        LEFT JOIN municipalities m ON m.id = b.municipality_id
        WHERE b.municipality_id IN ({ph})
        ORDER BY m.name, b.category
    """, conn.conn, params=tuple(muni_ids))

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
            details[cat] = pd.read_sql_query(
                f"SELECT * FROM {table} WHERE bylaw_id IN ({bph})",
                conn.conn, params=tuple(bylaw_ids))
        else:
            details[cat] = pd.DataFrame()

    # 4. Contacts
    contacts = pd.read_sql_query(
        f"SELECT * FROM contacts WHERE municipality_id IN ({ph}) ORDER BY municipality_id",
        conn.conn, params=tuple(muni_ids))

    # 5. Scanner signals
    signals = pd.read_sql_query(f"""
        SELECT s.*, m.name as municipality_name, m.geographic_area
        FROM scanner_signals s
        LEFT JOIN municipalities m ON m.id = s.municipality_id
        WHERE s.municipality_id IN ({ph})
        ORDER BY s.discovered_date DESC
    """, conn.conn, params=tuple(muni_ids))

    return {
        'municipalities': munis, 'bylaws': bylaws, 'details': details,
        'contacts': contacts, 'signals': signals,
        'scope': scope, 'scope_value': scope_value,
    }


def export_map_dataframe(conn) -> pd.DataFrame:
    """Export the entire database into the wide flat structure expected by the map builder."""
    # Determine the parameter placeholder based on connection type
    is_sqlite = type(conn.conn).__name__ == "Connection" and hasattr(conn.conn, "execute")
    p = "?" if is_sqlite else "%s"

    munis = pd.read_sql_query("SELECT * FROM municipalities", conn.conn)
    rows = []

    for _, m in munis.iterrows():
        mid = m["id"]
        row = {
            "Municipality":        m["name"],
            "Municipal Status":    m["municipal_status"],
            "Geographic Area":     m["geographic_area"],
            "Website":             m["website"],
        }

        # ── DC ──
        dc = pd.read_sql_query(f"""
            SELECT b.*, be.exemption_status, be.exemption_wording, d.*
            FROM bylaws b
            LEFT JOIN bylaw_exemptions be ON be.bylaw_id = b.id
            LEFT JOIN details_dc d ON d.bylaw_id = b.id
            WHERE b.municipality_id = {p} AND b.category = 'DC'
        """, conn.conn, params=[mid])
        if not dc.empty:
            d = dc.iloc[0]
            row["Farm Exemption for Development Charges"] = d["exemption_status"]
            row["Wording of exemption"]       = d["exemption_wording"]
            row["Bylaw Name Development Charges"] = d["bylaw_name"]
            row["Link to DC Bylaw"]           = d["bylaw_link"]
            row["Date Bylaw Enacted (Regional)"] = d["date_enacted"]
            row["Expiry Date"]                = d["expiry_date"]
            row["Municipality Has Development Charges?"] = d.get("has_dc", "")

        # ── STORMWATER ──
        sw = pd.read_sql_query(f"""
            SELECT b.*, be.exemption_status, be.exemption_wording, d.*
            FROM bylaws b
            LEFT JOIN bylaw_exemptions be ON be.bylaw_id = b.id
            LEFT JOIN details_stormwater d ON d.bylaw_id = b.id
            WHERE b.municipality_id = {p} AND b.category = 'STORMWATER'
        """, conn.conn, params=[mid])
        if not sw.empty:
            d = sw.iloc[0]
            row["Farm Exemption for Stormwater Charges"] = d["exemption_status"]
            row["Bylaw Name Stormwater"]                 = d["bylaw_name"]
            row["Link to Stormwater Bylaw"]              = d["bylaw_link"]
            row["Expiry Date_1"]                         = d["expiry_date"]

        # ── SITE_ALT ──
        sa = pd.read_sql_query(f"""
            SELECT b.*, be.exemption_status, be.exemption_wording, d.*
            FROM bylaws b
            LEFT JOIN bylaw_exemptions be ON be.bylaw_id = b.id
            LEFT JOIN details_site_alt d ON d.bylaw_id = b.id
            WHERE b.municipality_id = {p} AND b.category = 'SITE_ALT'
        """, conn.conn, params=[mid])
        if not sa.empty:
            d = sa.iloc[0]
            row["Farm Exemption for SA"]      = d["exemption_status"]
            row["Exception Wording"]          = d["exemption_wording"]
            row["Bylaw Name Site Alteration"] = d["bylaw_name"]
            row["Link to SA Bylaw"]           = d["bylaw_link"]
            row["Expiry Date_2"]              = d["expiry_date"]
            row["SA Special Provision"]       = d.get("special_provision", "")

        # ── LGD ──
        lgd = pd.read_sql_query(f"""
            SELECT b.*, be.exemption_status, be.exemption_wording, d.*
            FROM bylaws b
            LEFT JOIN bylaw_exemptions be ON be.bylaw_id = b.id
            LEFT JOIN details_lgd d ON d.bylaw_id = b.id
            WHERE b.municipality_id = {p} AND b.category = 'LGD'
        """, conn.conn, params=[mid])
        if not lgd.empty:
            d = lgd.iloc[0]
            row["Has Livestock Guardian dog Definition"] = d.get("has_lgd_definition", "")
            row["Herding Dog Definition Exists"]         = d.get("has_herding_def", "")
            row["LDG and HD exempt from license fees"]   = d.get("exempt_license_fees", "")
            row["LDG and HD Collar and tag requirements"] = d.get("collar_tag_req", "")
            row["LDG and HD Exempt from barking restrictions"] = d.get("exempt_barking", "")
            row["Bylaw Name LGD"]      = d["bylaw_name"]
            row["Link to LGD Bylaw"]   = d["bylaw_link"]
            row["Expiry Date_3"]       = d["expiry_date"]
            row["Dog limit details"]   = d.get("dog_limit", "")

        # ── TREES ──
        trees = pd.read_sql_query(f"""
            SELECT b.*, be.exemption_status, be.exemption_wording, d.*
            FROM bylaws b
            LEFT JOIN bylaw_exemptions be ON be.bylaw_id = b.id
            LEFT JOIN details_trees d ON d.bylaw_id = b.id
            WHERE b.municipality_id = {p} AND b.category = 'TREES'
        """, conn.conn, params=[mid])

        if not trees.empty:
            d = trees.iloc[0]
            # Fall back to bylaw_exemptions if details_trees doesn't have it
            farm_exempt = str(d.get("farm_exemption") if pd.notna(d.get("farm_exemption")) else "")
            if not farm_exempt: farm_exempt = str(d.get("exemption_status") if pd.notna(d.get("exemption_status")) else "")
            
            except_word = str(d.get("farming_exception_wording") if pd.notna(d.get("farming_exception_wording")) else "")
            if not except_word: except_word = str(d.get("exemption_wording") if pd.notna(d.get("exemption_wording")) else "")
            
            row["Farm Exemption - Tree Cutting Bylaw"]  = farm_exempt
            row["Exception Wording_1"]                  = except_word
            row["Bylaw Name Forest Conservation"]       = d["bylaw_name"]
            row["Link to Forest Conservation Bylaw"]    = d["bylaw_link"]
            row["Expiry Date_4"]                        = d["expiry_date"]

        # ── CHICKENS ──
        chk = pd.read_sql_query(f"""
            SELECT b.*, be.exemption_status, be.exemption_wording, d.*
            FROM bylaws b
            LEFT JOIN bylaw_exemptions be ON be.bylaw_id = b.id
            LEFT JOIN details_chickens d ON d.bylaw_id = b.id
            WHERE b.municipality_id = {p} AND b.category = 'CHICKENS'
        """, conn.conn, params=[mid])
        if not chk.empty:
            d = chk.iloc[0]
            row["Can you Keep Backyard Chickens"] = d.get("can_keep", "")
            row["Licence Required"]               = d.get("licence_required", "")
            row["Welfare Requirements"]           = d.get("welfare_requirements", "")
            row["Bylaw Name Backyard Chicken"]    = d["bylaw_name"]
            row["Link to BYC Bylaw"]              = d["bylaw_link"]
            row["Expiry Date_5"]                  = d["expiry_date"]
            row["Limit on # of chickens"]         = d.get("chicken_limit", "")
            row["Are roosters allowed"]           = d.get("roosters_allowed", "")

        # ── FENCES ──
        fen = pd.read_sql_query(f"""
            SELECT b.*, be.exemption_status, be.exemption_wording, d.*
            FROM bylaws b
            LEFT JOIN bylaw_exemptions be ON be.bylaw_id = b.id
            LEFT JOIN details_fences d ON d.bylaw_id = b.id
            WHERE b.municipality_id = {p} AND b.category = 'FENCES'
        """, conn.conn, params=[mid])
        if not fen.empty:
            d = fen.iloc[0]
            row["Municipality Has Fence Bylaw"] = d.get("has_fence_bylaw", "")
            row["Farm Exemption for Security fencing prohibitions"] = d.get("security_fencing_exemption", "")
            row["Farm Exemption for Electrified fencing prohibitions"] = d.get("electrified_fencing_exemption", "")
            row["Link to Fence Bylaw"]        = d["bylaw_link"]
            row["Date Bylaw Enacted 8"]       = d["date_enacted"]
            row["Expiry Date 8"]              = d["expiry_date"]

        rows.append(row)

    return pd.DataFrame(rows).fillna("")
