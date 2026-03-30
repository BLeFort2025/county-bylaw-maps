import os
import sys
import time
import datetime
import pandas as pd
import urllib.parse
import re
from io import BytesIO

# Try importing pdfplumber and requests for PDF processing
try:
    import pdfplumber
    import requests
except ImportError:
    print("Missing requirements. Please pip install pdfplumber requests bs4 selenium")
    sys.exit(1)

from bs4 import BeautifulSoup

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
import urllib3
import google.generativeai as genai

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- CONFIG ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REGISTRY_PATH = os.path.join(SCRIPT_DIR, "signals", "portal_registry.csv")
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "signals")

# Configure Gemini
api_key = os.environ.get("GEMINI_API_KEY")
if api_key:
    genai.configure(api_key=api_key)
else:
    print("WARNING: GEMINI_API_KEY not found in environment. AI Summarization will fail.")

if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)

from shared_config import KEYWORD_CONFIG

def setup_driver():
    """Configures a headless Chrome browser optimized for speed.""" 
    options = Options()
    options.add_argument("--headless=new") 
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--log-level=3")
    options.page_load_strategy = 'eager' # Don't wait for full render, just DOM
    
    # Custom User-Agent to prevent basic blocks
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    driver.set_page_load_timeout(30)
    return driver

def extract_pdf_text(url):
    """Downloads and extracts text from a PDF url without saving it to disk."""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        resp = requests.get(url, headers=headers, timeout=15, verify=False)
        if resp.status_code == 200:
            with pdfplumber.open(BytesIO(resp.content)) as pdf:
                text = ""
                for page in pdf.pages[:50]: # limit to 50 pages for speed/memory
                    extracted = page.extract_text()
                    if extracted:
                        text += extracted + "\n"
            return text
    except Exception as e:
        print(f"      [!] PDF Extraction failed for {url}: {e}")
    return ""

def check_keywords(text):
    """Returns a dictionary of found categories and their trigger words."""
    hits = []
    if not text: return hits
    
    text_lower = text.lower()
    for category, phrases in KEYWORD_CONFIG.items():
        for phrase in phrases:
            if phrase.lower() in text_lower:
                hits.append({"category": category, "trigger": phrase})
    return hits

def generate_ai_summary(text_content, keyword, category):
    """Uses Gemini 2.5 Flash to analyze the document and generate a polished summary."""
    if not os.environ.get("GEMINI_API_KEY"):
        return "ERROR: Missing GEMINI_API_KEY", 0

    # Safety Brake: Force a 5-second pause to prevent hitting the 15 Requests/Min Free Tier limit
    print("      [⏳] Rate limit pause (5s) for Free Tier...")
    time.sleep(5)

    try:
        model = genai.GenerativeModel('gemini-2.5-flash')
        
        # We limit the text sent to the LLM to save token costs and prevent limits
        # Find the keyword index and take an 8000 character window around it
        idx = text_content.lower().find(keyword.lower())
        start = max(0, idx - 4000)
        end = min(len(text_content), idx + 4000)
        window_text = text_content[start:end]

        prompt = f'''
        You are a highly skilled municipal policy expert working for the Ontario Federation of Agriculture.
        You are reading an excerpt from a municipal council document.
        
        The automated scanner flagged this document because it mentioned "{keyword}", which belongs to our "{category}" bylaw category.
        
        Your job:
        1. Determine if this is a genuine policy/bylaw action (e.g. Council passing a motion, proposing a new bylaw, increasing a fee related to {keyword}).
        2. If it is NOT a genuine policy action (e.g. it is just a random citizen complaining, an unrelated administrative note, or a reference to a past event without new action), reply with exactly: "NOISE".
        3. If it IS a genuine policy action, provide a polished, professional 2-sentence summary of exactly what the municipality is doing. Write in the 3rd person (e.g. "The municipality voted to...").
        
        Here is the document excerpt:
        ---
        {window_text}
        ---
        '''
        
        response = model.generate_content(prompt)
        result = response.text.strip()
        
        # Assign a basic confidence score (100 if it gave a summary, 0 if it rejected it)
        if "NOISE" in result.upper():
            return "Rejected by AI as Noise", 0
        else:
            return result, 100
        
    except Exception as e:
        print(f"      [!] AI Summarization failed: {e}")
        return f"AI Error: {e}", 0

def find_meeting_links(driver, base_url):
    """Spider logic: Finds links that likely point to agendas or minutes."""
    try:
        driver.get(base_url)
        time.sleep(4) # Let JS load
        
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        links = soup.find_all('a', href=True)
        
        valid_links = []
        for link in links:
            href = link['href']
            text = link.get_text().strip().lower()
            
            # Absolute URL resolution
            full_url = urllib.parse.urljoin(base_url, href)
            
            # Simple heuristic for meeting files
            is_pdf = full_url.lower().endswith('.pdf')
            looks_like_meeting = any(w in text for w in ['agenda', 'minute', 'meeting', 'council'])
            is_portal_link = '/document/' in full_url or 'FileStream.ashx' in full_url or 'Meeting.aspx' in full_url
            
            if is_pdf or looks_like_meeting or is_portal_link:
                if full_url not in valid_links:
                    valid_links.append(full_url)
                    
        # Limit to the top 5 most recent to save processing time
        return valid_links[:5]
    except Exception as e:
        print(f"    [!] Failed to spider {base_url}: {e}")
        return []

def main():
    print("=====================================================")
    print(" V3 ULTIMATE INTELLIGENCE SCANNER (DEEP CRAWLER)     ")
    print("=====================================================")
    
    if not os.path.exists(REGISTRY_PATH):
        print(f"ERROR: Cannot find registry at {REGISTRY_PATH}")
        sys.exit(1)
        
    df_reg = pd.read_csv(REGISTRY_PATH)
    total_munis = len(df_reg)
    print(f"Loaded {total_munis} municipalities for deep scanning.")
    
    driver = setup_driver()
    candidates = []
    
    try:
        for idx, row in df_reg.iterrows():
            munid = row['munid']
            name = row['municipality_name']
            
            # Use agenda portal if available, else fallback
            target_url = row.get('agenda_listing_url')
            if pd.isna(target_url) or str(target_url).strip() == '':
                target_url = row.get('example_recent_minutes_url')
            
            if pd.isna(target_url) or str(target_url).strip() == '':
                print(f"[{idx+1}/{total_munis}] Skipping {name} - No URL provided.")
                continue
                
            print(f"[{idx+1}/{total_munis}] Spidering {name} ({target_url[:40]}...)")
            
            links_to_scan = find_meeting_links(driver, target_url)
            
            # If the spider didn't find specific sub-links, just scan the main page itself
            if not links_to_scan:
                links_to_scan = [target_url]
                
            print(f"    Found {len(links_to_scan)} document candidates to scan.")
            
            for link in links_to_scan:
                # 1. Extract Text
                if link.lower().endswith('.pdf') or 'FileStream' in link:
                    text_content = extract_pdf_text(link)
                else:
                    try:
                        driver.get(link)
                        text_content = driver.find_element("tag name", "body").text
                    except:
                        text_content = ""
                
                # 2. Check for hits
                hits = check_keywords(text_content)
                if hits:
                    print(f"    ⭐ HIT FOUND in {link}! ({hits[0]['category']})")
                    for hit in hits:
                        ai_sum, confidence = generate_ai_summary(text_content, hit['trigger'], hit['category'])
                        
                        # Only append if AI found it genuinely relevant (score > 0)
                        if confidence > 0:
                            print(f"      🤖 AI Summary Generated: {ai_sum[:50]}...")
                            candidate = {
                                "munid": munid,
                                "name": name,
                                "found_url": link,
                                "found_date": datetime.date.today().isoformat(),
                                "trigger_keyword": hit['trigger'],
                                "category": hit['category'],
                                "raw_text_length": len(text_content),
                                "ai_summary": ai_sum,
                                "ai_confidence": confidence
                            }
                            candidates.append(candidate)
                        else:
                            print(f"      🤖 AI Filtered Out: Noise detected.")
                        
                        
    except KeyboardInterrupt:
        print("\nScan interrupted by user.")
    finally:
        driver.quit()
        
    # Save the output
    today_str = datetime.date.today().strftime('%Y-%m-%d')
    output_path = os.path.join(OUTPUT_DIR, f"v3_raw_hits_{today_str}.csv")
    
    if candidates:
        pd.DataFrame(candidates).to_csv(output_path, index=False)
        print(f"\n✅ SUCCESS: Phase 1 Crawler finished. Found {len(candidates)} raw hits.")
        print(f"Saved to: {output_path}")
    else:
        print("\nScan complete. No hits found.")

if __name__ == "__main__":
    main()
