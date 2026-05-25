import psycopg2

conn = psycopg2.connect('postgresql://neondb_owner:npg_gjmiS41HEeXB@ep-fancy-resonance-amthrghm.c-5.us-east-1.aws.neon.tech/neondb?sslmode=require')
cur = conn.cursor()

# Check Grey County LGD data in cloud DB
cur.execute("""
    SELECT m.name, d.has_lgd_definition, d.has_herding_def, b.progress_label
    FROM municipalities m
    JOIN bylaws b ON b.municipality_id = m.id
    JOIN details_lgd d ON d.bylaw_id = b.id
    WHERE b.category = 'LGD' AND m.geographic_area = 'Grey'
    ORDER BY m.name
""")
rows = cur.fetchall()
print("=== Cloud DB: Grey County LGD Data ===")
print(f"{'Municipality':<25} {'LGD Def':<10} {'Herding':<10} {'Progress Label'}")
print("-" * 80)
for r in rows:
    print(f"{r[0]:<25} {r[1] or 'None':<10} {r[2] or 'None':<10} {r[3] or 'None'}")

print(f"\nTotal: {len(rows)} municipalities")
lgd_defs = sum(1 for r in rows if r[1] and r[1].lower() == 'yes')
print(f"With LGD definition: {lgd_defs}")

conn.close()
