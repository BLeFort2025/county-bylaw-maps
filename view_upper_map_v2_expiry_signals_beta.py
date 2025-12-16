import os
import json
import re
from datetime import date

import streamlit as st
import geopandas as gpd
import pydeck as pdk
import pandas as pd

st.set_page_config(page_title="Upper Tier Bylaw Exemptions Map", layout="wide")

HERE = os.path.dirname(__file__)
UPPER_PARQUET = os.path.join(HERE, "upper_single_map_beta.parquet")

# --- Expiry-based signal tuning ---
EXPIRY_SOON_DAYS = 540  # ~18 months


@st.cache_data
def load_parquet(path):
    gdf = gpd.read_parquet(path)
    try:
        gdf = gdf.to_crs(4326)
    except Exception:
        pass
    return gdf


def find_status_columns(df: pd.DataFrame) -> list[str]:
    return sorted([c for c in df.columns if c.strip().endswith(" Status")])


def pick_name_field(df: pd.DataFrame) -> str:
    for c in ["MUNICIPALITY", "Municipality", "NAME", "OFFICIAL_M", "_UPPER_NAME"]:
        if c in df.columns:
            return c
    return df.columns[0]


def status_color(s: str) -> list[int]:
    s = (s or "").strip().upper()
    if s == "YES":
        return [0, 128, 0, 160]
    if s == "NO":
        return [200, 0, 0, 160]
    if s == "N/A":
        return [128, 128, 128, 160]
    return [0, 0, 160, 140]


# Same label->metadata mapping as lower map.
# IMPORTANT: Upper-tier parquet may not contain these fields unless build_maps.py is updated
# to aggregate them. The code below degrades gracefully (shows N/A).
META_BY_LABEL: dict[str, dict[str, str]] = {
    "Farm Exemption for Development Charges": {
        "bylaw_name": "Bylaw Name Development Charges",
        "bylaw_link": "Link to DC Bylaw",
        "enacted": "Date Bylaw Enacted (Regional)",
        "expiry": "Expiry Date",
    },
    "Farm Exemption for Stormwater Charges": {
        "bylaw_name": "Bylaw Name Stormwater",
        "bylaw_link": "Link to Storm Water bylaw",
        "enacted": "Date Bylaw Enacted2 (Regional)",
        "expiry": "Expiry date2",
    },
    "Farm Exemption for SA": {
        "bylaw_name": "Bylaw Name Sute Alteration",
        "bylaw_link": "Link to site alteration & fill bylaw",
        "enacted": "Date Bylaw Enacted4 (Regional)",
        "expiry": "Expiry date 4",
    },
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
    "Farm Exemption - Tree Cutting Bylaw": {
        "bylaw_name": "Bylaw Name Forest Conservation",
        "bylaw_link": "Tree Cutting Bylaw Link",
        "enacted": "Date Bylaw Enacted 6 (Regional)",
        "expiry": "Expiry Date 6",
    },
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
    if col and col in df.columns:
        return df[col]
    return pd.Series([""] * len(df), index=df.index)


def add_expiry_signal_columns(gdf: gpd.GeoDataFrame, selected_label: str) -> gpd.GeoDataFrame:
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

    expiry_display = expiry_raw.where(expiry_raw.ne(""), other="N/A")
    expiry_display = expiry_display.where(expiry_dt.isna(), other=expiry_dt.dt.date.astype(str))

    signal = pd.Series([""] * len(gdf), index=gdf.index)
    has_expiry = expiry_dt.notna()
    signal.loc[has_expiry & (days < 0)] = "Expired"
    signal.loc[has_expiry & (days >= 0) & (days <= EXPIRY_SOON_DAYS)] = "Expiring soon"

    expects_expiry = bool(expiry_col)
    has_bylaw = bylaw_name.ne("") | bylaw_link.ne("")
    signal.loc[expects_expiry & ~has_expiry & has_bylaw] = "Expiry unknown"

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


# ---------- Load data ----------
try:
    gdf = load_parquet(UPPER_PARQUET)
except FileNotFoundError:
    st.error(f"Parquet not found: {UPPER_PARQUET}. Commit the file to the repo.")
    st.stop()

status_cols = find_status_columns(gdf)
if not status_cols:
    st.error("No ‘… Status’ columns found. Rebuild with build_maps.py and push the new Parquet.")
    st.stop()

name_field = pick_name_field(gdf)

# ---------- Sidebar ----------
st.sidebar.header("Filters")

display_labels = {col: col.replace(" Status", "") for col in status_cols}
label_to_col = {v: k for k, v in display_labels.items()}

selected_label = st.sidebar.selectbox("Bylaw", list(display_labels.values()), index=0)
selected_col = label_to_col[selected_label]

choice = st.sidebar.selectbox("Show", ["All", "YES", "NO", "N/A"], index=0)
search_term = st.sidebar.text_input(f"Search {name_field}", value="", placeholder="Type part of a name…").strip()

# ---------- Dynamic title ----------
st.title(f"Upper Tier Bylaw Exemptions Map – {selected_label}")

# ---------- Prepare styling ----------
gdf = gdf.copy()

gdf["__STATUS__"] = (
    gdf[selected_col]
    .fillna("")
    .astype(str)
    .str.strip()
    .str.upper()
    .replace({"UNKNOWN": "NOT KNOWN", "NA": "N/A", "NOT KNOWN": "N/A"})
)

if choice != "All":
    gdf = gdf[gdf["__STATUS__"].eq(choice)]

if search_term:
    gdf = gdf[gdf[name_field].astype(str).str.contains(search_term, case=False, na=False)]

gdf["__COLOR__"] = gdf["__STATUS__"].apply(status_color)

# Add expiry + signal columns (will show N/A if upper parquet doesn't contain expiry fields)
gdf = add_expiry_signal_columns(gdf, selected_label)

# Summary cards
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
