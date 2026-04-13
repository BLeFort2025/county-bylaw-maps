"""Check the second Council folder in the second iframe."""
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

driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
url = "https://laserfiche.bayham.on.ca/WebLink/Browse.aspx?id=445794&dbid=0&repo=BAYHAM"
print(f"Loading second iframe Council folder: {url}")
driver.get(url)
time.sleep(5)

soup = BeautifulSoup(driver.page_source, "html.parser")
for link in soup.find_all("a", href=True):
    href = link["href"]
    text = link.get_text().strip()
    if text and text.isdigit():
        print(f"  [{text}] -> {href}")

driver.quit()
