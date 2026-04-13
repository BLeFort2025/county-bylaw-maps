"""Quick Selenium test on Bayham's Laserfiche 2024 folder."""
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

url = "https://laserfiche.bayham.on.ca/WebLink/Browse.aspx?id=481053&dbid=0&repo=BAYHAM"
print(f"Loading: {url}")
driver.get(url)
time.sleep(5)

soup = BeautifulSoup(driver.page_source, "html.parser")
print("\nLinks in 2024 folder:")
for link in soup.find_all("a", href=True):
    href = link["href"]
    text = link.get_text().strip()
    full = urllib.parse.urljoin(url, href) if not href.startswith("http") else href
    if href.startswith("javascript:") or href == "#" or not text:
        continue
    if "Advanced" not in text and "Home" not in text:
        print(f"  [{text[:60]}] -> {full[:100]}")

driver.quit()
print("\nDone.")
