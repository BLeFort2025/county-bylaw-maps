import re
import time

text = "This is a large document about greenhouses and agriculture. It discusses the " * 10000 # 760 KB text
keywords = [
    "agriculture", "development charges", "farm", "chicken", "livestock",
    "fence", "wind turbine", "solar", "zoning", "greenhouse",
    "pesticide", "nutrient", "drainage", "tile", "conservation",
    "wetland", "woodlot", "tree", "species at risk", "source water", "MDS"
]

content_lower = text.lower()

# Original approach
start = time.time()
for _ in range(10):
    matches = []
    for keyword in keywords:
        pattern = r'\b' + re.escape(keyword.lower()) + r'\b'
        if re.search(pattern, content_lower):
            matches.append(keyword)
print(f"Original approach: {time.time() - start:.4f}s")

# Combined regex approach
start = time.time()
combined_pattern = re.compile(r'\b(' + '|'.join(re.escape(kw.lower()) for kw in keywords) + r')\b')
for _ in range(10):
    matches = []
    if combined_pattern.search(content_lower):
        for keyword in keywords:
            pattern = r'\b' + re.escape(keyword.lower()) + r'\b'
            if re.search(pattern, content_lower):
                matches.append(keyword)
print(f"Combined approach: {time.time() - start:.4f}s")

# Combined approach when NO MATCHES
text2 = "This is a completely unrelated document about urban planning and transit." * 10000
content_lower2 = text2.lower()

start = time.time()
for _ in range(10):
    matches = []
    for keyword in keywords:
        pattern = r'\b' + re.escape(keyword.lower()) + r'\b'
        if re.search(pattern, content_lower2):
            matches.append(keyword)
print(f"Original approach (no match): {time.time() - start:.4f}s")

start = time.time()
for _ in range(10):
    matches = []
    if combined_pattern.search(content_lower2):
        for keyword in keywords:
            pattern = r'\b' + re.escape(keyword.lower()) + r'\b'
            if re.search(pattern, content_lower2):
                matches.append(keyword)
print(f"Combined approach (no match): {time.time() - start:.4f}s")
