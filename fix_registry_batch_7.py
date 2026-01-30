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

# --- BATCH 7: The Master Fix ---
FIXES = {
    # 1. THE ST. THOMAS BUG CLUSTER (Crucial Fix)
    "ADMASTON BROMLEY TP": "https://admastonbromley.com/council/minutes-agendas/",
    "AMHERSTBURG TP": "https://pub-amherstburg.escribemeetings.com/",
    "ARMSTRONG TP": "https://armstrong.civicweb.net/Portal/",
    "AUGUSTA TP": "https://augusta.civicweb.net/Portal/",
    "BRADFORD WEST GWILLIMBURY TP": "https://bradfordwestgwillimbury.civicweb.net/Portal/",
    "BROOKE ALVINSTON M": "https://brookealvinston.civicweb.net/Portal/",
    "CENTRE HASTINGS M": "https://centrehastings.civicweb.net/Portal/",
    "EAST FERRIS M": "https://eastferris.civicweb.net/Portal/",
    "EAST GARAFRAXA TP": "https://www.eastgarafraxa.ca/en/municipal-government/council-meetings.aspx",
    "EAST GWILLIMBURY TP": "https://eastgwillimbury.civicweb.net/Portal/",
    "EAST HAWKESBURY TP": "https://easthawkesbury.ca/council-meetings/",
    "EAST ZORRA TAVISTOCK TP": "https://pub-ezt.escribemeetings.com/",
    "FAUQUIER STRICKLAND TP": "https://www.fauquierstrickland.com/en/municipal-office/council-minutes.aspx",
    "GRAVENHURST T": "https://gravenhurst.civicweb.net/Portal/",
    "GREENSTONE M": "https://greenstone.civicweb.net/Portal/",

    # 2. STUBBORN ERRORS (Forbidden/403s fixed with better URLs)
    "BURK TMS FALLS TP": "https://www.burksfalls.net/townhall/council",
    "BURPEE AND MILLS TP": "https://www.burpeemills.com/",
    "CARLING TP": "https://carling.ca/municipal-information/info-about-carling-council/agenda-and-minutes/",
    "GUELPH/ERAMOSA TP": "https://www.get.on.ca/township-services/council/agendas-and-minutes",
    "HARRIS TP": "https://harristownship.weebly.com/minutes.html",
    
    # 3. MAJOR CITIES CLEANUP
    "TORONTO C": "https://secure.toronto.ca/council/#/home",
    "WINDSOR C": "https://pub-citywindsor.escribemeetings.com/"
}

def apply_fixes():
    print(f"--- Registry Repair Tool (Batch 7 - Master Fix) ---")
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
        # Robust matching
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