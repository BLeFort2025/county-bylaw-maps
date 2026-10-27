"""
build_outreach_data.py — Builds the self-contained empirical data bundle for the
Post-Election Municipal Council Outreach & Letter Generator Streamlit App.

Sources:
1. Municipal Clerk & Address Directory: bylaws.db (municipalities + contacts tables)
2. OMAFA Economic Attribution Model (GDP & Jobs by County): attribution_county (6).xlsx
3. Statistics Canada 2021 Census of Agriculture (County & Lower-Tier CCS):
   - agcensus_wide.csv
   - ag_census_panel_data.csv
4. OFA 2025 Farm Business Confidence Survey:
   - Clean Farm Business Confidence Survey 2025 - Copy.xlsx
"""

import os
import json
import sqlite3
import pandas as pd
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "data")
os.makedirs(DATA_DIR, exist_ok=True)

# Source paths
DB_PATH = os.path.abspath(os.path.join(HERE, "..", "bylaws.db"))
SURVEY_PATH = r"C:\Users\ben.lefort\OneDrive - Ontario Federation of Agriculture\Desktop\Ben Desktop Files\Farm Business Confidence Survey\2025\DATA\Clean Farm Business Confidence Survey 2025 - Copy.xlsx"
ATTR_PATH = r"C:\Users\ben.lefort\Downloads\attribution_county (6).xlsx"
AGCENSUS_WIDE_PATH = r"C:\Users\ben.lefort\OneDrive - Ontario Federation of Agriculture\Desktop\ontario-ag-dashboard\data\agcensus_wide.csv"
AGCENSUS_LT_PATH = r"C:\Users\ben.lefort\OneDrive - Ontario Federation of Agriculture\Desktop\Ben Desktop Files\Economic Analyst Position\Ag Econ Dashboard\Lower Tier Ag Census Data\ag_census_panel_data.csv"


# ── Cross-Mapping Table for the 48 Agricultural Counties/Regions/Districts ──
# Maps bylaws.db geographic_area -> {
#   display_name, default_federation, attr_key, census_wide_key, census_lt_county,
#   survey_primary_keys, survey_regional_pool_keys, region_name
# }
COUNTY_CONFIG = {
    "Algoma": {
        "display_name": "Algoma District",
        "default_federation": "Algoma Federation of Agriculture",
        "attr_key": "Algoma",
        "census_wide_key": "ALGOMA",
        "census_lt_county": "Algoma District",
        "survey_keys": ["Algoma"],
        "region_name": "Northern Ontario",
    },
    "Brant": {
        "display_name": "County of Brant",
        "default_federation": "Brant County Federation of Agriculture",
        "attr_key": "Brant County",
        "census_wide_key": "BRANT",
        "census_lt_county": "Brant County",
        "survey_keys": ["Brant"],
        "region_name": "Southern Ontario",
    },
    "Bruce": {
        "display_name": "Bruce County",
        "default_federation": "Bruce County Federation of Agriculture",
        "attr_key": "Bruce County",
        "census_wide_key": "BRUCE",
        "census_lt_county": "Bruce County",
        "survey_keys": ["Bruce"],
        "region_name": "Western Ontario",
    },
    "Chatham-Kent": {
        "display_name": "Municipality of Chatham-Kent",
        "default_federation": "Kent Federation of Agriculture",
        "attr_key": "Chatham-Kent Division",
        "census_wide_key": "CHATHAM_KENT",
        "census_lt_county": "Chatham-Kent Division",
        "survey_keys": ["Kent"],
        "region_name": "Southern Ontario",
    },
    "Cochrane": {
        "display_name": "Cochrane District",
        "default_federation": "Cochrane Federation of Agriculture",
        "attr_key": "Cochrane",
        "census_wide_key": "COCHRANE",
        "census_lt_county": "Cochrane District",
        "survey_keys": ["Cochrane"],
        "region_name": "Northern Ontario",
    },
    "Dufferin": {
        "display_name": "Dufferin County",
        "default_federation": "Dufferin Federation of Agriculture",
        "attr_key": "Dufferin County",
        "census_wide_key": "DUFFERIN",
        "census_lt_county": "Dufferin County",
        "survey_keys": ["Dufferin"],
        "region_name": "Western Ontario",
    },
    "Durham": {
        "display_name": "Region of Durham",
        "default_federation": "Durham Region Federation of Agriculture",
        "attr_key": "Durham Regional Municipality",
        "census_wide_key": "DURHAM",
        "census_lt_county": "Durham Regional Municipality",
        "survey_keys": ["Durham"],
        "region_name": "Central Ontario",
    },
    "Elgin": {
        "display_name": "Elgin County",
        "default_federation": "Elgin Federation of Agriculture",
        "attr_key": "Elgin County",
        "census_wide_key": "ELGIN",
        "census_lt_county": "Elgin County",
        "survey_keys": ["Elgin"],
        "region_name": "Southern Ontario",
    },
    "Essex": {
        "display_name": "Essex County",
        "default_federation": "Essex County Federation of Agriculture",
        "attr_key": "Essex County",
        "census_wide_key": "ESSEX",
        "census_lt_county": "Essex County",
        "survey_keys": ["Essex"],
        "region_name": "Southern Ontario",
    },
    "Frontenac": {
        "display_name": "Frontenac County",
        "default_federation": "Frontenac Federation of Agriculture",
        "attr_key": "Frontenac County",
        "census_wide_key": "FRONTENAC",
        "census_lt_county": "Frontenac County",
        "survey_keys": ["Frontenac"],
        "region_name": "Eastern Ontario",
    },
    "Grey": {
        "display_name": "Grey County",
        "default_federation": "Grey County Federation of Agriculture",
        "attr_key": "Grey County",
        "census_wide_key": "GREY",
        "census_lt_county": "Grey County",
        "survey_keys": ["Grey"],
        "region_name": "Western Ontario",
    },
    "Haldimand": {
        "display_name": "Haldimand County",
        "default_federation": "Haldimand Federation of Agriculture",
        "attr_key": "Haldimand-Norfolk Regional Municipality",
        "attr_is_combined_cd": True,
        "attr_cd_label": "Haldimand-Norfolk Census Division",
        "census_wide_key": "HALDIMAND_NORFOLK",
        "census_lt_county": "Haldimand Norfolk Regional",
        "census_lt_muni_override": "Haldimand County",
        "survey_keys": ["Haldimand"],
        "region_name": "Southern Ontario",
    },
    "Haliburton": {
        "display_name": "Haliburton County",
        "default_federation": "Kawartha Lakes-Haliburton Federation of Agriculture",
        "attr_key": "Haliburton County",
        "census_wide_key": "HALIBURTON",
        "census_lt_county": "Haliburton County",
        "survey_keys": ["Kawartha Lakes \u2013 Haliburton", "Kawartha Lakes - Haliburton"],
        "region_name": "Central Ontario",
    },
    "Halton": {
        "display_name": "Halton Region",
        "default_federation": "Halton Region Federation of Agriculture",
        "attr_key": "Halton Regional Municipality",
        "census_wide_key": "HALTON",
        "census_lt_county": "Halton Regional Municipality",
        "survey_keys": ["Halton"],
        "region_name": "Western Ontario",
    },
    "Hamilton": {
        "display_name": "City of Hamilton",
        "default_federation": "Hamilton-Wentworth Federation of Agriculture",
        "attr_key": "Hamilton Division",
        "census_wide_key": "HAMILTON",
        "census_lt_county": "Hamilton Division",
        "survey_keys": ["Hamilton-Wentworth"],
        "region_name": "Southern Ontario",
    },
    "Hastings": {
        "display_name": "Hastings County",
        "default_federation": "Hastings Federation of Agriculture",
        "attr_key": "Hastings County",
        "census_wide_key": "HASTINGS",
        "census_lt_county": "Hasting County",
        "survey_keys": ["Hastings"],
        "region_name": "Central Ontario",
    },
    "Huron": {
        "display_name": "Huron County",
        "default_federation": "Huron County Federation of Agriculture",
        "attr_key": "Huron County",
        "census_wide_key": "HURON",
        "census_lt_county": "Huron County",
        "survey_keys": ["Huron"],
        "region_name": "Western Ontario",
    },
    "Kawartha Lakes": {
        "display_name": "City of Kawartha Lakes",
        "default_federation": "Kawartha Lakes-Haliburton Federation of Agriculture",
        "attr_key": "Kawartha Lakes Division",
        "census_wide_key": "KAWARTHA_LAKES",
        "census_lt_county": "Kawarth Lakes Division",
        "survey_keys": ["Kawartha Lakes \u2013 Haliburton", "Kawartha Lakes - Haliburton"],
        "region_name": "Central Ontario",
    },
    "Kenora": {
        "display_name": "Kenora District",
        "default_federation": "Kenora District Federation of Agriculture",
        "attr_key": "Kenora",
        "census_wide_key": "KENORA",
        "census_lt_county": "Kenora District",
        "survey_keys": ["Kenora"],
        "region_name": "Northern Ontario",
    },
    "Lambton": {
        "display_name": "Lambton County",
        "default_federation": "Lambton Federation of Agriculture",
        "attr_key": "Lambton County",
        "census_wide_key": "LAMBTON",
        "census_lt_county": "Lambton County",
        "survey_keys": ["Lambton"],
        "region_name": "Southern Ontario",
    },
    "Lanark": {
        "display_name": "Lanark County",
        "default_federation": "Lanark Federation of Agriculture",
        "attr_key": "Lanark County",
        "census_wide_key": "LANARK",
        "census_lt_county": "Lanark County",
        "survey_keys": ["Lanark"],
        "region_name": "Eastern Ontario",
    },
    "Leeds and Grenville": {
        "display_name": "United Counties of Leeds and Grenville",
        "default_federation": "Leeds / Grenville Federation of Agriculture",
        "attr_key": "Leeds and Grenville United Counties",
        "census_wide_key": "LEEDS_AND_GRENVILLE",
        "census_lt_county": "Leeds & Grenville United Counties",
        "survey_keys": ["Leeds", "Grenville"],
        "sub_federations": {
            "Leeds & Grenville (Combined)": ["Leeds", "Grenville"],
            "Leeds Federation of Agriculture": ["Leeds"],
            "Grenville Federation of Agriculture": ["Grenville"],
        },
        "region_name": "Eastern Ontario",
    },
    "Lennox and Addington": {
        "display_name": "County of Lennox and Addington",
        "default_federation": "Lennox & Addington Federation of Agriculture",
        "attr_key": "Lennox and Addington County",
        "census_wide_key": "LENNOX_AND_ADDINGTON",
        "census_lt_county": "Lennox & Addington County",
        "survey_keys": ["Lennox & Addington"],
        "region_name": "Eastern Ontario",
    },
    "Manitoulin": {
        "display_name": "Manitoulin District",
        "default_federation": "Manitoulin-North Shore Federation of Agriculture",
        "attr_key": "Manitoulin",
        "census_wide_key": "MANITOULIN",
        "census_lt_county": "Manitoulin District",
        "survey_keys": ["Manitoulin-North Shore \u2013 Sudbury West"],
        "region_name": "Northern Ontario",
    },
    "Middlesex": {
        "display_name": "Middlesex County",
        "default_federation": "Middlesex Federation of Agriculture",
        "attr_key": "Middlesex County",
        "census_wide_key": "MIDDLESEX",
        "census_lt_county": "Middlesex County",
        "survey_keys": ["Middlesex"],
        "region_name": "Southern Ontario",
    },
    "Muskoka": {
        "display_name": "District Municipality of Muskoka",
        "default_federation": "Muskoka Federation of Agriculture",
        "attr_key": "Muskoka District Municipality",
        "census_wide_key": "MUSKOKA",
        "census_lt_county": "Muskoka District Municipality",
        "survey_keys": ["Muskoka"],
        "region_name": "Central Ontario",
    },
    "Niagara": {
        "display_name": "Niagara Region",
        "default_federation": "Niagara Federation of Agriculture",
        "attr_key": "Niagara Regional Municipality",
        "census_wide_key": "NIAGARA",
        "census_lt_county": "Niagara Regional Municipality",
        "survey_keys": ["Niagara (North and South)"],
        "region_name": "Southern Ontario",
    },
    "Nipissing": {
        "display_name": "Nipissing District",
        "default_federation": "East Nipissing-Parry Sound / West Nipissing-Sudbury East Federation of Agriculture",
        "attr_key": "Nipissing",
        "census_wide_key": "NIPISSING",
        "census_lt_county": "Nipissing District",
        "survey_keys": ["East Nipissing \u2013 Parry Sound", "West Nipissing \u2013 Sudbury East"],
        "sub_federations": {
            "Nipissing (Combined East & West)": ["East Nipissing \u2013 Parry Sound", "West Nipissing \u2013 Sudbury East"],
            "East Nipissing-Parry Sound Federation of Agriculture": ["East Nipissing \u2013 Parry Sound"],
            "West Nipissing-Sudbury East Federation of Agriculture": ["West Nipissing \u2013 Sudbury East"],
        },
        "region_name": "Northern Ontario",
    },
    "Norfolk": {
        "display_name": "Norfolk County",
        "default_federation": "Norfolk Federation of Agriculture",
        "attr_key": "Haldimand-Norfolk Regional Municipality",
        "attr_is_combined_cd": True,
        "attr_cd_label": "Haldimand-Norfolk Census Division",
        "census_wide_key": "HALDIMAND_NORFOLK",
        "census_lt_county": "Haldimand Norfolk Regional",
        "census_lt_muni_override": "Norfolk County",
        "survey_keys": ["Norfolk"],
        "region_name": "Southern Ontario",
    },
    "Northumberland": {
        "display_name": "Northumberland County",
        "default_federation": "Northumberland Federation of Agriculture",
        "attr_key": "Northumberland County",
        "census_wide_key": "NORTHUMBERLAND",
        "census_lt_county": "Northumberland County",
        "survey_keys": ["Northumberland"],
        "region_name": "Central Ontario",
    },
    "Ottawa": {
        "display_name": "City of Ottawa",
        "default_federation": "Ottawa Federation of Agriculture",
        "attr_key": "Ottawa Division",
        "census_wide_key": "OTTAWA",
        "census_lt_county": "Ottawa Division",
        "survey_keys": ["Ottawa"],
        "sub_federations": {
            "Ottawa Federation of Agriculture": ["Ottawa"],
            "Ottawa & Arnprior Combined": ["Ottawa", "Arnprior"],
            "Arnprior Federation of Agriculture": ["Arnprior"],
        },
        "region_name": "Eastern Ontario",
    },
    "Oxford": {
        "display_name": "Oxford County",
        "default_federation": "Oxford County Federation of Agriculture",
        "attr_key": "Oxford County",
        "census_wide_key": "OXFORD",
        "census_lt_county": "Oxford County",
        "survey_keys": ["Oxford"],
        "region_name": "Southern Ontario",
    },
    "Parry Sound": {
        "display_name": "Parry Sound District",
        "default_federation": "East Nipissing-Parry Sound Federation of Agriculture",
        "attr_key": "Parry Sound District",
        "census_wide_key": "PARRY_SOUND",
        "census_lt_county": "Parry Sound District",
        "survey_keys": ["East Nipissing \u2013 Parry Sound"],
        "region_name": "Central Ontario",
    },
    "Peel": {
        "display_name": "Region of Peel",
        "default_federation": "Peel Federation of Agriculture",
        "attr_key": "Peel Regional Municipality",
        "census_wide_key": "PEEL",
        "census_lt_county": "Peel Regional Municipality",
        "survey_keys": ["Peel"],
        "region_name": "Western Ontario",
    },
    "Perth": {
        "display_name": "Perth County",
        "default_federation": "Perth County Federation of Agriculture",
        "attr_key": "Perth County",
        "census_wide_key": "PERTH",
        "census_lt_county": "Perth County",
        "survey_keys": ["Perth"],
        "region_name": "Western Ontario",
    },
    "Peterborough": {
        "display_name": "Peterborough County",
        "default_federation": "Peterborough County Federation of Agriculture",
        "attr_key": "Peterborough County",
        "census_wide_key": "PETERBOROUGH",
        "census_lt_county": "Peterborough County",
        "survey_keys": ["Peterborough"],
        "region_name": "Central Ontario",
    },
    "Prescott and Russell": {
        "display_name": "United Counties of Prescott and Russell",
        "default_federation": "Prescott / Russell Federation of Agriculture",
        "attr_key": "Prescott and Russell United Counties",
        "census_wide_key": "PRESCOTT_AND_RUSSELL",
        "census_lt_county": "Prescott & Russell Counties",
        "survey_keys": ["Prescott", "Russell"],
        "sub_federations": {
            "Prescott & Russell (Combined)": ["Prescott", "Russell"],
            "Russell Federation of Agriculture": ["Russell"],
            "Prescott Federation of Agriculture": ["Prescott"],
        },
        "region_name": "Eastern Ontario",
    },
    "Prince Edward": {
        "display_name": "Prince Edward County",
        "default_federation": "Prince Edward Federation of Agriculture",
        "attr_key": "Prince Edward Division",
        "census_wide_key": "PRINCE_EDWARD",
        "census_lt_county": "Prince Edward County",
        "survey_keys": ["Prince Edward"],
        "region_name": "Central Ontario",
    },
    "Rainy River": {
        "display_name": "Rainy River District",
        "default_federation": "Rainy River Federation of Agriculture",
        "attr_key": "Rainy River",
        "census_wide_key": "RAINY_RIVER",
        "census_lt_county": "Rainy River District",
        "survey_keys": ["Rainy River"],
        "region_name": "Northern Ontario",
    },
    "Renfrew": {
        "display_name": "Renfrew County",
        "default_federation": "Renfrew County / Arnprior Federation of Agriculture",
        "attr_key": "Renfrew County",
        "census_wide_key": "RENFREW",
        "census_lt_county": "Renfrew County",
        "survey_keys": ["Renfrew", "Arnprior"],
        "sub_federations": {
            "Renfrew & Arnprior (Combined)": ["Renfrew", "Arnprior"],
            "Renfrew County Federation of Agriculture": ["Renfrew"],
            "Arnprior Federation of Agriculture": ["Arnprior"],
        },
        "region_name": "Eastern Ontario",
    },
    "Simcoe": {
        "display_name": "Simcoe County",
        "default_federation": "Simcoe County Federation of Agriculture",
        "attr_key": "Simcoe County",
        "census_wide_key": "SIMCOE",
        "census_lt_county": "Simcoe County",
        "survey_keys": ["Simcoe"],
        "region_name": "Western Ontario",
    },
    "Stormont, Dundas and Glengarry": {
        "display_name": "United Counties of Stormont, Dundas and Glengarry",
        "default_federation": "Stormont / Dundas / Glengarry Federation of Agriculture",
        "attr_key": "Stormont, Dundas and Glengarry Counties",
        "census_wide_key": "STORMONTDUNDASANDGLENGARRY",
        "census_lt_county": "Stormont, Dundas & Glengarry United Counties",
        "survey_keys": ["Stormont", "Dundas", "Glengarry"],
        "sub_federations": {
            "Stormont, Dundas & Glengarry (Combined)": ["Stormont", "Dundas", "Glengarry"],
            "Stormont Federation of Agriculture": ["Stormont"],
            "Dundas Federation of Agriculture": ["Dundas"],
            "Glengarry Federation of Agriculture": ["Glengarry"],
        },
        "region_name": "Eastern Ontario",
    },
    "Sudbury": {
        "display_name": "Sudbury District & Greater Sudbury",
        "default_federation": "West Nipissing-Sudbury East / Manitoulin-North Shore Federation of Agriculture",
        "attr_key": "Sudbury",
        "attr_extra_key": "Greater Sudbury / Grand Sudbury",
        "census_wide_key": "SUDBURY",
        "census_extra_key": "GREATER_SUDBURY",
        "census_lt_county": "Sudbury District",
        "survey_keys": ["Manitoulin-North Shore \u2013 Sudbury West", "West Nipissing \u2013 Sudbury East"],
        "region_name": "Northern Ontario",
    },
    "Thunder Bay": {
        "display_name": "Thunder Bay District",
        "default_federation": "Thunder Bay Federation of Agriculture",
        "attr_key": "Thunder Bay",
        "census_wide_key": "THUNDER_BAY",
        "census_lt_county": "Thunder Bay District",
        "survey_keys": ["Thunder Bay"],
        "region_name": "Northern Ontario",
    },
    "Timiskaming": {
        "display_name": "Timiskaming District",
        "default_federation": "Temiskaming Federation of Agriculture",
        "attr_key": "Timiskaming",
        "census_wide_key": "TIMISKAMING",
        "census_lt_county": "Timiskaming District",
        "survey_keys": ["Temiskaming"],
        "region_name": "Northern Ontario",
    },
    "Waterloo": {
        "display_name": "Region of Waterloo",
        "default_federation": "Waterloo Federation of Agriculture",
        "attr_key": "Waterloo Regional Municipality",
        "census_wide_key": "WATERLOO",
        "census_lt_county": "Waterloo Regional Municipality",
        "survey_keys": ["Waterloo"],
        "region_name": "Western Ontario",
    },
    "Wellington": {
        "display_name": "Wellington County",
        "default_federation": "Wellington Federation of Agriculture",
        "attr_key": "Wellington County",
        "census_wide_key": "WELLINGTON",
        "census_lt_county": "Wellington County",
        "survey_keys": ["Wellington"],
        "region_name": "Western Ontario",
    },
    "York": {
        "display_name": "York Region",
        "default_federation": "York Region Federation of Agriculture",
        "attr_key": "York Regional Municipality",
        "census_wide_key": "YORK",
        "census_lt_county": "York Regional Municipality",
        "survey_keys": ["York"],
        "region_name": "Central Ontario",
    },
}

# Mutually exclusive NAICS farm type columns in 2021 Census of Agriculture
NAICS_FARM_TYPES = [
    ("Oilseed and grain farming - Farm Reporting_2021", "Oilseed and grain farming (corn, soybeans, wheat & small grains)"),
    ("Beef cattle ranching and farming, including feedlots - Farm Reporting_2021", "Beef cattle ranching and feedlots"),
    ("Dairy cattle and milk production - Farm Reporting_2021", "Dairy cattle and milk production"),
    ("Hay farming - Farm Reporting_2021", "Hay and forage farming"),
    ("Poultry and egg production - Farm Reporting_2021", "Poultry and egg production"),
    ("Hog and pig farming - Farm Reporting_2021", "Hog and pig farming"),
    ("Fruit and tree nut farming - Farm Reporting_2021", "Fruit, berry, and tree nut farming"),
    ("Vegetable and melon farming  - Farm Reporting_2021", "Field vegetable and melon farming"),
    ("Greenhouse, nursery and floriculture production - Farm Reporting_2021", "Greenhouse, nursery, and floriculture production"),
    ("Sheep and goat farming - Farm Reporting_2021", "Sheep and goat farming"),
    ("Horse and other equine production - Farm Reporting_2021", "Horse and equine production"),
    ("Maple syrup and products production - Farm Reporting_2021", "Maple syrup and products production"),
    ("Potato farming - Farm Reporting_2021", "Potato farming"),
    ("Apiculture - Farm Reporting_2021", "Beekeeping and honey production (apiculture)"),
    ("Tobacco farming - Farm Reporting_2021", "Tobacco farming"),
]


def resolve_muni_email_and_address(conn, muni_id, clerk_email_fallback, contact_name_fallback):
    """Exact replica of letter_engine.py recipient resolution for a municipality."""
    cur = conn.cursor()
    address_str = ""
    cur.execute("""
        SELECT address_1, address_2, city, postal
        FROM contacts
        WHERE municipality_id = ? AND address_1 IS NOT NULL
        LIMIT 1
    """, (muni_id,))
    r_addr = cur.fetchone()
    if r_addr:
        parts = [p for p in [r_addr[0], r_addr[1], r_addr[2], r_addr[3]] if p and str(p).strip()]
        address_str = ", ".join(parts)

    cur.execute("""
        SELECT municipal_email, first_name, last_name, title
        FROM contacts
        WHERE municipality_id = ?
          AND municipal_email IS NOT NULL
          AND length(municipal_email) > 2
        ORDER BY
            CASE WHEN title LIKE '%Clerk%' AND title NOT LIKE '%Deputy%' THEN 0
                 WHEN title LIKE '%Clerk%' THEN 1
                 WHEN title LIKE '%CAO%' THEN 2
                 ELSE 3
            END
        LIMIT 1
    """, (muni_id,))
    row = cur.fetchone()
    if row:
        email = str(row[0]).strip()
        cname = f"{row[1] or ''} {row[2] or ''}".strip()
        return {
            "email": email,
            "contact_name": cname or None,
            "contact_title": row[3] or "Municipal Clerk",
            "address": address_str,
            "source": "contacts.municipal_email"
        }

    if clerk_email_fallback and len(str(clerk_email_fallback).strip()) > 2:
        cname = str(contact_name_fallback).strip() if contact_name_fallback and str(contact_name_fallback).strip() not in ("", "None", "NOT KNOWN") else None
        return {
            "email": str(clerk_email_fallback).strip(),
            "contact_name": cname,
            "contact_title": "Municipal Clerk",
            "address": address_str,
            "source": "municipalities.clerk_email"
        }

    return {
        "email": "",
        "contact_name": None,
        "contact_title": "Municipal Clerk",
        "address": address_str,
        "source": "none"
    }


def compute_survey_summary(df_sub, subheaders_challenges, subheaders_priorities, col36_name):
    """Compute empirical survey metrics for a subset of 2025 FBCS respondents."""
    n = len(df_sub)
    if n == 0:
        return {
            "n": 0,
            "challenges": [],
            "policy_priorities": [],
            "municipal_priorities": [],
            "farmland_price_too_high_pct": None,
        }

    # 1. Challenges (cols 123..134)
    challenges = []
    for col_idx, label in subheaders_challenges.items():
        cnt = int(df_sub.iloc[:, col_idx].notna().sum())
        if cnt > 0:
            clean_lbl = str(label).replace("\ufffd", "-").strip()
            challenges.append({
                "label": clean_lbl,
                "count": cnt,
                "pct": round(cnt * 100.0 / n, 1)
            })
    challenges.sort(key=lambda x: (-x["count"], x["label"]))

    # 2. Policy priorities (cols 97..121)
    MUNICIPAL_RELEVANT_LABELS = {
        "Reducing farm taxes",
        "Investments in municipal infrastructure \u2014such as roads, bridges, stormwater management and municipal drains",
        "Investments in municipal infrastructure -such as roads, bridges, stormwater management and municipal drains",
        "Accelerating rural access to high-speed broadband",
        "Protecting the right of property access",
        "Expanding natural gas access to rural Ontario",
        "Changes to the Planning Act",
        "Reducing countryside fragmentation",
        "Changes to the Conservation Authorities Act",
        "Keeping rural schools open",
        "Improving rural healthcare",
        "Encouraging Ontarians to buy local food",
    }

    priorities = []
    muni_priorities = []
    for col_idx, label in subheaders_priorities.items():
        cnt = int(df_sub.iloc[:, col_idx].notna().sum())
        if cnt > 0:
            clean_lbl = (
                str(label)
                .replace("\ufffd", "\u2014")
                .replace("\u2014such", "\u2014 such")
                .replace("\u2013such", "\u2014 such")
                .strip()
            )
            item = {
                "label": clean_lbl,
                "count": cnt,
                "pct": round(cnt * 100.0 / n, 1),
            }
            priorities.append(item)
            if any(k in clean_lbl.lower() for k in [
                "farm taxes", "municipal infrastructure", "broadband", "property access",
                "natural gas", "planning act", "countryside fragmentation",
                "conservation authorities", "rural schools", "rural healthcare", "buy local food"
            ]):
                muni_priorities.append(item)

    priorities.sort(key=lambda x: (-x["count"], x["label"]))
    muni_priorities.sort(key=lambda x: (-x["count"], x["label"]))

    # Farmland price perception (col 36)
    s36 = df_sub[col36_name].dropna().astype(str).str.strip()
    too_high_pct = round((s36 == "Too High").sum() * 100.0 / len(s36), 1) if len(s36) > 0 else None

    return {
        "n": n,
        "challenges": challenges,
        "policy_priorities": priorities,
        "municipal_priorities": muni_priorities,
        "farmland_price_too_high_pct": too_high_pct,
    }


def main():
    print("1. Loading municipalities and clerk contacts from bylaws.db...")
    conn = sqlite3.connect(DB_PATH)
    munis_df = pd.read_sql_query("""
        SELECT id, name, municipal_status, geographic_area, clerk_email, contact_name, website
        FROM municipalities
        WHERE geographic_area IS NOT NULL AND geographic_area != 'Toronto'
        ORDER BY geographic_area, municipal_status DESC, name
    """, conn)

    municipalities_by_county = {}
    for _, m in munis_df.iterrows():
        ga = m["geographic_area"]
        if ga not in COUNTY_CONFIG:
            continue
        info = resolve_muni_email_and_address(conn, int(m["id"]), m["clerk_email"], m["contact_name"])
        muni_entry = {
            "id": int(m["id"]),
            "name": m["name"],
            "municipal_status": m["municipal_status"],
            "geographic_area": ga,
            "website": m["website"] or "",
            "clerk_email": info["email"],
            "contact_name": info["contact_name"],
            "contact_title": info["contact_title"],
            "address": info["address"],
            "email_source": info["source"],
        }
        municipalities_by_county.setdefault(ga, []).append(muni_entry)
    conn.close()

    print("2. Loading OMAFA Attribution Model (GDP & Jobs by County)...")
    df_attr = pd.read_excel(ATTR_PATH, sheet_name="county_En")
    gdp_rows = df_attr.iloc[2:57].copy()
    emp_rows = df_attr.iloc[61:116].copy()

    attr_lookup = {}
    for _, r in gdp_rows.iterrows():
        k = str(r.iloc[0]).strip()
        attr_lookup[k] = {
            "gdp_2024_m": round(float(r.iloc[-2]), 2),
            "gdp_2025_m": round(float(r.iloc[-1]), 2),
        }
    for _, r in emp_rows.iterrows():
        k = str(r.iloc[0]).strip()
        if k in attr_lookup:
            attr_lookup[k]["jobs_prev"] = int(round(float(r.iloc[-2])))
            attr_lookup[k]["jobs_latest"] = int(round(float(r.iloc[-1])))

    print("3. Loading 2021 Census of Agriculture (County & Lower-Tier CCS)...")
    ag_wide = pd.read_csv(AGCENSUS_WIDE_PATH).set_index("join_key")
    ag_lt = pd.read_csv(AGCENSUS_LT_PATH)
    ag_lt_2021 = ag_lt[ag_lt["Year"] == 2021].copy()

    # Build lower-tier CCS lookup: (County, Municipality) -> dict of key stats
    lt_lookup = {}
    for (cnty, muni_name), grp in ag_lt_2021[ag_lt_2021["Municipality"].notna()].groupby(["County", "Municipality"]):
        vmap = dict(zip(grp["Variable"], grp["Value"]))
        farms = vmap.get("Total number of farms") or vmap.get("Total farm area - Farms reporting")
        acres = vmap.get("Total farm area - Acres")
        crop_acres = vmap.get("Land in crops (excluding Christmas tree area) - Acres")
        receipts = vmap.get("Total gross farm receipts (excluding sales of forest products) in the calendar year prior to the census or for the last complete accounting (fiscal) year prior to the census - Amount $")
        capital = vmap.get("Total farm capital - Market value $")
        woodlands = vmap.get("Woodlands and wetlands - Acres")
        direct_farms = vmap.get("Agricultural products directly sold to consumers for human consumption - Farms reporting")

        # Top NAICS farm types for this CCS/municipality
        lt_types = []
        for raw_col, clean_label in NAICS_FARM_TYPES:
            var_name = raw_col.replace("_2021", "").replace("ecluding", "excluding").replace("ecept", "except")
            val = vmap.get(var_name, 0)
            if pd.notna(val) and float(val) > 0:
                lt_types.append({"sector": clean_label, "farms": int(round(float(val)))})
        lt_types.sort(key=lambda x: -x["farms"])

        lt_lookup[(str(cnty).strip(), str(muni_name).strip())] = {
            "municipality_census_name": str(muni_name).strip(),
            "total_farms": int(round(float(farms))) if pd.notna(farms) else None,
            "total_acres": int(round(float(acres))) if pd.notna(acres) else None,
            "crop_acres": int(round(float(crop_acres))) if pd.notna(crop_acres) else None,
            "woodlands_wetlands_acres": int(round(float(woodlands))) if pd.notna(woodlands) else None,
            "gross_farm_receipts": int(round(float(receipts))) if pd.notna(receipts) else None,
            "total_farm_capital": int(round(float(capital))) if pd.notna(capital) else None,
            "direct_sales_farms": int(round(float(direct_farms))) if pd.notna(direct_farms) else None,
            "top_sectors": lt_types[:4],
        }

    print("4. Loading 2025 Farm Business Confidence Survey...")
    sdf = pd.read_excel(SURVEY_PATH)
    subheaders = sdf.iloc[0]
    sdata = sdf.iloc[1:].copy()
    c_col = sdf.columns[0]
    sdata[c_col] = sdata[c_col].astype(str).str.strip()
    col36_name = sdf.columns[36]

    subheaders_priorities = {i: subheaders.iloc[i] for i in range(97, 122)}
    subheaders_challenges = {i: subheaders.iloc[i] for i in range(123, 135)}

    # Precompute Provincial and Regional survey pools for small-sample comparison/fallback
    provincial_survey = compute_survey_summary(sdata, subheaders_challenges, subheaders_priorities, col36_name)

    region_to_survey_keys = {}
    for ga, cfg in COUNTY_CONFIG.items():
        rname = cfg["region_name"]
        region_to_survey_keys.setdefault(rname, set()).update(cfg["survey_keys"])

    regional_survey = {}
    for rname, skeys in region_to_survey_keys.items():
        r_sub = sdata[sdata[c_col].isin(list(skeys))]
        regional_survey[rname] = compute_survey_summary(r_sub, subheaders_challenges, subheaders_priorities, col36_name)

    # 5. Assemble complete county records
    counties_bundle = {}
    for ga, cfg in sorted(COUNTY_CONFIG.items()):
        # A. Attribution
        ak = cfg["attr_key"]
        attr_data = dict(attr_lookup.get(ak, {}))
        if cfg.get("attr_extra_key") and cfg["attr_extra_key"] in attr_lookup:
            ext = attr_lookup[cfg["attr_extra_key"]]
            attr_data["gdp_2024_m"] = round(attr_data.get("gdp_2024_m", 0) + ext.get("gdp_2024_m", 0), 2)
            attr_data["gdp_2025_m"] = round(attr_data.get("gdp_2025_m", 0) + ext.get("gdp_2025_m", 0), 2)
            attr_data["jobs_prev"] = attr_data.get("jobs_prev", 0) + ext.get("jobs_prev", 0)
            attr_data["jobs_latest"] = attr_data.get("jobs_latest", 0) + ext.get("jobs_latest", 0)
        attr_data["is_combined_cd"] = bool(cfg.get("attr_is_combined_cd", False))
        attr_data["cd_label"] = cfg.get("attr_cd_label", cfg["display_name"])

        # B. 2021 Census of Agriculture
        if cfg.get("census_lt_muni_override"):
            # Haldimand and Norfolk have exact separate county-level Census stats in ag_lt_2021!
            ov_key = (cfg["census_lt_county"], cfg["census_lt_muni_override"])
            c_stats = dict(lt_lookup[ov_key])
            # Also get operators from wide proportionally or exact if available
            c_stats["total_operators"] = None
            c_stats["census_scope_label"] = cfg["display_name"]
        else:
            cw_row = ag_wide.loc[cfg["census_wide_key"]]
            if cfg.get("census_extra_key") and cfg["census_extra_key"] in ag_wide.index:
                cw_row = cw_row.add(ag_wide.loc[cfg["census_extra_key"]], fill_value=0)

            top_types = []
            for raw_col, clean_label in NAICS_FARM_TYPES:
                val = cw_row.get(raw_col, 0)
                if pd.notna(val) and float(val) > 0:
                    top_types.append({"sector": clean_label, "farms": int(round(float(val)))})
            top_types.sort(key=lambda x: -x["farms"])

            c_stats = {
                "census_scope_label": cfg["display_name"],
                "total_farms": int(round(float(cw_row["Total farm area - Farms reporting_2021"]))),
                "total_operators": int(round(float(cw_row["Total number of farm operators_2021"]))),
                "total_acres": int(round(float(cw_row["Total farm area - Acres_2021"]))),
                "crop_acres": int(round(float(cw_row["Land in crops (ecluding Christmas tree area) - Acres_2021"]))),
                "woodlands_wetlands_acres": int(round(float(cw_row["Woodlands and wetlands - Acres_2021"]))),
                "gross_farm_receipts": int(round(float(cw_row["Total gross farm receipts (ecluding sales of forest products) in the calendar year prior to the census or for the last complete accounting (fiscal) year prior to the census - Amount $_2021"]))),
                "total_farm_capital": int(round(float(cw_row["Total farm capital - Market value $_2021"]))),
                "direct_sales_farms": int(round(float(cw_row["Agricultural products directly sold to consumers for human consumption - Farms reporting_2021"]))),
                "top_sectors": top_types[:4],
            }

        # Attach lower-tier CCS census profiles to matching municipalities in this county
        lt_cnty = cfg["census_lt_county"]
        cnty_lt_profiles = {
            m_name.upper(): prof
            for (c_name, m_name), prof in lt_lookup.items()
            if c_name == lt_cnty
        }
        for m_obj in municipalities_by_county.get(ga, []):
            m_up = m_obj["name"].upper().strip()
            matched_prof = cnty_lt_profiles.get(m_up)
            if not matched_prof:
                # Try substring match on canonical name
                for k_up, prof in cnty_lt_profiles.items():
                    if m_up in k_up or k_up in m_up:
                        matched_prof = prof
                        break
            # Avoid attaching county-override as lower-tier duplicate for single-tier Haldimand/Norfolk
            if cfg.get("census_lt_muni_override") and matched_prof:
                matched_prof = None
            m_obj["lower_tier_census"] = matched_prof

        # C. Survey summary (primary + optional sub-federations)
        sub_df = sdata[sdata[c_col].isin(cfg["survey_keys"])]
        survey_primary = compute_survey_summary(sub_df, subheaders_challenges, subheaders_priorities, col36_name)

        sub_fed_summaries = {}
        if "sub_federations" in cfg:
            for sf_label, sf_keys in cfg["sub_federations"].items():
                sf_df = sdata[sdata[c_col].isin(sf_keys)]
                sub_fed_summaries[sf_label] = compute_survey_summary(sf_df, subheaders_challenges, subheaders_priorities, col36_name)

        counties_bundle[ga] = {
            "county_key": ga,
            "display_name": cfg["display_name"],
            "default_federation": cfg["default_federation"],
            "region_name": cfg["region_name"],
            "attribution": attr_data,
            "census_2021": c_stats,
            "survey_2025": survey_primary,
            "sub_federation_surveys": sub_fed_summaries,
            "municipalities": municipalities_by_county.get(ga, []),
        }

    full_bundle = {
        "generated_at": pd.Timestamp.now().isoformat(),
        "provincial_survey_2025": provincial_survey,
        "regional_survey_2025": regional_survey,
        "counties": counties_bundle,
    }

    out_json = os.path.join(DATA_DIR, "outreach_data_bundle.json")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(full_bundle, f, indent=2)

    print(f"SUCCESS: Wrote {out_json} with {len(counties_bundle)} counties and {sum(len(v['municipalities']) for v in counties_bundle.values())} municipalities.")


if __name__ == "__main__":
    main()
