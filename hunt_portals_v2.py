import pandas as pd
import requests
from bs4 import BeautifulSoup
import os
import re
import urllib3
import time

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- CONFIG ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REGISTRY_PATH = os.path.join(SCRIPT_DIR, "signals", "portal_registry.csv")

# --- THE HIT LIST (Extracted from your Error Report) ---
# These are the ~190 municipalities that failed scanning but were skipped by the previous hunter.
TARGETS = [
    "ADMASTON BROMLEY TP", "ALBERTON TP", "ALNWICK HALDIMAND TP", "AMARANTH TP", 
    "ARCHIPELAGO TP", "ARMOUR TP", "ARRAN ELDERSLIE M", "ASHFIELD COLBORNE WAWANOSH TP", 
    "ASPHODEL NORWOOD TP", "ASSIGINACK TP", "ATHENS TP", "ATIKOKAN TP", "AYLMER T", 
    "BALDWIN TP", "BANCROFT T", "BECKWITH TP", "BILLINGS TP", "BLACK RIVER MATHESON TP", 
    "BLANDFORD BLENHEIM TP", "BLIND RIVER T", "BLUEWATER M", "BONFIELD TP", "BONNECHERE VALLEY TP", 
    "BRACEBRIDGE T", "BRAMPTON C", "BRANTFORD C", "BRETHOUR TP", "BRIGHTON M", "BROCKTON M", 
    "BROCKVILLE C", "BRUCE MINES T", "BRUDENELL LYNDOCH AND RAGLAN TP", "BURK TMS FALLS TP", 
    "BURPEE AND MILLS TP", "CALLANDER M", "CALVIN M", "CAMBRIDGE C", "CARLETON PLACE T", 
    "CARLING TP", "CARLOW MAYO TP", "CASEY TP", "CASSELMAN M", "CENTRAL FRONTENAC TP", 
    "CENTRAL HURON M", "CENTRAL MANITOULIN M", "CHAMBERLAIN TP", "CHAMPLAIN TP", "CHAPLEAU TP", 
    "CHAPPLE TP", "CHARLTON AND DACK M", "CHISHOLM TP", "CLARENCE ROCKLAND C", "COBOURG T", 
    "COCHRANE T", "COCKBURN ISLAND TP", "COLEMAN TP", "COLLINGWOOD T", "CONMEE TP", "CORNWALL C", 
    "CRAMAHE TP", "DAWN EUPHEMIA TP", "DEEP RIVER T", "DESERONTO T", "DORION TP", 
    "DOURO DUMMER TP", "DRUMMOND NORTH ELMSLEY TP", "DRYDEN C", "DUBREUILVILLE TP", 
    "DUTTON DUNWICH M", "DYSART ET AL M", "EAR FALLS TP", "EAST FERRIS M", "EAST GARAFRAXA TP", 
    "EAST HAWKESBURY TP", "ELIZABETHTOWN KITLEY TP", "EMO TP", "ENGLEHART T", "ENNISKILLEN TP", 
    "ERIN T", "ESPANOLA T", "ESSA TP", "EVANTUREL TP", "FARADAY TP", "FORT FRANCES T", 
    "FRENCH RIVER M", "FRONT OF YONGE TP", "FRONTENAC ISLANDS TP", "GANANOQUE T", "GAUTHIER TP", 
    "GILLIES TP", "GODERICH T", "GORDON BARRIE ISLAND M", "GORE BAY T", "GRAND VALLEY T", 
    "GRIMSBY T", "GUELPH/ERAMOSA TP", "HAMILTON TP", "HARRIS TP", "HAVELOCK BELMONT METHUEN TP", 
    "HAWKESBURY T", "HEAD CLARA AND MARIA TP", "HEARST T", "HIGHGATE V", "HIGHLANDS EAST M", 
    "HILLIARD TP", "HILTON BEACH V", "HILTON TP", "HORNEPAYNE TP", "HORTON TP", "HOWICK TP", 
    "HUDSON TP", "HUNTSVILLE T", "HURON EAST M", "HURON KINLOSS TP", "HURON SHORES M", 
    "IGNACE TP", "INGERSOLL T", "INNISFIL T", "IROQUOIS FALLS T", "JAMES TP", "JOCELYN TP", 
    "JOHNSON TP", "JOLY TP", "KAPUSKASING T", "KEARNEY T", "KENORA C", "KERNS TP", 
    "KILLALOE HAGARTY AND RICHARDS TP", "KILLARNEY M", "KINCARDINE M", "KING TP", "KINGSTON C", 
    "KINGSVILLE T", "KIRKLAND LAKE T", "KITCHENER C", "LA VALLEE TP", "LAIRD TP", 
    "LAKE OF BAYS TP", "LAKE OF THE WOODS TP", "LAKESHORE M", "LAMBTON SHORES M", 
    "LANARK HIGHLANDS TP", "LARDER LAKE TP", "LASALLE T", "LATCHFORD T", "LAURENTIAN HILLS T", 
    "LAURENTIAN VALLEY TP", "LEAMINGTON M", "LEEDS AND THE THOUSAND ISLANDS TP", "LIMERICK TP", 
    "LINCOLN T", "LONDON C", "LOYALIST TP", "LUCAN BIDDULPH TP", "MACHIN M", "MADAWASKA VALLEY TP", 
    "MADOC TP", "MAGNETAWAN M", "MALAHIDE TP", "MANITOUWADGE TP", "MAPLETON TP", "MARATHON T", 
    "MARKHAM C", "MARKSTAY-WARREN M", "MARMORA AND LAKE M", "MASSEY T", "MATTAWA T", 
    "MATTAWAN TP", "MCDOUGALL M", "MCGARRY TP", "MCKELLAR TP", "MCMURRICH MONTEITH TP", 
    "MCNAB BRAESIDE TP", "MEAFORD M", "MELANCTHON TP", "MERRICKVILLE-WOLFORD V", 
    "MIDDLESEX CENTRE M", "MIDLAND T", "MILTON T", "MINDEN HILLS TP", "MINTO T", 
    "MISSISSAUGA C", "MISSISSIPPI MILLS T", "MONO T", "MONTAGUE TP", "MOONBEAM TP", 
    "MOOSONEE T", "MORLEY TP", "MORRIS-TURNBERRY M", "MULMUR TP", "MUSKOKA LAKES TP", 
    "NAIRN AND HYMAN TP", "NEEBING M", "NEWMARKET T", "NIAGARA FALLS C", "NIAGARA-ON-THE-LAKE T", 
    "NIPISSING TP", "NORFOLK COUNTY", "NORTH ALGONA WILBERFORCE TP", "NORTH BAY C", 
    "NORTH DUMFRIES TP", "NORTH DUNDAS TP", "NORTH FRONTENAC TP", "NORTH GLENGARRY TP", 
    "NORTH GRENVILLE M", "NORTH HURON TP", "NORTH KAWARTHA TP", "NORTH MIDDLESEX M", 
    "NORTH PERTH M", "NORTH SHORE TP", "NORTH STORMONT TP", "NORTHEASTERN MANITOULIN AND THE ISLANDS T", 
    "NORTHERN BRUCE PENINSULA M", "NORWICH TP", "OAKVILLE T", "O'CONNOR TP", "OIL SPRINGS V", 
    "OLIVER PAIPOONGE M", "ORANGEVILLE T", "ORILLIA C", "ORO-MEDONTE TP", "OSHAWA C", 
    "OTTAWA C", "OWEN SOUND C", "PAPINEAU-CAMERON TP", "PARRY SOUND T", "PELEE TP", 
    "PELHAM T", "PEMBROKE C", "PENETANGUISHENE T", "PERRY TP", "PERTH T", "PETERBOROUGH C", 
    "PETROLIA T", "PICKERING C", "PICKLE LAKE TP", "PLUMMER ADDITIONAL TP", "PLYMPTON-WYOMING T", 
    "POINT EDWARD V", "PORT COLBORNE C", "PORT HOPE M", "POWASSAN M", "PRESCOTT T", 
    "PRINCE EDWARD COUNTY", "PRINCE TP", "PUSLINCH TP", "RAINY RIVER T", "RAMARA TP", 
    "RED LAKE M", "RED ROCK TP", "RENFREW T", "RICHMOND HILL C", "RIDEAU LAKES TP", 
    "RYERSON TP", "SARNIA C", "SAUGEEN SHORES T", "SAULT STE. MARIE C", "SCHREIBER TP", 
    "SEGUIN TP", "SELWYN TP", "SEVERN TP", "SHELBURNE T", "SHUNIAH M", "SIOUX LOOKOUT M", 
    "SIOUX NARROWS-NESTOR FALLS TP", "SMITHS FALLS T", "SMOOTH ROCK FALLS T", "SOUTH ALGONQUIN TP", 
    "SOUTH BRUCE PENINSULA T", "SOUTH BRUCE M", "SOUTH DUNDAS M", "SOUTH FRONTENAC TP", 
    "SOUTH GLENGARRY TP", "SOUTH HURON M", "SOUTH RIVER V", "SOUTH STORMONT TP", "SOUTHGATE TP", 
    "SOUTHWEST MIDDLESEX M", "SOUTHWOLD TP", "SPANISH T", "SPRINGWATER TP", "ST. CATHARINES C", 
    "ST. CHARLES M", "ST. CLAIR TP", "ST. JOSEPH TP", "ST. MARYS T", "ST. THOMAS C", 
    "STIRLING-RAWDON T", "STONE MILLS TP", "STRATFORD C", "STRATHROY-CARADOC M", 
    "STRONG TP", "SUNDRIDGE V", "TARBUTT TP", "TAY TP", "TAY VALLEY TP", "TECUMSEH T", 
    "TEHKUMMAH TP", "TEMAGAMI M", "TEMISKAMING SHORES C", "TERRACE BAY TP", "THAMES CENTRE M", 
    "THE BLUE MOUNTAINS T", "THESSALON T", "THOROLD C", "THUNDER BAY C", "TILLSONBURG T", 
    "TIMMINS C", "TINY TP", "TORONTO C", "TRENT HILLS M", "TRENT LAKES M", "TUDOR AND CASHEL TP", 
    "TWEED M", "TYENDINAGA TP", "UXBRIDGE TP", "VAL RITA-HARTY TP", "VAUGHAN C", 
    "WAINFLEET TP", "WARWICK TP", "WASAGA BEACH T", "WATERLOO C", "WAWA M", "WELLAND C", 
    "WELLESLEY TP", "WELLINGTON NORTH TP", "WEST GREY M", "WEST LINCOLN TP", "WEST NIPISSING M", 
    "WEST PERTH M", "WEST WHITBY T", # Typo in user data usually WHITBY T
    "WHITBY T", "WHITCHURCH-STOUFFVILLE T", "WHITE RIVER TP", "WHITEWATER REGION TP", 
    "WILMOT TP", "WINDSOR C", "WOLLASTON TP", "WOODSTOCK C", "WOOLWICH TP", "WYOMING"
]

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5'
}

GOLDEN_KEYWORDS = ["civicweb", "escribemeetings", "siretechnologies", "agendasonline"]
SILVER_KEYWORDS = ["minutes", "agenda", "council meetings", "calendar"]

def get_homepage_candidates(name):
    # Clean name: "AUGUSTA TP" -> "augusta"
    clean = re.sub(r'\s+(TP|M|C|T|V)$', '', name, flags=re.IGNORECASE).strip().lower()
    clean_nospace = clean.replace(" ", "")
    clean_hyphen = clean.replace(" ", "-")
    
    domains = [
        f"https://{clean_nospace}.civicweb.net/Portal/",
        f"https://pub-{clean_nospace}.escribemeetings.com/",
        f"https://pub-{clean_hyphen}.escribemeetings.com/",
        f"https://www.{clean_nospace}.ca",
        f"https://www.{clean_nospace}.on.ca",
        f"https://www.{clean_hyphen}.ca",
        f"https://{clean_nospace}.ca"
    ]
    return domains

def hunt_for_portal(munid, name):
    print(f"\n[HUNTING] {name}...")
    candidates = get_homepage_candidates(name)
    
    for url in candidates:
        try:
            # Check if it's a direct portal hit first (fastest)
            if "civicweb" in url or "escribemeetings" in url:
                r = requests.get(url, headers=HEADERS, timeout=4, verify=False)
                if r.status_code == 200 and ("council" in r.text.lower() or "search" in r.text.lower()):
                    print(f"  [!!!] DIRECT PORTAL HIT: {url}")
                    return url
            
            # Otherwise scrape homepage
            r = requests.get(url, headers=HEADERS, timeout=4, verify=False)
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, 'html.parser')
                
                # 1. Look for external portal links
                for link in soup.find_all('a', href=True):
                    href = link['href']
                    if href.startswith("/"): href = url.rstrip("/") + href
                    if any(k in href.lower() for k in GOLDEN_KEYWORDS):
                        print(f"  [!!!] FOUND PORTAL ON PAGE: {href}")
                        return href
                
                # 2. Look for "Minutes" page
                for link in soup.find_all('a', href=True):
                    href = link['href']
                    text = link.get_text().lower()
                    if any(k in text for k in SILVER_KEYWORDS):
                        if href.startswith("/"): href = url.rstrip("/") + href
                        if not href.startswith("http"): continue
                        if "mailto" in href: continue
                        
                        print(f"  [+] Found Minutes Page: {href}")
                        return href
                        
        except Exception:
            continue
            
    print("  [-] No portal found.")
    return None

def main():
    print("--- TARGETED PORTAL HUNTER V2 ---")
    
    if not os.path.exists(REGISTRY_PATH):
        print(f"Registry not found at {REGISTRY_PATH}")
        return
    df = pd.read_csv(REGISTRY_PATH)
    
    fixed_count = 0
    
    for munid in TARGETS:
        # Find row in registry
        mask = df['munid'] == munid
        if not mask.any(): 
            continue
        
        # Don't skip even if URL exists - we assume it's broken if it's in the target list
        name = df.loc[mask, 'municipality_name'].values[0]
        
        # Hunt!
        new_url = hunt_for_portal(munid, name)
        
        if new_url:
            df.loc[mask, 'minutes_listing_url'] = new_url
            df.loc[mask, 'example_recent_minutes_url'] = new_url
            fixed_count += 1
            
            if fixed_count % 5 == 0:
                df.to_csv(REGISTRY_PATH, index=False)
                print(f"  >> SAVED PROGRESS ({fixed_count} fixed)")

    if fixed_count > 0:
        df.to_csv(REGISTRY_PATH, index=False)
        print(f"\nSUCCESS: Targeted Hunter fixed {fixed_count} municipalities!")
    else:
        print("\nNo new portals found.")

if __name__ == "__main__":
    main()