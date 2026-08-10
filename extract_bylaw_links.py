import requests
from bs4 import BeautifulSoup
import urllib.parse
import re
import fitz # PyMuPDF
import os

def download_and_extract(url, name):
    print(f"Processing {name} at {url}")
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
    except Exception as e:
        print(f"Failed to fetch {url}: {e}")
        return

    soup = BeautifulSoup(response.content, 'html.parser')
    
    # Find PDF links
    pdf_links = []
    for a in soup.find_all('a', href=True):
        href = a['href']
        if '.pdf' in href.lower() or 'document' in href.lower() or 'bylaw' in href.lower() or 'by-law' in href.lower():
            full_url = urllib.parse.urljoin(url, href)
            pdf_links.append((a.text.strip(), full_url))
            
    print(f"Found potential links for {name}:")
    for text, link in pdf_links:
        print(f" - {text}: {link}")
        
        # We can try downloading one if it looks like a bylaw
        if 'by-law' in text.lower() or 'bylaw' in text.lower() or '.pdf' in link.lower() or 'tree' in text.lower():
            print(f"Attempting to download {link}")
            try:
                pdf_resp = requests.get(link, headers=headers)
                if pdf_resp.status_code == 200 and 'application/pdf' in pdf_resp.headers.get('Content-Type', ''):
                    pdf_path = f"{name}.pdf"
                    with open(pdf_path, 'wb') as f:
                        f.write(pdf_resp.content)
                    
                    # Extract text
                    doc = fitz.open(pdf_path)
                    text_content = ""
                    for page in doc:
                        text_content += page.get_text()
                    
                    txt_path = f"{name}.txt"
                    with open(txt_path, 'w', encoding='utf-8') as f:
                        f.write(text_content)
                    print(f"Successfully extracted text to {txt_path}\n")
                    return # Stop after finding the first valid PDF
            except Exception as e:
                print(f"Failed to download/extract {link}: {e}")

urls = [
    ("Caledon", "https://www.caledon.ca/en/town-services/tree-preservation-by-law-permitting-process.aspx"),
    ("Lincoln", "https://www.lincoln.ca/parks-forestry-recreation-culture/trees-urban-forestry/tree-protection"),
    ("Saugeen_Shores", "https://www.saugeenshores.ca/news-and-notices/posts/new-by-laws-protect-trees-in-saugeen-shores/")
]

for name, url in urls:
    download_and_extract(url, name)
