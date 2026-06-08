import pandas as pd
import sqlite3
import re

def _load_county_dict():
    db_path = "bylaws.db"
    county_dict = {}
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
    clean_m_no_punct = re.sub(r'[^\w\s]', '', clean_m)
    if clean_m in county_dict:
        return county_dict[clean_m]

    for db_name, area in county_dict.items():
        db_name_no_punct = re.sub(r'[^\w\s]', '', db_name)
        if clean_m_no_punct in db_name_no_punct or db_name_no_punct in clean_m_no_punct:
            return area
            
    # special fallbacks for some that might be missing
    if "CHATHAM" in m_upper and "KENT" in m_upper:
        return "Chatham-Kent"
        
    return m_name

registry_df = pd.read_csv('signals/portal_registry.csv')
county_dict = _load_county_dict()
registry_df['county'] = registry_df['municipality_name'].apply(lambda n: _map_county(n, county_dict))

print("Is Chatham-Kent mapped now?")
print(registry_df[registry_df['municipality_name'].str.contains('CHATHAM')]['county'].values)

valid_regions = set(county_dict.values())
unique_counties = sorted([str(c) for c in registry_df['county'].unique() if c and str(c).strip() and str(c) in valid_regions])
print(f"Total unique valid counties: {len(unique_counties)}")
