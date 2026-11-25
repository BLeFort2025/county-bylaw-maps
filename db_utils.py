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


# Lookup map for semicolon-delimited Access Chicken Welfare codes (List 10 - Chicken Welfare Req)
WELFARE_LOOKUP = {
    "1": "NONE",
    "2": "Food",
    "3": "Enclosure",
    "4": "Water",
    "5": "Land",
    "6": "Other",
    "7": "Specific Requirements",
    "8": "Non-Specific Requirements",
    "9": "Vet Care - as needed",
    "10": "N/A",
    "11": "Biosecurity measures",
}


def resolve_welfare_codes(val) -> str:
    """Resolve semicolon-delimited Access Chicken Welfare codes (e.g. '2;3;4;5') to human-readable text."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return "N/A"
    s = str(val).strip()
    if not s or s.lower() in ("nan", "none"):
        return "N/A"
    if s.upper() in ("NO", "N/A", "NOT KNOWN", "YES"):
        return s
    parts = [p.strip() for p in s.split(";") if p.strip()]
    resolved = [WELFARE_LOOKUP.get(p, p) for p in parts]
    return ", ".join(resolved) if resolved else "N/A"


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
    if 'has_dc' in df.columns:
        df['has_dc'] = df['has_dc'].apply(resolve_yes_no)
    if 'can_keep' in df.columns:
        df['can_keep'] = df['can_keep'].apply(resolve_yes_no)
    if 'welfare_requirements' in df.columns:
        df['welfare_requirements'] = df['welfare_requirements'].apply(resolve_welfare_codes)
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
            row["SA NFP Exemption Scope"]                 = d.get("nfp_exemption_scope", "")
            row["SA Drainage Act Exempt"]                 = d.get("drainage_act_exempt", "")
            row["SA O. Reg. 406/19"]                      = d.get("excess_soil_reg_406_19", "")
            row["SA Fill Captures Ag Materials"]          = d.get("fill_captures_ag_materials", "")

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


# ═══════════════════════════════════════════════════════════════
# County Federation Weekly Digest Subscriptions & Sent Log
# ═══════════════════════════════════════════════════════════════

DEFAULT_BCC_EMAIL = "ben.lefort@ofa.on.ca"
DEFAULT_NEON_URL = "postgresql://neondb_owner:npg_gjmiS41HEeXB@ep-fancy-resonance-amthrghm.c-5.us-east-1.aws.neon.tech/neondb?sslmode=require"


def get_cli_connection(prefer_postgres: bool = True):
    """Connect to Neon PostgreSQL (or local SQLite fallback) safely outside Streamlit."""
    if prefer_postgres:
        url = os.environ.get("DATABASE_URL", "").strip()
        if not url:
            secrets_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".streamlit", "secrets.toml")
            if os.path.exists(secrets_path):
                try:
                    import tomllib
                    with open(secrets_path, "rb") as fh:
                        sec = tomllib.load(fh)
                    url = str(sec.get("DATABASE_URL", "")).strip()
                except Exception:
                    pass
        url = url or DEFAULT_NEON_URL
        try:
            return PgWrapper(url)
        except Exception:
            pass
    return SqliteWrapper(DB_PATH)


def _is_sqlite_conn(conn) -> bool:
    raw = conn.conn if hasattr(conn, "conn") else conn
    return isinstance(raw, sqlite3.Connection)


def ensure_digest_tables(conn) -> None:
    """Create county digest subscription, watchlist, and sent-log tables on SQLite or PostgreSQL."""
    pk = "INTEGER PRIMARY KEY AUTOINCREMENT" if _is_sqlite_conn(conn) else "SERIAL PRIMARY KEY"
    stmts = [
        f"""
        CREATE TABLE IF NOT EXISTS county_subscriptions (
            id                    {pk},
            federation_name       TEXT NOT NULL,
            geographic_area       TEXT NOT NULL,
            municipality_ids_json TEXT,
            exclude_large_cities  INTEGER DEFAULT 1,
            recipient_emails      TEXT NOT NULL,
            cc_emails             TEXT DEFAULT '',
            bcc_emails            TEXT DEFAULT '{DEFAULT_BCC_EMAIL}',
            send_empty_digest     INTEGER DEFAULT 1,
            is_test_profile       INTEGER DEFAULT 0,
            active                INTEGER DEFAULT 1,
            notes                 TEXT DEFAULT '',
            created_at            TEXT,
            updated_at            TEXT
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS county_watchlist_keywords (
            id              {pk},
            subscription_id INTEGER NOT NULL REFERENCES county_subscriptions(id) ON DELETE CASCADE,
            keyword         TEXT NOT NULL,
            is_negative     INTEGER DEFAULT 0,
            UNIQUE(subscription_id, keyword, is_negative)
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS county_digest_sent_log (
            id                {pk},
            subscription_id   INTEGER NOT NULL REFERENCES county_subscriptions(id) ON DELETE CASCADE,
            run_date          TEXT NOT NULL,
            municipality_id   INTEGER,
            municipality_name TEXT,
            doc_url           TEXT,
            doc_type          TEXT,
            content_hash      TEXT,
            matched_keywords  TEXT,
            recipients_sent   TEXT,
            delivery_mode     TEXT DEFAULT 'live',
            sent_at           TEXT NOT NULL
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_digest_kw_sub ON county_watchlist_keywords(subscription_id)",
        "CREATE INDEX IF NOT EXISTS idx_digest_log_sub ON county_digest_sent_log(subscription_id)",
        "CREATE INDEX IF NOT EXISTS idx_digest_log_hash ON county_digest_sent_log(subscription_id, content_hash)",
    ]
    for stmt in stmts:
        conn.execute(stmt)
    conn.commit()


def list_county_subscriptions(conn, active_only: bool = False) -> list[dict]:
    """Return all county digest subscriptions with their positive/negative watchlists."""
    import json

    ensure_digest_tables(conn)
    sql = "SELECT * FROM county_subscriptions"
    if active_only:
        sql += " WHERE active = 1"
    sql += " ORDER BY is_test_profile ASC, geographic_area ASC, federation_name ASC"
    sub_df = _read_sql(conn, sql)
    if sub_df.empty:
        return []

    kw_df = _read_sql(conn, "SELECT subscription_id, keyword, is_negative FROM county_watchlist_keywords ORDER BY id ASC")
    kw_by_sub: dict[int, tuple[list[str], list[str]]] = {}
    for _, r in kw_df.iterrows():
        sid = int(r["subscription_id"])
        kw_by_sub.setdefault(sid, ([], []))
        if int(r["is_negative"] or 0) == 1:
            kw_by_sub[sid][1].append(str(r["keyword"]))
        else:
            kw_by_sub[sid][0].append(str(r["keyword"]))

    results = []
    for _, r in sub_df.iterrows():
        sid = int(r["id"])
        pos, neg = kw_by_sub.get(sid, ([], []))
        raw_ids = r.get("municipality_ids_json")
        try:
            m_ids = json.loads(raw_ids) if raw_ids else []
        except Exception:
            m_ids = []
        results.append({
            "id": sid,
            "federation_name": str(r.get("federation_name") or ""),
            "geographic_area": str(r.get("geographic_area") or ""),
            "municipality_ids": [int(x) for x in m_ids],
            "exclude_large_cities": bool(int(r.get("exclude_large_cities") if pd.notna(r.get("exclude_large_cities")) else 1)),
            "recipient_emails": str(r.get("recipient_emails") or ""),
            "cc_emails": str(r.get("cc_emails") or ""),
            "bcc_emails": str(r.get("bcc_emails") if pd.notna(r.get("bcc_emails")) else DEFAULT_BCC_EMAIL),
            "send_empty_digest": bool(int(r.get("send_empty_digest") if pd.notna(r.get("send_empty_digest")) else 1)),
            "is_test_profile": bool(int(r.get("is_test_profile") if pd.notna(r.get("is_test_profile")) else 0)),
            "active": bool(int(r.get("active") if pd.notna(r.get("active")) else 1)),
            "notes": str(r.get("notes") or ""),
            "created_at": str(r.get("created_at") or ""),
            "updated_at": str(r.get("updated_at") or ""),
            "keywords": pos,
            "negative_keywords": neg,
        })
    return results


def get_county_subscription(conn, subscription_id: int) -> dict | None:
    for sub in list_county_subscriptions(conn, active_only=False):
        if sub["id"] == int(subscription_id):
            return sub
    return None


def upsert_county_subscription(
    conn,
    sub: dict,
    keywords: list[str],
    negative_keywords: list[str] | None = None,
) -> int:
    """Create or update a County Federation subscription and its keyword watchlists."""
    import json

    ensure_digest_tables(conn)
    now_iso = datetime.datetime.now().isoformat(timespec="seconds")
    muni_ids = [int(x) for x in (sub.get("municipality_ids") or [])]
    muni_ids_json = json.dumps(muni_ids)

    fed_name = str(sub.get("federation_name") or "").strip()
    geo_area = str(sub.get("geographic_area") or "").strip()
    excl_cities = 1 if sub.get("exclude_large_cities", True) else 0
    recip = str(sub.get("recipient_emails") or "").strip()
    cc = str(sub.get("cc_emails") or "").strip()
    bcc = str(sub.get("bcc_emails", DEFAULT_BCC_EMAIL) or "").strip()
    send_empty = 1 if sub.get("send_empty_digest", True) else 0
    is_test = 1 if sub.get("is_test_profile", False) else 0
    active = 1 if sub.get("active", True) else 0
    notes = str(sub.get("notes") or "").strip()

    sub_id = sub.get("id")
    if sub_id:
        sub_id = int(sub_id)
        conn.execute(
            """
            UPDATE county_subscriptions
               SET federation_name = %s,
                   geographic_area = %s,
                   municipality_ids_json = %s,
                   exclude_large_cities = %s,
                   recipient_emails = %s,
                   cc_emails = %s,
                   bcc_emails = %s,
                   send_empty_digest = %s,
                   is_test_profile = %s,
                   active = %s,
                   notes = %s,
                   updated_at = %s
             WHERE id = %s
            """,
            (
                fed_name, geo_area, muni_ids_json, excl_cities,
                recip, cc, bcc, send_empty, is_test, active, notes, now_iso, sub_id,
            ),
        )
    else:
        if _is_sqlite_conn(conn):
            cur = conn.execute(
                """
                INSERT INTO county_subscriptions (
                    federation_name, geographic_area, municipality_ids_json, exclude_large_cities,
                    recipient_emails, cc_emails, bcc_emails, send_empty_digest,
                    is_test_profile, active, notes, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    fed_name, geo_area, muni_ids_json, excl_cities,
                    recip, cc, bcc, send_empty, is_test, active, notes, now_iso, now_iso,
                ),
            )
            sub_id = int(cur.lastrowid)
        else:
            cur = conn.execute(
                """
                INSERT INTO county_subscriptions (
                    federation_name, geographic_area, municipality_ids_json, exclude_large_cities,
                    recipient_emails, cc_emails, bcc_emails, send_empty_digest,
                    is_test_profile, active, notes, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    fed_name, geo_area, muni_ids_json, excl_cities,
                    recip, cc, bcc, send_empty, is_test, active, notes, now_iso, now_iso,
                ),
            )
            sub_id = int(cur.fetchone()[0])

    # Replace watchlists cleanly
    conn.execute("DELETE FROM county_watchlist_keywords WHERE subscription_id = %s", (sub_id,))
    seen_pos = set()
    for kw in (keywords or []):
        k = str(kw).strip()
        if k and k.lower() not in seen_pos:
            seen_pos.add(k.lower())
            conn.execute(
                "INSERT INTO county_watchlist_keywords (subscription_id, keyword, is_negative) VALUES (%s, %s, 0)",
                (sub_id, k),
            )

    seen_neg = set()
    for nkw in (negative_keywords or []):
        k = str(nkw).strip()
        if k and k.lower() not in seen_neg:
            seen_neg.add(k.lower())
            conn.execute(
                "INSERT INTO county_watchlist_keywords (subscription_id, keyword, is_negative) VALUES (%s, %s, 1)",
                (sub_id, k),
            )

    conn.commit()
    return sub_id


def delete_county_subscription(conn, subscription_id: int) -> None:
    ensure_digest_tables(conn)
    sid = int(subscription_id)
    conn.execute("DELETE FROM county_watchlist_keywords WHERE subscription_id = %s", (sid,))
    conn.execute("DELETE FROM county_digest_sent_log WHERE subscription_id = %s", (sid,))
    conn.execute("DELETE FROM county_subscriptions WHERE id = %s", (sid,))
    conn.commit()


def get_sent_content_hashes(conn, subscription_id: int) -> set[str]:
    """Return all content hashes already delivered in live runs for this subscription."""
    ensure_digest_tables(conn)
    df = _read_sql(
        conn,
        "SELECT DISTINCT content_hash FROM county_digest_sent_log WHERE subscription_id = %s AND delivery_mode = 'live' AND content_hash IS NOT NULL",
        params=(int(subscription_id),),
    )
    if df.empty:
        return set()
    return set(df["content_hash"].dropna().astype(str).tolist())


def record_digest_sent(
    conn,
    subscription_id: int,
    entries: list[dict],
    run_date: str,
    recipients_sent: str,
    delivery_mode: str = "live",
) -> None:
    """Persist sent digest items (or an ALL_CLEAR_SUMMARY row) for deduplication and audit."""
    ensure_digest_tables(conn)
    now_iso = datetime.datetime.now().isoformat(timespec="seconds")
    sid = int(subscription_id)

    if not entries:
        conn.execute(
            """
            INSERT INTO county_digest_sent_log (
                subscription_id, run_date, municipality_id, municipality_name,
                doc_url, doc_type, content_hash, matched_keywords,
                recipients_sent, delivery_mode, sent_at
            ) VALUES (%s, %s, NULL, %s, '', 'ALL_CLEAR_SUMMARY', %s, '', %s, %s, %s)
            """,
            (sid, run_date, "All Monitored Municipalities", f"ALL_CLEAR_{run_date}", recipients_sent, delivery_mode, now_iso),
        )
    else:
        for e in entries:
            conn.execute(
                """
                INSERT INTO county_digest_sent_log (
                    subscription_id, run_date, municipality_id, municipality_name,
                    doc_url, doc_type, content_hash, matched_keywords,
                    recipients_sent, delivery_mode, sent_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    sid,
                    run_date,
                    e.get("municipality_id"),
                    str(e.get("municipality_name") or ""),
                    str(e.get("doc_url") or ""),
                    str(e.get("doc_type") or ""),
                    str(e.get("content_hash") or ""),
                    ", ".join(e.get("matched_keywords") or []),
                    recipients_sent,
                    delivery_mode,
                    now_iso,
                ),
            )
    conn.commit()


def get_digest_sent_history(conn, subscription_id: int | None = None, limit: int = 100) -> pd.DataFrame:
    ensure_digest_tables(conn)
    sql = """
        SELECT l.id, l.subscription_id, s.federation_name, s.geographic_area,
               l.run_date, l.municipality_name, l.doc_type, l.matched_keywords,
               l.recipients_sent, l.delivery_mode, l.doc_url, l.sent_at
        FROM county_digest_sent_log l
        LEFT JOIN county_subscriptions s ON s.id = l.subscription_id
    """
    params = []
    if subscription_id is not None:
        sql += " WHERE l.subscription_id = %s"
        params.append(int(subscription_id))
    sql += " ORDER BY l.sent_at DESC LIMIT %s"
    params.append(int(limit))
    return _read_sql(conn, sql, params=tuple(params))


CATEGORY_LABELS_MAP = {
    "DC": "Development Charges",
    "STORMWATER": "Stormwater Charges",
    "SITE_ALT": "Site Alteration & Fill",
    "LGD": "Livestock Guardian Dogs",
    "TREES": "Tree / Forest Conservation",
    "CHICKENS": "Backyard Chickens",
    "FENCES": "Fence Bylaws",
}


def get_upcoming_bylaw_renewals(
    conn,
    municipality_ids: list[int],
    months_ahead: int = 12,
    reference_date: datetime.date | None = None,
) -> list[dict]:
    """Return all recorded bylaws expiring within the next `months_ahead` months for the given municipalities.

    Covers all 7 bylaw categories across Upper Tier (County/Region), Lower Tier, and Single Tier
    municipalities, resolving integer exemption codes to clean human-readable labels.
    """
    if not municipality_ids:
        return []

    clean_ids = [int(x) for x in municipality_ids]
    ph = ",".join(["%s"] * len(clean_ids))
    sql = f"""
        SELECT m.id AS municipality_id,
               m.name AS municipality_name,
               m.municipal_status,
               m.geographic_area,
               b.category,
               b.bylaw_name,
               b.bylaw_link,
               b.date_enacted,
               b.expiry_date,
               b.expiry_notes,
               be.exemption_status,
               dt.farm_exemption AS trees_farm_exemption,
               dsa.farm_exemption AS sa_farm_exemption,
               dc.can_keep AS chickens_can_keep,
               dlgd.exempt_license_fees AS lgd_exempt_fees,
               dfen.security_fencing_exemption AS fence_sec_exempt
        FROM bylaws b
        JOIN municipalities m ON m.id = b.municipality_id
        LEFT JOIN bylaw_exemptions be ON be.bylaw_id = b.id
        LEFT JOIN details_trees dt ON dt.bylaw_id = b.id
        LEFT JOIN details_site_alt dsa ON dsa.bylaw_id = b.id
        LEFT JOIN details_chickens dc ON dc.bylaw_id = b.id
        LEFT JOIN details_lgd dlgd ON dlgd.bylaw_id = b.id
        LEFT JOIN details_fences dfen ON dfen.bylaw_id = b.id
        WHERE b.municipality_id IN ({ph})
          AND b.expiry_date IS NOT NULL
          AND b.expiry_date != ''
    """
    df = _read_sql(conn, sql, params=tuple(clean_ids))
    if df.empty:
        return []

    today = reference_date or datetime.date.today()
    cutoff = today + datetime.timedelta(days=int(round(months_ahead * 30.4375)))

    rows = []
    for _, r in df.iterrows():
        raw_exp = str(r.get("expiry_date") or "").strip()
        parsed_dt = pd.to_datetime(raw_exp, errors="coerce")
        if pd.isna(parsed_dt):
            continue
        exp_date = parsed_dt.date()
        if not (today <= exp_date <= cutoff):
            continue

        cat_code = str(r.get("category") or "").strip().upper()
        cat_label = CATEGORY_LABELS_MAP.get(cat_code, cat_code)

        # Resolve human-readable exemption status cleanly across categories
        raw_ex = r.get("exemption_status")
        ex_label = resolve_yes_no(raw_ex) if (raw_ex is not None and str(raw_ex).strip() not in ("", "nan", "None")) else ""
        if not ex_label or ex_label == "N/A":
            if cat_code == "TREES" and pd.notna(r.get("trees_farm_exemption")) and str(r.get("trees_farm_exemption")).strip():
                ex_label = resolve_yes_no(r.get("trees_farm_exemption"))
            elif cat_code == "SITE_ALT" and pd.notna(r.get("sa_farm_exemption")) and str(r.get("sa_farm_exemption")).strip():
                ex_label = resolve_yes_no(r.get("sa_farm_exemption"))
            elif cat_code == "CHICKENS" and pd.notna(r.get("chickens_can_keep")) and str(r.get("chickens_can_keep")).strip():
                ex_label = resolve_yes_no(r.get("chickens_can_keep"))
            elif cat_code == "LGD" and pd.notna(r.get("lgd_exempt_fees")) and str(r.get("lgd_exempt_fees")).strip():
                ex_label = resolve_yes_no(r.get("lgd_exempt_fees"))
            elif cat_code == "FENCES" and pd.notna(r.get("fence_sec_exempt")) and str(r.get("fence_sec_exempt")).strip():
                ex_label = resolve_yes_no(r.get("fence_sec_exempt"))
        if not ex_label or str(ex_label).strip().lower() in ("nan", "none"):
            ex_label = "Not Known"

        days_left = (exp_date - today).days
        bylaw_name = str(r.get("bylaw_name") or "").strip()
        if not bylaw_name or bylaw_name.lower() in ("nan", "none"):
            bylaw_name = f"{cat_label} By-law"
        bylaw_link = str(r.get("bylaw_link") or "").strip()
        if bylaw_link.lower() in ("nan", "none"):
            bylaw_link = ""

        rows.append({
            "municipality_id": int(r["municipality_id"]),
            "municipality_name": str(r["municipality_name"] or ""),
            "municipal_status": str(r.get("municipal_status") or ""),
            "geographic_area": str(r.get("geographic_area") or ""),
            "category_code": cat_code,
            "category_label": cat_label,
            "bylaw_name": bylaw_name,
            "bylaw_link": bylaw_link,
            "expiry_date": exp_date.isoformat(),
            "expiry_date_display": exp_date.strftime("%b %d, %Y"),
            "days_until_expiry": days_left,
            "exemption_status": ex_label,
        })

    rows.sort(key=lambda x: (x["expiry_date"], x["municipality_name"], x["category_label"]))
    return rows
