import sqlite3
conn = sqlite3.connect('bylaws.db')
print(conn.execute('SELECT m.name, b.category, b.bylaw_name FROM municipalities m JOIN bylaws b ON b.municipality_id = m.id WHERE m.name = "Gravenhurst"').fetchall())
conn.close()
