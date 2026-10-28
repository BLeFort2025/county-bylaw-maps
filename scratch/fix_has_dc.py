import sqlite3

c = sqlite3.connect('bylaws.db')

for name in ['Petrolia', 'Sarnia', 'Stone Mills']:
    c.execute(f"UPDATE details_dc SET has_dc = '1' WHERE bylaw_id = (SELECT b.id FROM bylaws b JOIN municipalities m ON b.municipality_id = m.id WHERE b.category='DC' AND m.name = '{name}')")

c.commit()
c.close()
print("Fixed has_dc for Petrolia, Sarnia, Stone Mills.")
