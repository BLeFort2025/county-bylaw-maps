import sqlite3
conn = sqlite3.connect('bylaws.db')

# Check AMCTO contacts table structure
cur = conn.execute("SELECT municipality_id, title, first_name, last_name, email FROM contacts WHERE email IS NOT NULL AND length(email)>2 LIMIT 10")
for r in cur.fetchall():
    print(r)

print()

# Check how many have Clerk in title
cur2 = conn.execute("SELECT count(*) FROM contacts WHERE title LIKE '%Clerk%' AND email IS NOT NULL AND length(email)>2")
print('Contacts with Clerk title + email:', cur2.fetchone()[0])

cur3 = conn.execute("SELECT DISTINCT title FROM contacts WHERE title LIKE '%Clerk%' LIMIT 15")
print('Clerk titles:')
for r in cur3.fetchall():
    print(' ', r[0])

# How many unique municipalities have a contact with Clerk title
cur4 = conn.execute("SELECT count(DISTINCT municipality_id) FROM contacts WHERE title LIKE '%Clerk%' AND email IS NOT NULL AND length(email)>2")
print('\nUnique munis with Clerk contact + email:', cur4.fetchone()[0])

# Sample a few to see structure
print('\n--- Sample Clerk contacts ---')
cur5 = conn.execute("""
    SELECT c.municipality_id, m.name, c.title, c.first_name, c.last_name, c.email
    FROM contacts c
    JOIN municipalities m ON m.id = c.municipality_id
    WHERE c.title LIKE '%Clerk%' AND c.email IS NOT NULL AND length(c.email)>2
    LIMIT 10
""")
for r in cur5.fetchall():
    print(r)

conn.close()
