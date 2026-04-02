import sqlite3
import psycopg2
import re

DB_PATH = r"c:\Users\ben.lefort\OneDrive - Ontario Federation of Agriculture\Desktop\Municipal Bylaw Database\Data Pulls\Reports\Province Wide\All bylaws\county-bylaw-maps\bylaws.db"
NEON_URL = "postgresql://neondb_owner:npg_gjmiS41HEeXB@ep-fancy-resonance-amthrghm.c-5.us-east-1.aws.neon.tech/neondb?sslmode=require"

try:
    pg_conn = psycopg2.connect(NEON_URL)
    pg_cur = pg_conn.cursor()

    sqlite_conn = sqlite3.connect(DB_PATH)
    sqlite_cur = sqlite_conn.cursor()

    tables = sqlite_cur.execute("SELECT name, sql FROM sqlite_master WHERE type='table'").fetchall()

    for table_name, sql in tables:
        if table_name == 'sqlite_sequence' or table_name.startswith('sqlite_'): 
            continue
        
        print(f"\nProcessing {table_name}...")
        
        # Standardize SQL for Postgres
        pg_sql = sql.replace('"', '')  
        pg_sql = re.sub(r'INTEGER PRIMARY KEY AUTOINCREMENT', 'SERIAL PRIMARY KEY', pg_sql, flags=re.IGNORECASE)
        pg_sql = re.sub(r'INTEGER PRIMARY KEY', 'SERIAL PRIMARY KEY', pg_sql, flags=re.IGNORECASE)
        pg_sql = re.sub(r'DATETIME', 'TIMESTAMP', pg_sql, flags=re.IGNORECASE)
        
        # Drop and create
        pg_cur.execute(f"DROP TABLE IF EXISTS {table_name} CASCADE;")
        try:
            pg_cur.execute(pg_sql)
        except Exception as e:
            print(f"Error creating table {table_name}: {e}")
            pg_conn.rollback()
            continue
            
        sqlite_cur.execute(f"PRAGMA table_info({table_name})")
        cols = [row[1] for row in sqlite_cur.fetchall()]
        
        sqlite_cur.execute(f"SELECT * FROM {table_name}")
        rows = sqlite_cur.fetchall()
        
        if rows:
            placeholders = ','.join(['%s'] * len(cols))
            col_names = ','.join([f'"{c}"' for c in cols])
            insert_sql = f"INSERT INTO {table_name} ({col_names}) VALUES ({placeholders})"
            try:
                pg_cur.executemany(insert_sql, rows)
                print(f"Migrated {len(rows)} rows into {table_name}.")
                
                if 'id' in cols:
                    pg_cur.execute(f"SELECT setval('{table_name}_id_seq', (SELECT COALESCE(MAX(id), 1) FROM {table_name}));")
            except Exception as e:
                print(f"Error inserting into {table_name}: {e}")
                pg_conn.rollback()
                continue
                
        pg_conn.commit()
    
    print("\nSUCCESS! All tables migrated.")
except Exception as e:
    print(f"Fatal error: {e}")
