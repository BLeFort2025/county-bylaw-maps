import sys
sys.path.append('pages')
import requests
from bs4 import BeautifulSoup
import urllib.parse
import re
import datetime

BS4_SUPPORT = True

def _extract_date_from_text(text):
    text = text.lower()
    months = {
        'january': 1, 'february': 2, 'march': 3, 'april': 4,
        'may': 5, 'june': 6, 'july': 7, 'august': 8,
        'september': 9, 'october': 10, 'november': 11, 'december': 12
    }
    for m_name, m_num in months.items():
        match = re.search(rf'{m_name}\s+(\d{{1,2}}),?\s*(\d{{4}})', text)
        if match:
            try:
                return datetime.date(int(match.group(2)), m_num, int(match.group(1)))
            except ValueError:
                pass
    match = re.search(r'(\d{4})[-/](\d{1,2})[-/](\d{1,2})', text)
    if match:
        try:
            return datetime.date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except ValueError:
            pass
    match = re.search(r'(\d{4})[-/](\d{1,2})', text)
    if match:
        try:
            return datetime.date(int(match.group(1)), int(match.group(2)), 1)
        except ValueError:
            pass
    return None

def _spider_civicweb(listing_url, soup, headers, max_links):
    return []

def _find_recent_doc_links(listing_url, headers, max_links=3):
    try:
        resp = requests.get(listing_url, headers=headers, timeout=12, verify=False)
        if resp.status_code != 200:
            return []
        soup = BeautifulSoup(resp.text, "html.parser")
        links = soup.find_all("a", href=True)
        
        candidates = []
        seen_urls = set()
        for link in links:
            href = link["href"]
            text = link.get_text().strip()
            full_url = urllib.parse.urljoin(listing_url, href)

            if href.startswith("javascript:") or href == "#":
                continue

            is_pdf = full_url.lower().endswith(".pdf")
            is_ashx = "View.ashx" in full_url or "FileStream" in full_url
            is_filestream = "filestream" in full_url.lower()
            has_doc_keyword = any(w in text.lower() for w in ["minute", "agenda", "council meeting", "regular meeting"])

            is_self_loop = full_url.lower().rstrip("/") == listing_url.lower().rstrip("/")
            if is_self_loop:
                continue

            if (is_pdf or is_ashx or is_filestream or has_doc_keyword) and full_url not in seen_urls:
                date_hint = _extract_date_from_text(text + " " + full_url)
                candidates.append((full_url, text[:80], date_hint))
                seen_urls.add(full_url)
                
        dated = [(u, t, d) for u, t, d in candidates if d is not None]
        undated = [(u, t, d) for u, t, d in candidates if d is None]
        dated.sort(key=lambda x: x[2], reverse=True)
        final_list = dated + undated
        return [u for u, t, d in final_list][:max_links]
    except Exception as e:
        print(f"Error: {e}")
        return []

headers = {'User-Agent': 'Mozilla/5.0'}
links = _find_recent_doc_links("https://www.bayham.on.ca/governance/council/agendas-minutes/", headers)
print("Found links:", links)
