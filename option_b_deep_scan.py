import sqlite3
import pandas as pd
import requests
import urllib3
import io
import re
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
import pdfplumber

urllib3.disable_warnings()

DB_PATH = 'bylaws.db'
PORTAL_REGISTRY = 'signals/portal_registry.csv'
REVIEW_FILE = 'Needs_Review_LGD.csv'

TIER_1_KEYWORDS = ['farm dog', 'herding dog', 'herding animals', 'livestock guardian']
TIER_2_KEYWORDS = ['protect livestock', 'repelling predators', 'cattle', 'sheep']

def get_portal_url(muni_name):
    try:
        df = pd.read_csv(PORTAL_REGISTRY)
        row = df[df['municipality_name'] == muni_name]
        if not row.empty:
            return row.iloc[0]['council_listing_url']
    except Exception as e:
        pass
    return None

def auto_heal_link(muni_name, old_link):
    base_url = get_portal_url(muni_name)
    if not base_url or pd.isna(base_url):
        return None
        
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        r = requests.get(base_url, headers=headers, timeout=10, verify=False)
        soup = BeautifulSoup(r.text, 'html.parser')
        
        candidates = []
        for a in soup.find_all('a', href=True):
            text = a.text.lower()
            href = a['href'].lower()
            if ('dog' in text or 'animal' in text or 'canine' in text) and ('bylaw' in text or 'by-law' in text or 'bylaw' in href or 'by-law' in href):
                link = a['href']
                if not link.startswith('http'):
                    from urllib.parse import urljoin
                    link = urljoin(base_url, link)
                candidates.append(link)
                
        # Return the first PDF we find, or the first link
        for c in candidates:
            if c.endswith('.pdf'): return c
        if candidates: return candidates[0]
    except Exception as e:
        pass
    return None

def download_and_extract_text(url):
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        r = requests.get(url, headers=headers, timeout=15, verify=False)
        if r.status_code == 200 and 'application/pdf' in r.headers.get('Content-Type', '').lower():
            with pdfplumber.open(io.BytesIO(r.content)) as pdf:
                text = ""
                for page in pdf.pages[:15]: # Limit to first 15 pages to save time
                    page_text = page.extract_text()
                    if page_text: text += page_text + " "
                return text.lower()
    except Exception as e:
        pass
    return None

def extract_snippet(text, keyword):
    idx = text.find(keyword)
    if idx == -1: return ""
    start = max(0, idx - 100)
    end = min(len(text), idx + 100)
    return text[start:end].replace('\n', ' ').strip() + "..."

def scan_municipality(row):
    bylaw_id, muni_name, bylaw_link = row
    
    text = download_and_extract_text(bylaw_link)
    new_link = None
    healed = False
    
    if text is None:
        # Try auto-healing
        new_link = auto_heal_link(muni_name, bylaw_link)
        if new_link and new_link != bylaw_link:
            text = download_and_extract_text(new_link)
            if text is not None:
                healed = True
                bylaw_link = new_link
    
    if text is None:
        return {'id': bylaw_id, 'muni': muni_name, 'status': 'Error: Dead link, healing failed', 'healed': False}
        
    # Search TIER 1
    for kw in TIER_1_KEYWORDS:
        if kw in text:
            snip = extract_snippet(text, kw)
            return {'id': bylaw_id, 'muni': muni_name, 'status': 'TIER 1', 'keyword': kw, 'snippet': snip, 'link': bylaw_link, 'healed': healed}
            
    # Search TIER 2
    for kw in TIER_2_KEYWORDS:
        # Regex check to make sure it's not part of a larger word
        if re.search(rf'\b{kw}\b', text):
            snip = extract_snippet(text, kw)
            return {'id': bylaw_id, 'muni': muni_name, 'status': 'TIER 2', 'keyword': kw, 'snippet': snip, 'link': bylaw_link, 'healed': healed}
            
    return {'id': bylaw_id, 'muni': muni_name, 'status': 'No Keywords', 'link': bylaw_link, 'healed': healed}

def main():
    conn = sqlite3.connect(DB_PATH)
    q = '''
    SELECT b.id, m.name, b.bylaw_link 
    FROM municipalities m 
    JOIN bylaws b ON b.municipality_id = m.id 
    JOIN details_lgd d ON d.bylaw_id = b.id 
    WHERE b.category = 'LGD' AND d.has_lgd_definition = 'No' AND d.has_herding_def = 'No'
    '''
    df = pd.read_sql_query(q, conn)
    rows = list(df.itertuples(index=False, name=None))
    
    print(f"Starting Deep Scan of {len(rows)} municipalities...")
    
    results = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(scan_municipality, r): r for r in rows}
        for future in as_completed(futures):
            results.append(future.result())
            print(f"Completed {len(results)}/{len(rows)}", end='\r')
            
    print("\n\nScan Complete! Processing results...")
    
    tier_1_count = 0
    tier_2_count = 0
    healed_count = 0
    tier_2_rows = []
    
    for res in results:
        if res.get('healed'):
            healed_count += 1
            conn.execute('UPDATE bylaws SET bylaw_link = ? WHERE id = ?', (res['link'], res['id']))
            
        if res['status'] == 'TIER 1':
            tier_1_count += 1
            conn.execute("UPDATE details_lgd SET has_lgd_definition = 'Yes', lgd_definition = ? WHERE bylaw_id = ?", 
                         (f"[DEEP SCAN MATCH: {res['keyword']}] {res['snippet']}", res['id']))
        elif res['status'] == 'TIER 2':
            tier_2_count += 1
            tier_2_rows.append({
                'Municipality': res['muni'],
                'Keyword Found': res['keyword'],
                'Snippet Context': res['snippet'],
                'Bylaw Link': res['link']
            })
            
    conn.commit()
    conn.close()
    
    if tier_2_rows:
        pd.DataFrame(tier_2_rows).to_csv(REVIEW_FILE, index=False)
        print(f"Wrote {tier_2_count} Tier 2 hits to {REVIEW_FILE}")
        
    print(f"Summary:\n- Healed Links: {healed_count}\n- Tier 1 Flips (Auto-Yes): {tier_1_count}\n- Tier 2 Flags (Follow-up): {tier_2_count}")

if __name__ == '__main__':
    main()
