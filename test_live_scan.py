import sys
sys.path.append('pages')
import requests
import io
import datetime
import pandas as pd
from bs4 import BeautifulSoup

def _fetch_and_extract_text(url, headers):
    try:
        response = requests.get(url, headers=headers, timeout=12, verify=False)
        content_type = response.headers.get('Content-Type', '').lower()
        if 'pdf' in content_type or url.lower().endswith('.pdf'):
            return "MOCK PDF TEXT WITH KEYWORD", True # Mocked PDF extraction
        else:
            soup = BeautifulSoup(response.text, "html.parser")
            for tag in soup(["script", "style", "nav", "header", "footer"]):
                tag.decompose()
            text = soup.get_text(separator=" ", strip=True)
            return text, False
    except Exception as e:
        return "", False

def run_mock_live_scan(registry_subset, custom_keyword):
    results = []
    headers = {'User-Agent': 'Mozilla/5.0'}
    kw_lower = custom_keyword.lower()

    for i, row in registry_subset.iterrows():
        name = row.get('municipality_name', 'Unknown')
        listing_url = row.get('minutes_listing_url', None)
        fallback_url = row.get('example_recent_minutes_url', None)

        listing_clean = str(listing_url).strip().rstrip("/") if listing_url and not pd.isna(listing_url) else ""
        fallback_clean = str(fallback_url).strip().rstrip("/") if fallback_url and not pd.isna(fallback_url) else ""

        print(f"Name: {name}")
        print(f"Listing url: {listing_clean}")
        print(f"Fallback url: {fallback_clean}")
        
        urls_to_scan = []
        found_real_docs = False
        
        # We know spider finds nothing, so skip the spidering mock and simulate what would happen
        print("Spidering found nothing (found_real_docs = False)")
        
        if not urls_to_scan and fallback_clean:
            urls_to_scan = [fallback_clean]

        if not urls_to_scan:
            continue

        print(f"URLs to scan: {urls_to_scan}")

        for url in urls_to_scan:
            text_content, is_pdf = _fetch_and_extract_text(url, headers)
            print(f"Scanned {url}: is_pdf={is_pdf}, len={len(text_content)}")

            if not is_pdf and not found_real_docs:
                print("Skipping non-pdf since found_real_docs = False")
                continue

            if kw_lower in text_content.lower():
                results.append(url)
                print("Match found!")
                break
    return results

# Load bayham from the real csv
df = pd.read_csv('signals/portal_registry.csv')
b = df[df['municipality_name'] == 'BAYHAM']
print(run_mock_live_scan(b, "keyword"))

