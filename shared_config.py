"""
shared_config.py – Single source of truth for scanner keywords and utility functions.

Both scanner_v1_robust.py and scanner_v2_selenium.py import from here
to keep their keyword lists in sync.
"""

import re

# ── Admin config ──
# Default password is "ofa2026" — change the hash below to change the password.
# Generate a new hash with:  python -c "import hashlib; print(hashlib.sha256(b'YOUR_PASSWORD').hexdigest())"
ADMIN_PASSWORD_HASH = "92cfbe42146108c20a6c78f0f6885fd9880a8e8f004699a6d81dc7ed21a7ce4b"

BYLAW_CATEGORIES = [
    ("DC",        "Development Charges"),
    ("STORMWATER","Stormwater"),
    ("SITE_ALT",  "Site Alteration & Fill"),
    ("LGD",       "Livestock Guardian Dogs"),
    ("TREES",     "Tree / Forest Conservation"),
    ("CHICKENS",  "Backyard Chickens"),
    ("FENCES",    "Fence Bylaws"),
]

# ──────────────────────────────────────────────────────────────────
# KEYWORD_CONFIG
# Maps scanner category codes to trigger phrases.
# * Case-insensitive matching is applied by the scanners.
# * Keep phrases specific to reduce false positives.
# ──────────────────────────────────────────────────────────────────
KEYWORD_CONFIG = {
    "DC": [
        "Development Charges Background Study", "DC Background Study",
        "Development Charges Update Study", "Draft Development Charges By-law",
        "Proposed Development Charges By-law", "Passage of Development Charges By-law",
        "Statutory Public Meeting regarding Development Charges",
        "Notice of Public Meeting regarding Development Charges",
        "Development Charges Public Meeting", "Agricultural Exemption Review",
        "Farm Building Exemption", "Bona Fide Farm", "More Homes Built Faster Act",
        "Community Benefits Charge", "Bill 185", "Comprehensive Zoning Bylaw"
    ],
    "STORMWATER": [
        "Stormwater Rate Study", "Stormwater Utility Feasibility",
        "Impervious Area Charge", "Runoff Management Fee",
        "Drainage Master Plan", "Stormwater User Fee",
        "Stormwater Funding Model"
    ],
    "SITE_ALT": [
        "Site Alteration Bylaw", "Fill Bylaw", "Topsoil Preservation",
        "Topsoil Removal", "Dumping of Fill", "Large Scale Fill Agreement",
        "Commercial Fill Operation"
    ],
    "TREES": [
        "Tree Cutting Bylaw", "Private Tree Protection",
        "Woodland Conservation Bylaw", "Forest Conservation Bylaw",
        "Tree Canopy Strategy", "Significant Woodland Review",
        "Stop Work Order - Trees"
    ],
    "CHICKENS": [
        "Backyard Chickens",           # Most important — from V2
        "Backyard Hens",
        "Urban Hens Pilot",
        "Backyard Poultry",
        "Chicken Coop Regulations",
        # NOTE: "Keeping of Animals Bylaw" was removed — too broad.
        # Every Ontario municipality has a generic "Keeping of Animals"
        # bylaw that is unrelated to backyard chickens specifically.
    ],
    "LGD": [
        "Animal Control Bylaw Review", "Dog Control Bylaw",
        "Kennel By-law", "Livestock Guardian Dog",
        "Working Dog Exemption", "Dog Licensing Fee Review"
    ],
    "FENCES": [
        "Fence Bylaw", "Division Fence", "Line Fences Act",
        "Cost of Division Fences"
    ]
}


# ──────────────────────────────────────────────────────────────────
# CUSTOM KEYWORD PACKS  (used by live scanner & fast_ad_hoc_scanner)
# Named presets that group related policy-watch keywords.
# ──────────────────────────────────────────────────────────────────
CUSTOM_KEYWORD_PACKS = {
    "🚄 ALTO Rail": [
        "ALTO", "High Speed Rail", "High-speed rail", "Passenger Rail",
        "High Frequency Rail", "High-frequency rail", "HFR", "Alt-NO", "ALT-NO", "VIA HFR",
    ],
    "🌱 Plant-Based Treaty": [
        "Plant Based Treaty", "Plant-Based Treaty", "Vegan Treaty",
    ],
    "🌾 Ontario Foodbelt": [
        "Foodbelt", "Food Belt", "Agricultural Preserve",
        "Golden Horseshoe Food and Farming",
    ],
}

# ──────────────────────────────────────────────────────────────────
# REGION MAPPING  (shared between terminal scanner & Streamlit UI)
# Maps county / municipality name fragments to OFA advocacy regions.
# ──────────────────────────────────────────────────────────────────
REGION_MAPPING = {
    'Northern': [
        'Rainy River', 'Timiskaming', 'Manitoulin', 'Sudbury', 'Cochrane',
        'Algoma', 'Nipissing', 'Thunder Bay', 'Kenora', 'Parry Sound',
        'Muskoka', 'Black River', 'Burk', 'Fauquier', 'Mattice',
        'McMurrich', 'Papineau', 'Sioux Narrows', 'St Charles', 'Val Rita',
    ],
    'Eastern': [
        'Leeds and Grenville', 'Lennox and Addington', 'Renfrew',
        'Prescott and Russell', 'Frontenac', 'Stormont', 'Dundas',
        'Glengarry', 'Lanark', 'Hastings', 'Ottawa', 'Prince Edward',
        'Admaston', 'Brudenell', 'Carlow', 'Clarence', 'Drummond',
        'Edwardsburgh', 'Elizabethtown', 'Head Clara', 'McNab',
        'Merrickville', 'Stirling',
    ],
    'Western': [
        'Middlesex', 'Essex', 'Bruce', 'Huron', 'Elgin', 'Oxford',
        'Lambton', 'Waterloo', 'Wellington', 'Chatham-Kent', 'Chatham Kent',
        'Grey', 'Perth', 'Brant', 'Haldimand', 'Norfolk', 'Adelaide',
        'Arran', 'Blandford', 'Brooke', 'Dutton', 'Morris', 'Plympton',
        'Strathroy',
    ],
    'Central': [
        'York', 'Simcoe', 'Durham', 'Haliburton', 'Northumberland',
        'Dufferin', 'Peterborough', 'Peel', 'Halton', 'Niagara',
        'Hamilton', 'Kawartha Lakes', 'Toronto', 'Adjala', 'Asphodel',
        'Douro', 'Havelock', 'Oro Medonte', 'Otonabee', 'Whitchurch',
    ],
}


def get_region(county, name):
    """Resolve a municipality's OFA advocacy region from county/name fragments."""
    for text in [str(county).lower(), str(name).lower()]:
        if not text or text == "nan" or text == "unknown":
            continue
        for region, keywords in REGION_MAPPING.items():
            if any(k.lower() in text for k in keywords):
                return region
    return "Unknown"


def extract_readable_snippet(text, keyword, window=250):
    """Extract a context snippet with visible keyword markers for CSV/UI output.

    Preserves list formatting and injects [ ** KEYWORD ** ] markers for
    instant readability in Excel and Streamlit data tables.
    """
    if not text or not keyword:
        return ""

    # Flatten all newlines, tabs, and carriage returns into single spaces
    # This prevents Excel rows from becoming massively tall and hard to read
    text = re.sub(r'[\r\n\t]+', ' ', text)
    text = re.sub(r' {2,}', ' ', text)

    idx = text.lower().find(keyword.lower())
    if idx == -1:
        return text[:window].strip()

    start = max(0, idx - window)
    end = min(len(text), idx + len(keyword) + window)

    snippet = text[start:end].strip()

    # Inject an inline, highly visible marker around the keyword
    pattern = re.compile(re.escape(keyword), re.IGNORECASE)
    snippet = pattern.sub(f" [ ** {keyword.upper()} ** ] ", snippet)

    return f"... {snippet} ..."


def canon_name(x: str) -> str:
    """Canonical municipality name for consistent matching across data sources."""
    if x is None:
        return ""
    s = str(x).replace("\u00A0", " ").strip().upper()
    s = s.replace("&", " AND ").replace("-", " ")
    s = re.sub(r"[''`]", "", s)
    s = re.sub(r"[^A-Z0-9 /]", " ", s)
    s = s.replace("/", " ")
    s = re.sub(r"\s+", " ", s).strip()
    for p in [
        "CITY OF ",
        "TOWN OF ",
        "TOWNSHIP OF ",
        "VILLAGE OF ",
        "MUNICIPALITY OF ",
        "REGIONAL MUNICIPALITY OF ",
        "REGION OF ",
        "COUNTY OF ",
        "DISTRICT OF ",
    ]:
        if s.startswith(p):
            s = s[len(p):].strip()
            break
    for suf in [
        " COUNTY",
        " REGION",
        " CITY",
        " TOWN",
        " TOWNSHIP",
        " VILLAGE",
        " MUNICIPALITY",
        " DISTRICT",
    ]:
        if s.endswith(suf):
            s = s[: -len(suf)].strip()
            break
    s = re.sub(r"\b(CO\.?|CNTY)\b$", "", s).strip()
    return re.sub(r"\s+", " ", s).strip()


def check_keywords(text: str):
    """Returns (keyword, category) for the first match, or (None, None)."""
    if not text:
        return None, None
    text_lower = text.lower()
    for cat, phrases in KEYWORD_CONFIG.items():
        for p in phrases:
            if p.lower() in text_lower:
                return p, cat
    return None, None


def extract_snippet(raw_text: str, trigger_keyword: str, window: int = 200) -> str:
    """Extract a meaningful context snippet around the keyword match.

    Instead of blindly taking the first 300 characters (which is often
    HTML boilerplate), this function:
      1. Strips HTML tags and script/style blocks
      2. Collapses whitespace
      3. Locates the keyword match
      4. Returns ±window characters around it

    Args:
        raw_text:        The full page text (may contain HTML).
        trigger_keyword: The keyword phrase that was matched.
        window:          Number of characters on each side of the match.

    Returns:
        A clean, human-readable snippet (max ~2*window + len(keyword) chars).
    """
    if not raw_text or not trigger_keyword:
        return ""

    text = raw_text

    # --- Step 1: Remove script / style blocks entirely ---
    text = re.sub(r"<script[^>]*>.*?</script>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.DOTALL | re.IGNORECASE)

    # --- Step 2: Strip all remaining HTML tags ---
    text = re.sub(r"<[^>]+>", " ", text)

    # --- Step 3: Decode common HTML entities ---
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&nbsp;", " ").replace("&quot;", '"')

    # --- Step 4: Collapse whitespace ---
    text = re.sub(r"\s+", " ", text).strip()

    # --- Step 5: Find the keyword and extract a context window ---
    idx = text.lower().find(trigger_keyword.lower())
    if idx == -1:
        # Keyword not found after stripping — fall back to first 400 clean chars
        return text[:400].strip()

    start = max(0, idx - window)
    end = min(len(text), idx + len(trigger_keyword) + window)

    snippet = text[start:end].strip()

    # Try to start/end at word boundaries
    if start > 0:
        first_space = snippet.find(" ")
        if first_space != -1 and first_space < 30:
            snippet = snippet[first_space + 1:]
        snippet = "..." + snippet
    if end < len(text):
        last_space = snippet.rfind(" ")
        if last_space != -1 and (len(snippet) - last_space) < 30:
            snippet = snippet[:last_space]
        snippet = snippet + "..."

    return snippet
