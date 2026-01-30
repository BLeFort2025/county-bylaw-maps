# build_maps.py
# Rebuild Parquet layers for Streamlit lower/upper bylaw maps
#
# - TRUSTS mapping rows with accept=Y in name_map_lower.csv (score ignored; forced 100)
# - Joins CSV -> LOWER using mapping first; falls back to best auto field if no mapping
# - Aggregates LOWER -> UPPER (NO > YES > NOT KNOWN)
# - Uses fence existence from "Municipality Has Fence Bylaw"
# - Robust canon incl. NBSP & "CO/CO./CNTY" suffix
# - Fills upper rows with NOT KNOWN when no contributing lowers (so no "unmatched")
# - Prints unmatched lists for quick debugging
#
# One-time installs: pip install pandas geopandas pyarrow shapely fiona

import os, re, sys, unicodedata, warnings
import pandas as pd
import geopandas as gpd

warnings.filterwarnings("ignore", category=UserWarning)

# ---------- INPUTS ----------
BYLAW_CSV = r"C:\Users\ben.lefort\OneDrive - Ontario Federation of Agriculture\Desktop\Municipal Bylaw Database\Data Pulls\Reports\Province Wide\All bylaws\Updated Bylaw Exemption Files for Map\Final_Bylaw_Data__Grouped_Correctly_.csv"
LOWER_GEO = r"C:\Users\ben.lefort\OneDrive - Ontario Federation of Agriculture\Desktop\Municipal Bylaw Database\Data Pulls\Reports\Province Wide\All bylaws\Updated Bylaw Exemption Files for Map\Lower_Tier.geojson"
UPPER_GEO = r"C:\Users\ben.lefort\OneDrive - Ontario Federation of Agriculture\Desktop\Municipal Bylaw Database\Data Pulls\Reports\Province Wide\All bylaws\Updated Bylaw Exemption Files for Map\Upper_Tier.geojson"
NAME_MAP  = r"C:\OFA\bylaw_maps\name_map_lower.csv"

# ---------- OUTPUTS ----------
BUILD_DIR = r"C:\OFA\bylaw_maps\build"
UPPER_PARQUET = os.path.join(BUILD_DIR, "upper_single_map.parquet")
LOWER_PARQUET = os.path.join(BUILD_DIR, "lower_single_map.parquet")

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
    """Canonicalize names to maximize cross-source matches, incl. 'Co' suffixes."""
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
    # also trim abbreviated suffixes like CO / CO. / CNTY at the end
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

        # Fence rules: existence from flag, not bylaw name (case-insensitive detection)
        ("Farm Exemption for Security fencing prohibitions",  ["Farm Exemption for Security fencing prohibitions"], [], False),
        ("Farm Exemption for Electrified fencing prohibitions", ["Farm Exemption for Electrified fencing prohibitions"], [], False),
    ]

    for label, value_cols, name_cols, treat_text in rules:
        status_col = f"{label} Status"
        vcol = next((v for v in value_cols if v in df.columns), None)

        # Fence existence (case-insensitive match on 'fenc')
        if "fenc" in label.lower():
            fcol = "Municipality Has Fence Bylaw" if "Municipality Has Fence Bylaw" in df.columns else None
            exists = df[fcol].map(lambda x: status_val(x) == "YES") if fcol else pd.Series(False, index=df.index)
        else:
            ncol = next((n for n in name_cols if n in df.columns), None)
            exists = df[ncol].astype(str).str.strip().ne("") if ncol else pd.Series(False, index=df.index)
            if ncol is None:
                print(f"⚠️  No 'Bylaw Name' column found for '{label}'. Treating as no bylaw.")

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
    """Return the first non-empty string value from a Series (for links/names)."""
    for v in values:
        s = strip_nbsp_and_space(v)
        if s != "":
            return s
    return ""

def agg_min_date(values: pd.Series) -> str:
    """Parse a Series as dates and return the minimum date as YYYY-MM-DD (or blank)."""
    # values often come in as strings like '2026-12-31' (ISO)
    dt = pd.to_datetime(values, errors="coerce")
    if dt.notna().any():
        return dt.min().date().isoformat()
    return ""

# ---------- MAIN ----------
def main():
    print("Reading bylaw CSV…")
    df, used_enc = _read_csv(BYLAW_CSV)
    print(f"Loaded CSV with encoding: {used_enc}")
    print(f"Rows: {len(df):,} | Columns: {len(df.columns):,}")

    print("Computing status columns…")
    df, status_cols = compute_status_columns(df)

    # LOWER boundary
    g_low_ref = gpd.read_file(LOWER_GEO)
    candidates = [c for c in LOWER_NAME_FIELD_CANDIDATES if c in g_low_ref.columns]
    print("\nLOWER name field candidates overlap (diagnostic):")
    csv_names = set(df["_MUNI_NAME"].unique())
    best_col, best_hits = None, -1
    for c in candidates:
        vals = set(g_low_ref[c].astype(str).map(canon))
        hits = len(vals & csv_names)
        print(f"  {c:<15} -> {hits}")
        if hits > best_hits:
            best_col, best_hits = c, hits
    if best_col is None: die("No viable LOWER name fields found in boundary.")

    # TRUST mapping accept=Y (score ignored; force to 100)
    mapping = None
    if os.path.exists(NAME_MAP):
        m = pd.read_csv(NAME_MAP, dtype=str).fillna("")
        needed = {"csv_name_canon","csv_name_raw","suggested_lower_field","suggested_lower_raw","suggested_lower_canon","accept"}
        if not needed.issubset(m.columns):
            die(f"{NAME_MAP} missing required columns {needed}")
        mapping = m[m["accept"].str.upper().eq("Y")].copy()
        mapping["score"] = "100"
        mapping["csv_name_canon"]      = mapping["csv_name_canon"].map(canon)
        mapping["suggested_lower_raw"] = mapping["suggested_lower_raw"].map(strip_nbsp_and_space)
        mapping["lower_key"]           = mapping["suggested_lower_field"].str.strip() + "||" + mapping["suggested_lower_raw"].map(canon)
        print(f"\nUsing reviewed mapping rows (accept=Y): {len(mapping)}")
    else:
        print("\nNo mapping file found; using auto match only.")

    g_low = g_low_ref.copy()
    g_low["_AUTO_CANON"] = g_low[best_col].astype(str).map(canon)
    g_low["_AUTO_CANON"] = g_low["_AUTO_CANON"].str.replace("\u00A0"," ", regex=False).str.strip()

    if mapping is not None and len(mapping):
        map_fields = sorted(set(mapping["suggested_lower_field"]))
        def row_keys(row):
            keys = []
            for fld in map_fields:
                if fld in g_low.columns:
                    keys.append(f"{fld}||{canon(row.get(fld,''))}")
            return keys
        g_low["__keys__"] = g_low.apply(row_keys, axis=1)
        mm = dict(zip(mapping["lower_key"], mapping["csv_name_canon"]))
        def resolve(keys, auto_val):
            for k in keys:
                if k in mm:
                    return mm[k]
            return auto_val
        g_low["_MUNI_NAME"] = [resolve(k, a) for k, a in zip(g_low["__keys__"], g_low["_AUTO_CANON"])]
    else:
        g_low["_MUNI_NAME"] = g_low["_AUTO_CANON"]

    g_low["_MUNI_NAME"] = g_low["_MUNI_NAME"].str.replace("\u00A0"," ", regex=False).str.strip()

    # Join LOWER (left)
    lower = g_low.merge(df.drop_duplicates("_MUNI_NAME"), on="_MUNI_NAME", how="left")

    # Report unmatched LOWER
    miss_l = lower[[c for c in lower.columns if c.lower().endswith(" status")]].isna().all(axis=1)
    n_miss_l = int(miss_l.sum())
    print(f"\nLOWER unmatched polygons: {n_miss_l}")
    if n_miss_l:
        print("  Unmatched LOWER _MUNI_NAME examples:", lower.loc[miss_l, "_MUNI_NAME"].head(20).tolist())

    # Aggregate LOWER -> UPPER
    if LOWER_TO_UPPER_FIELD not in lower.columns:
        die(f"Lower boundary missing '{LOWER_TO_UPPER_FIELD}'")
    tmp = pd.DataFrame(lower.drop(columns=lower.geometry.name))
    tmp["_UPPER_NAME"] = tmp[LOWER_TO_UPPER_FIELD].astype(str).map(canon)
    tmp["_UPPER_NAME"] = tmp["_UPPER_NAME"].str.replace("\u00A0"," ", regex=False).str.strip()

    upper_agg = tmp.groupby("_UPPER_NAME", dropna=False)[status_cols].agg(agg_status).reset_index()

    # --- Roll up bylaw metadata to the upper-tier layer (so the upper map can show expiry/link info) ---
    # We keep this intentionally simple:
    #   - Dates (expiry/enacted) -> minimum date across member municipalities
    #   - Text fields (links/bylaw names) -> first non-empty value
    meta_cols = [
        c for c in tmp.columns
        if (
            str(c).lower().startswith("bylaw name")
            or " link" in str(c).lower()
            or str(c).lower().startswith("link")
            or "expiry" in str(c).lower()
            or "date bylaw enacted" in str(c).lower()
        )
        and c not in status_cols
        and c != "_UPPER_NAME"
    ]

    if meta_cols:
        meta_aggs = {}
        for c in meta_cols:
            lc = str(c).lower()
            if ("expiry" in lc) or ("date bylaw enacted" in lc):
                meta_aggs[c] = agg_min_date
            else:
                meta_aggs[c] = agg_first_non_empty

        upper_meta = tmp.groupby("_UPPER_NAME", dropna=False)[meta_cols].agg(meta_aggs).reset_index()
        upper_agg = upper_agg.merge(upper_meta, on="_UPPER_NAME", how="left")


    # Join UPPER polygons
    g_up = gpd.read_file(UPPER_GEO)
    if UPPER_NAME_FIELD not in g_up.columns:
        die(f"Upper boundary missing '{UPPER_NAME_FIELD}'")
    g_up["_UPPER_NAME"] = g_up[UPPER_NAME_FIELD].astype(str).map(canon)
    g_up["_UPPER_NAME"] = g_up["_UPPER_NAME"].str.replace("\u00A0"," ", regex=False).str.strip()

    upper = g_up.merge(upper_agg, on="_UPPER_NAME", how="left")

    # FILL any uppers with no contributing lowers as NOT KNOWN (so not "unmatched")
    for c in status_cols:
        if c in upper.columns:
            upper[c] = upper[c].fillna("NOT KNOWN")

    # Report unmatched UPPER (should now be 0)
    miss_u = upper[[c for c in upper.columns if c.lower().endswith(" status")]].isna().all(axis=1)
    n_miss_u = int(miss_u.sum())
    print(f"UPPER unmatched polygons: {n_miss_u}")
    if n_miss_u:
        print("  Unmatched UPPER _UPPER_NAME examples:", upper.loc[miss_u, "_UPPER_NAME"].head(20).tolist())

    # Write Parquet
    os.makedirs(BUILD_DIR, exist_ok=True)
    upper.to_parquet(UPPER_PARQUET, index=False)
    lower.to_parquet(LOWER_PARQUET, index=False)
    print(f"\n✅ Wrote {UPPER_PARQUET}  | features: {len(upper):,}")
    print(f"✅ Wrote {LOWER_PARQUET}  | features: {len(lower):,}")
    print("\nDone. Fence rules use the 'Municipality Has Fence Bylaw' flag; mapping rows with accept=Y are always applied.")

if __name__ == "__main__":
    main()
