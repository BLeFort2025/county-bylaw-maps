"""Test if ElectronicFile.aspx can be downloaded via plain HTTP."""
import requests

url = "https://laserfiche.bayham.on.ca/WebLink/ElectronicFile.aspx?docid=536969&dbid=0&repo=BAYHAM"
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}

r = requests.get(url, headers=headers, verify=False)
print(f"Status: {r.status_code}")
print(f"Content Type: {r.headers.get('Content-Type')}")
print(f"Length: {len(r.content)} bytes")

if len(r.content) > 1000 and "pdf" in r.headers.get("Content-Type", "").lower():
    print("PDF download successful!")
else:
    print(f"Response start: {r.content[:100]}")
