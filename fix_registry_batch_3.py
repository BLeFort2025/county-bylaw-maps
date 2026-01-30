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

# --- BATCH 3 FIXES (30 Targets + Guelph Retry) ---
FIXES = {
    # Retry from Batch 2
    "GUELPH C": "https://pub-guelph.escribemeetings.com/", 
    
    # New Targets
    "LANARK HIGHLANDS TP": "https://lanarkhighlands.civicweb.net/Portal/",
    "LARDER LAKE TP": "https://larderlake.ca/government/mayor-and-council/minutes-and-agendas/",
    "LATCHFORD T": "https://latchford.ca/municipal-office/council/minutes-and-agendas/",
    "LAURENTIAN HILLS TP": "https://laurentianhills.civicweb.net/Portal/",
    "LAURENTIAN VALLEY TP": "https://laurentianvalley.civicweb.net/Portal/",
    "LEAMINGTON M": "https://townofleamington-pub.escribemeetings.com/",
    "LEEDS AND THE THOUSAND ISLANDS TP": "https://pub-leeds1000islands.escribemeetings.com/",
    "LIMERICK TP": "https://townshipoflimerick.ca/council/minutes-agendas/",
    "LINCOLN T": "https://lincoln.civicweb.net/Portal/",
    "LONDON C": "https://pub-london.escribemeetings.com/",
    "LOYALIST TP": "https://loyalist.civicweb.net/Portal/",
    "LUCAN BIDDULPH TP": "https://pub-lucanbiddulph.escribemeetings.com/",
    "MACHIN M": "https://visitmachin.com/council/minutes/",
    "MADOC TP": "https://madoc.ca/council/council-meetings/",
    "MAGNETAWAN M": "https://magnetawan.civicweb.net/Portal/",
    "MALAHIDE TP": "https://calendar.malahide.ca/council",
    "MANITOUWADGE TP": "https://manitouwadge.civicweb.net/Portal/",
    "MAPLETON TP": "https://pub-mapleton.escribemeetings.com/",
    "MARATHON T": "https://marathon.civicweb.net/Portal/",
    "MARKSTAY-WARREN M": "https://markstay-warren.civicweb.net/Portal/",
    "MARMORA AND LAKE M": "https://marmoraandlake.civicweb.net/Portal/",
    "MASSEY T": "https://townshipofsablesspanishrivers.ca/council/agendas-minutes/", # Massey is part of Sables-Spanish Rivers
    "MATTAWA T": "https://mattawa.ca/town-hall/council/agendas-minutes/",
    "MATTAWAN TP": "https://www.mattawantownship.ca/content/council-minutes",
    "MCDOUGALL M": "https://pub-mcdougall.escribemeetings.com/",
    "MCGARRY TP": "https://www.mcgarry.ca/council/minutes-and-agendas",
    "MCKELLAR TP": "https://mckellar.civicweb.net/Portal/",
    "MCMURRICH MONTEITH TP": "https://mcmurrichmonteith.com/municipal-services/council/minutes-agendas",
    "MCNAB BRAESIDE TP": "https://mcnabbraeside.civicweb.net/Portal/",
    "MEAFORD M": "https://pub-meaford.escribemeetings.com/"
}

def apply_fixes():
    print(f"--- Registry Repair Tool (Batch 3) ---")
    print(f"Targeting Registry at: {os.path.abspath(REGISTRY_PATH)}")
    
    if not os.path.exists(REGISTRY_PATH):
        print(f"ERROR: Could not find registry file.")
        return

    try:
        df = pd.read_csv(REGISTRY_PATH)
        print(f"Loaded registry: {len(df)} rows.")
    except Exception as e:
        print(f"Error reading registry: {e}")
        return
    
    fixed_count = 0
    
    for munid, new_url in FIXES.items():
        # Fuzzy match attempt: exact, or match start
        # Use simple exact or contains logic for safety
        mask = df['munid'].astype(str).str.upper().str.contains(munid.split(" ")[0].upper())
        # Refine: Exact Match Preferred
        exact_mask = df['munid'].astype(str).str.upper() == munid.upper()
        
        if exact_mask.any():
            final_mask = exact_mask
        else:
            # Fallback for mismatches like "Lincoln TP" vs "Lincoln T"
            final_mask = mask
            
        if final_mask.any():
            df.loc[final_mask, 'minutes_listing_url'] = new_url
            df.loc[final_mask, 'example_recent_minutes_url'] = new_url
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