"""Quick Selenium test on Bayham's Laserfiche portal."""
import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import urllib.parse

options = Options()
options.add_argument("--headless=new")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--log-level=3")
options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64)")

driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
driver.set_page_load_timeout(30)

url = "http://www.bayham.on.ca/governance/council/agendas-minutes/"
print(f"Loading: {url}")
driver.get(url)
time.sleep(8)  # Let Laserfiche load

soup = BeautifulSoup(driver.page_source, "html.parser")

# Find all links
print(f"\nAll links on page ({len(soup.find_all('a', href=True))} total):")
for link in soup.find_all("a", href=True):
    href = link["href"]
    text = link.get_text().strip()
    full = urllib.parse.urljoin(url, href) if not href.startswith("http") else href
    if href.startswith("javascript:") or href == "#" or not text:
        continue
    is_interesting = (
        full.lower().endswith(".pdf") or
        "filestream" in href.lower() or
        "download" in href.lower() or
        "View.ashx" in href or
        any(w in text.lower() for w in ["minute", "agenda", "council", "meeting"])
    )
    if is_interesting:
        print(f"  [{text[:60]}] -> {full[:120]}")

# Check for iframes (Laserfiche might be in an iframe)
iframes = soup.find_all("iframe")
print(f"\nIframes found: {len(iframes)}")
for iframe in iframes:
    src = iframe.get("src", "")
    print(f"  src: {src[:150]}")
    if src:
        print("  >> Loading iframe...")
        full_src = urllib.parse.urljoin(url, src) if not src.startswith("http") else src
        driver.get(full_src)
        time.sleep(5)
        iframe_soup = BeautifulSoup(driver.page_source, "html.parser")
        for link in iframe_soup.find_all("a", href=True):
            href = link["href"]
            text = link.get_text().strip()
            if text and not href.startswith("javascript:"):
                full = urllib.parse.urljoin(full_src, href)
                print(f"    [{text[:50]}] -> {full[:120]}")

driver.quit()
print("\nDone.")
