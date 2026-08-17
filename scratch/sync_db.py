import pandas as pd
import sqlite3
import numpy as np

excel_path = r"C:\Users\ben.lefort\Downloads\Ontario Municipal DC Bylaws 2026 Verification Tracker (1).xlsx"
db_path = r"C:\Users\ben.lefort\OneDrive - Ontario Federation of Agriculture\Desktop\Municipal Bylaw Database\Data Pulls\Reports\Province Wide\All bylaws\county-bylaw-maps\bylaws.db"

# 1. Update from Excel
df = pd.read_excel(excel_path)
df['match_name'] = df['Municipality'].str.strip().str.lower()

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

def get_exemption_code(val):
    v = str(val).strip().lower()
    if v == 'yes': return '1'
    if v == 'no': return '2'
    if v == 'n/a': return '3'
    if v == 'not known': return '4'
    return None

def get_has_dc_code(val):
    v = str(val).strip().lower()
    if v == 'yes': return '1'
    if v == 'no': return '2'
    if v == 'not known': return '4'
    return None

def clean_date(d):
    if pd.isna(d): return None
    s = str(d)[:10]
    if s in ('nan', 'NaT', ''): return None
    return s

for idx, row in df.iterrows():
    m_name = row['match_name']
    
    # Get muni ID
    cursor.execute("SELECT id FROM municipalities WHERE lower(trim(name)) = ?", (m_name,))
    m_res = cursor.fetchone()
    if not m_res: continue
    m_id = m_res[0]
    
    # Get bylaw ID
    cursor.execute("SELECT id FROM bylaws WHERE municipality_id = ? AND category = 'DC'", (m_id,))
    b_res = cursor.fetchone()
    if not b_res: continue
    b_id = b_res[0]
    
    # Update bylaws table
    b_name = str(row.get('Bylaw Name')).strip() if pd.notna(row.get('Bylaw Name')) else None
    if b_name in ('nan', 'No DC By-law', 'No DC Bylaw'): b_name = None
    
    enacted = clean_date(row.get('Enacted Date'))
    expiry = clean_date(row.get('Expiry Date'))
    link = str(row.get('Bylaw Link')).strip() if pd.notna(row.get('Bylaw Link')) else None
    if link == 'nan': link = None
    
    cursor.execute("""
        UPDATE bylaws 
        SET bylaw_name = ?, date_enacted = ?, expiry_date = ?, bylaw_link = COALESCE(?, bylaw_link)
        WHERE id = ?
    """, (b_name, enacted, expiry, link, b_id))
    
    # Update bylaw_exemptions
    ex_code = get_exemption_code(row.get('Farm Exemption'))
    if ex_code:
        cursor.execute("UPDATE bylaw_exemptions SET exemption_status = ? WHERE bylaw_id = ?", (ex_code, b_id))
        
    # Update details_dc
    has_dc = get_has_dc_code(row.get('Has DC Bylaw'))
    if has_dc:
        cursor.execute("UPDATE details_dc SET has_dc = ? WHERE bylaw_id = ?", (has_dc, b_id))


# 2. Manual Overrides for the 7 specific municipalities
overrides = [
    ('Sarnia', '2', None), # No
    ('Petrolia', '1', None), # Yes
    ('Stone Mills', '1', None), # Yes
    ('North Huron', '4', 'https://www.northhuron.ca/'), # NOT KNOWN
    ('Northumberland', '4', 'https://www.northumberland.ca/DevelopmentCharges'), # NOT KNOWN
    ('Smiths Falls', '4', 'https://www.smithsfalls.ca/'), # NOT KNOWN
    ('Southwold', '4', 'https://www.southwold.ca/') # NOT KNOWN
]

for name, ex_code, new_link in overrides:
    cursor.execute("SELECT id FROM municipalities WHERE name = ?", (name,))
    m_id = cursor.fetchone()[0]
    cursor.execute("SELECT id FROM bylaws WHERE municipality_id = ? AND category = 'DC'", (m_id,))
    b_id = cursor.fetchone()[0]
    
    cursor.execute("UPDATE bylaw_exemptions SET exemption_status = ? WHERE bylaw_id = ?", (ex_code, b_id))
    if new_link:
        cursor.execute("UPDATE bylaws SET bylaw_link = ? WHERE id = ?", (new_link, b_id))

conn.commit()
conn.close()
print("Database successfully synchronized.")
