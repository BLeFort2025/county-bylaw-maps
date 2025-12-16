import os
import json
import re
from datetime import date

import geopandas as gpd
import pandas as pd
import pydeck as pdk
import streamlit as st

from ofa_content import get_content_for_label

st.set_page_config(page_title="Lower Tier Bylaw Exemptions Map", layout="wide")

HERE = os.path.dirname(__file__)
LOWER_PARQUET = os.path.join(HERE, "lower_single_map_beta.parquet")

# --- Expiry-based signal tuning ---
EXPIRY_SOON_DAYS = 540  # ~18 months


def find_status_columns(df: pd.DataFrame) -> list[str]:
    """Return all columns that represent map-ready status fields."""
    return sorted([c for c in df.columns if c.strip().endswith(" Status")])


def pick_name_field(df: pd.DataFrame) -> str:
    """Pick a human-readable name column for municipalities."""
    for c in [
        "MUNICIPALITY",
        "Municipality",
        "NAME",
        "OFFICIAL_M",
        "MUNICIPA_8",
        "MUNICIPA_2",
        "_MUNI_NAME",
    ]:
        if c in df.columns:
            return c
    # Fallback: first column
    return df.columns[0]


def status_color(s: str) -> list[int]:
    """Map a YES/NO/N/A style status string to an RGBA colour."""
    s = (s or "").strip().upper()
    if s == "YES":
        return [0, 128, 0, 160]  # green
    if s == "NO":
        return [200, 0, 0, 160]  # red
    if s == "N/A":
        return [128, 128, 128, 160]  # gray
    return [0, 0, 160, 140]  # blue (other/blank)


def canon_name(x: str) -> str:
    """Lightweight canon used only for joining signals/metadata if needed."""
    if x is None:
        return ""
    s = str(x).replace("\u00A0", " ").strip().upper()
    s = s.replace("&", " AND ").replace("-", " ")
    s = re.sub(r"[’'`]", "", s)
    s = re.sub(r"[^A-Z0-9 /]", " ", s)
    s = s.replace("/", " ")
    s = re.sub(r"\s+", " ", s).strip()
    for p in [
        "CITY OF ",
        "TOWN OF ",
        "TOWNSHIP OF ",
        "VILLAGE OF ",
        "MUNICIPALITY OF ",
        "REGIONAL MUNICIPALITY OF ",
        "REGION OF ",
        "COUNTY OF ",
        "DISTRICT OF ",
    ]:
        if s.startswith(p):
            s = s[len(p) :].strip()
            break
    for suf in [
        " COUNTY",
        " REGION",
        " CITY",
        " TOWN",
        " TOWNSHIP",
        " VILLAGE",
        " MUNICIPALITY",
        " DISTRICT",
    ]:
        if s.endswith(suf):
            s = s[: -len(suf)].strip()
            break
    s = re.sub(r"\b(CO\.?|CNTY)\b$", "", s).strip()
    return re.sub(r"\s+", " ", s).strip()


# Map labels -> where to find bylaw metadata in the Parquet
# NOTE: keys must match the map dropdown labels exactly (status col without " Status")
META_BY_LABEL: dict[str, dict[str, str]] = {
    # Development Charges
    "Farm Exemption for Development Charges": {
        "bylaw_name": "Bylaw Name Development Charges",
        "bylaw_link": "Link to DC Bylaw",
        "enacted": "Date Bylaw Enacted (Regional)",
        "expiry": "Expiry Date",
    },
    # Stormwater
    "Farm Exemption for Stormwater Charges": {
        "bylaw_name": "Bylaw Name Stormwater",
        "bylaw_link": "Link to Storm Water bylaw",
        "enacted": "Date Bylaw Enacted2 (Regional)",
        "expiry": "Expiry date2",
    },
    # Site alteration
    "Farm Exemption for SA": {
        "bylaw_name": "Bylaw Name Sute Alteration",
        "bylaw_link": "Link to site alteration & fill bylaw",
        "enacted": "Date Bylaw Enacted4 (Regional)",
        "expiry": "Expiry date 4",
    },
    # Livestock Guardian Dogs (multiple map labels, same bylaw metadata)
    "Has Livestock Guardian dog Definition": {
        "bylaw_name": "Bylaw Name LGD",
        "bylaw_link": "Livestock Guardian Dog bylaw link",
        "enacted": "Date Bylaw Enacted 5 (Regional)",
        "expiry": "Expiry Date 5",
    },
    "LDG - Definition": {
        "bylaw_name": "Bylaw Name LGD",
        "bylaw_link": "Livestock Guardian Dog bylaw link",
        "enacted": "Date Bylaw Enacted 5 (Regional)",
        "expiry": "Expiry Date 5",
    },
    "Herding Dog Definition Exists": {
        "bylaw_name": "Bylaw Name LGD",
        "bylaw_link": "Livestock Guardian Dog bylaw link",
        "enacted": "Date Bylaw Enacted 5 (Regional)",
        "expiry": "Expiry Date 5",
    },
    "LDG and HD exempt from license fees": {
        "bylaw_name": "Bylaw Name LGD",
        "bylaw_link": "Livestock Guardian Dog bylaw link",
        "enacted": "Date Bylaw Enacted 5 (Regional)",
        "expiry": "Expiry Date 5",
    },
    "LDG and HD Collar and tag requirements": {
        "bylaw_name": "Bylaw Name LGD",
        "bylaw_link": "Livestock Guardian Dog bylaw link",
        "enacted": "Date Bylaw Enacted 5 (Regional)",
        "expiry": "Expiry Date 5",
    },
    "LDG and HD Exempt from barking restrictions": {
        "bylaw_name": "Bylaw Name LGD",
        "bylaw_link": "Livestock Guardian Dog bylaw link",
        "enacted": "Date Bylaw Enacted 5 (Regional)",
        "expiry": "Expiry Date 5",
    },
    # Backyard chickens (multiple labels, same bylaw metadata)
    "Can you Keep Backyard Chickens": {
        "bylaw_name": "Bylaw Name Backyard Chicken",
        "bylaw_link": "Backyard Chicken Bylaw Link",
        "enacted": "Date Bylaw Enacted 7 (Regional)",
        "expiry": "Expiry Date 7",
    },
    "Licence Required": {
        "bylaw_name": "Bylaw Name Backyard Chicken",
        "bylaw_link": "Backyard Chicken Bylaw Link",
        "enacted": "Date Bylaw Enacted 7 (Regional)",
        "expiry": "Expiry Date 7",
    },
    "Welfare Requirements": {
        "bylaw_name": "Bylaw Name Backyard Chicken",
        "bylaw_link": "Backyard Chicken Bylaw Link",
        "enacted": "Date Bylaw Enacted 7 (Regional)",
        "expiry": "Expiry Date 7",
    },
    # Tree cutting / forest conservation
    "Farm Exemption - Tree Cutting Bylaw": {
        "bylaw_name": "Bylaw Name Forest Conservation",
        "bylaw_link": "Tree Cutting Bylaw Link",
        "enacted": "Date Bylaw Enacted 6 (Regional)",
        "expiry": "Expiry Date 6",
    },
    # Fence (no expiry currently tracked)
    "Farm Exemption for Security fencing prohibitions": {
        "bylaw_name": "",
        "bylaw_link": "Link to Fence Bylaw",
        "enacted": "",
        "expiry": "",
    },
    "Farm Exemption for Electrified fencing prohibitions": {
        "bylaw_name": "",
        "bylaw_link": "Link to Fence Bylaw",
        "enacted": "",
        "expiry": "",
    },
}


def _safe_series(df: pd.DataFrame, col: str) -> pd.Series:
    """Return df[col] if it exists, otherwise a blank Series of equal length."""
    if col and col in df.columns:
        return df[col]
    return pd.Series([""] * len(df), index=df.index)


def add_expiry_signal_columns(gdf: gpd.GeoDataFrame, selected_label: str) -> gpd.GeoDataFrame:
    """Add __EXPIRY__, __SIGNAL__, and __LINE_COLOR__ based on selected label metadata."""
    meta = META_BY_LABEL.get(selected_label, {})
    expiry_col = meta.get("expiry", "")
    bylaw_name_col = meta.get("bylaw_name", "")
    link_col = meta.get("bylaw_link", "")

    expiry_raw = _safe_series(gdf, expiry_col).fillna("").astype(str).str.strip()
    bylaw_name = _safe_series(gdf, bylaw_name_col).fillna("").astype(str).str.strip()
    bylaw_link = _safe_series(gdf, link_col).fillna("").astype(str).str.strip()

    expiry_dt = pd.to_datetime(expiry_raw, errors="coerce")
    today = pd.Timestamp(date.today())
    days = (expiry_dt - today).dt.days

    # Display expiry
    expiry_display = expiry_raw.copy()
    expiry_display = expiry_display.where(expiry_display.ne(""), other="N/A")
    expiry_display = expiry_display.where(expiry_dt.isna(), other=expiry_dt.dt.date.astype(str))

    # Signal logic
    signal = pd.Series([""] * len(gdf), index=gdf.index)

    has_expiry = expiry_dt.notna()
    signal.loc[has_expiry & (days < 0)] = "Expired"
    signal.loc[has_expiry & (days >= 0) & (days <= EXPIRY_SOON_DAYS)] = "Expiring soon"

    # If we expect expiry but don't have one, flag as "Expiry unknown" when a bylaw likely exists
    expects_expiry = bool(expiry_col)
    has_bylaw = bylaw_name.ne("") | bylaw_link.ne("")
    signal.loc[expects_expiry & ~has_expiry & has_bylaw] = "Expiry unknown"

    # Line colour to draw attention to signals (outline only; fill still reflects Status)
    line_color = pd.Series([[60, 60, 60, 255]] * len(gdf), index=gdf.index)

    mask = signal.eq("Expiring soon")
    if mask.any():
        line_color.loc[mask] = [[255, 165, 0, 255]] * int(mask.sum())  # orange

    mask = signal.eq("Expired")
    if mask.any():
        line_color.loc[mask] = [[0, 0, 0, 255]] * int(mask.sum())  # black

    mask = signal.eq("Expiry unknown")
    if mask.any():
        line_color.loc[mask] = [[255, 215, 0, 255]] * int(mask.sum())  # gold

    gdf["__EXPIRY__"] = expiry_display
    gdf["__SIGNAL__"] = signal
    gdf["__BYLAW_NAME__"] = bylaw_name
    gdf["__BYLAW_LINK__"] = bylaw_link
    gdf["__LINE_COLOR__"] = line_color

    return gdf


@st.cache_data
def load_data(path: str):
    """Load, reproject and lightly simplify the lower-tier map data.

    Returns:
        gdf: GeoDataFrame with the needed columns (status + metadata + geometry)
        status_cols: list of "... Status" columns
        name_field: chosen municipality name column
    """
    gdf = gpd.read_parquet(path)

    # Ensure WGS84 for pydeck
    try:
        gdf = gdf.to_crs(4326)
    except Exception:
        pass

    status_cols = find_status_columns(gdf)
    name_field = pick_name_field(gdf)

    # Keep: name + all status fields + geometry + all metadata columns that might be used in tooltips
    geom_col = gdf.geometry.name

    meta_cols = []
    patterns = [
        r"(?i)^bylaw name\b",
        r"(?i)\bexpiry\b",
        r"(?i)\blink\b",
        r"(?i)\bdate bylaw enacted\b",
        r"(?i)\bmunicipality has fence bylaw\b",
    ]
    for c in gdf.columns:
        if c == geom_col or c == name_field or c in status_cols:
            continue
        if any(re.search(p, c) for p in patterns):
            meta_cols.append(c)

    keep_cols = set(status_cols + [name_field, geom_col] + meta_cols)
    gdf = gdf[list(keep_cols)].copy()

    # Light geometry simplification to cut JSON size and drawing time.
    gdf[geom_col] = gdf[geom_col].simplify(tolerance=0.001, preserve_topology=True)

    return gdf, status_cols, name_field


# ---------- Load data ----------
try:
    base_gdf, status_cols, name_field = load_data(LOWER_PARQUET)
except FileNotFoundError:
    st.error(f"Parquet not found: {LOWER_PARQUET}. Commit the file to the repo.")
    st.stop()

if not status_cols:
    st.error("No '… Status' columns found. Rebuild the data and push the new Parquet file.")
    st.stop()

# ---------- Sidebar ----------
st.sidebar.header("Filters")

display_labels = {col: col.replace(" Status", "") for col in status_cols}
label_to_col = {v: k for k, v in display_labels.items()}

selected_label = st.sidebar.selectbox("Bylaw", list(display_labels.values()), index=0)
selected_col = label_to_col[selected_label]

choice = st.sidebar.selectbox("Show", ["All", "YES", "NO", "N/A"], index=0)

# Search box
search_term = st.sidebar.text_input(
    f"Search {name_field}", value="", placeholder="Type part of a name…"
).strip()

# Optional: municipality details panel (selection-based; Streamlit can't bind sidebar to hover)
st.sidebar.divider()
st.sidebar.subheader("Municipality details")
muni_options = sorted(base_gdf[name_field].dropna().astype(str).unique().tolist())
selected_muni = st.sidebar.selectbox("Select a municipality", options=muni_options, index=0)

# ---------- Dynamic title ----------
st.title(f"Lower Tier Bylaw Exemptions Map – {selected_label}")

# Work on a copy so the cached base_gdf stays clean.
gdf = base_gdf.copy()

# ---------- Prepare styling ----------
gdf["__STATUS__"] = (
    gdf[selected_col]
    .fillna("")
    .astype(str)
    .str.strip()
    .str.upper()
    .replace({"UNKNOWN": "NOT KNOWN", "NA": "N/A", "NOT KNOWN": "N/A"})
)

# Apply filter for status
if choice != "All":
    gdf = gdf[gdf["__STATUS__"].eq(choice)]

# Apply search filter
if search_term:
    gdf = gdf[gdf[name_field].astype(str).str.contains(search_term, case=False, na=False)]

# Compute colours
gdf["__COLOR__"] = gdf["__STATUS__"].apply(status_color)

# Add expiry + signal columns for the current selection
gdf = add_expiry_signal_columns(gdf, selected_label)

# ---------- Summary cards ----------
counts = gdf["__STATUS__"].value_counts()
yes = int(counts.get("YES", 0))
no = int(counts.get("NO", 0))
na = int(counts.get("N/A", 0))

sig_counts = gdf["__SIGNAL__"].value_counts()
expiring = int(sig_counts.get("Expiring soon", 0))
expired = int(sig_counts.get("Expired", 0))

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("YES", f"{yes}")
c2.metric("NO", f"{no}")
c3.metric("N/A", f"{na}")
c4.metric("Expiring soon", f"{expiring}")
c5.metric("Expired", f"{expired}")

# ---------- Map data prep ----------
geom_col = gdf.geometry.name

props_df = gdf[
    [name_field, "__STATUS__", "__COLOR__", "__EXPIRY__", "__SIGNAL__", "__BYLAW_NAME__", "__BYLAW_LINK__", "__LINE_COLOR__", geom_col]
].copy()

geojson = json.loads(props_df.to_json())

# ---------- Map ----------
layer = pdk.Layer(
    "GeoJsonLayer",
    data=geojson,
    pickable=True,
    stroked=True,
    filled=True,
    get_fill_color="properties.__COLOR__",
    get_line_color="properties.__LINE_COLOR__",
    lineWidthMinPixels=2,
)

view_state = pdk.ViewState(latitude=44.0, longitude=-80.0, zoom=5.8)

st.pydeck_chart(
    pdk.Deck(
        layers=[layer],
        initial_view_state=view_state,
        map_style="light",
        tooltip={
            "text": (
                f"{{{name_field}}}\n"
                "Status: {__STATUS__}\n"
                "Expiry: {__EXPIRY__}\n"
                "Signal: {__SIGNAL__}\n"
                "Bylaw: {__BYLAW_NAME__}\n"
                "Link: {__BYLAW_LINK__}"
            )
        },
    )
)

# ---------- Municipality details panel (sidebar) ----------
# Pull from the unfiltered base_gdf so selection always works
detail_row = base_gdf[base_gdf[name_field].astype(str).eq(str(selected_muni))].head(1)
if len(detail_row) == 1:
    detail_row = detail_row.iloc[0]
    meta = META_BY_LABEL.get(selected_label, {})
    bylaw_name = str(detail_row.get(meta.get("bylaw_name", ""), "") or "").strip()
    bylaw_link = str(detail_row.get(meta.get("bylaw_link", ""), "") or "").strip()
    expiry = str(detail_row.get(meta.get("expiry", ""), "") or "").strip()
    enacted = str(detail_row.get(meta.get("enacted", ""), "") or "").strip()

    # Compute signal for this one municipality
    exp_dt = pd.to_datetime(expiry, errors="coerce")
    today = pd.Timestamp(date.today())
    if pd.notna(exp_dt):
        days = int((exp_dt - today).days)
        if days < 0:
            sig = f"Expired ({abs(days)} days ago)"
        elif days <= EXPIRY_SOON_DAYS:
            sig = f"Expiring soon ({days} days)"
        else:
            sig = f"Not soon ({days} days)"
    else:
        sig = "Expiry unknown" if expiry == "" else "Expiry format issue"

    st.sidebar.markdown(f"**Selected bylaw topic:** {selected_label}")
    if bylaw_name:
        st.sidebar.markdown(f"**Bylaw:** {bylaw_name}")
    if enacted:
        st.sidebar.markdown(f"**Enacted:** {enacted}")
    if expiry:
        st.sidebar.markdown(f"**Expiry:** {expiry}")
    st.sidebar.markdown(f"**Expiry signal:** {sig}")
    if bylaw_link:
        # streamlit can render a clickable markdown link if it's a real URL
        st.sidebar.markdown(f"**Source:** {bylaw_link}")

# ---------- OFA position + template letter ----------
content = get_content_for_label(selected_label)

if content is not None:
    st.subheader(content.title)
    st.markdown(content.body_md)

    if content.letter_path:
        template_path = os.path.join(HERE, content.letter_path)
        if os.path.exists(template_path):
            with open(template_path, "rb") as f:
                st.download_button(
                    label="Download template letter for this bylaw (.docx)",
                    data=f,
                    file_name=os.path.basename(template_path),
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
        else:
            st.info(
                "A template letter is expected for this bylaw, but the .docx file is not present in the repository."
            )
    else:
        st.info("A template letter for this bylaw type is not currently available.")

# ---------- Legend ----------
with st.expander("Legend", expanded=False):
    st.markdown(
        "- **YES** = green  \n"
        "- **NO** = red  \n"
        "- **N/A** = gray  \n"
        "- **Other/blank** = blue  \n"
        "- **Orange outline** = expiring soon  \n"
        "- **Black outline** = expired  \n"
        "- **Gold outline** = expiry unknown (bylaw exists)"
    )

# ---------- Optional: table for quick search/export ----------
with st.expander("Filtered municipalities (table)", expanded=False):
    table = gdf[[name_field, "__STATUS__", "__EXPIRY__", "__SIGNAL__", "__BYLAW_LINK__"]].copy()
    table = table.rename(columns={name_field: "Municipality", "__BYLAW_LINK__": "Bylaw link"})
    st.dataframe(table, use_container_width=True)
