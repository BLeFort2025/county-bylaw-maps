import requests
from bs4 import BeautifulSoup
import urllib.parse
import re
import fitz # PyMuPDF
import json

def extract_bylaw_data(text, name):
    data = {
        "bylaw_name": "",
        "date_enacted": "",
        "expiry_date": "",
        "expiry_notes": "",
        "farm_exemption": "No",
        "bylaw_wording": "",
        "farming_exception_wording": None,
        "list_of_exceptions": ""
    }
    
    # Very basic extraction logic
    # Bylaw name
    bylaw_match = re.search(r'(?i)by-law\s+(no\.?\s*)?(\d{4}-\d+|\d+-\d{4})', text)
    if bylaw_match:
        data["bylaw_name"] = bylaw_match.group(0).strip()
        
    # Date enacted
    date_match = re.search(r'(?i)enacted.*?(\d{1,2}\s+[a-z]+\s+\d{4})', text)
    if date_match:
        data["date_enacted"] = date_match.group(1)
        
    # Farm exemption
    farm_keywords = ['normal farm practice', 'farming and food production', 'agricultural operation']
    for kw in farm_keywords:
        if kw.lower() in text.lower():
            data["farm_exemption"] = "Yes"
            # Try to find the section
            section_match = re.search(r'([^\n]*' + kw + r'[^\n]*)', text, re.IGNORECASE)
            if section_match:
                data["farming_exception_wording"] = section_match.group(1)[:300]
            break
            
    # Bylaw wording
    prohibit_match = re.search(r'(?i)(no person shall.*?)(?:\.|\n)', text)
    if prohibit_match:
        data["bylaw_wording"] = prohibit_match.group(1)[:200]
        
    return data

def process_municipality(url, name):
    print(f"Processing {name} at {url}")
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
    except Exception as e:
        print(f"Failed to fetch {url}: {e}")
        return None

    soup = BeautifulSoup(response.content, 'html.parser')
    
    pdf_link = None
    for a in soup.find_all('a', href=True):
        href = a['href']
        text = a.text.strip().lower()
        if 'by-law' in text or 'bylaw' in text or 'tree' in text:
            if '.pdf' in href.lower() or 'document' in href.lower():
                pdf_link = urllib.parse.urljoin(url, href)
                break
                
    if not pdf_link:
        print(f"Could not find PDF link for {name}")
        return None
        
    print(f"Downloading PDF: {pdf_link}")
    try:
        pdf_resp = requests.get(pdf_link, headers=headers)
        if pdf_resp.status_code == 200:
            pdf_path = f"{name}.pdf"
            with open(pdf_path, 'wb') as f:
                f.write(pdf_resp.content)
            
            doc = fitz.open(pdf_path)
            text_content = ""
            for page in doc:
                text_content += page.get_text()
            
            return extract_bylaw_data(text_content, name)
    except Exception as e:
        print(f"Failed to process PDF for {name}: {e}")
    return None

urls = [
    ("Caledon", "https://www.caledon.ca/en/town-services/tree-preservation-by-law-permitting-process.aspx"),
    ("Lincoln", "https://www.lincoln.ca/parks-forestry-recreation-culture/trees-urban-forestry/tree-protection"),
    ("Saugeen_Shores", "https://www.saugeenshores.ca/news-and-notices/posts/new-by-laws-protect-trees-in-saugeen-shores/")
]

results = {}
for name, url in urls:
    data = process_municipality(url, name)
    if data:
        results[name] = data

with open('extracted_bylaw_data.json', 'w') as f:
    json.dump(results, f, indent=4)
    
print("Extraction complete. Results saved to extracted_bylaw_data.json")
