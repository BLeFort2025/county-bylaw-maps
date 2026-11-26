"""
db_schema.py — SQLite schema for the Municipal Bylaw Database.

Creates all tables in a normalised structure.  Called by
migrate_access_to_sqlite.py and by db_utils.get_connection() on first use.
"""

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bylaws.db")

# ── 8 active categories (Hoop Houses dropped per OFA decision; BLDG_FEES added) ──
CATEGORIES = [
    "DC",           # Development Charges
    "STORMWATER",   # Stormwater
    "SITE_ALT",     # Site Alteration & Fill
    "LGD",          # Livestock Guardian Dogs
    "TREES",        # Forest / Tree Conservation
    "CHICKENS",     # Backyard Chickens
    "FENCES",       # Fence Bylaws
    "BLDG_FEES",    # Farm Building Permit Fees
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
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    bylaw_id                INTEGER NOT NULL REFERENCES bylaws(id) UNIQUE,
    farm_exemption          TEXT,            -- Yes / Partial / No / NOT KNOWN
    special_provision       TEXT,            -- Yes / No
    guidelines_wording      TEXT,
    exception_wording       TEXT,
    nfp_exemption_scope     TEXT,            -- Full NFP / Fill & Grading | Statutory Topsoil & Drainage Only | Topsoil Removal Only | Drainage Only | No NFP Exemption
    drainage_act_exempt     TEXT,            -- Yes / No / NOT KNOWN
    excess_soil_reg_406_19  TEXT,            -- Yes / No / NOT KNOWN
    fill_captures_ag_materials TEXT,         -- None Flagged | Sod | Compost or Manure | Sod + Compost/Manure
    -- Structured Excess Soil & Site Alteration Permit Fee fields
    fee_verification_status TEXT,            -- Verified | Verified (Ag Exempt - $0) | Verified (Ag Tier) | Verified (Scanned PDF) | Not Published Online | Pending | N/A (No Bylaw)
    fee_year                INTEGER,         -- Effective fee schedule year (e.g. 2025, 2026)
    fees_bylaw_name         TEXT,            -- Consolidated Fees & Charges / User Fee By-law name (or 'In Site Alteration By-law')
    fees_bylaw_link         TEXT,            -- Direct URL to enacted fee schedule / User Fee By-law
    ag_import_fee_status    TEXT,            -- Exempt ($0) | Exempt up to Volume Cap | Waiver Available ($0 App Fee) | Reduced Farm Tier | Standard Commercial Rate | No Bylaw | Pending
    ag_exempt_volume_cap_m3 REAL,            -- Max exempt imported topsoil/fill volume (m³) before permit/fees apply
    out_of_muni_fill_ban    TEXT,            -- Yes | No | Restricted | Unknown
    fee_pricing_model       TEXT,            -- Tiered Volume + Per m³ | Base + Per m³ | Per m³ Only | Flat Fee | Base + Per Hectare | Reduced Farm Flat Fee | Exempt ($0) | Waiver ($0 App Fee) | Cost Recovery Only | Not Published
    base_fee_small          REAL,            -- Base permit application fee ($) for small/minor fill tier
    base_fee_large          REAL,            -- Base permit application fee ($) for large/commercial fill tier
    per_m3_rate             REAL,            -- Volumetric fill/topsoil fee ($ per cubic metre, m³)
    fee_calc_spec_json      TEXT,            -- Structured JSON formula for tiered volume brackets, caps, & ag tiers
    est_fee_500_m3          REAL,            -- Standardized benchmark: est. farm permit fee ($) for 500 m³ clean topsoil
    est_fee_5000_m3         REAL,            -- Standardized benchmark: est. farm permit fee ($) for 5,000 m³ clean topsoil
    est_fee_15000_m3        REAL,            -- Standardized benchmark: est. farm permit fee ($) for 15,000 m³ clean topsoil
    security_deposit_terms  TEXT,            -- Refundable security / Letter of Credit / road damage deposit terms
    peer_review_recovery    TEXT,            -- Third-party engineering / Qualified Person / peer-review cost recovery terms
    fee_formula_notes       TEXT             -- Concise verified breakdown of fee tiers, volume thresholds, renewals, & ag rules
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

-- Farm Building Permit Fees extras
CREATE TABLE IF NOT EXISTS details_bldg_fees (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    bylaw_id                INTEGER NOT NULL REFERENCES bylaws(id) UNIQUE,
    verification_status     TEXT,       -- Verified | Verified (Scanned PDF) | Verified (County Shared) | Urban - No Farm Tier | Upper Tier - Local Jurisdiction | Not Published Online | Pending
    fee_year                INTEGER,    -- Effective fee schedule year (e.g. 2025, 2026)
    doc_type                TEXT,       -- Fees & Charges By-law | Building By-law | Building Fee Schedule PDF | Webpage Fee Table | Not Published Online
    shared_authority        TEXT,       -- Municipal | Dufferin County Building Services | Joint Building Committee | etc.
    has_farm_tier           TEXT,       -- Yes | No — Urban/ICI Rate | N/A | Not Verified
    pricing_model           TEXT,       -- Per Area (sq ft / m²) | Base + Per Area | Per Area + High Min Floor | Tiered Brackets | OBC Large/Small Farm Split | Flat Fee | Valuation ($/$1,000) | No Dedicated Farm Tier
    base_fee                REAL,
    min_fee                 REAL,
    rate_per_sqft_livestock REAL,
    rate_per_sqft_other_farm REAL,
    flat_fee                REAL,
    value_rate_per_1000     REAL,
    calc_spec_json          TEXT,       -- Structured JSON formula for stepped / OBC Group G brackets
    est_2500_shed           REAL,       -- Standardized 2,500 ft² Equipment / Drive Shed ($)
    est_10000_barn          REAL,       -- Standardized 10,000 ft² Livestock Barn ($)
    est_10000_shed          REAL,       -- Standardized 10,000 ft² Equipment / Drive Shed ($)
    est_20000_barn          REAL,       -- Standardized 20,000 ft² Large Livestock Barn ($)
    silo_grain_bin_fee      TEXT,
    manure_storage_fee      TEXT,
    greenhouse_tarp_fee     TEXT,
    refundable_deposit      TEXT,
    has_obc_group_g_split   TEXT,       -- Yes | No | Unknown
    formula_notes           TEXT
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
    evidence_url    TEXT,
    ai_summary      TEXT,
    ai_confidence   INTEGER
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
-- Advocacy log (tracks outgoing advocacy letters)
-- ═══════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS advocacy_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TEXT NOT NULL,
    municipality_id INTEGER REFERENCES municipalities(id),
    municipality_name TEXT,
    bylaw_category  TEXT,
    recipient_email TEXT,
    sender_name     TEXT,
    sender_org      TEXT,
    action          TEXT  -- 'letter_downloaded', 'mailto_opened'
);


-- ═══════════════════════════════════════════════
-- County Federation Weekly Digest Subscriptions
-- ═══════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS county_subscriptions (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    federation_name       TEXT NOT NULL,
    geographic_area       TEXT NOT NULL,
    municipality_ids_json TEXT,
    exclude_large_cities  INTEGER DEFAULT 1,
    recipient_emails      TEXT NOT NULL,
    cc_emails             TEXT DEFAULT '',
    bcc_emails            TEXT DEFAULT 'ben.lefort@ofa.on.ca',
    send_empty_digest     INTEGER DEFAULT 1,
    is_test_profile       INTEGER DEFAULT 0,
    active                INTEGER DEFAULT 1,
    notes                 TEXT DEFAULT '',
    created_at            TEXT,
    updated_at            TEXT
);

CREATE TABLE IF NOT EXISTS county_watchlist_keywords (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    subscription_id INTEGER NOT NULL REFERENCES county_subscriptions(id) ON DELETE CASCADE,
    keyword         TEXT NOT NULL,
    is_negative     INTEGER DEFAULT 0,
    UNIQUE(subscription_id, keyword, is_negative)
);

CREATE TABLE IF NOT EXISTS county_digest_sent_log (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
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
);

CREATE INDEX IF NOT EXISTS idx_digest_kw_sub   ON county_watchlist_keywords(subscription_id);
CREATE INDEX IF NOT EXISTS idx_digest_log_sub  ON county_digest_sent_log(subscription_id);
CREATE INDEX IF NOT EXISTS idx_digest_log_hash ON county_digest_sent_log(subscription_id, content_hash);

-- ═══════════════════════════════════════════════
-- Indexes for common queries
-- ═══════════════════════════════════════════════
CREATE INDEX IF NOT EXISTS idx_bylaws_muni    ON bylaws(municipality_id);
CREATE INDEX IF NOT EXISTS idx_bylaws_cat     ON bylaws(category);
CREATE INDEX IF NOT EXISTS idx_contacts_muni  ON contacts(municipality_id);
CREATE INDEX IF NOT EXISTS idx_signals_muni   ON scanner_signals(municipality_id);
CREATE INDEX IF NOT EXISTS idx_audit_ts       ON audit_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_advocacy_muni  ON advocacy_log(municipality_id);
CREATE INDEX IF NOT EXISTS idx_advocacy_ts    ON advocacy_log(timestamp);
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
