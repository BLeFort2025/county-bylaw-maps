import urllib.request
import PyPDF2
import io
import re

urls = [
    ('North Huron', 'https://www.northhuron.ca/en/municipal-government/resources/By-laws/Development%20Charges%20By-law%20-%20By-law%20No.%2074-2021.pdf'),
    ('Northumberland', 'https://www.northumberland.ca/en/doing-business/development-charges.aspx'),
    ('Petrolia', 'https://petrolia.civicweb.net/document/71871/'),
    ('Sarnia', 'https://sarnia.civicweb.net/filepro/documents/180924/?preview=180925'),
    ('Smiths Falls', 'https://www.smithsfalls.ca/en/town-hall/resources/Documents/Bylaws/10324-2022_Development-Charges-By-law.pdf'),
    ('Southwold', 'https://southwold.ca/en/doing-business/development-charges.aspx'),
    ('Stone Mills', 'https://www.stonemills.com/media/hyxau0ze/2024-1276-being-a-by-law-to-impose-dcs.pdf')
]

for name, url in urls:
    print(f"--- {name} ---")
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=15) as response:
            content = response.read()
            text = ""
            if url.endswith('.pdf') or response.info().get_content_type() == 'application/pdf':
                reader = PyPDF2.PdfReader(io.BytesIO(content))
                for page in reader.pages:
                    text += page.extract_text() + "\n"
            else:
                text = content.decode('utf-8', errors='ignore')
            
            # Simple keyword search
            lines = text.split('\n')
            found = False
            for i, line in enumerate(lines):
                if re.search(r'(farm|agri|bona fide)', line, re.IGNORECASE):
                    start = max(0, i-2)
                    end = min(len(lines), i+3)
                    print(f"Match found:\n" + "\n".join(lines[start:end]).strip())
                    found = True
                    break
            
            if not found:
                print("No agricultural/farm keywords found in document.")
    except Exception as e:
        print(f"Error fetching/parsing: {e}")
    print("\n")
