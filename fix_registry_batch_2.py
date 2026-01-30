import pandas as pd
import os

# --- CONFIG ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REGISTRY_PATH = os.path.join(SCRIPT_DIR, "signals", "portal_registry.csv")

# --- BATCH 2 FIXES (Corrected Portals) ---
FIXES = {
    "GUELPH C": "https://guelph.ca/city-hall/mayor-and-council/city-council/agendas-and-minutes/",
    "GUELPH/ERAMOSA TP": "https://www.get.on.ca/township-services/council/agendas-and-minutes",
    "HARRIS TP": "https://harristownship.weebly.com/minutes.html",
    "HAVELOCK BELMONT METHUEN TP": "https://havelockbelmontmethuen.civicweb.net/Portal/",
    "HEAD CLARA AND MARIA TP": "https://townshipsofheadclariamaria.ca/council/minutes-agendas/",
    "KAWARTHA LAKES C": "https://pub-kawarthalakes.escribemeetings.com/",
    "KEARNEY TP": "https://townofkearney.ca/council/council-meetings/",
    "KENORA C": "https://pub-kenora.escribemeetings.com/",
    "KERNS TP": "https://kerns.ca/municipal-office/council/minutes-agendas/",
    "KILLALOE HAGARTY AND RICHARDS TP": "https://www.killaloe-hagarty-richards.ca/council/minutes-agendas",
    "KILLARNEY M": "https://www.municipalityofkillarney.ca/council/agendas-minutes",
    "KINCARDINE M": "https://pub-kincardine.escribemeetings.com/",
    "KING TP": "https://pub-king.escribemeetings.com/",
    "KINGSTON C": "https://pub-cityofkingston.escribemeetings.com/",
    "KITCHENER C": "https://pub-kitchener.escribemeetings.com/",
    "LA VALLEE TP": "https://lavallee.ca/government/council-minutes/",
    "LAIRD TP": "https://lairdtownship.ca/council/minutes/",
    "LAKE OF BAYS TP": "https://lakeofbays.civicweb.net/Portal/",
    "LAKE OF THE WOODS TP": "https://www.lakeofthewoods.ca/council/minutes",
    "LAKESHORE M": "https://pub-lakeshore.escribemeetings.com/",
    "LAMBTON SHORES M": "https://pub-lambtonshores.escribemeetings.com/"
}

def apply_fixes():
    print("--- Registry Repair Tool (Batch 2) ---")
    
    if not os.path.exists(REGISTRY_PATH):
        print(f"ERROR: Could not find registry at {REGISTRY_PATH}")
        return

    try:
        df = pd.read_csv(REGISTRY_PATH)
        print(f"Loaded registry: {len(df)} rows.")
    except Exception as e:
        print(f"Error reading registry: {e}")
        return
    
    fixed_count = 0
    
    for munid, new_url in FIXES.items():
        mask = df['munid'].astype(str).str.upper() == munid.upper()
        
        if mask.any():
            df.loc[mask, 'minutes_listing_url'] = new_url
            df.loc[mask, 'example_recent_minutes_url'] = new_url
            fixed_count += 1
            print(f"Fixed: {munid}")
        else:
            print(f"WARNING: Could not find MUNID '{munid}' in registry.")

    if fixed_count > 0:
        df.to_csv(REGISTRY_PATH, index=False)
        print(f"SUCCESS: Updated {fixed_count} municipalities.")
    else:
        print("No changes made.")

if __name__ == "__main__":
    apply_fixes()