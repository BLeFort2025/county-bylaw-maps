import pandas as pd
import sqlite3
import numpy as np

excel_path = r"C:\Users\ben.lefort\Downloads\Ontario Municipal DC Bylaws 2026 Verification Tracker (1).xlsx"
db_path = r"C:\Users\ben.lefort\OneDrive - Ontario Federation of Agriculture\Desktop\Municipal Bylaw Database\Data Pulls\Reports\Province Wide\All bylaws\county-bylaw-maps\bylaws.db"

print("Loading Excel...")
df = pd.read_excel(excel_path)

cleaned = 0
for idx, row in df.iterrows():
    enacted = str(row.get('Enacted Date'))[:10]
    expiry = str(row.get('Expiry Date'))[:10]
    if enacted == expiry and enacted not in ('nan', 'NaT', ''):
        df.at[idx, 'Expiry Date'] = np.nan
        cleaned += 1

print(f"Cleaned {cleaned} duplicate expiry dates in Excel.")
df.to_excel(excel_path, index=False)
print("Saved corrected Excel file.")

# --- Database Comparison ---
conn = sqlite3.connect(db_path)
query = """
SELECT 
    m.name as Municipality,
    e.exemption_status as db_farm_exemption,
    d.has_dc as db_has_dc,
    b.bylaw_name as db_bylaw_name,
    b.date_enacted as db_enacted,
    b.expiry_date as db_expiry
FROM municipalities m
LEFT JOIN bylaws b ON m.id = b.municipality_id AND b.category = 'DC'
LEFT JOIN bylaw_exemptions e ON b.id = e.bylaw_id
LEFT JOIN details_dc d ON b.id = d.bylaw_id
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
    if pd.isna(code): return ''
    return str(code).strip()

def clean_str(s):
    if pd.isna(s) or str(s) == '': return ""
    return str(s).strip()

num_exemptions = 0
num_has_dc = 0
num_names = 0
num_dates = 0

for idx, row in merged.iterrows():
    xl_exemption = clean_str(row.get('Farm Exemption'))
    db_exemption = map_yes_no(row.get('db_farm_exemption'))
    if xl_exemption and db_exemption and xl_exemption != db_exemption and xl_exemption not in ('nan', 'NaT'):
        num_exemptions += 1
        
    xl_has_dc = clean_str(row.get('Has DC Bylaw'))
    db_has_dc = map_yes_no(row.get('db_has_dc'))
    if xl_has_dc and db_has_dc and xl_has_dc != db_has_dc and xl_has_dc not in ('nan', 'NaT'):
        num_has_dc += 1
        
    xl_name = clean_str(row.get('Bylaw Name')).replace('\n', ' ')
    db_name = clean_str(row.get('db_bylaw_name')).replace('\n', ' ')
    if xl_name and xl_name != db_name and xl_name not in ('nan', 'NaT', 'No DC By-law', 'No DC Bylaw'):
        num_names += 1
        
    xl_enacted = str(row.get('Enacted Date'))[:10] if pd.notna(row.get('Enacted Date')) else ""
    db_enacted = clean_str(row.get('db_enacted'))[:10]
    xl_expiry = str(row.get('Expiry Date'))[:10] if pd.notna(row.get('Expiry Date')) else ""
    db_expiry = clean_str(row.get('db_expiry'))[:10]
    
    if (xl_enacted and xl_enacted != db_enacted and xl_enacted not in ('nan', 'NaT')) or (xl_expiry and xl_expiry != db_expiry and xl_expiry not in ('nan', 'NaT')):
        num_dates += 1

print("\n--- SUMMARY OF UPDATES IN EXCEL ---")
print(f"Farm Exemption Status changed for {num_exemptions} municipalities.")
print(f"'Has DC Bylaw' status changed for {num_has_dc} municipalities.")
print(f"Bylaw Name was updated for {num_names} municipalities.")
print(f"Enacted or Expiry Dates were updated for {num_dates} municipalities.")
