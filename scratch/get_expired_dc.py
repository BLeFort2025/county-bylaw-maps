import os, sys, pandas as pd
sys.path.insert(0, r'c:\Users\ben.lefort\OneDrive - Ontario Federation of Agriculture\Desktop\Municipal Bylaw Database\Data Pulls\Reports\Province Wide\All bylaws\county-bylaw-maps')
import db_utils
from datetime import datetime
conn = db_utils.get_connection()
query = """
SELECT m.name, b.bylaw_name, b.expiry_date 
FROM bylaws b 
JOIN municipalities m ON m.id = b.municipality_id 
WHERE b.category = 'DC'
"""
df = pd.read_sql_query(query, conn.conn)
df['expiry_date'] = pd.to_datetime(df['expiry_date'], errors='coerce')
expired = df[df['expiry_date'] < datetime.now()]
print('Expired count:', len(expired))
print(expired.to_string())
