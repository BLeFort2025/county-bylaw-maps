import pandas as pd
import os

# --- CONFIG ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REGISTRY_PATH = os.path.join(SCRIPT_DIR, "signals", "portal_registry.csv")

# --- THE FINAL 10 FIXES ---
FIXES = {
    "MARKSTAY WARREN M": "https://markstay-warren.civicweb.net/Portal/",
    "NORTHEASTERN MANITOULIN AND THE ISLANDS TP": "https://nemi.civicweb.net/Portal/",
    "PERTH EAST TP": "https://pertheast.civicweb.net/Portal/",
    "QUINTE WEST C": "https://quintewest.civicweb.net/Portal/",
    "SAULT STE. MARIE C": "https://saultstemarie.ca/City-Hall/City-Council/Agenda-and-Minutes.aspx",
    "SOUTH-WEST OXFORD TP": "https://www.swox.org/en/township-services/council-meetings.aspx",
    "ST. CLAIR TP": "https://stclair.civicweb.net/Portal/",
    "STRATFORD C": "https://stratford.civicweb.net/Portal/",
    "THESSALON T": "https://thessalon.ca/council/minutes-agendas/",
    "WEST GREY M": "https://westgrey.civicweb.net/Portal/"
}

def apply_fixes():
    print(f"--- Registry Repair Tool (Final Polish) ---")
    
    if not os.path.exists(REGISTRY_PATH):
        print(f"ERROR: Could not find registry at {REGISTRY_PATH}")
        return

    try:
        df = pd.read_csv(REGISTRY_PATH)
    except Exception as e:
        print(f"Error reading registry: {e}")
        return
    
    fixed_count = 0
    
    for munid, new_url in FIXES.items():
        # Clean fuzzy matching
        clean_target = munid.split(" ")[0].upper()
        mask = df['munid'].astype(str).str.upper().str.contains(clean_target)
        
        if mask.any():
            df.loc[mask, 'minutes_listing_url'] = new_url
            df.loc[mask, 'example_recent_minutes_url'] = new_url
            fixed_count += 1
            print(f"Fixed: {munid}")

    if fixed_count > 0:
        df.to_csv(REGISTRY_PATH, index=False)
        print(f"\nSUCCESS: Updated {fixed_count} municipalities.")
    else:
        print("\nNo changes made.")

if __name__ == "__main__":
    apply_fixes()