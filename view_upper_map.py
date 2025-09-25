import os
import json
import streamlit as st
import geopandas as gpd
import pydeck as pdk
import pandas as pd

st.set_page_config(page_title="Upper Tier Bylaw Exemptions Map", layout="wide")
st.title("Upper Tier Bylaw Exemptions Map")

HERE = os.path.dirname(__file__)
UPPER_PARQUET = os.path.join(HERE, "upper_single_map.parquet")

@st.cache_data
def load_parquet(path):
    gdf = gpd.read_parquet(path)
    try:
        gdf = gdf.to_crs(4326)
    except Exception:
        pass
    return gdf

def find_status_columns(df: pd.DataFrame):
    return sorted([c for c in df.columns if c.strip().endswith(" Status")])

def pick_name_field(df: pd.DataFrame):
    for c in ["MUNICIPALITY","Municipality","NAME","OFFICIAL_M","_UPPER_NAME"]:
        if c in df.columns:
            return c
    return df.columns[0]

def status_color(s: str):
    s = (s or "").strip().upper()
    if s == "YES": return [0,128,0,160]
    if s == "NO":  return [200,0,0,160]
    if s in ("NOT KNOWN","UNKNOWN","N/A","NA"): return [128,128,128,160]
    return [0,0,160,140]

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

st.sidebar.header("Filters")
selected = st.sidebar.selectbox("Bylaw", status_cols, index=0)
choice = st.sidebar.selectbox("Show", ["All", "YES", "NO", "NOT KNOWN"], index=0)

gdf["__STATUS__"] = gdf[selected].fillna("").astype(str)
if choice != "All":
    gdf = gdf[gdf["__STATUS__"].str.strip().str.upper().eq(choice)]
gdf["__COLOR__"] = gdf["__STATUS__"].apply(status_color)

geom_col = gdf.geometry.name
props_df = gdf[[name_field, "__STATUS__", "__COLOR__", geom_col]].copy()

geojson = json.loads(props_df.to_json())

layer = pdk.Layer(
    "GeoJsonLayer",
    data=geojson,
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
