import pandas as pd
import sqlite3

excel_path = r"C:\Users\ben.lefort\Downloads\Ontario Municipal DC Bylaws 2026 Verification Tracker (1).xlsx"
db_path = r"C:\Users\ben.lefort\OneDrive - Ontario Federation of Agriculture\Desktop\Municipal Bylaw Database\Data Pulls\Reports\Province Wide\All bylaws\county-bylaw-maps\bylaws.db"

df = pd.read_excel(excel_path)
conn = sqlite3.connect(db_path)
query = """
SELECT 
    m.name as Municipality,
    e.exemption_status as db_farm_exemption
FROM municipalities m
LEFT JOIN bylaws b ON m.id = b.municipality_id AND b.category = 'DC'
LEFT JOIN bylaw_exemptions e ON b.id = e.bylaw_id
"""
db_df = pd.read_sql_query(query, conn)
conn.close()

df['match_name'] = df['Municipality'].str.strip().str.lower()
db_df['match_name'] = db_df['Municipality'].str.strip().str.lower()
merged = pd.merge(df, db_df, on='match_name', how='inner')

def map_yes_no(code):
    if str(code) == '1': return 'Yes'
    if str(code) == '2': return 'No'
    if str(code) == '3': return 'N/A'
    if str(code) == '4': return 'NOT KNOWN'
    if pd.isna(code): return 'Blank'
    return str(code).strip()

def clean_str(s):
    if pd.isna(s) or str(s) == '': return 'Blank'
    return str(s).strip()

transitions = {}

for idx, row in merged.iterrows():
    muni = row['Municipality_x']
    xl_exemption = clean_str(row.get('Farm Exemption'))
    db_exemption = map_yes_no(row.get('db_farm_exemption'))
    
    if xl_exemption != 'nan' and xl_exemption != 'NaT':
        if xl_exemption != db_exemption:
            transition_key = f"{db_exemption} -> {xl_exemption}"
            if transition_key not in transitions:
                transitions[transition_key] = []
            transitions[transition_key].append(muni)

print("\n--- FARM EXEMPTION CHANGES ---")
total_changes = sum(len(m) for m in transitions.values())
print(f"Total Farm Exemption changes: {total_changes}\n")

for trans, munis in sorted(transitions.items()):
    print(f"{trans} ({len(munis)} municipalities):")
    for m in munis:
        print(f"  - {m}")
    print()
