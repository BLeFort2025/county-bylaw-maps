from __future__ import annotations

import re
import shutil
from pathlib import Path
from datetime import datetime

import pandas as pd


# -----------------------------
# Settings
# -----------------------------
BASE_DIR = Path(__file__).resolve().parent

MASTER_CSV = BASE_DIR / "Final_Bylaw_Data__Grouped_Correctly_.csv"

# Auto-pick latest DC_Bylaws_*.xlsx in this folder
DC_GLOB = "DC_Bylaws_*.xlsx"

# DC columns -> MASTER columns mapping
DC_TO_MASTER = {
    "Farm Exemption for Development Charges": "Farm Exemption for Development Charges",
    "Bylaw Name 1": "Bylaw Name Development Charges",
    "Wording of exemption": "Wording of exemption",
    "Date Bylaw Enacted (Regional)": "Date Bylaw Enacted (Regional)",
    "Expiry Date": "Expiry Date",
    "Link to DC Bylaw": "Link to DC Bylaw",
}

# Key field in DC file
DC_KEY_COL = "LOOKUP"

# Candidate key fields in MASTER file (we’ll pick the first one that exists)
MASTER_KEY_CANDIDATES = [
    "LOOKUP",
    "Municipality",
    "MUNICIPALITY",
    "_MUNI_NAME",
    "MUNICIPA_8",
    "MUNICIPA_2",
]


# -----------------------------
# Helpers
# -----------------------------
def norm_key(x: str) -> str:
    s = "" if x is None else str(x)
    s = s.strip().upper()
    s = re.sub(r"\s+", " ", s)
    return s


def read_csv_smart(path: Path) -> tuple[pd.DataFrame, str]:
    # Your data has historically been cp1252 sometimes.
    for enc in ("utf-8", "utf-8-sig", "cp1252"):
        try:
            df = pd.read_csv(path, dtype=str, encoding=enc).fillna("")
            return df, enc
        except UnicodeDecodeError:
            continue
    # Final fallback (rare)
    df = pd.read_csv(path, dtype=str, encoding="cp1252", errors="replace").fillna("")
    return df, "cp1252(errors=replace)"


def write_csv_cp1252_safe(df: pd.DataFrame, path: Path) -> None:
    # Write in cp1252 safely (replace any unencodable chars)
    with open(path, "w", encoding="cp1252", errors="replace", newline="") as f:
        df.to_csv(f, index=False)


def pick_latest_dc_file(folder: Path) -> Path:
    matches = sorted(folder.glob(DC_GLOB), key=lambda p: p.stat().st_mtime, reverse=True)
    if not matches:
        raise FileNotFoundError(f"No DC file found matching {DC_GLOB} in {folder}")
    return matches[0]


def main() -> None:
    if not MASTER_CSV.exists():
        raise FileNotFoundError(f"Master CSV not found: {MASTER_CSV}")

    dc_xlsx = pick_latest_dc_file(BASE_DIR)

    print("MASTER CSV:", MASTER_CSV)
    print("DC XLSX   :", dc_xlsx)

    master, enc = read_csv_smart(MASTER_CSV)
    print(f"Loaded MASTER rows={len(master)} cols={len(master.columns)} encoding={enc}")

    # Find master key col
    master_key = None
    for c in MASTER_KEY_CANDIDATES:
        if c in master.columns:
            master_key = c
            break
    if master_key is None:
        raise KeyError(
            "Could not find a municipality key column in MASTER. "
            f"Tried: {MASTER_KEY_CANDIDATES}\n"
            f"Available columns include: {list(master.columns)[:50]} ..."
        )

    # Read DC excel
    dc = pd.read_excel(dc_xlsx, sheet_name=0, dtype=str).fillna("")
    print(f"Loaded DC rows={len(dc)} cols={len(dc.columns)}")

    if DC_KEY_COL not in dc.columns:
        raise KeyError(f"DC file missing key column '{DC_KEY_COL}'. Found: {list(dc.columns)}")

    # Verify expected DC columns exist
    missing_dc_cols = [c for c in DC_TO_MASTER.keys() if c not in dc.columns]
    if missing_dc_cols:
        raise KeyError(f"DC file is missing expected column(s): {missing_dc_cols}")

    # Add normalized keys
    master["_KEY_TMP_"] = master[master_key].apply(norm_key)
    dc["_KEY_TMP_"] = dc[DC_KEY_COL].apply(norm_key)

    # Check duplicates
    if master["_KEY_TMP_"].duplicated().any():
        dups = master.loc[master["_KEY_TMP_"].duplicated(), master_key].head(10).tolist()
        raise ValueError(f"MASTER has duplicate keys (sample): {dups}")

    if dc["_KEY_TMP_"].duplicated().any():
        dups = dc.loc[dc["_KEY_TMP_"].duplicated(), DC_KEY_COL].head(10).tolist()
        raise ValueError(f"DC has duplicate keys (sample): {dups}")

    master_idx = master.set_index("_KEY_TMP_", drop=False)
    dc_idx = dc.set_index("_KEY_TMP_", drop=False)

    common = master_idx.index.intersection(dc_idx.index)
    only_in_dc = dc_idx.index.difference(master_idx.index)
    only_in_master = master_idx.index.difference(dc_idx.index)

    print(f"Key matches: {len(common)}")
    if len(only_in_dc) > 0:
        print("⚠️  Keys in DC but not MASTER (sample):", dc_idx.loc[list(only_in_dc)[:10], DC_KEY_COL].tolist())
    if len(only_in_master) > 0:
        # This can happen if master has extra rows; usually OK
        print("ℹ️  Keys in MASTER but not DC (sample):", master_idx.loc[list(only_in_master)[:10], master_key].tolist())

    # Ensure target columns exist in master
    for src, tgt in DC_TO_MASTER.items():
        if tgt not in master_idx.columns:
            master_idx[tgt] = ""

    # Apply overwrite from DC -> MASTER for all matching municipalities
    updated_cells = 0
    for src, tgt in DC_TO_MASTER.items():
        before = master_idx.loc[common, tgt].copy()
        master_idx.loc[common, tgt] = dc_idx.loc[common, src].values
        updated_cells += int((before != master_idx.loc[common, tgt]).sum())

    # Backup master before overwriting
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = MASTER_CSV.parent / f"{MASTER_CSV.stem}.bak_{ts}.csv"
    shutil.copy2(MASTER_CSV, backup)
    print("✅ Backup created:", backup)

    # Drop temp key and write
    out = master_idx.drop(columns=["_KEY_TMP_"]).reset_index(drop=True)

    write_csv_cp1252_safe(out, MASTER_CSV)
    print("✅ Wrote updated MASTER CSV:", MASTER_CSV)
    print(f"Updated cells (approx): {updated_cells}")

    # Quick sanity: show DC bylaw presence/exemption distribution
    if "Bylaw Name Development Charges" in out.columns:
        has_bylaw = (out["Bylaw Name Development Charges"].fillna("").astype(str).str.strip() != "").sum()
        print(f"DC bylaw name non-empty count: {int(has_bylaw)} / {len(out)}")

    if "Farm Exemption for Development Charges" in out.columns:
        dist = (
            out["Farm Exemption for Development Charges"]
            .fillna("")
            .astype(str)
            .str.strip()
            .replace({"": "(blank)"})
            .value_counts()
            .head(15)
        )
        print("Top DC exemption values:")
        print(dist.to_string())


if __name__ == "__main__":
    main()
