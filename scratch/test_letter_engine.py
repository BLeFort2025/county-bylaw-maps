"""Quick smoke test for letter_engine.py"""
import sys, os
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
if sys.platform == "win32":
    try: sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except: pass

from letter_engine import (
    fill_letter_template, letter_to_plain_text,
    generate_mailto_link, build_email_subject, build_fields,
    resolve_municipality_id, get_recipient_email,
)

# 1. Test build_fields
fields = build_fields(
    sender_name="John Smith",
    sender_title="President",
    county_federation="Huron County Federation of Agriculture",
    contact_info="john@example.com | (519) 555-1234",
    municipality_name="Bayham",
    bylaw_name="BY-LAW No. 2022-045",
)
print("✅ build_fields():", fields)

# 2. Test letter_to_plain_text
template = os.path.join(PROJECT_ROOT, "letters", "development_charges_letter.docx")
text = ""
if os.path.exists(template):
    text = letter_to_plain_text(template, fields)
    print(f"\n✅ letter_to_plain_text() — {len(text)} chars")
    print("First 500 chars:")
    print(text[:500])
    
    # Check all placeholders are gone
    import re
    remaining = re.findall(r'\[INSERT [^\]]+\]', text)
    if remaining:
        print(f"\n❌ UNFILLED PLACEHOLDERS: {remaining}")
    else:
        print(f"\n✅ All placeholders replaced!")
else:
    print(f"⚠️ Template not found: {template}")

# 3. Test fill_letter_template (docx generation)
if os.path.exists(template):
    doc_bytes = fill_letter_template(template, fields)
    print(f"\n✅ fill_letter_template() — {doc_bytes.getbuffer().nbytes} bytes")

# 4. Test mailto link
subject = build_email_subject("Bayham", "Development Charges")
mailto = generate_mailto_link("bayham@bayham.on.ca", subject, text[:200])
print(f"\n✅ generate_mailto_link() — {len(mailto)} chars")
print(f"   Subject: {subject}")
print(f"   Starts with: {mailto[:100]}...")

# 5. Test DB functions (using SQLite directly for testing)
import sqlite3
db_path = os.path.join(PROJECT_ROOT, "bylaws.db")
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    
    # Test resolve_municipality_id
    mid = resolve_municipality_id(conn, "Bayham")
    print(f"\n✅ resolve_municipality_id('Bayham') = {mid}")
    
    mid2 = resolve_municipality_id(conn, "Chatham-Kent")
    print(f"✅ resolve_municipality_id('Chatham-Kent') = {mid2}")
    
    # Test get_recipient_email
    if mid:
        recipient = get_recipient_email(conn, mid, "Bayham")
        print(f"✅ get_recipient_email(Bayham) = {recipient}")
    
    if mid2:
        recipient2 = get_recipient_email(conn, mid2, "Chatham-Kent")
        print(f"✅ get_recipient_email(Chatham-Kent) = {recipient2}")
    
    # Test a municipality we know has no municipal_email
    mid3 = resolve_municipality_id(conn, "Georgian Bluffs")
    if mid3:
        recipient3 = get_recipient_email(conn, mid3, "Georgian Bluffs")
        print(f"✅ get_recipient_email(Georgian Bluffs) = {recipient3}")
    
    conn.close()
else:
    print(f"⚠️ Database not found: {db_path}")

print("\n🏁 All tests complete!")
