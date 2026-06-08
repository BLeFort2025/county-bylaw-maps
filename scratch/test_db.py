import sqlite3
import pandas as pd

conn = sqlite3.connect('bylaws.db')
df = pd.read_sql_query("SELECT name, geographic_area FROM municipalities", conn)
print("Some names in DB:")
print(df['name'].head(20).tolist())
print("\nIs Addington anywhere?")
print(df[df['name'].str.contains('ADDINGTON', case=False, na=False)][['name', 'geographic_area']])

conn.close()
