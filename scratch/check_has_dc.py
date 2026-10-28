import sqlite3

c = sqlite3.connect('bylaws.db')
res = c.execute("SELECT m.name, d.has_dc FROM municipalities m JOIN bylaws b ON m.id = b.municipality_id JOIN details_dc d ON b.id = d.bylaw_id WHERE b.category='DC' AND m.name IN ('Petrolia', 'Stone Mills', 'Sarnia')").fetchall()
print(res)
