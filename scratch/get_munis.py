import os, sys, pandas as pd
sys.path.insert(0, r'c:\Users\ben.lefort\OneDrive - Ontario Federation of Agriculture\Desktop\Municipal Bylaw Database\Data Pulls\Reports\Province Wide\All bylaws\county-bylaw-maps')
import db_utils

conn = db_utils.get_connection()
munis = ['Centre Wellington', 'Wasaga Beach', 'West Grey', 'Grimsby']
query = """
SELECT m.id as muni_id, m.name, b.id as bylaw_id, b.bylaw_name, b.date_enacted, b.expiry_date, b.bylaw_link, be.exemption_status, be.exemption_wording
FROM municipalities m
JOIN bylaws b ON b.municipality_id = m.id
LEFT JOIN bylaw_exemptions be ON be.bylaw_id = b.id
WHERE m.name = ANY(%s) AND b.category = 'DC'
"""
df = pd.read_sql_query(query, conn.conn, params=(munis,))
print(df.to_dict('records'))
