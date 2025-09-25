import os
import json
import streamlit as st
import geopandas as gpd
import pydeck as pdk
import pandas as pd

st.set_page_config(page_title="Upper Tier Bylaw Exemptions Map", layout="wide")

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

def find_status_columns(df: pd.DataFrame) -> list[str]:
    return sorted([c for c in df.columns if c.strip().endswith(" Status")])

def pick_name_field(df: pd.DataFrame) -> str:
    for c in ["MUNICIPALITY", "Municipality", "NAME", "OFFICIAL_M", "_UPPER_NAME"]:
        if c in df.columns:
            return c
    return df.columns[0]

def status_color(s: str) -> list[int]:
    s = (s or "").strip().upper()
    if s == "YES": return [0, 128, 0, 160]
    if s == "NO":  return [200, 0, 0, 160]
    if s == "N/A": return [128, 128, 128, 160]
    return [0, 0, 160, 140]

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
selected_col   = label_to_col[selected_label]

choice = st.sidebar.selectbox("Show", ["All", "YES", "NO", "N/A"], index=0)
search_term = st.sidebar.text_input(f"Search {name_field}", value="", placeholder="Type part of a name…").strip()

# ---------- Dynamic title ----------
st.title(f"Upper Tier Bylaw Exemptions Map – {selected_label}")

# ---------- Prepare styling ----------
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

# Summary card
counts = gdf["__STATUS__"].value_counts()
yes = int(counts.get("YES", 0))
no  = int(counts.get("NO", 0))
na  = int(counts.get("N/A", 0))

c1, c2, c3 = st.columns(3)
c1.metric("YES", f"{yes}")
c2.metric("NO", f"{no}")
c3.metric("N/A", f"{na}")

geom_col = gdf.geometry.name
props_df = gdf[[name_field, "__STATUS__", "__COLOR__", geom_col]].copy()
geojson = json.loads(props_df.to_json())

# ---------- Map ----------
layer = pdk.Layer(
    "GeoJsonLayer",
    data=geojson,
    pickable=True,
    stroked=True,
    filled=True,
    get_fill_color="properties.__COLOR__",
    get_line_color=[60, 60, 60, 255],
    lineWidthMinPixels=1,
)
view_state = pdk.ViewState(latitude=44.0, longitude=-80.0, zoom=5.8)

st.pydeck_chart(
    pdk.Deck(
        layers=[layer],
        initial_view_state=view_state,
        map_style="light",
        tooltip={"text": f"{{{name_field}}}\nStatus: {{__STATUS__}}"},
    )
)

with st.expander("Legend", expanded=False):
    st.markdown(
        "- **YES** = green  \n"
        "- **NO** = red  \n"
        "- **N/A** = gray  \n"
        "- **Other/blank** = blue"
    )
