# build_maps_v2_rollup_metadata.py
# Rebuild Parquet layers for Streamlit lower/upper bylaw maps

import os, re, sys, unicodedata, warnings
import pandas as pd
import geopandas as gpd

warnings.filterwarnings("ignore", category=UserWarning)

# --- CONFIG: PORTABLE PATHS ---
# Uses files in the same directory as this script
HERE = os.path.dirname(os.path.abspath(__file__))

# INPUTS
BYLAW_CSV = os.path.join(HERE, "Final_Bylaw_Data__Grouped_Correctly_.csv")
LOWER_GEO = os.path.join(HERE, "Lower_Tier.geojson")
UPPER_GEO = os.path.join(HERE, "Upper_Tier.geojson")
NAME_MAP  = os.path.join(HERE, "name_map_lower.csv")

# OUTPUTS (Updated filenames to match your Streamlit App)
UPPER_PARQUET = os.path.join(HERE, "upper_single_map_beta.parquet") 
LOWER_PARQUET = os.path.join(HERE, "lower_single_map_beta.parquet")

# ---------- FIELD CONSTANTS ----------
DATA_MUNI_CANDIDATES = ["Municipality","Municipality Name","Municipality_Name","MUNICIPALITY","Name"]
LOWER_TO_UPPER_FIELD = "UPPER_TI_1"
UPPER_NAME_FIELD     = "OFFICIAL_M"

LOWER_NAME_FIELD_CANDIDATES = [
    "MUNICIPA_8","MUNICIPA_2","MUNICIPA_9","OFFICIAL_M","EN_NAME","NAME",
    "CSDNAME","MUNICIPAL_","MUNICIPAL_N","MUNICIPAAL_N",
]

# ---------- CANON + HELPERS ----------
def die(msg: str):
    print("ERROR:", msg); sys.exit(1)

def strip_nbsp_and_space(s: str) -> str:
    return ("" if s is None else str(s).replace("\u00A0"," ").strip())

def canon(x: str) -> str:
    s = strip_nbsp_and_space(x)
    s = unicodedata.normalize("NFKC", s).upper()
    s = s.replace("&", " AND ").replace("-", " ")
    s = re.sub(r"[’'`]", "", s)
    s = re.sub(r"[^A-Z0-9 /]", " ", s)
    s = s.replace("/", " ")
    s = re.sub(r"\s+", " ", s).strip()
    for p in ["CITY OF ","TOWN OF ","TOWNSHIP OF ","VILLAGE OF ",
              "MUNICIPALITY OF ","REGIONAL MUNICIPALITY OF ",
              "REGION OF ","COUNTY OF ","DISTRICT OF "]:
        if s.startswith(p):
            s = s[len(p):].strip()
            break
    for suf in [" COUNTY"," REGION"," CITY"," TOWN"," TOWNSHIP"," VILLAGE"," MUNICIPALITY"," DISTRICT"]:
        if s.endswith(suf):
            s = s[:-len(suf)].strip()
            break
    s = re.sub(r"\b(CO\.?|CNTY)\b$", "", s).strip()
    return re.sub(r"\s+"," ", s).strip()

YES_SET     = {"YES","Y","TRUE","T","1","ALLOW","ALLOWED","PERMITTED","PERMIT","EXEMPT","EXEMPTION","EXCEPTION","PRESENT","EXISTS"}
NO_SET      = {"NO","N","FALSE","F","0","NOT ALLOWED","PROHIBITED","NONE","ABSENT"}
UNKNOWN_SET = {"UNKNOWN","NOT KNOWN","N/A","NA","NOT APPLICABLE","UNSURE","TBD","", "-", "NULL", "NONE (UNKNOWN)"}

def status_val(v, treat_text_as_yes=False) -> str:
    s = strip_nbsp_and_space(v).upper()
    if s in YES_SET: return "YES"
    if s in NO_SET:  return "NO"
    if s in UNKNOWN_SET: return "NOT KNOWN"
    return "YES" if (treat_text_as_yes and s != "") else "NOT KNOWN"

def _read_csv(path: str) -> tuple[pd.DataFrame, str]:
    if not os.path.exists(path):
        die(f"File not found: {path}")
    for enc in ("utf-8","utf-8-sig","cp1252","latin1"):
        try:
            return pd.read_csv(path, dtype=str, encoding=enc, sep=None, engine="python").fillna(""), enc
        except Exception:
            pass
    die("Could not read CSV with utf-8/utf-8-sig/cp1252/latin1")

# ---------- STATUS COLUMNS ----------
def compute_status_columns(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    created = []
    muni = next((c for c in DATA_MUNI_CANDIDATES if c in df.columns), None)
    if not muni: die(f"Municipality column not found; tried {DATA_MUNI_CANDIDATES}")
    df["_MUNI_NAME"] = df[muni].map(canon)
    df["_MUNI_NAME"] = df["_MUNI_NAME"].str.replace("\u00A0"," ", regex=False).str.strip()

    rules = [
        ("Farm Exemption for Development Charges", ["Farm Exemption for Development Charges"], ["Bylaw Name Development Charges"], False),
        ("Farm Exemption for Stormwater Charges",  ["Farm Exemption for Stormwater Charges"],  ["Bylaw Name Stormwater","Bylaw Name Storm Water"], False),
        ("Farm Exemption for SA",                  ["Farm Exemption for SA"],                  ["Bylaw Name Sute Alteration","Bylaw Name Site Alteration","Bylaw Name Site Alternation"], False),
        ("Has Livestock Guardian dog Definition",  ["Has Livestock Guardian dog Definition"],   ["Bylaw Name LGD","Bylaw Name LDG"], False),
        ("LDG - Definition",                       ["LDG - Definition"],                        ["Bylaw Name LGD","Bylaw Name LDG"], True),
        ("Herding Dog Definition Exists",          ["Herding Dog Definition Exists"],           ["Bylaw Name LGD","Bylaw Name LDG"], False),
        ("LDG and HD exempt from license fees",    ["LDG and HD exempt from license fees"],     ["Bylaw Name LGD","Bylaw Name LDG"], False),
        ("LDG and HD Collar and tag requirements", ["LDG and HD Collar and tag requirements"],  ["Bylaw Name LGD","Bylaw Name LDG"], False),
        ("LDG and HD Exempt from barking restrictions", ["LDG and HD Exempt from barking restrictions"], ["Bylaw Name LGD","Bylaw Name LDG"], False),
        ("Can you Keep Backyard Chickens",         ["Can you Keep Backyard Chickens"],          ["Bylaw Name Backyard Chicken","Bylaw Name Backyard Chickens"], False),
        ("Licence Required",                       ["Licence Required"],                        ["Bylaw Name Backyard Chicken","Bylaw Name Backyard Chickens"], False),
        ("Welfare Requirements",                   ["Welfare Requirements"],                    ["Bylaw Name Backyard Chicken","Bylaw Name Backyard Chickens"], False),
        ("Farm Exemption - Tree Cutting Bylaw",    ["Farm Exemption - Tree Cutting Bylaw"],     ["Bylaw Name Forest Conservation","Bylaw Name Tree Cutting","Bylaw Name Forestry","Tree Conservation Bylaw Name"], False),
        ("Farm Exemption for Security fencing prohibitions",  ["Farm Exemption for Security fencing prohibitions"], [], False),
        ("Farm Exemption for Electrified fencing prohibitions", ["Farm Exemption for Electrified fencing prohibitions"], [], False),
    ]

    for label, value_cols, name_cols, treat_text in rules:
        status_col = f"{label} Status"
        vcol = next((v for v in value_cols if v in df.columns), None)
        if "fenc" in label.lower():
            fcol = "Municipality Has Fence Bylaw" if "Municipality Has Fence Bylaw" in df.columns else None
            exists = df[fcol].map(lambda x: status_val(x) == "YES") if fcol else pd.Series(False, index=df.index)
        else:
            ncol = next((n for n in name_cols if n in df.columns), None)
            exists = df[ncol].astype(str).str.strip().ne("") if ncol else pd.Series(False, index=df.index)
        
        if vcol is None:
            df[status_col] = "NOT KNOWN"
        else:
            st = pd.Series("NOT KNOWN", index=df.index)
            m = exists.fillna(False)
            st.loc[m] = df.loc[m, vcol].map(lambda x: status_val(x, treat_text_as_yes=treat_text))
            df[status_col] = st
        created.append(status_col)
    return df, created

def agg_status(values: pd.Series) -> str:
    vals = set(v if isinstance(v, str) else str(v) for v in values)
    if "NO" in vals:  return "NO"
    if "YES" in vals: return "YES"
    return "NOT KNOWN"

def agg_first_non_empty(values: pd.Series) -> str:
    for v in values:
        s = strip_nbsp_and_space(v)
        if s != "": return s
    return ""

def agg_min_date(values: pd.Series) -> str:
    dt = pd.to_datetime(values, errors="coerce")
    if dt.notna().any():
        return dt.min().date().isoformat()
    return ""

# ---------- MAIN ----------
def main():
    print(f"Working Directory: {HERE}")
    
    # 1. READ CSV
    print("Reading bylaw CSV...")
    df, used_enc = _read_csv(BYLAW_CSV)
    print(f"Loaded CSV with encoding: {used_enc}")
    
    print("Computing status columns...")
    df, status_cols = compute_status_columns(df)

    # 2. READ LOWER GEOJSON
    if not os.path.exists(LOWER_GEO):
        die(f"Lower GeoJSON not found at: {LOWER_GEO}. Please move 'Lower_Tier.geojson' to the root folder.")
    g_low_ref = gpd.read_file(LOWER_GEO)
    
    candidates = [c for c in LOWER_NAME_FIELD_CANDIDATES if c in g_low_ref.columns]
    best_col, best_hits = None, -1
    csv_names = set(df["_MUNI_NAME"].unique())
    for c in candidates:
        vals = set(g_low_ref[c].astype(str).map(canon))
        hits = len(vals & csv_names)
        if hits > best_hits: best_col, best_hits = c, hits
    if best_col is None: die("No viable LOWER name fields found in boundary.")

    # 3. READ NAME MAP (Optional)
    mapping = None
    if os.path.exists(NAME_MAP):
        m = pd.read_csv(NAME_MAP, dtype=str).fillna("")
        mapping = m[m["accept"].str.upper().eq("Y")].copy()
        mapping["lower_key"] = mapping["suggested_lower_field"].str.strip() + "||" + mapping["suggested_lower_raw"].map(strip_nbsp_and_space).map(canon)
    
    g_low = g_low_ref.copy()
    g_low["_AUTO_CANON"] = g_low[best_col].astype(str).map(canon)

    if mapping is not None and len(mapping):
        mm = dict(zip(mapping["lower_key"], mapping["csv_name_canon"].map(canon)))
        def resolve(row):
            for fld in sorted(set(mapping["suggested_lower_field"])):
                if fld in row:
                    k = f"{fld}||{canon(row[fld])}"
                    if k in mm: return mm[k]
            return row["_AUTO_CANON"]
        g_low["_MUNI_NAME"] = g_low.apply(resolve, axis=1)
    else:
        g_low["_MUNI_NAME"] = g_low["_AUTO_CANON"]

    lower = g_low.merge(df.drop_duplicates("_MUNI_NAME"), on="_MUNI_NAME", how="left")

    # 4. READ UPPER GEOJSON & AGGREGATE
    if not os.path.exists(UPPER_GEO):
         die(f"Upper GeoJSON not found at: {UPPER_GEO}. Please move 'Upper_Tier.geojson' to the root folder.")
    
    tmp = pd.DataFrame(lower.drop(columns=lower.geometry.name))
    if LOWER_TO_UPPER_FIELD in tmp.columns:
        tmp["_UPPER_NAME"] = tmp[LOWER_TO_UPPER_FIELD].astype(str).map(canon)
        upper_agg = tmp.groupby("_UPPER_NAME", dropna=False)[status_cols].agg(agg_status).reset_index()
        g_up = gpd.read_file(UPPER_GEO)
        g_up["_UPPER_NAME"] = g_up[UPPER_NAME_FIELD].astype(str).map(canon)
        upper = g_up.merge(upper_agg, on="_UPPER_NAME", how="left")
        for c in status_cols:
            if c in upper.columns: upper[c] = upper[c].fillna("NOT KNOWN")
        upper.to_parquet(UPPER_PARQUET, index=False)
        print(f"✅ Wrote {UPPER_PARQUET}")

    lower.to_parquet(LOWER_PARQUET, index=False)
    print(f"✅ Wrote {LOWER_PARQUET}")

if __name__ == "__main__":
    main()