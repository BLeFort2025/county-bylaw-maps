"""
db_schema.py — SQLite schema for the Municipal Bylaw Database.

Creates all tables in a normalised structure.  Called by
migrate_access_to_sqlite.py and by db_utils.get_connection() on first use.
"""

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bylaws.db")

# ── 7 active categories (Hoop Houses dropped per OFA decision) ──
CATEGORIES = [
    "DC",           # Development Charges
    "STORMWATER",   # Stormwater
    "SITE_ALT",     # Site Alteration & Fill
    "LGD",          # Livestock Guardian Dogs
    "TREES",        # Forest / Tree Conservation
    "CHICKENS",     # Backyard Chickens
    "FENCES",       # Fence Bylaws
]

SCHEMA_SQL = """
-- ═══════════════════════════════════════════════
-- Core municipality record (one row per muni)
-- ═══════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS municipalities (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    lookup_key      TEXT UNIQUE NOT NULL,    -- e.g. "Augusta, Tp"
    name            TEXT NOT NULL,           -- e.g. "Augusta"
    municipal_status TEXT,                   -- "Lower Tier" / "Upper Tier"
    geographic_area TEXT,                    -- County/Region name
    zone            REAL,
    website         TEXT,
    bylaw_page_link TEXT,
    staff_directory_link TEXT,
    contact_position TEXT,
    contact_name    TEXT,
    clerk_email     TEXT,
    clerk_phone     TEXT,
    progress_overall INTEGER,
    progress_notes  TEXT,
    lookup_test     TEXT,
    export_html     TEXT
);

-- ═══════════════════════════════════════════════
-- Bylaw record — one row per (municipality, category)
-- ═══════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS bylaws (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    municipality_id INTEGER NOT NULL REFERENCES municipalities(id),
    category        TEXT NOT NULL,           -- DC, STORMWATER, SITE_ALT, ...
    progress        INTEGER,                -- lookup code
    progress_label  TEXT,                    -- resolved human-readable label
    bylaw_name      TEXT,
    bylaw_name_2    TEXT,                    -- some categories have two bylaws
    bylaw_link      TEXT,
    bylaw_link_2    TEXT,
    date_enacted    TEXT,                    -- ISO date string
    expiry_date     TEXT,
    expiry_notes    TEXT,
    other_notes     TEXT,
    date_last_updated TEXT,
    UNIQUE(municipality_id, category)
);

-- ═══════════════════════════════════════════════
-- Exemptions — one row per bylaw, stores the
-- YES/NO/N/A status and wording
-- ═══════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS bylaw_exemptions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    bylaw_id        INTEGER NOT NULL REFERENCES bylaws(id),
    exemption_status TEXT,                   -- YES / NO / N/A / NOT KNOWN
    exemption_wording TEXT,
    UNIQUE(bylaw_id)
);

-- ═══════════════════════════════════════════════
-- Category-specific detail tables
-- Only categories with extra structured fields
-- ═══════════════════════════════════════════════

-- Development Charges extras
CREATE TABLE IF NOT EXISTS details_dc (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    bylaw_id        INTEGER NOT NULL REFERENCES bylaws(id) UNIQUE,
    has_dc          TEXT,                    -- YES / NO / NOT KNOWN
    fees_bylaw_name TEXT,
    fees_bylaw_link TEXT,
    fees_enacted    TEXT,
    fees_expiry     TEXT,
    fees_expiry_notes TEXT
);

-- Stormwater extras
CREATE TABLE IF NOT EXISTS details_stormwater (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    bylaw_id        INTEGER NOT NULL REFERENCES bylaws(id) UNIQUE,
    charge_type     TEXT,                    -- from lookup
    fee_calculation TEXT
);

-- Site Alteration extras
CREATE TABLE IF NOT EXISTS details_site_alt (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    bylaw_id        INTEGER NOT NULL REFERENCES bylaws(id) UNIQUE,
    farm_exemption  TEXT,                    -- YES / NO
    special_provision TEXT,                  -- YES / NO
    guidelines_wording TEXT,
    exception_wording TEXT
);

-- Livestock Guardian Dogs extras
CREATE TABLE IF NOT EXISTS details_lgd (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    bylaw_id        INTEGER NOT NULL REFERENCES bylaws(id) UNIQUE,
    has_lgd_definition TEXT,
    lgd_definition  TEXT,
    has_herding_def TEXT,
    herding_definition TEXT,
    exempt_license_fees TEXT,
    collar_tag_req  TEXT,
    barking_restrictions TEXT,
    exempt_barking  TEXT,
    dog_limit       TEXT
);

-- Tree / Forest Conservation extras
CREATE TABLE IF NOT EXISTS details_trees (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    bylaw_id        INTEGER NOT NULL REFERENCES bylaws(id) UNIQUE,
    farm_exemption  TEXT,
    bylaw_wording   TEXT,
    farming_exception_wording TEXT,
    list_of_exceptions TEXT
);

-- Backyard Chickens extras
CREATE TABLE IF NOT EXISTS details_chickens (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    bylaw_id        INTEGER NOT NULL REFERENCES bylaws(id) UNIQUE,
    can_keep        TEXT,                    -- YES / NO / NOT KNOWN
    definition      TEXT,
    chicken_limit   TEXT,
    roosters_allowed TEXT,
    licence_required TEXT,
    welfare_requirements TEXT
);

-- Fences extras
CREATE TABLE IF NOT EXISTS details_fences (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    bylaw_id        INTEGER NOT NULL REFERENCES bylaws(id) UNIQUE,
    has_fence_bylaw TEXT,
    applies_all_lands TEXT,
    replaces_lfa    TEXT,               -- Line Fences Act
    security_fencing_exemption TEXT,
    electrified_fencing_exemption TEXT,
    equal_apportionment TEXT,
    apportionment_bylaw TEXT,
    fence_notes     TEXT
);

-- ═══════════════════════════════════════════════
-- AMCTO contacts (multiple per municipality)
-- ═══════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS contacts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    municipality_id INTEGER REFERENCES municipalities(id),
    lookup_key      TEXT,           -- for joining if municipality_id is NULL
    contact_type    TEXT,
    title           TEXT,
    department      TEXT,
    first_name      TEXT,
    last_name       TEXT,
    email           TEXT,
    phone           TEXT,
    address_1       TEXT,
    address_2       TEXT,
    city            TEXT,
    postal          TEXT,
    fax             TEXT,
    municipal_email TEXT,
    municipal_phone TEXT,
    website         TEXT,
    households      INTEGER,
    population      INTEGER
);

-- ═══════════════════════════════════════════════
-- Lookup values (dropdown options)
-- ═══════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS lookup_values (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    lookup_table    TEXT NOT NULL,       -- e.g. "Yes/No", "Progress", "Stormwater Charge Type"
    code            INTEGER,             -- original Access ID
    display_value   TEXT NOT NULL
);

-- ═══════════════════════════════════════════════
-- Provincial legislation references
-- ═══════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS provincial_acts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    category        TEXT NOT NULL,
    act_name        TEXT,
    notes           TEXT,
    date_enacted    TEXT
);

-- ═══════════════════════════════════════════════
-- Category descriptions (one row per category)
-- ═══════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS category_descriptions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    category        TEXT UNIQUE NOT NULL,
    description     TEXT,
    reason_for_interest TEXT,
    general_notes   TEXT
);

-- ═══════════════════════════════════════════════
-- Scanner signals (from weekly intelligence scan)
-- ═══════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS scanner_signals (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    municipality_id INTEGER REFERENCES municipalities(id),
    munid_raw       TEXT,               -- original munid from signals.csv
    signal_type     TEXT DEFAULT 'scanner_hit',
    discovered_date TEXT,
    trigger_keyword TEXT,
    category        TEXT,
    snippet         TEXT,
    evidence_url    TEXT
);

-- ═══════════════════════════════════════════════
-- Audit log (tracks every edit)
-- ═══════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS audit_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TEXT NOT NULL,
    user_name       TEXT DEFAULT 'admin',
    table_name      TEXT NOT NULL,
    record_id       INTEGER,
    field_name      TEXT,
    old_value       TEXT,
    new_value       TEXT
);

-- ═══════════════════════════════════════════════
-- Indexes for common queries
-- ═══════════════════════════════════════════════
CREATE INDEX IF NOT EXISTS idx_bylaws_muni    ON bylaws(municipality_id);
CREATE INDEX IF NOT EXISTS idx_bylaws_cat     ON bylaws(category);
CREATE INDEX IF NOT EXISTS idx_contacts_muni  ON contacts(municipality_id);
CREATE INDEX IF NOT EXISTS idx_signals_muni   ON scanner_signals(municipality_id);
CREATE INDEX IF NOT EXISTS idx_audit_ts       ON audit_log(timestamp);
"""


def create_database(db_path: str = DB_PATH) -> sqlite3.Connection:
    """Create the SQLite database with all tables. Safe to call repeatedly."""
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    return conn


if __name__ == "__main__":
    conn = create_database()
    # Print table list as verification
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    tables = [r[0] for r in cursor.fetchall()]
    print(f"Created {DB_PATH}")
    print(f"Tables ({len(tables)}): {', '.join(tables)}")
    conn.close()
