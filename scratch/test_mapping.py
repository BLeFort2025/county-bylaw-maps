import pandas as pd
import sys
import os

# Add pages directory to path so we can import the module
sys.path.append(os.path.join(os.getcwd(), 'pages'))

# Or we can just redefine it here to test it exactly
import re
import sqlite3

def _load_county_dict():
    db_path = "bylaws.db"
    county_dict = {}
    if os.path.exists(db_path):
        conn = sqlite3.connect(db_path)
        db_df = pd.read_sql_query("SELECT name, geographic_area FROM municipalities", conn)
        for _, r in db_df.iterrows():
            if pd.notna(r['name']) and pd.notna(r['geographic_area']):
                county_dict[str(r['name']).upper().strip()] = r['geographic_area']
        conn.close()
    return county_dict

def _map_county(m_name, county_dict):
    m_upper = str(m_name).upper().strip()
    if m_upper in county_dict:
        return county_dict[m_upper]

    clean_m = re.sub(r'\s+(TP|C|M)$', '', m_upper).strip()
    if clean_m in county_dict:
        return county_dict[clean_m]

    for db_name, area in county_dict.items():
        if clean_m in db_name or db_name in clean_m:
            return area
    return m_name

registry_df = pd.read_csv('signals/portal_registry.csv')
county_dict = _load_county_dict()
registry_df['county'] = registry_df['municipality_name'].apply(lambda n: _map_county(n, county_dict))

counties = registry_df['county'].unique()
print(f"Unique counties ({len(counties)}):")
for c in sorted([str(x) for x in counties]):
    print("  -", c)

bad_counties = registry_df[~registry_df['county'].isin(county_dict.values())]['municipality_name'].tolist()
print(f"\nFailed to map ({len(bad_counties)}):")
print(bad_counties)
