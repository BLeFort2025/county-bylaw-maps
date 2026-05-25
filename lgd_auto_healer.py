import sqlite3
import pandas as pd
import requests
import urllib3
import urllib.parse
import io
import re
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
import pdfplumber
import time

urllib3.disable_warnings()

DB_PATH = 'bylaws.db'
REVIEW_FILE = 'Needs_Review_LGD.csv'

TIER_1_KEYWORDS = ['farm dog', 'herding dog', 'herding animals', 'livestock guardian']
TIER_2_KEYWORDS = ['protect livestock', 'repelling predators', 'cattle', 'sheep']

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

def search_duckduckgo(muni_name):
    # Search for the PDF
    search_query = f"{muni_name} Ontario animal control bylaw filetype:pdf"
    search_url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(search_query)}"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    candidates = []
    try:
        r = requests.get(search_url, headers=headers, timeout=10)
        soup = BeautifulSoup(r.text, 'html.parser')
        for a in soup.find_all('a', class_='result__url', href=True):
            href = a['href']
            if 'uddg=' in href:
                decoded = urllib.parse.unquote(href.split('uddg=')[1].split('&')[0])
                if decoded.endswith('.pdf') or 'bylaw' in decoded.lower():
                    candidates.append(decoded)
    except Exception as e:
        pass
    
    # Filter candidates to make sure they plausibly belong to the municipality
    name_slug = re.sub(r'[^a-z]', '', muni_name.lower().replace(" ", ""))
    name_tokens = set(muni_name.lower().replace("-", " ").split()) - {"tp", "m", "c", "township", "municipality", "city", "town", "of", "and", "the"}
    
    validated = []
    for c in candidates:
        cl = c.lower()
        if name_slug in cl or any(len(t) >= 4 and t in cl for t in name_tokens):
            validated.append(c)
            
    return validated[:3] # Top 3 best matches

def download_and_extract_text(url):
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        r = requests.get(url, headers=headers, timeout=15, verify=False)
        if r.status_code == 200 and 'application/pdf' in r.headers.get('Content-Type', '').lower():
            with pdfplumber.open(io.BytesIO(r.content)) as pdf:
                text = ""
                for page in pdf.pages[:15]: # Limit to first 15 pages
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

def heal_and_scan(row):
    bylaw_id, muni_name, old_link = row
    
    # Give duckduckgo a tiny bit of breathing room to avoid rate limits
    time.sleep(0.5)
    
    candidates = search_duckduckgo(muni_name)
    healed_link = None
    text = None
    
    for cand in candidates:
        if is_link_working(cand):
            text = download_and_extract_text(cand)
            if text:
                healed_link = cand
                break
                
    if not healed_link:
        return {'id': bylaw_id, 'muni': muni_name, 'healed': False, 'status': 'Failed to heal'}
        
    # We healed the link! Now deep scan it.
    for kw in TIER_1_KEYWORDS:
        if kw in text:
            snip = extract_snippet(text, kw)
            return {'id': bylaw_id, 'muni': muni_name, 'healed': True, 'link': healed_link, 'status': 'TIER 1', 'keyword': kw, 'snippet': snip}
            
    for kw in TIER_2_KEYWORDS:
        if re.search(rf'\b{kw}\b', text):
            snip = extract_snippet(text, kw)
            return {'id': bylaw_id, 'muni': muni_name, 'healed': True, 'link': healed_link, 'status': 'TIER 2', 'keyword': kw, 'snippet': snip}
            
    return {'id': bylaw_id, 'muni': muni_name, 'healed': True, 'link': healed_link, 'status': 'No Keywords'}

def main():
    conn = sqlite3.connect(DB_PATH)
    links = conn.execute('SELECT b.id, m.name, b.bylaw_link FROM bylaws b JOIN municipalities m ON b.municipality_id = m.id WHERE b.category = \'LGD\'').fetchall()
    
    # Filter to only the 246 dead/missing links
    targets = []
    print("Verifying link statuses to build target list...")
    # Just a quick check to save us checking them again
    for row in links:
        if not is_link_working(row[2]):
            targets.append(row)
            
    print(f"Targeting {len(targets)} municipalities with Dead/Missing links...")
    
    results = []
    # Use max_workers=5 to avoid hammering DuckDuckGo too hard and getting temp-banned
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(heal_and_scan, r): r for r in targets}
        for future in as_completed(futures):
            results.append(future.result())
            print(f"Processed {len(results)}/{len(targets)}", end='\r')
            
    print("\n\nHealer Complete! Processing results...")
    
    healed_count = 0
    tier_1_count = 0
    tier_2_count = 0
    tier_2_rows = []
    
    for res in results:
        if res.get('healed'):
            healed_count += 1
            # Update the database with the healed link
            conn.execute('UPDATE bylaws SET bylaw_link = ? WHERE id = ?', (res['link'], res['id']))
            
            if res['status'] == 'TIER 1':
                tier_1_count += 1
                conn.execute("UPDATE details_lgd SET has_lgd_definition = 'Yes', lgd_definition = ? WHERE bylaw_id = ?", 
                             (f"[HEALER TIER 1: {res['keyword']}] {res['snippet']}", res['id']))
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
        # Append to existing review file
        import os
        header = not os.path.exists(REVIEW_FILE)
        pd.DataFrame(tier_2_rows).to_csv(REVIEW_FILE, mode='a', header=header, index=False)
        print(f"Appended {tier_2_count} new Tier 2 hits to {REVIEW_FILE}")
        
    print(f"\nFinal Summary:")
    print(f"- Total Links Healed & Saved: {healed_count}")
    print(f"- New Tier 1 Flips (Auto-Yes): {tier_1_count}")
    print(f"- New Tier 2 Flags (Follow-up): {tier_2_count}")

if __name__ == '__main__':
    main()
