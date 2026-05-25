import sqlite3
import pandas as pd

conn = sqlite3.connect('bylaws.db')

query = """
SELECT 
    m.name as municipality,
    b.progress_label,
    d.has_lgd_definition,
    d.lgd_definition,
    d.has_herding_def,
    d.herding_definition
FROM bylaws b
JOIN municipalities m ON b.municipality_id = m.id
JOIN details_lgd d ON b.id = d.bylaw_id
WHERE d.has_lgd_definition = 'Yes' OR d.has_herding_def = 'Yes' OR d.lgd_definition IS NOT NULL
"""

df = pd.read_sql_query(query, conn)
conn.close()

for index, row in df.iterrows():
    if row['lgd_definition'] or row['herding_definition']:
        print(f"[{row['progress_label']}] {row['municipality']}:")
        if row['lgd_definition']:
            print(f"  LGD Def: {row['lgd_definition']}")
        if row['herding_definition']:
            print(f"  Herd Def: {row['herding_definition']}")
        print("-" * 60)
