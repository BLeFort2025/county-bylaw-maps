import sqlite3
import pandas as pd
import requests
import urllib3
import os

urllib3.disable_warnings()

DB_PATH = 'bylaws.db'
OUT_DIR = 'signals'
os.makedirs(OUT_DIR, exist_ok=True)

def is_link_working(link):
    if not link or str(link).lower() in ['none', 'nan', 'n/a', 'missing', '']: return False
    if not link.startswith('http'): return False
    try:
        r = requests.head(link, timeout=5, verify=False, allow_redirects=True, headers={'User-Agent': 'Mozilla/5.0'})
        if r.status_code in [405, 403]:
            r = requests.get(link, timeout=5, verify=False, stream=True, headers={'User-Agent': 'Mozilla/5.0'})
        return r.status_code < 400
    except:
        return False

def main():
    conn = sqlite3.connect(DB_PATH)
    links = conn.execute('SELECT b.id, m.name, b.bylaw_link FROM bylaws b JOIN municipalities m ON b.municipality_id = m.id WHERE b.category = \'LGD\'').fetchall()
    conn.close()
    
    print("Verifying link statuses to build target list...")
    targets = []
    
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as exc:
        results = list(exc.map(lambda r: (r, is_link_working(r[2])), links))
        
    for row, is_working in results:
        if not is_working:
            targets.append(row)
            
    print(f"Targeting {len(targets)} municipalities with Dead/Missing links...")
    
    # Sort targets alphabetically by municipality name
    targets.sort(key=lambda x: x[1])
    
    batch_size = 25
    batches = [targets[i:i + batch_size] for i in range(0, len(targets), batch_size)]
    
    prompt_template = """Use your live web search capabilities to find the current, live URL for the official "Animal Control By-law" for the following Ontario municipalities.

CRITICAL INSTRUCTIONS:
1. ONLY return direct links to the official municipal bylaw PDF or the official municipal bylaw page.
2. Ensure the URL is currently active and not a 404 dead link.
3. Your output MUST be STRICTLY formatted as a single JSON array of objects. Do not include any markdown formatting, conversational text, or explanations. 

Example output format:
[
  {{"id": 1234, "municipality": "Example Town", "healed_url": "https://www.example.ca/bylaw.pdf"}},
  {{"id": 5678, "municipality": "Another City", "healed_url": "https://www.anothercity.ca/animal.pdf"}}
]

Here is the list of municipalities to search:

"""

    for idx, batch in enumerate(batches, 1):
        filename = os.path.join(OUT_DIR, f'lgd_healer_prompt_batch_{idx}.txt')
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(prompt_template)
            for bylaw_id, muni_name, _ in batch:
                f.write(f"- ID: {bylaw_id} | Municipality: {muni_name}, Ontario\n")
        print(f"Generated {filename} ({len(batch)} municipalities)")

if __name__ == '__main__':
    main()
