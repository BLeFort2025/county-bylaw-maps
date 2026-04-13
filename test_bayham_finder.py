import time
from refresh_registry import setup_driver, find_latest_document

driver = setup_driver()
url = "http://www.bayham.on.ca/governance/council/agendas-minutes/"
print(f"Testing find_latest_document on {url}")
result = find_latest_document(driver, url)
print(f"Resulting URL: {result}")
driver.quit()
