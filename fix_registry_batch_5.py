import pandas as pd
import os

# --- SMART CONFIG ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
path_sibling = os.path.join(SCRIPT_DIR, "signals", "portal_registry.csv")
path_parent = os.path.join(os.path.dirname(SCRIPT_DIR), "signals", "portal_registry.csv")

if os.path.exists(path_sibling):
    REGISTRY_PATH = path_sibling
elif os.path.exists(path_parent):
    REGISTRY_PATH = path_parent
else:
    REGISTRY_PATH = path_sibling

# --- BATCH 5 FIXES (O - Z) ---
FIXES = {
    "OAKVILLE T": "https://pub-oakville.escribemeetings.com/",
    "OIL SPRINGS V": "https://oilsprings.ca/village-office/council-minutes/",
    "OLIVER PAIPOONGE M": "https://oliverpaipoonge.civicweb.net/Portal/",
    "ORANGEVILLE T": "https://calendar.orangeville.ca/meetings",
    "ORILLIA C": "https://orillia.civicweb.net/Portal/",
    "ORO-MEDONTE TP": "https://pub-oro-medonte.escribemeetings.com/",
    "OSHAWA C": "https://pub-oshawa.escribemeetings.com/",
    "OTTAWA C": "https://pub-ottawa.escribemeetings.com/",
    "OWEN SOUND C": "https://pub-owensound.escribemeetings.com/",
    "PELHAM T": "https://pelham.civicweb.net/Portal/",
    "PEMBROKE C": "https://pembroke.civicweb.net/Portal/",
    "PENETANGUISHENE T": "https://pub-penetanguishene.escribemeetings.com/",
    "PERRY TP": "https://townshipofperry.ca/council-agendas-and-minutes/",
    "PERTH T": "https://perth.civicweb.net/Portal/",
    "PETERBOROUGH C": "https://pub-peterborough.escribemeetings.com/",
    "PETROLIA T": "https://petrolia.civicweb.net/Portal/",
    "PICKERING C": "https://calendar.pickering.ca/council",
    "PLYMPTON-WYOMING T": "https://pub-plympton-wyoming.escribemeetings.com/",
    "POINT EDWARD V": "https://villageofpointedward.com/council/minutes/",
    "PORT COLBORNE C": "https://portcolborne.civicweb.net/Portal/",
    "PORT HOPE M": "https://pub-porthope.escribemeetings.com/",
    "POWASSAN M": "https://powassan.civicweb.net/Portal/",
    "PRESCOTT T": "https://prescott.ca/government/agendas-minutes/",
    "PRINCE EDWARD COUNTY": "https://pub-pec.escribemeetings.com/",
    "PUSLINCH TP": "https://pub-puslinch.escribemeetings.com/",
    "RAMARA TP": "https://ramara.civicweb.net/Portal/",
    "RENFREW T": "https://renfrew.civicweb.net/Portal/",
    "RICHMOND HILL C": "https://pub-richmondhill.escribemeetings.com/",
    "RIDEAU LAKES TP": "https://pub-rideaulakes.escribemeetings.com/",
    "SARNIA C": "https://pub-sarnia.escribemeetings.com/",
    "SAUGEEN SHORES T": "https://pub-saugeenshores.escribemeetings.com/",
    "SAULT STE. MARIE C": "https://saultstemarie.ca/City-Hall/City-Council/Agenda-and-Minutes.aspx",
    "SEGUIN TP": "https://pub-seguin.escribemeetings.com/",
    "SELWYN TP": "https://selwyn.civicweb.net/Portal/",
    "SIOUX LOOKOUT M": "https://siouxlookout.civicweb.net/Portal/",
    "SMITHS FALLS T": "https://pub-smithsfalls.escribemeetings.com/",
    "SOUTH FRONTENAC TP": "https://southfrontenac.civicweb.net/Portal/",
    "SOUTH STORMONT TP": "https://southstormont.civicweb.net/Portal/",
    "SPRINGWATER TP": "https://springwater.civicweb.net/Portal/",
    "ST. CATHARINES C": "https://stcatharines.civicweb.net/Portal/",
    "ST. THOMAS C": "https://stthomas.civicweb.net/Portal/",
    "STRATFORD C": "https://stratford.civicweb.net/Portal/",
    "STRATHROY-CARADOC M": "https://pub-strathroy-caradoc.escribemeetings.com/",
    "TAY TP": "https://tay.civicweb.net/Portal/",
    "TECUMSEH T": "https://pub-tecumseh.escribemeetings.com/",
    "TEMISKAMING SHORES C": "https://temiskamingshores.civicweb.net/Portal/",
    "THOROLD C": "https://pub-thorold.escribemeetings.com/",
    "THUNDER BAY C": "https://pub-thunderbay.escribemeetings.com/",
    "TILLSONBURG T": "https://pub-tillsonburg.escribemeetings.com/",
    "TIMMINS C": "https://timmins.civicweb.net/Portal/",
    "TORONTO C": "https://secure.toronto.ca/council/#/home",
    "VAUGHAN C": "https://pub-vaughan.escribemeetings.com/",
    "WAINFLEET TP": "https://pub-wainfleet.escribemeetings.com/",
    "WASAGA BEACH T": "https://pub-wasagabeach.escribemeetings.com/",
    "WATERLOO C": "https://pub-waterloo.escribemeetings.com/",
    "WELLAND C": "https://www.welland.ca/Council/CouncilMeetings.asp",
    "WELLESLEY TP": "https://calendar.wellesley.ca/council",
    "WELLINGTON NORTH TP": "https://pub-wellington-north.escribemeetings.com/",
    "WEST LINCOLN TP": "https://pub-westlincoln.escribemeetings.com/",
    "WHITBY T": "https://pub-whitby.escribemeetings.com/",
    "WHITCHURCH-STOUFFVILLE T": "https://pub-townofws.escribemeetings.com/",
    "WINDSOR C": "https://pub-citywindsor.escribemeetings.com/",
    "WOOLWICH TP": "https://woolwich.civicweb.net/Portal/"
}

def apply_fixes():
    print(f"--- Registry Repair Tool (Batch 5) ---")
    print(f"Targeting Registry at: {os.path.abspath(REGISTRY_PATH)}")
    
    if not os.path.exists(REGISTRY_PATH):
        print(f"ERROR: Could not find registry file.")
        return

    try:
        df = pd.read_csv(REGISTRY_PATH)
    except Exception as e:
        print(f"Error reading registry: {e}")
        return
    
    fixed_count = 0
    
    for munid, new_url in FIXES.items():
        clean_target = munid.split(" ")[0].upper()
        mask = df['munid'].astype(str).str.upper().str.contains(clean_target)
        
        # Prefer exact match
        exact_mask = df['munid'].astype(str).str.upper() == munid.upper()
        if exact_mask.any():
            mask = exact_mask

        if mask.any():
            df.loc[mask, 'minutes_listing_url'] = new_url
            df.loc[mask, 'example_recent_minutes_url'] = new_url
            fixed_count += 1
            print(f"Fixed: {munid}")
        else:
            print(f"WARNING: Could not find MUNID '{munid}'")

    if fixed_count > 0:
        df.to_csv(REGISTRY_PATH, index=False)
        print(f"\nSUCCESS: Updated {fixed_count} municipalities.")
    else:
        print("\nNo changes made.")

if __name__ == "__main__":
    apply_fixes()