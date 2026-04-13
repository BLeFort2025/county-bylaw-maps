"""See what links or PDF sources are inside DocView.aspx"""
import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup

options = Options()
options.add_argument("--headless=new")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--log-level=3")
options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64)")

driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
driver.set_page_load_timeout(30)

url = "https://laserfiche.bayham.on.ca/WebLink/DocView.aspx?id=536969&dbid=0&repo=BAYHAM"
print(f"Loading: {url}")
driver.get(url)
time.sleep(10)  # Wait for viewer to render

soup = BeautifulSoup(driver.page_source, "html.parser")
print("\nIframes inside DocView:")
for iframe in soup.find_all("iframe"):
    print(f"  src = {iframe.get('src')}")

print("\nPDF or Pdf or Export or Download links:")
for link in soup.find_all("a", href=True):
    href = link["href"]
    text = link.get_text().strip()
    if any(k in href.lower() or k in text.lower() for k in ["pdf", "download", "export"]):
        print(f"  [{text}] -> {href}")

driver.quit()
print("\nDone.")
