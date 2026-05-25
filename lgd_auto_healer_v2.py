import sqlite3
import pandas as pd
import requests
import urllib3
import urllib.parse
import io
import re
import time
from bs4 import BeautifulSoup
import pdfplumber

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

urllib3.disable_warnings()

DB_PATH = 'bylaws.db'
REVIEW_FILE = 'Needs_Review_LGD.csv'

TIER_1_KEYWORDS = ['farm dog', 'herding dog', 'herding animals', 'livestock guardian']
TIER_2_KEYWORDS = ['protect livestock', 'repelling predators', 'cattle', 'sheep']

def setup_driver():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--log-level=3")
    options.page_load_strategy = "eager"
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    driver.set_page_load_timeout(30)
    return driver

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

def search_duckduckgo_selenium(driver, muni_name):
    search_query = f"{muni_name} Ontario animal control bylaw filetype:pdf"
    search_url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(search_query)}"
    
    candidates = []
    try:
        driver.get(search_url)
        time.sleep(2) # let JS render if needed, or just let page load
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        for a in soup.find_all('a', class_='result__url', href=True):
            href = a['href']
            if 'uddg=' in href:
                decoded = urllib.parse.unquote(href.split('uddg=')[1].split('&')[0])
                if decoded.endswith('.pdf') or 'bylaw' in decoded.lower():
                    candidates.append(decoded)
    except Exception as e:
        pass
    
    name_slug = re.sub(r'[^a-z]', '', muni_name.lower().replace(" ", ""))
    name_tokens = set(muni_name.lower().replace("-", " ").split()) - {"tp", "m", "c", "township", "municipality", "city", "town", "of", "and", "the"}
    
    validated = []
    for c in candidates:
        cl = c.lower()
        if name_slug in cl or any(len(t) >= 4 and t in cl for t in name_tokens):
            validated.append(c)
            
    return validated[:3]

def download_and_extract_text(url):
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        r = requests.get(url, headers=headers, timeout=15, verify=False)
        if r.status_code == 200 and 'application/pdf' in r.headers.get('Content-Type', '').lower():
            with pdfplumber.open(io.BytesIO(r.content)) as pdf:
                text = ""
                for page in pdf.pages[:15]:
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

def main():
    conn = sqlite3.connect(DB_PATH)
    links = conn.execute('SELECT b.id, m.name, b.bylaw_link FROM bylaws b JOIN municipalities m ON b.municipality_id = m.id WHERE b.category = \'LGD\'').fetchall()
    
    targets = []
    print("Verifying link statuses to build target list...")
    for row in links:
        if not is_link_working(row[2]):
            targets.append(row)
            
    print(f"Targeting {len(targets)} municipalities with Dead/Missing links...")
    
    driver = setup_driver()
    
    healed_count = 0
    tier_1_count = 0
    tier_2_count = 0
    tier_2_rows = []
    
    try:
        for idx, (bylaw_id, muni_name, old_link) in enumerate(targets):
            print(f"[{idx+1}/{len(targets)}] {muni_name}...", end=" ", flush=True)
            
            candidates = search_duckduckgo_selenium(driver, muni_name)
            healed_link = None
            text = None
            
            for cand in candidates:
                if is_link_working(cand):
                    text = download_and_extract_text(cand)
                    if text:
                        healed_link = cand
                        break
                        
            if not healed_link:
                print("Failed.")
                continue
                
            healed_count += 1
            conn.execute('UPDATE bylaws SET bylaw_link = ? WHERE id = ?', (healed_link, bylaw_id))
            
            # Deep Scan logic
            status = 'No Keywords'
            for kw in TIER_1_KEYWORDS:
                if kw in text:
                    snip = extract_snippet(text, kw)
                    tier_1_count += 1
                    conn.execute("UPDATE details_lgd SET has_lgd_definition = 'Yes', lgd_definition = ? WHERE bylaw_id = ?", 
                                 (f"[HEALER TIER 1: {kw}] {snip}", bylaw_id))
                    status = f'TIER 1 ({kw})'
                    break
                    
            if status == 'No Keywords':
                for kw in TIER_2_KEYWORDS:
                    if re.search(rf'\b{kw}\b', text):
                        snip = extract_snippet(text, kw)
                        tier_2_count += 1
                        tier_2_rows.append({
                            'Municipality': muni_name,
                            'Keyword Found': kw,
                            'Snippet Context': snip,
                            'Bylaw Link': healed_link
                        })
                        status = f'TIER 2 ({kw})'
                        break
                        
            print(f"Healed! -> {status}")
            conn.commit() # commit after each heal
            
    except KeyboardInterrupt:
        print("\nInterrupted.")
    finally:
        driver.quit()
        conn.close()
    
    if tier_2_rows:
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
