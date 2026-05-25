import sqlite3

conn = sqlite3.connect('bylaws.db')
cur = conn.cursor()
cur.execute("""
    SELECT m.name, d.has_lgd_definition, d.has_herding_def, b.progress_label
    FROM municipalities m
    JOIN bylaws b ON b.municipality_id = m.id
    JOIN details_lgd d ON d.bylaw_id = b.id
    WHERE b.category = 'LGD' AND m.geographic_area = 'Grey'
    ORDER BY m.name
""")
rows = cur.fetchall()
print("=== Local DB: Grey County LGD Data ===")
for r in rows:
    print(f"{r[0]:<25} LGD={str(r[1] or 'None'):<5} HD={str(r[2] or 'None'):<5} Label={r[3]}")
print(f"\nTotal: {len(rows)}")
lgd_defs = sum(1 for r in rows if r[1] and r[1].lower() == 'yes')
print(f"With LGD definition: {lgd_defs}")
conn.close()
