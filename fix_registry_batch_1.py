import pandas as pd
import os

# --- CONFIG ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REGISTRY_PATH = os.path.join(SCRIPT_DIR, "signals", "portal_registry.csv")

# --- BATCH 1 FIXES ---
FIXES = {
    "BONNECHERE VALLEY TP": "https://www.bonnecherevalleytwp.com/council-and-staff/council-minutes/",
    "BURK TMS FALLS TP": "https://www.burksfalls.net/townhall/council/agenda-minutes", 
    "BURPEE AND MILLS TP": "https://www.burpeemills.com/municipality/2024-council-meetings/",
    "CARLING TP": "https://carling.ca/municipal-information/info-about-carling-council/agenda-and-minutes/",
    "EAST ZORRA TAVISTOCK TP": "https://pub-ezt.escribemeetings.com/",
    "ELLIOT LAKE C": "https://www.elliotlake.ca/en/city-hall/agendas-and-minutes.aspx",
    "ESSEX TP": "https://townofessex-pub.escribemeetings.com/meetingscalendarview.aspx?Expanded=Regular+Council+Meeting",
    "GEORGIAN BLUFFS TP": "https://pub-georgianbluffs.escribemeetings.com/",
    "GEORGINA T": "https://www.georgina.ca/municipal-government/council-meetings/agendas-minutes-and-meetings",
    "GILLIES TP": "https://www.gilliestownship.com/en/our-government/agendas-and-minutes.aspx",
    "GORE BAY T": "https://gorebay.civicweb.net/Portal/",
    "GRAND VALLEY T": "https://pub-townofgrandvalley.escribemeetings.com/",
    "GREATER SUDBURY C": "https://pub-greatersudbury.escribemeetings.com/",
    "GRIMSBY T": "https://www.grimsby.ca/town-hall/agendas-and-minutes/",
    "GUELPH C": "https://guelph.ca/city-hall/mayor-and-council/city-council/agendas-and-minutes/council-meetings/",
    "GUELPH/ERAMOSA TP": "https://www.get.on.ca/township-services/council/agendas-and-minutes",
    "HALDIMAND COUNTY": "https://pub-haldimandcounty.escribemeetings.com/",
    "HALTON HILLS T": "https://pub-haltonhills.escribemeetings.com/",
    "HAMILTON TP": "https://www.hamiltontownship.ca/your-municipal-government/agendas-minutes-and-meetings/",
    "HANOVER T": "https://pub-hanover.escribemeetings.com/"
}

def apply_fixes():
    print("--- Registry Repair Tool (Batch 1) ---")
    
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