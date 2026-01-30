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

# --- BATCH 4 FIXES (M-N + Batch 3 Corrections) ---
FIXES = {
    # --- CORRECTIONS FROM BATCH 3 FAILURES ---
    "HAVELOCK BELMONT METHUEN TP": "https://www.hbmtwp.ca/en/municipal-government/agendas-and-minutes.aspx",
    "HEAD CLARA AND MARIA TP": "https://townshipsofheadclaramaria.ca/council/minutes-agendas/", # Fixed typo in URL
    "LANARK HIGHLANDS TP": "https://www.lanarkhighlands.ca/en/municipal-government/agendas-minutes.aspx",
    "LEAMINGTON M": "https://www.leamington.ca/en/municipal-services/council-and-committee-meetings.aspx",
    "MAGNETAWAN M": "https://magnetawan.com/municipal-services/council/council-meetings",
    "MAPLETON TP": "https://www.mapleton.ca/en/township-services/council-calendar.aspx",
    "MARATHON T": "https://www.marathon.ca/en/town-hall/council-meetings.aspx",
    "MATTAWAN TP": "https://www.mattawantownship.ca/content/council-minutes",
    "MEAFORD M": "https://www.meaford.ca/en/municipal-government/council-and-committee-meetings.aspx",

    # --- NEW TARGETS (M - N) ---
    "MCDOUGALL M": "https://mcdougall.civicweb.net/Portal/",
    "MCGARRY TP": "https://www.mcgarry.ca/council/minutes-and-agendas",
    "MCKELLAR TP": "https://mckellar.civicweb.net/Portal/",
    "MCMURRICH MONTEITH TP": "https://mcmurrichmonteith.com/municipal-services/council/minutes-agendas",
    "MCNAB BRAESIDE TP": "https://mcnabbraeside.civicweb.net/Portal/",
    "MELANCTHON TP": "https://melancthontownship.ca/council/agendas-minutes/",
    "MERRICKVILLE-WOLFORD V": "https://merrickville-wolford.civicweb.net/Portal/",
    "MIDDLESEX CENTRE M": "https://pub-middlesexcentre.escribemeetings.com/",
    "MIDLAND T": "https://midland.civicweb.net/Portal/",
    "MILTON T": "https://pub-milton.escribemeetings.com/",
    "MINDEN HILLS TP": "https://mindenhills.civicweb.net/Portal/",
    "MINTO T": "https://town.minto.on.ca/town-hall/council/council-agenda-minutes",
    "MISSISSAUGA C": "https://pub-mississauga.escribemeetings.com/",
    "MISSISSIPPI MILLS T": "https://mississippimills.civicweb.net/Portal/",
    "MONO T": "https://mono.civicweb.net/Portal/",
    "MONTAGUE TP": "https://www.township.montague.on.ca/council/agendas-minutes",
    "MOONBEAM TP": "https://moonbeam.ca/council-meetings/",
    "MOOSONEE T": "https://moosonee.ca/town-hall/council-minutes/",
    "MORLEY TP": "https://townshipofmorley.ca/council/minutes/",
    "MORRIS-TURNBERRY M": "https://morristurnberry.ca/council/agendas-minutes/",
    "MULMUR TP": "https://mulmur.civicweb.net/Portal/",
    "MUSKOKA LAKES TP": "https://muskokalakes.civicweb.net/Portal/",
    "NAIRN AND HYMAN TP": "https://nairncentre.ca/council/minutes/",
    "NEEBING M": "https://www.neebing.org/en/town-hall/agendas-and-minutes.aspx",
    "NEWMARKET T": "https://pub-newmarket.escribemeetings.com/",
    "NIAGARA FALLS C": "https://niagarafalls.civicweb.net/Portal/",
    "NIAGARA-ON-THE-LAKE T": "https://niagaraonthelake.civicweb.net/Portal/",
    "NIPISSING TP": "https://nipissingtownship.com/council/minutes/",
    "NORFOLK COUNTY": "https://pub-norfolkcounty.escribemeetings.com/"
}

def apply_fixes():
    print(f"--- Registry Repair Tool (Batch 4) ---")
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
        # Clean matching (handles 'TP' vs 'T' mismatches)
        clean_target = munid.split(" ")[0].upper()
        mask = df['munid'].astype(str).str.upper().str.contains(clean_target)
        
        # Prefer exact match if available
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