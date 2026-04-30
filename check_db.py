import sqlite3
conn = sqlite3.connect('bylaws.db')
print(conn.execute('SELECT bylaw_name FROM bylaws WHERE municipality_id = (SELECT id FROM municipalities WHERE name = "Gravenhurst")').fetchone()[0])
conn.close()
