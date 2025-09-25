import os
import streamlit as st
import geopandas as gpd
import pydeck as pdk
import pandas as pd

st.set_page_config(page_title="Lower Tier Bylaw Exemptions Map", layout="wide")
st.title("Lower Tier Bylaw Exemptions Map")

# ---------- Paths ----------
HERE = os.path.dirname(__file__)
# Put the Parquet(s) in the same folder as this script,
# or change to os.path.join(HERE, "data", "lower_single_map.parquet") if you keep them in /data
LOWER_PARQUET = os.path.join(HERE, "lower_single_map.parquet")

# ---------- Helpers ----------
@st.cache_data
def load_parquet(path):
    gdf = gpd.read_parquet(path)
    # Ensure WGS84 for pydeck
    try:
        gdf = gdf.to_crs(4326)
    except Exception:
        # Parquet may already be in 4326; ignore
        pass
    return gdf

def find_status_columns(df: pd.DataFrame):
    cols = [c for c in df.columns if c.strip().endswith(" Status")]
    return sorted(cols)

def pick_name_field(df: pd.DataFrame):
    candidates = [
        "MUNICIPALITY","Municipality","NAME","OFFICIAL_M",
        "MUNICIPA_8","MUNICIPA_2","_MUNI_NAME"
    ]
    for c in candidates:
        if c in df.columns:
            return c
    # last resort: show canonical key if nothing else
    return "_MUNI_NAME" if "_MUNI_NAME" in df.columns else df.columns[0]

def status_color(s: str):
    s = (s or "").strip().upper()
    if s == "YES": return [0,128,0,160]     # green
    if s == "NO":  return [200,0,0,160]     # red
    if s in ("NOT KNOWN","UNKNOWN","N/A","NA"): return [128,128,128,160]  # gray
    return [0,0,160,140]                    # blue (other/blank)

# ---------- Load data ----------
try:
    gdf = load_parquet(LOWER_PARQUET)
except FileNotFoundError:
    st.error(f"Parquet not found: {LOWER_PARQUET}. Make sure you committed the file to the repo.")
    st.stop()

status_cols = find_status_columns(gdf)
if not status_cols:
    st.error("No ‘… Status’ columns found in the Parquet. Rebuild with build_maps.py and push the new file.")
    st.stop()

name_field = pick_name_field(gdf)

# ---------- Sidebar UI ----------
st.sidebar.header("Filters")
selected = st.sidebar.selectbox("Bylaw", status_cols, index=0)

# Optional: filter by status (All/YES/NO/NOT KNOWN)
choice = st.sidebar.selectbox("Show", ["All", "YES", "NO", "NOT KNOWN"], index=0)

# ---------- Compute styling ----------
gdf["__STATUS__"] = gdf[selected].fillna("").astype(str)
if choice != "All":
    gdf = gdf[gdf["__STATUS__"].str.strip().str.upper().eq(choice)]

gdf["__COLOR__"] = gdf["__STATUS__"].apply(status_color)

# ---------- Map ----------
layer = pdk.Layer(
    "GeoJsonLayer",
    data=gdf.__geo_interface__,
    pickable=True,
    stroked=True,
    filled=True,
    get_fill_color="properties.__COLOR__",
    get_line_color=[60,60,60,255],
    lineWidthMinPixels=1,
)
view_state = pdk.ViewState(latitude=44.4, longitude=-79.5, zoom=6)
st.pydeck_chart(
    pdk.Deck(
        layers=[layer],
        initial_view_state=view_state,
        tooltip={"text": f"{{{name_field}}}\nStatus: {{__STATUS__}}"},
    )
)

with st.expander("Legend", expanded=False):
    st.markdown(
        "- **YES** = green  \n"
        "- **NO** = red  \n"
        "- **NOT KNOWN/UNKNOWN/N/A** = gray  \n"
        "- **Other/blank** = blue"
    )
