"""Quick test: For the 328 'same URL' municipalities, how many can our spider find docs for?"""
import pandas as pd
import requests
from bs4 import BeautifulSoup
import urllib.parse

headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

df = pd.read_csv('signals/portal_registry.csv')
same_url = df[df['minutes_listing_url'].fillna('') == df['example_recent_minutes_url'].fillna('')]

# Test a sample of custom_html_pdf portals (the ones that SHOULD work with our spider)
custom = same_url[same_url['portal_type'] == 'custom_html_pdf'].head(20)

success = 0
fail = 0
fail_names = []

for _, row in custom.iterrows():
    name = row['municipality_name']
    url = str(row.get('minutes_listing_url', '')).strip()
    if not url:
        continue
    
    try:
        r = requests.get(url, headers=headers, timeout=8, verify=False)
        if r.status_code != 200:
            fail += 1
            fail_names.append(f"{name} (HTTP {r.status_code})")
            continue
            
        soup = BeautifulSoup(r.text, "html.parser")
        links = soup.find_all("a", href=True)
        
        doc_links = []
        for link in links:
            href = link["href"]
            text = link.get_text().strip()
            full = urllib.parse.urljoin(url, href)
            if href.startswith("javascript:") or href == "#":
                continue
            if full.lower().endswith(".pdf") or "filestream" in href.lower() or "View.ashx" in href:
                doc_links.append(full)
        
        if doc_links:
            success += 1
            print(f"  ✅ {name}: {len(doc_links)} docs found")
        else:
            fail += 1
            fail_names.append(name)
            print(f"  ❌ {name}: no docs (JS portal?)")
    except Exception as e:
        fail += 1
        fail_names.append(f"{name} ({str(e)[:40]})")

print(f"\nResults: {success} success, {fail} fail out of {success+fail} tested")
print(f"\nFailed municipalities:")
for n in fail_names:
    print(f"  - {n}")
