import time
from bs4 import BeautifulSoup
import urllib.parse
import re
from refresh_registry import setup_driver

def _navigate_laserfiche(driver, base_url):
    print("Navigating laserfiche:", base_url)
    try:
        driver.get(base_url)
        time.sleep(5)
        soup = BeautifulSoup(driver.page_source, "html.parser")

        # Step 1: Look for Council / Minutes folder
        council_url = None
        for link in soup.find_all("a", href=True):
            href = link["href"]
            text = link.get_text().strip().lower()
            if "weblink/browse.aspx" in href.lower() and ("council" in text or "minute" in text):
                council_url = urllib.parse.urljoin(base_url, href)
                print("Found council url:", council_url)
                break
        
        if not council_url and "weblink/browse.aspx" in base_url.lower():
            print("Assuming base url is council url")
            council_url = base_url

        if council_url:
            driver.get(council_url)
            time.sleep(4)
            soup = BeautifulSoup(driver.page_source, "html.parser")

            # Step 2: Find the most recent year folder
            year_folders = []
            for link in soup.find_all("a", href=True):
                text = link.get_text().strip()
                href = link["href"]
                if "weblink/browse.aspx" in href.lower() and text.isdigit() and len(text) == 4:
                    year_folders.append((urllib.parse.urljoin(council_url, href), int(text)))
            
            print(f"Year folders: {year_folders}")
            if year_folders:
                year_folders.sort(key=lambda x: x[1], reverse=True)
                latest_year_url = year_folders[0][0]
                print(f"Navigating to latest year: {latest_year_url}")
                driver.get(latest_year_url)
                time.sleep(4)
                soup = BeautifulSoup(driver.page_source, "html.parser")

                # Step 3: Find highest numbered month/date folder
                date_folders = []
                for link in soup.find_all("a", href=True):
                    text = link.get_text().strip()
                    href = link["href"]
                    if "weblink/browse.aspx" in href.lower() and text:
                        match = re.match(r"^(\d+)", text)
                        if match:
                            date_folders.append((urllib.parse.urljoin(latest_year_url, href), int(match.group(1))))
                
                print(f"Date folders: {date_folders}")
                if date_folders:
                    date_folders.sort(key=lambda x: x[1], reverse=True)
                    latest_date_url = date_folders[0][0]
                    print(f"Navigating to latest date: {latest_date_url}")
                    driver.get(latest_date_url)
                    time.sleep(4)
                    soup = BeautifulSoup(driver.page_source, "html.parser")
            
            # Step 4: Now find DocView links
            doc_links = []
            for link in soup.find_all("a", href=True):
                href = link["href"]
                text = link.get_text().strip().lower()
                if "weblink/docview.aspx" in href.lower() and ("council" in text or "minute" in text or "agenda" in text):
                    doc_links.append(urllib.parse.urljoin(driver.current_url, href))
            
            print(f"DocView links specific: {doc_links}")
            if not doc_links:
                for link in soup.find_all("a", href=True):
                    if "weblink/docview.aspx" in link["href"].lower():
                        doc_links.append(urllib.parse.urljoin(driver.current_url, link["href"]))
            
            print(f"DocView links all: {doc_links}")

            if doc_links:
                selected = doc_links[0]
                parsed = urllib.parse.urlparse(selected)
                query = urllib.parse.parse_qs(parsed.query)
                doc_id = query.get("id", [""])[0]
                repo = query.get("repo", [""])[0]
                dbid = query.get("dbid", ["0"])[0]
                
                new_query = urllib.parse.urlencode({
                    "docid": doc_id,
                    "dbid": dbid,
                    "repo": repo
                })
                new_path = parsed.path.replace("DocView.aspx", "ElectronicFile.aspx", 1).replace("docview.aspx", "ElectronicFile.aspx", 1)
                return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, new_path, "", new_query, ""))
                
    except Exception as e:
        print(f" Laserfiche error: {e}")
    return None

driver = setup_driver()
driver.get("http://www.bayham.on.ca/governance/council/agendas-minutes/")
time.sleep(5)
soup = BeautifulSoup(driver.page_source, "html.parser")
found = False
for iframe in soup.find_all("iframe"):
    src = iframe.get("src", "")
    if src and ("laserfiche" in src.lower() or "weblink" in src.lower()):
        print(f"Found iframe: {src}")
        url = urllib.parse.urljoin("http://www.bayham.on.ca/governance/council/agendas-minutes/", src)
        res = _navigate_laserfiche(driver, url)
        print(f"Result: {res}")
        found = True
        break

if not found:
    print("No iframe found.")

driver.quit()
