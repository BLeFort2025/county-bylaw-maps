"""
Analyze the contacts and municipalities tables for generic vs personal email addresses.
Generic = clerk@, info@, admin@, general@, office@, municipality@, reception@, etc.
Personal = first initial + last name patterns like jsmith@, j.smith@, etc.
"""
import sqlite3
import re
from collections import Counter

conn = sqlite3.connect('bylaws.db')

# ── 1. Check municipalities.clerk_email ──
print("=" * 70)
print("  MUNICIPALITIES TABLE: clerk_email field")
print("=" * 70)
cur = conn.execute("""
    SELECT name, clerk_email FROM municipalities 
    WHERE clerk_email IS NOT NULL AND length(clerk_email) > 2
""")
muni_emails = cur.fetchall()
print(f"Total with clerk_email: {len(muni_emails)}")
for name, email in muni_emails:
    local = email.split('@')[0].lower() if '@' in email else email
    is_generic = any(w in local for w in ['clerk', 'info', 'admin', 'general', 'office', 'reception', 
                                           'bylaw', 'municipal', 'township', 'town', 'city', 'contact'])
    tag = "GENERIC" if is_generic else "PERSONAL"
    print(f"  [{tag}] {name}: {email}")

# ── 2. Check municipalities.website for deriving generic emails ──
print("\n" + "=" * 70)
print("  MUNICIPALITIES TABLE: website field (for domain extraction)")
print("=" * 70)
cur2 = conn.execute("""
    SELECT count(*) FROM municipalities 
    WHERE website IS NOT NULL AND length(website) > 5
""")
print(f"Municipalities with website: {cur2.fetchone()[0]}")

# ── 3. Check contacts table - municipal_email field ──
print("\n" + "=" * 70)
print("  CONTACTS TABLE: municipal_email field")
print("=" * 70)
cur3 = conn.execute("""
    SELECT count(*) FROM contacts 
    WHERE municipal_email IS NOT NULL AND length(municipal_email) > 2
""")
print(f"Contacts with municipal_email: {cur3.fetchone()[0]}")

cur4 = conn.execute("""
    SELECT DISTINCT c.municipality_id, m.name, c.municipal_email 
    FROM contacts c
    JOIN municipalities m ON m.id = c.municipality_id
    WHERE c.municipal_email IS NOT NULL AND length(c.municipal_email) > 2
    LIMIT 30
""")
rows = cur4.fetchall()
print(f"Sample municipal_email values:")
for mid, name, email in rows:
    print(f"  {name}: {email}")

# ── 4. Analyze generic patterns in contacts.email ──
print("\n" + "=" * 70)
print("  CONTACTS TABLE: Generic email patterns in personal email field")
print("=" * 70)

# Get all Clerk-titled contacts
cur5 = conn.execute("""
    SELECT c.municipality_id, m.name, c.title, c.email, c.municipal_email
    FROM contacts c
    JOIN municipalities m ON m.id = c.municipality_id
    WHERE c.title LIKE '%Clerk%' 
      AND c.title NOT LIKE '%Deputy%'
      AND c.email IS NOT NULL AND length(c.email) > 2
    ORDER BY m.name
""")
clerk_contacts = cur5.fetchall()
print(f"\nClerk (non-Deputy) contacts with email: {len(clerk_contacts)}")

generic_count = 0
personal_count = 0
generic_patterns = ['clerk', 'info', 'admin', 'general', 'office', 'reception', 
                    'bylaw', 'municipal', 'township', 'town', 'city', 'contact']

for mid, name, title, email, muni_email in clerk_contacts[:40]:
    local = email.split('@')[0].lower() if '@' in email else email.lower()
    is_generic = any(w in local for w in generic_patterns)
    if is_generic:
        generic_count += 1
    else:
        personal_count += 1
    tag = "GENERIC" if is_generic else "PERSONAL"
    muni_note = f" | municipal_email={muni_email}" if muni_email else ""
    print(f"  [{tag}] {name} | {title} | {email}{muni_note}")

# Count all
for mid, name, title, email, muni_email in clerk_contacts[40:]:
    local = email.split('@')[0].lower() if '@' in email else email.lower()
    is_generic = any(w in local for w in generic_patterns)
    if is_generic:
        generic_count += 1
    else:
        personal_count += 1

print(f"\n  Summary: {generic_count} GENERIC, {personal_count} PERSONAL out of {len(clerk_contacts)} Clerk contacts")

# ── 5. How many municipalities have a generic clerk/info@ email available? ──
print("\n" + "=" * 70)
print("  COVERAGE: Municipalities with ANY generic email available")
print("=" * 70)

cur6 = conn.execute("""
    SELECT DISTINCT c.municipality_id, m.name
    FROM contacts c
    JOIN municipalities m ON m.id = c.municipality_id
    WHERE c.email IS NOT NULL AND length(c.email) > 2
      AND (
        lower(c.email) LIKE 'clerk%' OR
        lower(c.email) LIKE 'info%' OR
        lower(c.email) LIKE 'admin%' OR
        lower(c.email) LIKE 'general%' OR 
        lower(c.email) LIKE 'office%' OR
        lower(c.email) LIKE 'reception%' OR
        lower(c.email) LIKE 'contact%' OR
        lower(c.email) LIKE 'municipal%' OR
        lower(c.email) LIKE 'township%' OR
        lower(c.email) LIKE 'town@%' OR
        lower(c.email) LIKE 'city@%'
      )
""")
generic_munis = cur6.fetchall()
print(f"Municipalities with generic email in contacts.email: {len(generic_munis)}")

# Also check municipal_email field
cur7 = conn.execute("""
    SELECT DISTINCT c.municipality_id, m.name
    FROM contacts c
    JOIN municipalities m ON m.id = c.municipality_id
    WHERE c.municipal_email IS NOT NULL AND length(c.municipal_email) > 2
""")
muni_email_munis = cur7.fetchall()
print(f"Municipalities with contacts.municipal_email populated: {len(muni_email_munis)}")

# Combined: either generic in email or has municipal_email
cur8 = conn.execute("""
    SELECT DISTINCT c.municipality_id, m.name
    FROM contacts c
    JOIN municipalities m ON m.id = c.municipality_id
    WHERE (
        (c.email IS NOT NULL AND length(c.email) > 2 AND (
            lower(c.email) LIKE 'clerk%' OR
            lower(c.email) LIKE 'info%' OR
            lower(c.email) LIKE 'admin%' OR
            lower(c.email) LIKE 'general%' OR 
            lower(c.email) LIKE 'office%'
        ))
        OR
        (c.municipal_email IS NOT NULL AND length(c.municipal_email) > 2)
    )
""")
combined = cur8.fetchall()
print(f"Combined (generic email OR municipal_email): {len(combined)}")

conn.close()
