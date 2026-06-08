import os, sys
from datetime import datetime
sys.path.insert(0, r'c:\Users\ben.lefort\OneDrive - Ontario Federation of Agriculture\Desktop\Municipal Bylaw Database\Data Pulls\Reports\Province Wide\All bylaws\county-bylaw-maps')
import db_utils

conn = db_utils.get_connection()

updates = [
    {
        'muni_id': 70, # Centre Wellington
        'bylaw_name': 'By-law 2026-xx (Replaces 2021-1)',
        'date_enacted': '2026-03-30',
        'expiry_date': '2031-03-30', # typically 5 years
        'expiry_notes': 'New bylaw passed March 2026. Phased rates.',
        'bylaw_link': 'https://www.centrewellington.ca/developmentcharges',
    },
    {
        'muni_id': 153, # Grimsby
        'bylaw_name': 'BY-LAW NO. 21-14 (amended by 25-51)',
        'date_enacted': '2021-03-22',
        'expiry_date': None,
        'expiry_notes': 'Bylaw 25-51 removed the expiration date',
        'bylaw_link': 'https://www.grimsby.ca/en/doing-business/development-charges.aspx',
    },
    {
        'muni_id': 419, # Wasaga Beach
        'bylaw_name': 'BY-LAW 2026-35 & 2026-36',
        'date_enacted': '2026-04-30',
        'expiry_date': '2031-04-30',
        'expiry_notes': 'Passed April 30, 2026',
        'bylaw_link': 'https://www.wasagabeach.com/programs-services/by-laws-policies',
    },
    {
        'muni_id': 428, # West Grey
        'bylaw_name': 'By-law 31-2020 (amended by 2025-022)',
        'date_enacted': '2020-04-28',
        'expiry_date': None,
        'expiry_notes': 'Bylaw 2025-022 removed the expiration date',
        'bylaw_link': 'https://www.westgrey.com/en/build-invest-grow/development-charges.aspx',
    }
]

for u in updates:
    # Get bylaw_id
    cur = conn.execute("SELECT id FROM bylaws WHERE municipality_id = %s AND category = 'DC'", (u['muni_id'],))
    row = cur.fetchone()
    if row:
        bylaw_id = row['id']
        db_utils.update_record(conn, 'bylaws', bylaw_id, 'bylaw_name', u['bylaw_name'], user='AI_Agent')
        db_utils.update_record(conn, 'bylaws', bylaw_id, 'date_enacted', u['date_enacted'], user='AI_Agent')
        db_utils.update_record(conn, 'bylaws', bylaw_id, 'expiry_date', u['expiry_date'], user='AI_Agent')
        db_utils.update_record(conn, 'bylaws', bylaw_id, 'expiry_notes', u['expiry_notes'], user='AI_Agent')
        db_utils.update_record(conn, 'bylaws', bylaw_id, 'bylaw_link', u['bylaw_link'], user='AI_Agent')
        print(f"Updated municipality {u['muni_id']}")
    else:
        print(f"Could not find DC bylaw for municipality {u['muni_id']}")

print("Updates complete.")
