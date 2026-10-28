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
        "Development Charges By-law",
        "Development Charge By-law",
        "Development Charges Background Study",
        "DC Background Study",
        "Development Charges Study",
        "Development Charges Update",
        "Development Charges Review",
        "Development Charges Public Meeting",
        "Development Charges Act",
        "Development Charge Exemption",
        "Agricultural Development Charge",
        "Farm Building Exemption",
    ],
    "STORMWATER": [
        "Stormwater Management By-law",
        "Stormwater Charge",
        "Stormwater Fee",
        "Stormwater User Fee",
        "Stormwater Rate",
        "Stormwater Utility",
        "Stormwater Credit",
        "Stormwater Funding",
        "Impervious Area Charge",
        "Runoff Management Fee",
    ],
    "SITE_ALT": [
        "Site Alteration By-law",
        "Fill By-law",
        "Fill Management By-law",
        "Topsoil Preservation",
        "Topsoil Removal",
        "Dumping of Fill",
        "Excess Soil By-law",
        "Large Scale Fill",
        "Commercial Fill Operation",
    ],
    "TREES": [
        "Tree Cutting By-law",
        "Tree Preservation By-law",
        "Tree Protection By-law",
        "Private Tree By-law",
        "Woodland Conservation By-law",
        "Woodlands Conservation By-law",
        "Woodlot Conservation By-law",
        "Forest Conservation By-law",
        "Good Forestry Practices",
        "Tree Canopy Strategy",
        "Significant Woodland",
    ],
    "CHICKENS": [
        "Backyard Chickens",
        "Backyard Hens",
        "Urban Hens",
        "Urban Chickens",
        "Backyard Poultry",
        "Keeping of Chickens",
        "Keeping of Hens",
        "Chicken Coop",
    ],
    "LGD": [
        "Livestock Guardian Dog",
        "Working Dog Exemption",
        "Working Dog",
        "Herding Dog",
        "Dog Control By-law",
        "Canine Control By-law",
        "Animal Control By-law",
        "Kennel By-law",
        "Dog Licensing By-law",
    ],
    "FENCES": [
        "Fence By-law",
        "Line Fence By-law",
        "Division Fence",
        "Line Fences Act",
        "Cost of Division Fences",
        "Fence Cost Sharing",
        "Fence Viewer",
        "Fence-Viewer",
    ],
}


# ──────────────────────────────────────────────────────────────────
# CORE OFA BYLAW CATEGORY PACKS (7 core categories tracked on maps)
# ──────────────────────────────────────────────────────────────────
OFA_BYLAW_CATEGORY_PACKS = {
    "🏗️ Development Charges": KEYWORD_CONFIG["DC"],
    "🌧️ Stormwater Charges": KEYWORD_CONFIG["STORMWATER"],
    "🚜 Site Alteration & Fill": KEYWORD_CONFIG["SITE_ALT"],
    "🌲 Tree Cutting & Forestry": KEYWORD_CONFIG["TREES"],
    "🐔 Backyard Chickens": KEYWORD_CONFIG["CHICKENS"],
    "🐕 Livestock Guardian Dogs": KEYWORD_CONFIG["LGD"],
    "🚧 Fence Bylaws": KEYWORD_CONFIG["FENCES"],
}

# ──────────────────────────────────────────────────────────────────
# CUSTOM KEYWORD PACKS  (used by live scanner & fast_ad_hoc_scanner)
# Named presets that group related policy-watch keywords.
# ──────────────────────────────────────────────────────────────────
CUSTOM_KEYWORD_PACKS = {
    "🚄 ALTO Rail": [
        "ALTO", "ALTO Rail", "High Frequency Rail", "High-frequency rail",
        "High Speed Rail", "High-speed rail", "VIA HFR", "HFR", "Alt-NO", "ALT-NO",
    ],
    "🌱 Plant-Based Treaty": [
        "Plant Based Treaty", "Plant-Based Treaty", "Vegan Treaty",
    ],
    "🌾 Ontario Foodbelt": [
        "Foodbelt", "Food Belt", "Agricultural Preserve",
        "Golden Horseshoe Food and Farming",
    ],
    "🏠 On-Farm Worker Housing": [
        "on-farm worker housing", "farm worker housing", "agricultural worker housing",
        "seasonal farm worker", "seasonal agricultural worker", "farm bunkhouse",
        "bunkhouse", "bunk house", "farm help house", "help house", "helphouse",
        "farm labour housing", "farm labor housing", "agricultural worker accommodation",
    ],
    "🌿 Cannabis & Greenhouse DC Carve-Outs": [
        "cannabis production", "cannabis facility", "cannabis cultivation",
        "licensed producer", "agricultural cannabis", "commercial greenhouses",
        "retail-related greenhouses", "greenhouse development charge",
        "greenhouse by-law", "greenhouse abatement",
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


def build_keyword_regex_str(keyword: str) -> str:
    """Build a regex pattern string for a keyword that treats 'bylaw'/'by-law'/'by law' as interchangeable
    and safely applies word boundaries only when the keyword starts/ends with a word character."""
    kw = str(keyword or "").strip()
    if not kw:
        return r"(?!)"
    raw_tokens = re.split(r"[\s\-]+", kw)
    pattern_tokens = []
    i = 0
    while i < len(raw_tokens):
        tok = raw_tokens[i].lower()
        if tok in ("bylaw", "bylaws"):
            pattern_tokens.append(r"by[-\s]?laws?")
            i += 1
        elif tok == "by" and (i + 1) < len(raw_tokens) and raw_tokens[i + 1].lower() in ("law", "laws"):
            pattern_tokens.append(r"by[-\s]?laws?")
            i += 2
        else:
            pattern_tokens.append(re.escape(raw_tokens[i]))
            i += 1

    core = r"[\s\-]+".join(pattern_tokens)
    prefix = r"\b" if re.match(r"^\w", kw) else ""
    suffix = r"\b" if re.search(r"\w$", kw) else ""
    return f"{prefix}{core}{suffix}"


def build_keyword_regex(keyword: str) -> re.Pattern:
    """Compile a case-insensitive regex pattern for a single keyword."""
    return re.compile(build_keyword_regex_str(keyword), re.IGNORECASE)


def build_combined_keyword_regex(keywords: list[str]) -> re.Pattern:
    """Compile a single combined fast-exit regex across all keywords."""
    valid = [build_keyword_regex_str(k) for k in keywords if str(k or "").strip()]
    if not valid:
        return re.compile(r"(?!)")
    return re.compile("|".join(f"(?:{p})" for p in valid), re.IGNORECASE)


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

    kw_regex = build_keyword_regex(keyword)
    m = kw_regex.search(text)
    if m:
        idx = m.start()
        match_len = m.end() - m.start()
    else:
        idx = text.lower().find(keyword.lower())
        match_len = len(keyword)
        if idx == -1:
            return text[:window].strip()

    start = max(0, idx - window)
    end = min(len(text), idx + match_len + window)

    snippet = text[start:end].strip()

    # Inject an inline, highly visible marker around the matched phrase
    snippet = kw_regex.sub(lambda match: f" [ ** {match.group(0).upper()} ** ] ", snippet)

    return f"... {snippet} ..."


def canon_name(x: str) -> str:
    """Canonical municipality name for consistent matching across data sources."""
    if x is None:
        return ""
    import unicodedata
    s = str(x).replace("\u00A0", " ").strip()
    s = unicodedata.normalize("NFKC", s).upper()
    s = s.replace("&", " AND ").replace("-", " ")
    s = re.sub(r"[’'`]", "", s)
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
        "DISTRICT MUNICIPALITY OF ",
        "UNITED COUNTIES OF ",
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
    s = re.sub(r"\b(CO\.?|CNTY|TP|C|M|T|TV|VL|MU|R)\b$", "", s).strip()
    s = re.sub(r"\s+", " ", s).strip()
    aliases = {
        "ESSEX T": "ESSEX",
        "PERTH T": "PERTH",
        "PETERBOROUGH C": "PETERBOROUGH",
        "RENFREW T": "RENFREW",
        "WATERLOO C": "WATERLOO",
        "CHARLTON DACK": "CHARLTON AND DACK",
        "MATTICE VAL C T": "MATTICE VAL COTE",
        "THE SOUTH BRUCE PENINSULA": "SOUTH BRUCE PENINSULA",
        "MACDONALD MEREDITH ET AL": "MACDONALD MEREDITH AND ABERDEEN ADDITIONAL",
        "NORTHEASTERN MANITOULIN AND THE ISL": "NORTHEASTERN MANITOULIN AND THE ISLANDS",
        "SUDBURY": "GREATER SUDBURY",
    }
    return aliases.get(s, s)


def check_all_keywords(text: str) -> list[tuple[str, str]]:
    """Returns a list of (keyword, category) for every OFA category matched in text."""
    if not text:
        return []
    hits = []
    for cat, phrases in KEYWORD_CONFIG.items():
        for p in phrases:
            if build_keyword_regex(p).search(text):
                hits.append((p, cat))
                break  # One representative trigger per category per document
    return hits


def check_keywords(text: str):
    """Returns (keyword, category) for the first match, or (None, None)."""
    hits = check_all_keywords(text)
    if hits:
        return hits[0]
    return None, None


def extract_snippet(raw_text: str, trigger_keyword: str, window: int = 200) -> str:
    """Extract a meaningful context snippet around the keyword match.

    Instead of blindly taking the first 300 characters (which is often
    HTML boilerplate), this function:
      1. Strips HTML tags and script/style blocks
      2. Collapses whitespace
      3. Locates the keyword match (handling Bylaw / By-law variations)
      4. Returns ±window characters around it
    """
    if not raw_text or not trigger_keyword:
        return ""

    text = raw_text

    # --- Step 1: Remove script / style blocks entirely ---
    text = re.sub(r"<script[^>]*>.*?</script>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.DOTALL | re.IGNORECASE)

    # --- Step 2: Strip HTML tags (bounded so stray < and > in OCR PDFs do not eat pages) ---
    text = re.sub(r"<[a-zA-Z/!][^>\n]{0,300}>", " ", text)

    # --- Step 3: Decode common HTML entities ---
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&nbsp;", " ").replace("&quot;", '"')

    # --- Step 4: Collapse whitespace ---
    text = re.sub(r"\s+", " ", text).strip()

    # --- Step 5: Find the keyword using build_keyword_regex ---
    kw_regex = build_keyword_regex(trigger_keyword)
    m = kw_regex.search(text)
    if m:
        idx = m.start()
        match_len = m.end() - m.start()
    else:
        idx = text.lower().find(trigger_keyword.lower())
        match_len = len(trigger_keyword)
        if idx == -1:
            return text[:400].strip()

    start = max(0, idx - window)
    end = min(len(text), idx + match_len + window)

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


# ──────────────────────────────────────────────────────────────────
# DATE PARSING, NEGATIVE KEYWORD & DOCUMENT CLASSIFICATION HELPERS
# ──────────────────────────────────────────────────────────────────

def extract_date_from_text(text):
    """Extract a realistic calendar date from link text or URL while ignoring GUIDs and bylaw numbers."""
    import datetime
    if not text:
        return None
    cleaned = re.sub(
        r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',
        ' ',
        str(text),
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r'[?&]id=[0-9a-f\-]+', ' ', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(
        r'\b(?:by-?law|report|res(?:olution)?|no\.?|file|item)\s*#?\s*\d{4}[-/]\d{1,4}\b',
        ' ',
        cleaned,
        flags=re.IGNORECASE,
    )
    months = {
        'january': 1, 'february': 2, 'march': 3, 'april': 4,
        'may': 5, 'june': 6, 'july': 7, 'august': 8,
        'september': 9, 'october': 10, 'november': 11, 'december': 12,
        'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'jun': 6,
        'jul': 7, 'aug': 8, 'sep': 9, 'sept': 9, 'oct': 10, 'nov': 11, 'dec': 12,
        'janvier': 1, 'février': 2, 'fevrier': 2, 'mars': 3, 'avril': 4,
        'mai': 5, 'juin': 6, 'juillet': 7, 'août': 8, 'aout': 8,
        'septembre': 9, 'octobre': 10, 'novembre': 11, 'décembre': 12, 'decembre': 12,
    }
    text_lower = cleaned.lower()
    for m_name, m_num in months.items():
        match = re.search(rf'\b{m_name}\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s*(20[12]\d)\b', text_lower)
        if match:
            try:
                return datetime.date(int(match.group(2)), m_num, int(match.group(1)))
            except ValueError:
                pass
        match_dmy = re.search(rf'\b(\d{{1,2}})\s+{m_name}\.?,?\s*(20[12]\d)\b', text_lower)
        if match_dmy:
            try:
                return datetime.date(int(match_dmy.group(2)), m_num, int(match_dmy.group(1)))
            except ValueError:
                pass

    match = re.search(r'(?<![0-9a-f\-])(20[12]\d)[-/](0?[1-9]|1[0-2])[-/](0?[1-9]|[12]\d|3[01])(?![0-9a-f\-])', text_lower)
    if match:
        try:
            return datetime.date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except ValueError:
            pass
    return None


def is_recent_date(d, max_days=180):
    """Check if a date is within max_days (default: 180 days / 6 months) from today."""
    import datetime
    if d is None:
        return True
    today = datetime.date.today()
    return (today - d).days <= max_days


SOCIAL_JUNK_DOMAINS = (
    "youtube.com", "youtu.be", "soundcloud.com", "facebook.com", "l.facebook.com",
    "instagram.com", "twitter.com", "x.com", "linkedin.com", "baidu.com",
)


def apply_negative_keywords(text, negative_keywords):
    """Strips out negative keywords using whitespace/newline-resilient word boundaries.
    
    Handles newlines, multiple spaces, and tabs (e.g. 'greenhouse\\ngas' is matched).
    """
    if not text or not negative_keywords:
        return text
    for n_kw in negative_keywords:
        clean = str(n_kw).strip()
        if clean:
            words = clean.split()
            # \s+ matches any whitespace including newlines \n, \r, \t
            pattern = re.compile(r'\b' + r'\s+'.join(re.escape(w) for w in words) + r'\b', re.IGNORECASE)
            text = pattern.sub(" [IGNORED] ", text)
    return text


def is_valid_meeting_document(url, text="", title=""):
    """Validates that a document is genuine council business and not a static report/plan or social media page."""
    url_low = str(url or "").lower()
    if any(dom in url_low for dom in SOCIAL_JUNK_DOMAINS):
        return False

    # Always reject static governance documents (Procedural Bylaws, Terms of Reference, multi-year highlight archives)
    static_doc_url_patterns = (
        "procedural%20bylaw", "procedural-bylaw", "procedural_bylaw", "procedure%20by-law",
        "terms%20of%20reference", "terms-of-reference", "terms_of_reference",
        "/council-highlights",
    )
    if any(p in url_low for p in static_doc_url_patterns):
        return False

    combined = (url_low + " " + str(text[:500]) + " " + str(title)).lower()
    
    # Reject static corporate plans, annual reports, master plans, etc.
    junk_patterns = [
        "strategic-plan", "strategic_plan", "strategic plan",
        "master-plan", "master_plan", "master plan",
        "annual-report", "annual_report", "annual report",
        "budget-book", "budget_book", "budget book",
        "official-plan", "official_plan", "official plan",
        "accessibility-plan", "recreation-master", "culture-plan",
        "community-improvement-plan-guidelines",
        "watch-midland-council-meetings-live-on-youtube",
        "procedural bylaw", "procedure by-law", "terms of reference",
    ]
    if any(p in combined for p in junk_patterns):
        # Only allow if it is explicitly an agenda/minutes item
        if not any(k in combined for k in ["agenda", "minute", "postminutes", "council meeting", "special council"]):
            return False
    return True


def classify_meeting_doc(url, text=""):
    """Classifies document as Official Minutes, Past Agenda (Minutes Pending), or Upcoming Agenda."""
    url_lower = str(url).lower()
    text_sample = str(text[:600]).lower()
    
    # 1. Official Minutes Check
    if "postminutes" in url_lower or "agenda=minutes" in url_lower or "minutes of" in text_sample or "regular council minutes" in text_sample:
        if "agenda=agenda" not in url_lower and "agenda=merged" not in url_lower:
            return "📄 Official Minutes"
            
    # 2. Agenda Check & Date Comparison
    date_match = re.search(r'\b(202[4-9])[-/.](0[1-9]|1[0-2])[-/.](0[1-9]|[12]\d|3[01])\b', url_lower + " " + text_sample)
    if not date_match:
        months = r'(january|february|march|april|may|june|july|august|september|october|november|december)'
        date_match_text = re.search(months + r'\s+(\d{1,2}),?\s+(202[4-9])', text_sample)
        if date_match_text:
            try:
                import datetime
                m_str, d_str, y_str = date_match_text.groups()
                m_num = datetime.datetime.strptime(m_str[:3], "%b").month
                doc_date = datetime.date(int(y_str), m_num, int(d_str))
                today = datetime.date.today()
                if doc_date < today:
                    return "📋 Agenda (* Minutes Pending)"
                else:
                    return "📅 Upcoming Agenda"
            except Exception:
                pass

    if date_match:
        try:
            import datetime
            y, m, d = date_match.groups()
            doc_date = datetime.date(int(y), int(m), int(d))
            today = datetime.date.today()
            if doc_date < today:
                return "📋 Agenda (* Minutes Pending)"
            else:
                return "📅 Upcoming Agenda"
        except Exception:
            pass

    if "agenda" in url_lower or "agenda" in text_sample:
        return "📋 Agenda (* Minutes Pending)"

    return "📋 Council Document"

