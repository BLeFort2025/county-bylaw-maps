import sqlite3
import pandas as pd
import requests
import urllib3
import io
import re
import os
import json
import glob
import pdfplumber

urllib3.disable_warnings()

DB_PATH = 'bylaws.db'
SIGNALS_DIR = 'signals'
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
    json_files = glob.glob(os.path.join(SIGNALS_DIR, 'lgd_healed_links_*.json'))
    if not json_files:
        print("No JSON files found in signals/ directory.")
        return
        
    print(f"Found {len(json_files)} JSON files. Importing...")
    
    conn = sqlite3.connect(DB_PATH)
    
    healed_count = 0
    tier_1_count = 0
    tier_2_count = 0
    tier_2_rows = []
    
    for jfile in json_files:
        with open(jfile, 'r', encoding='utf-8') as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                print(f"Error parsing {jfile}. Skipping.")
                continue
                
        for row in data:
            bylaw_id = row.get('id')
            muni = row.get('municipality')
            url = row.get('healed_url')
            
            if not bylaw_id or not url:
                continue
                
            print(f"Checking {muni}... ", end="", flush=True)
            if is_link_working(url):
                healed_count += 1
                conn.execute('UPDATE bylaws SET bylaw_link = ? WHERE id = ?', (url, bylaw_id))
                
                text = download_and_extract_text(url)
                if not text:
                    print("Healed! (Not a PDF or unreadable)")
                    continue
                    
                status = 'No Keywords'
                for kw in TIER_1_KEYWORDS:
                    if kw in text:
                        snip = extract_snippet(text, kw)
                        tier_1_count += 1
                        conn.execute("UPDATE details_lgd SET has_lgd_definition = 'Yes', lgd_definition = ? WHERE bylaw_id = ?", 
                                     (f"[GEMINI TIER 1: {kw}] {snip}", bylaw_id))
                        status = f'TIER 1 ({kw})'
                        break
                        
                if status == 'No Keywords':
                    for kw in TIER_2_KEYWORDS:
                        if re.search(rf'\b{kw}\b', text):
                            snip = extract_snippet(text, kw)
                            tier_2_count += 1
                            tier_2_rows.append({
                                'Municipality': muni,
                                'Keyword Found': kw,
                                'Snippet Context': snip,
                                'Bylaw Link': url
                            })
                            status = f'TIER 2 ({kw})'
                            break
                            
                if status.startswith('TIER 1'):
                    with open('scratch/last_batch_extracted.md', 'a', encoding='utf-8') as f:
                        f.write(f'# {muni} (ID: {bylaw_id})\n')
                        sents = text.split('.')
                        bark = [s.strip().replace('\n', ' ') for s in sents if 'bark' in s or 'noise' in s]
                        lic = [s.strip().replace('\n', ' ') for s in sents if 'license' in s or 'licence' in s or 'fee' in s]
                        tag = [s.strip().replace('\n', ' ') for s in sents if 'tag' in s]
                        limit = [s.strip().replace('\n', ' ') for s in sents if 'limit' in s or 'maximum' in s or 'more than' in s]
                        f.write('## Barking/Noise\n' + '\n'.join('- ' + x for x in bark) + '\n\n')
                        f.write('## License/Fee\n' + '\n'.join('- ' + x for x in lic[:5]) + '\n\n')
                        f.write('## Tags\n' + '\n'.join('- ' + x for x in tag[:5]) + '\n\n')
                        f.write('## Limits\n' + '\n'.join('- ' + x for x in limit) + '\n\n')

                print(f"Healed! -> {status}")
            else:
                print("Failed (Dead Link)")
                
    conn.commit()
    conn.close()
    
    if tier_2_rows:
        header = not os.path.exists(REVIEW_FILE)
        pd.DataFrame(tier_2_rows).to_csv(REVIEW_FILE, mode='a', header=header, index=False)
        print(f"Appended {tier_2_count} new Tier 2 hits to {REVIEW_FILE}")
        
    print(f"\nFinal Summary:")
    print(f"- Total Links Healed & Saved: {healed_count}")
    print(f"- New Tier 1 Flips (Auto-Yes): {tier_1_count}")
    print(f"- New Tier 2 Flags (Follow-up): {tier_2_count}")

if __name__ == '__main__':
    main()
