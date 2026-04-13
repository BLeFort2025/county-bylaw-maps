"""Test downloading Laserfiche DocView over HTTP."""
import requests
from bs4 import BeautifulSoup

url = "https://laserfiche.bayham.on.ca/WebLink/DocView.aspx?id=536969&dbid=0&repo=BAYHAM"
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}

r = requests.get(url, headers=headers, verify=False)
print(f"Status: {r.status_code}")
print(f"Content Type: {r.headers.get('Content-Type')}")
print(f"Length: {len(r.text)}")

soup = BeautifulSoup(r.text, "html.parser")
for tag in soup(["script", "style", "nav", "header", "footer"]):
    tag.decompose()
text = soup.get_text(separator=" ", strip=True)

print(f"Visible text length: {len(text)}")
print(f"Sample text:\n{text[:500]}")
