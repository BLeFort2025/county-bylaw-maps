"""Audit both databases to compare schemas and row counts."""
import sqlite3
import psycopg2

CLOUD_URL = 'postgresql://neondb_owner:npg_gjmiS41HEeXB@ep-fancy-resonance-amthrghm.c-5.us-east-1.aws.neon.tech/neondb?sslmode=require'
LOCAL_DB = 'bylaws.db'

# Local SQLite
print("=" * 70)
print("  LOCAL SQLITE DATABASE")
print("=" * 70)
lconn = sqlite3.connect(LOCAL_DB)
lcur = lconn.cursor()
lcur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
local_tables = [r[0] for r in lcur.fetchall()]
for t in local_tables:
    lcur.execute(f"SELECT COUNT(*) FROM [{t}]")
    count = lcur.fetchone()[0]
    lcur.execute(f"PRAGMA table_info([{t}])")
    cols = [r[1] for r in lcur.fetchall()]
    print(f"  {t:<30} {count:>5} rows  cols: {', '.join(cols[:8])}{'...' if len(cols) > 8 else ''}")
lconn.close()

# Cloud PostgreSQL
print("\n" + "=" * 70)
print("  CLOUD POSTGRESQL DATABASE (Neon)")
print("=" * 70)
pconn = psycopg2.connect(CLOUD_URL)
pcur = pconn.cursor()
pcur.execute("""
    SELECT table_name FROM information_schema.tables 
    WHERE table_schema = 'public' ORDER BY table_name
""")
cloud_tables = [r[0] for r in pcur.fetchall()]
for t in cloud_tables:
    pcur.execute(f'SELECT COUNT(*) FROM "{t}"')
    count = pcur.fetchone()[0]
    pcur.execute(f"""
        SELECT column_name FROM information_schema.columns 
        WHERE table_name = '{t}' ORDER BY ordinal_position
    """)
    cols = [r[0] for r in pcur.fetchall()]
    print(f"  {t:<30} {count:>5} rows  cols: {', '.join(cols[:8])}{'...' if len(cols) > 8 else ''}")
pconn.close()

# Diff
print("\n" + "=" * 70)
print("  COMPARISON")
print("=" * 70)
local_set = set(local_tables)
cloud_set = set(cloud_tables)
print(f"  Tables in local only:  {local_set - cloud_set or 'None'}")
print(f"  Tables in cloud only:  {cloud_set - local_set or 'None'}")
print(f"  Tables in both:        {local_set & cloud_set}")
