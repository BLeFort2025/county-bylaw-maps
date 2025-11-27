import os
import json

import geopandas as gpd
import pandas as pd
import pydeck as pdk
import streamlit as st

from ofa_content import get_content_for_label

st.set_page_config(page_title="Lower Tier Bylaw Exemptions Map", layout="wide")

HERE = os.path.dirname(__file__)
LOWER_PARQUET = os.path.join(HERE, "lower_single_map.parquet")


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


@st.cache_data
def load_data(path: str):
    """Load, reproject and lightly simplify the lower-tier map data.

    Returns:
        gdf: GeoDataFrame with only the needed columns
        status_cols: list of "... Status" columns
        name_field: chosen municipality name column
    """
    gdf = gpd.read_parquet(path)

    # Ensure WGS84 for pydeck
    try:
        gdf = gdf.to_crs(4326)
    except Exception:
        # If CRS is already 4326 or missing, just continue
        pass

    status_cols = find_status_columns(gdf)
    name_field = pick_name_field(gdf)

    # Keep only the columns we actually use: name, all status fields, geometry.
    geom_col = gdf.geometry.name
    keep_cols = set(status_cols + [name_field, geom_col])
    gdf = gdf[list(keep_cols)].copy()

    # Light geometry simplification to cut JSON size and drawing time.
    # Tolerance of ~0.001 degrees ≈ 100 m at these latitudes.
    gdf[geom_col] = gdf[geom_col].simplify(tolerance=0.001, preserve_topology=True)

    return gdf, status_cols, name_field


# ---------- Load data ----------
try:
    base_gdf, status_cols, name_field = load_data(LOWER_PARQUET)
except FileNotFoundError:
    st.error(f"Parquet not found: {LOWER_PARQUET}. Commit the file to the repo.")
    st.stop()

if not status_cols:
    st.error(
        "No '… Status' columns found. Rebuild the data and push the new Parquet file."
    )
    st.stop()

# ---------- Sidebar ----------
st.sidebar.header("Filters")

# Build display labels without the trailing " Status"
display_labels = {col: col.replace(" Status", "") for col in status_cols}
label_to_col = {v: k for k, v in display_labels.items()}

selected_label = st.sidebar.selectbox("Bylaw", list(display_labels.values()), index=0)
selected_col = label_to_col[selected_label]

choice = st.sidebar.selectbox("Show", ["All", "YES", "NO", "N/A"], index=0)

# Search box
search_term = st.sidebar.text_input(
    f"Search {name_field}", value="", placeholder="Type part of a name…"
).strip()

# ---------- Dynamic title ----------
st.title(f"Lower Tier Bylaw Exemptions Map – {selected_label}")

# Work on a copy so the cached base_gdf stays clean.
gdf = base_gdf.copy()

# ---------- Prepare styling ----------
# Normalize to display “N/A” instead of NOT KNOWN/UNKNOWN/NA
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
    gdf = gdf[
        gdf[name_field].astype(str).str.contains(search_term, case=False, na=False)
    ]

# Compute colours
gdf["__COLOR__"] = gdf["__STATUS__"].apply(status_color)

# ---------- Small summary card (YES / NO / N/A) ----------
counts = gdf["__STATUS__"].value_counts()
yes = int(counts.get("YES", 0))
no = int(counts.get("NO", 0))
na = int(counts.get("N/A", 0))

c1, c2, c3 = st.columns(3)
c1.metric("YES", f"{yes}")
c2.metric("NO", f"{no}")
c3.metric("N/A", f"{na}")

# ---------- Map data prep ----------
geom_col = gdf.geometry.name
props_df = gdf[[name_field, "__STATUS__", "__COLOR__", geom_col]].copy()

# Convert to clean GeoJSON dict for pydeck
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

# Slightly adjusted view to frame Ontario comfortably
view_state = pdk.ViewState(latitude=44.0, longitude=-80.0, zoom=5.8)

st.pydeck_chart(
    pdk.Deck(
        layers=[layer],
        initial_view_state=view_state,
        map_style="light",  # softer background
        tooltip={"text": f"{{{name_field}}}\nStatus: {{__STATUS__}}"},
    )
)

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
        "- **Other/blank** = blue"
    )
