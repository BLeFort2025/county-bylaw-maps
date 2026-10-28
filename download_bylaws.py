import requests
from bs4 import BeautifulSoup
import fitz  # PyMuPDF
import io
import os

headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

def download_pdf(url):
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    pdf = fitz.open(stream=response.content, filetype="pdf")
    text = ""
    for page in pdf:
        text += page.get_text()
    return text

def process_bracebridge():
    url = "https://www.bracebridge.ca/town-services/building-services/tree-cutting-and-preservation/"
    resp = requests.get(url, headers=headers)
    soup = BeautifulSoup(resp.content, 'html.parser')
    
    # Try to find a PDF link for By-law 2025-103 or general bylaw
    pdf_link = None
    for a in soup.find_all('a', href=True):
        if '2025-103' in a['href'] or 'bylaw' in a['href'].lower() or 'by-law' in a['href'].lower():
            if a['href'].endswith('.pdf') or 'document' in a['href']:
                pdf_link = a['href']
                break
    
    if pdf_link:
        if not pdf_link.startswith('http'):
            pdf_link = "https://www.bracebridge.ca" + pdf_link
        print(f"Bracebridge PDF link found: {pdf_link}")
        try:
            return download_pdf(pdf_link)
        except Exception as e:
            print(f"Failed to download Bracebridge PDF: {e}")
            return soup.get_text()
    else:
        return soup.get_text()

def process_brantford():
    url = "https://www.brantford.ca/your-government/by-laws/commonly-requested-by-laws/private-tree-by-law/private-tree-by-law-95-2024/"
    resp = requests.get(url, headers=headers)
    soup = BeautifulSoup(resp.content, 'html.parser')
    return soup.get_text()

def process_bruce():
    url = "https://www.brucecounty.on.ca/sites/default/files/By-law%202025-030%20Forest%20Conservation%20Bylaw.pdf"
    try:
        return download_pdf(url)
    except Exception as e:
        print(f"Failed to download Bruce PDF: {e}")
        return ""

if __name__ == "__main__":
    bb = process_bracebridge()
    with open("bracebridge.txt", "w", encoding="utf-8") as f:
        f.write(bb)
        
    brf = process_brantford()
    with open("brantford.txt", "w", encoding="utf-8") as f:
        f.write(brf)
        
    bruce = process_bruce()
    with open("bruce.txt", "w", encoding="utf-8") as f:
        f.write(bruce)
    print("Done downloading text.")
