# build_maps_v2_rollup_metadata.py
# Rebuild Parquet layers for Streamlit lower/upper bylaw maps

import os, re, sys, unicodedata, warnings
import pandas as pd
import geopandas as gpd

warnings.filterwarnings("ignore", category=UserWarning)

# --- CONFIG: PORTABLE PATHS ---
# Uses files in the same directory as this script
HERE = os.path.dirname(os.path.abspath(__file__))

# INPUTS — prefer SQLite database, fallback to CSV
BYLAW_CSV = os.path.join(HERE, "Final_Bylaw_Data__Grouped_Correctly_.csv")
BYLAW_DB  = os.path.join(HERE, "bylaws.db")
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
              "DISTRICT MUNICIPALITY OF ","UNITED COUNTIES OF ",
              "REGION OF ","COUNTY OF ","DISTRICT OF "]:
        if s.startswith(p):
            s = s[len(p):].strip()
            break
    for suf in [" COUNTY"," REGION"," CITY"," TOWN"," TOWNSHIP"," VILLAGE"," MUNICIPALITY"," DISTRICT"]:
        if s.endswith(suf):
            s = s[:-len(suf)].strip()
            break
    s = re.sub(r"\b(CO\.?|CNTY|R)\b$", "", s).strip()
    s = re.sub(r"\b(CO\.?|CNTY|R)\b$", "", s).strip()
    s = re.sub(r"\s+"," ", s).strip()
    aliases = {
        "ESSEX T": "ESSEX",
        "PERTH T": "PERTH",
        "PETERBOROUGH C": "PETERBOROUGH",
        "RENFREW T": "RENFREW",
        "WATERLOO C": "WATERLOO",
        "CHARLTON DACK": "CHARLTON AND DACK",
        "MATTICE VAL C T": "MATTICE VAL COTE",
        "THE SOUTH BRUCE PENINSULA": "SOUTH BRUCE PENINSULA",
        "MACDONALD MEREDITH ET AL": "MACDONALD MEREDITH AND ABERDEEN ADDITIONAL",
        "NORTHEASTERN MANITOULIN AND THE ISL": "NORTHEASTERN MANITOULIN AND THE ISLANDS",
        "DAWN": "ADDINGTON HIGHLANDS",
    }
    return aliases.get(s, s)

YES_SET     = {"YES","Y","TRUE","T","1","ALLOW","ALLOWED","PERMITTED","PERMIT","EXEMPT","EXEMPTION","EXCEPTION","PRESENT","EXISTS"}
NO_SET      = {"NO","N","FALSE","F","0","2","NOT ALLOWED","PROHIBITED","ABSENT"}
OTHER_SET   = {"OTHER","3","PARTIAL","CONDITIONAL"}
NO_BYLAW    = {"4"}   # Access code: municipality has no bylaw at all
UNKNOWN_SET = {"UNKNOWN","NOT KNOWN","N/A","NA","NOT APPLICABLE","UNSURE","TBD","", "-", "NULL", "NONE", "NONE (UNKNOWN)", "5"}

def status_val(v, treat_text_as_yes=False) -> str:
    s = strip_nbsp_and_space(v).upper()
    if s in YES_SET: return "YES"
    if s in NO_SET:  return "NO"
    if s in OTHER_SET: return "YES"  # Partial/conditional still means some form of exemption exists
    if s in NO_BYLAW: return "N/A"   # No bylaw → not applicable
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
        ("LGD/HD Working Dog Definition",          ["Has Livestock Guardian dog Definition", "Herding Dog Definition Exists"], ["Bylaw Name LGD"], False),
        ("LGD and HD Exempt from License Fees",    ["LDG and HD exempt from license fees"],     ["Bylaw Name LGD"], False),
        ("LGD and HD Collar and Tag Requirements", ["LDG and HD Collar and tag requirements"],  ["Bylaw Name LGD"], False),
        ("LGD and HD Exempt from Barking Restrictions", ["LDG and HD Exempt from barking restrictions"], ["Bylaw Name LGD"], False),
        ("Can you Keep Backyard Chickens",         ["Can you Keep Backyard Chickens"],          ["Bylaw Name Backyard Chicken","Bylaw Name Backyard Chickens"], False),
        ("Licence Required",                       ["Licence Required"],                        ["Bylaw Name Backyard Chicken","Bylaw Name Backyard Chickens"], False),
        ("Welfare Requirements",                   ["Welfare Requirements"],                    ["Bylaw Name Backyard Chicken","Bylaw Name Backyard Chickens"], True),
        ("Farm Exemption - Tree Cutting Bylaw",    ["Farm Exemption - Tree Cutting Bylaw"],     ["Bylaw Name Forest Conservation","Bylaw Name Tree Cutting","Bylaw Name Forestry","Tree Conservation Bylaw Name"], False),
        ("Farm Exemption for Security fencing prohibitions",  ["Farm Exemption for Security fencing prohibitions"], [], False),
        ("Farm Exemption for Electrified fencing prohibitions", ["Farm Exemption for Electrified fencing prohibitions"], [], False),
    ]

    for label, value_cols, name_cols, treat_text in rules:
        status_col = f"{label} Status"
        # Find which value columns exist in the DataFrame
        available_vcols = [v for v in value_cols if v in df.columns]
        if "fenc" in label.lower():
            fcol = "Municipality Has Fence Bylaw" if "Municipality Has Fence Bylaw" in df.columns else None
            exists = df[fcol].map(lambda x: status_val(x) == "YES") if fcol else pd.Series(False, index=df.index)
        else:
            ncol = next((n for n in name_cols if n in df.columns), None)
            exists = df[ncol].astype(str).str.strip().ne("") if ncol else pd.Series(False, index=df.index)
        
        if not available_vcols:
            df[status_col] = "NOT KNOWN"
        elif len(available_vcols) == 1:
            # Standard single-column logic
            st = pd.Series("NOT KNOWN", index=df.index)
            m = exists.fillna(False)
            st.loc[m] = df.loc[m, available_vcols[0]].map(lambda x: status_val(x, treat_text_as_yes=treat_text))
            df[status_col] = st
        else:
            # Multi-column OR: YES if ANY column is YES (for combined LGD/HD definition)
            st = pd.Series("NOT KNOWN", index=df.index)
            m = exists.fillna(False)
            for vc in available_vcols:
                col_status = df.loc[m, vc].map(lambda x: status_val(x, treat_text_as_yes=treat_text))
                # OR logic: upgrade to YES if any column says YES
                st.loc[m] = st.loc[m].where(st.loc[m].eq("YES"), col_status)
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

# Metadata columns to carry into Upper Tier Parquet
META_TEXT_COLS = [
    "Bylaw Name Development Charges", "Link to DC Bylaw", "Date Bylaw Enacted (Regional)",
    "Bylaw Name Stormwater", "Link to Storm Water bylaw", "Date Bylaw Enacted2 (Regional)",
    "Bylaw Name Site Alteration", "Link to site alteration & fill bylaw", "Date Bylaw Enacted4 (Regional)",
    "Bylaw Name LGD", "Livestock Guardian Dog bylaw link", "Date Bylaw Enacted 5 (Regional)",
    "Bylaw Name Forest Conservation", "Tree Cutting Bylaw Link", "Date Bylaw Enacted 6 (Regional)",
    "Bylaw Name Backyard Chicken", "Backyard Chicken Bylaw Link", "Date Bylaw Enacted 7 (Regional)",
    "Bylaw Name Fence", "Link to Fence Bylaw", "Date Bylaw Enacted 8",
]

META_EXPIRY_COLS = [
    "Expiry Date", "Expiry date2", "Expiry date 4", "Expiry Date 5",
    "Expiry Date 6", "Expiry Date 7", "Expiry Date 8",
]

def _load_live_df(conn=None):
    """Fetch the live database wide dataframe and compute status columns."""
    from db_utils import get_connection, export_map_dataframe
    close_after = False
    if conn is None:
        try:
            conn = get_connection()
        except Exception:
            conn = get_connection(BYLAW_DB)
        close_after = True
    try:
        df = export_map_dataframe(conn)
    finally:
        if close_after and conn is not None:
            try:
                conn.close()
            except Exception:
                pass
    df = df.astype(str).replace({"None": "", "nan": ""})
    return compute_status_columns(df)


def overlay_live_lower(gdf: gpd.GeoDataFrame, conn=None) -> gpd.GeoDataFrame:
    """Overlay live database status and metadata columns onto a cached Lower Tier GeoDataFrame."""
    df, status_cols = _load_live_df(conn)
    df_lower = df[df["Municipal Status"] != "Upper Tier"] if "Municipal Status" in df.columns else df
    df_dedup = df_lower.drop_duplicates("_MUNI_NAME").set_index("_MUNI_NAME")

    if "_MUNI_NAME" not in gdf.columns:
        name_col = next((c for c in ["Municipality", "MUNICIPA_8", "OFFICIAL_M", "NAME"] if c in gdf.columns), gdf.columns[0])
        gdf = gdf.copy()
        gdf["_MUNI_NAME"] = gdf[name_col].astype(str).map(canon)
    else:
        gdf = gdf.copy()

    overlay_cols = [c for c in (status_cols + META_TEXT_COLS + META_EXPIRY_COLS + ["Municipality Has Fence Bylaw"]) if c in df_dedup.columns]
    for col in overlay_cols:
        gdf[col] = gdf["_MUNI_NAME"].map(df_dedup[col])
    return gdf


def overlay_live_upper(upper_gdf: gpd.GeoDataFrame, lower_parquet_path: str = LOWER_PARQUET, conn=None) -> gpd.GeoDataFrame:
    """Overlay live database rollup status and metadata columns onto a cached Upper Tier GeoDataFrame."""
    df, status_cols = _load_live_df(conn)
    df_lower = df[df["Municipal Status"] != "Upper Tier"] if "Municipal Status" in df.columns else df
    df_dedup = df_lower.drop_duplicates("_MUNI_NAME")

    low_keys = pd.read_parquet(lower_parquet_path, columns=["_MUNI_NAME", LOWER_TO_UPPER_FIELD])
    tmp = low_keys.merge(df_dedup, on="_MUNI_NAME", how="left")
    tmp["_UPPER_NAME"] = tmp[LOWER_TO_UPPER_FIELD].astype(str).map(canon)

    agg_dict = {c: agg_status for c in status_cols if c in tmp.columns}
    for c in META_TEXT_COLS:
        if c in tmp.columns:
            agg_dict[c] = agg_first_non_empty
    for c in META_EXPIRY_COLS:
        if c in tmp.columns:
            agg_dict[c] = agg_min_date

    upper_agg = tmp.groupby("_UPPER_NAME", dropna=False).agg(agg_dict).reset_index()

    if "Municipal Status" in df.columns:
        up_df = df[df["Municipal Status"] == "Upper Tier"].drop_duplicates("_MUNI_NAME").set_index("_MUNI_NAME")
        all_meta_cols = [c for c in (META_TEXT_COLS + META_EXPIRY_COLS) if c in upper_agg.columns and c in up_df.columns]
        for idx, r in upper_agg.iterrows():
            uname = r["_UPPER_NAME"]
            if uname in up_df.index:
                up_row = up_df.loc[uname]
                for mc in all_meta_cols:
                    val = strip_nbsp_and_space(up_row.get(mc, ""))
                    if val and val.lower() not in ("see local municipalities", "(no bylaw)", "(no fence bylaw)"):
                        upper_agg.at[idx, mc] = val

    upper_agg_idx = upper_agg.drop_duplicates("_UPPER_NAME").set_index("_UPPER_NAME")
    upper_gdf = upper_gdf.copy()
    if "_UPPER_NAME" not in upper_gdf.columns and UPPER_NAME_FIELD in upper_gdf.columns:
        upper_gdf["_UPPER_NAME"] = upper_gdf[UPPER_NAME_FIELD].astype(str).map(canon)

    for c in status_cols:
        if c in upper_agg_idx.columns:
            upper_gdf[c] = upper_gdf["_UPPER_NAME"].map(upper_agg_idx[c]).fillna("NOT KNOWN")
    for c in (META_TEXT_COLS + META_EXPIRY_COLS):
        if c in upper_agg_idx.columns:
            upper_gdf[c] = upper_gdf["_UPPER_NAME"].map(upper_agg_idx[c]).fillna("")
    return upper_gdf


# ---------- MAIN ----------
def main():
    print(f"Working Directory: {HERE}")
    
    # 1. READ DATA — SQLite preferred, CSV fallback
    if os.path.exists(BYLAW_DB):
        print(f"Reading from SQLite database: {os.path.basename(BYLAW_DB)}")
        from db_utils import get_connection, export_map_dataframe
        conn = get_connection(BYLAW_DB)
        df = export_map_dataframe(conn)
        conn.close()
        # Ensure all columns are string-typed for status_val() compatibility
        df = df.astype(str).replace({"None": "", "nan": ""})
        print(f"Loaded {len(df)} municipalities from SQLite")
    else:
        print("Reading bylaw CSV (SQLite not found, using fallback)...")
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

    df_lower = df[df["Municipal Status"] != "Upper Tier"] if "Municipal Status" in df.columns else df
    lower = g_low.merge(df_lower.drop_duplicates("_MUNI_NAME"), on="_MUNI_NAME", how="left")

    # 4. READ UPPER GEOJSON & AGGREGATE
    if not os.path.exists(UPPER_GEO):
         die(f"Upper GeoJSON not found at: {UPPER_GEO}. Please move 'Upper_Tier.geojson' to the root folder.")
    
    tmp = pd.DataFrame(lower.drop(columns=lower.geometry.name))
    if LOWER_TO_UPPER_FIELD in tmp.columns:
        tmp["_UPPER_NAME"] = tmp[LOWER_TO_UPPER_FIELD].astype(str).map(canon)
        agg_dict = {c: agg_status for c in status_cols if c in tmp.columns}
        for c in META_TEXT_COLS:
            if c in tmp.columns:
                agg_dict[c] = agg_first_non_empty
        for c in META_EXPIRY_COLS:
            if c in tmp.columns:
                agg_dict[c] = agg_min_date

        upper_agg = tmp.groupby("_UPPER_NAME", dropna=False).agg(agg_dict).reset_index()

        # Overlay direct Upper Tier municipality metadata (bylaw name, link, enacted, expiry)
        # where the Upper Tier municipality itself has a recorded bylaw in df
        if "Municipal Status" in df.columns:
            up_df = df[df["Municipal Status"] == "Upper Tier"].drop_duplicates("_MUNI_NAME").set_index("_MUNI_NAME")
            all_meta_cols = [c for c in (META_TEXT_COLS + META_EXPIRY_COLS) if c in upper_agg.columns and c in up_df.columns]
            for idx, r in upper_agg.iterrows():
                uname = r["_UPPER_NAME"]
                if uname in up_df.index:
                    up_row = up_df.loc[uname]
                    for mc in all_meta_cols:
                        val = strip_nbsp_and_space(up_row.get(mc, ""))
                        if val and val.lower() not in ("see local municipalities", "(no bylaw)", "(no fence bylaw)"):
                            upper_agg.at[idx, mc] = val

        g_up = gpd.read_file(UPPER_GEO)
        g_up["_UPPER_NAME"] = g_up[UPPER_NAME_FIELD].astype(str).map(canon)
        upper = g_up.merge(upper_agg, on="_UPPER_NAME", how="left")
        for c in status_cols:
            if c in upper.columns: upper[c] = upper[c].fillna("NOT KNOWN")
        for c in (META_TEXT_COLS + META_EXPIRY_COLS):
            if c in upper.columns: upper[c] = upper[c].fillna("")
        upper.to_parquet(UPPER_PARQUET, index=False)
        print(f"Wrote {UPPER_PARQUET}")

    lower.to_parquet(LOWER_PARQUET, index=False)
    print(f"Wrote {LOWER_PARQUET}")

if __name__ == "__main__":
    main()
