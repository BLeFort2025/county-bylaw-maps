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

# Signal priority (used once multiple signal types exist)
SIGNAL_PRIORITY = [
    "Expired",
    "Expiring soon",
    "Mentioned in minutes/agendas",
    "Expiry unknown",
]


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
    line_color.loc[signal.eq("Expiring soon")] = [[255, 165, 0, 255]]
    line_color.loc[signal.eq("Expired")] = [[0, 0, 0, 255]]
    line_color.loc[signal.eq("Expiry unknown")] = [[255, 215, 0, 255]]

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

# Split filters: Status vs Expiry alerts (signals)
status_filter = st.sidebar.selectbox("Status", ["All", "YES", "NO", "N/A"], index=0)
signal_filter = st.sidebar.selectbox(
    "Expiry alert",
    ["All", "Expiring soon", "Expired", "Expiry unknown"],
    index=0,
)
display_mode = st.sidebar.selectbox(
    "Display mode",
    ["Highlight matches", "Filter to matches"],
    index=0,
)

search_term = st.sidebar.text_input(f"Search {name_field}", value="", placeholder="Type part of a name…").strip()

# ---------- Dynamic title ----------
st.title(f"Upper Tier Bylaw Exemptions Map – {selected_label}")

# ---------- Prepare data ----------
gdf_all = gdf.copy()

gdf_all["__STATUS__"] = (
    gdf_all[selected_col]
    .fillna("")
    .astype(str)
    .str.strip()
    .str.upper()
    .replace({"UNKNOWN": "NOT KNOWN", "NA": "N/A", "NOT KNOWN": "N/A"})
)

gdf_all["__COLOR__"] = gdf_all["__STATUS__"].apply(status_color)
gdf_all = add_expiry_signal_columns(gdf_all, selected_label)

# ---------- Build match mask ----------
match_mask = pd.Series(True, index=gdf_all.index)

if status_filter != "All":
    match_mask &= gdf_all["__STATUS__"].eq(status_filter)

if signal_filter != "All":
    match_mask &= gdf_all["__SIGNAL__"].eq(signal_filter)

if search_term:
    match_mask &= gdf_all[name_field].astype(str).str.contains(search_term, case=False, na=False)

gdf_match = gdf_all[match_mask].copy()

# ---------- Sidebar: Municipality details ----------
st.sidebar.divider()
st.sidebar.subheader("Municipality details")

limit_muni_list = st.sidebar.checkbox("Limit list to current results", value=True)

muni_source = gdf_match if (limit_muni_list and not gdf_match.empty) else gdf_all
muni_options = sorted(muni_source[name_field].dropna().astype(str).unique().tolist())

if not muni_options:
    muni_options = sorted(gdf_all[name_field].dropna().astype(str).unique().tolist())

if "selected_upper_muni" not in st.session_state:
    st.session_state["selected_upper_muni"] = muni_options[0] if muni_options else ""
elif st.session_state["selected_upper_muni"] not in muni_options and muni_options:
    st.session_state["selected_upper_muni"] = muni_options[0]

selected_muni = st.sidebar.selectbox("Select a municipality", options=muni_options, key="selected_upper_muni")

# ---------- Display mode: filter vs highlight ----------
if display_mode == "Filter to matches":
    gdf_view = gdf_match.copy()
else:
    gdf_view = gdf_all.copy()

    dim_alpha = 40

    def _dim_rgba(rgba):
        if isinstance(rgba, (list, tuple)) and len(rgba) == 4:
            return [int(rgba[0]), int(rgba[1]), int(rgba[2]), dim_alpha]
        return rgba

    nonmatch_line = [200, 200, 200, 40]

    gdf_view["__COLOR__"] = [
        (rgba if is_match else _dim_rgba(rgba))
        for rgba, is_match in zip(gdf_view["__COLOR__"].tolist(), match_mask.tolist())
    ]
    gdf_view["__LINE_COLOR__"] = [
        (lc if is_match else nonmatch_line)
        for lc, is_match in zip(gdf_view["__LINE_COLOR__"].tolist(), match_mask.tolist())
    ]

if display_mode == "Highlight matches":
    gdf_view["__LINE_WIDTH__"] = [2 if m else 1 for m in match_mask.tolist()]
else:
    gdf_view["__LINE_WIDTH__"] = 2

# ---------- Summary cards (counts reflect the matching set) ----------
counts = gdf_match["__STATUS__"].value_counts()
yes = int(counts.get("YES", 0))
no = int(counts.get("NO", 0))
na = int(counts.get("N/A", 0))

sig_counts = gdf_match["__SIGNAL__"].value_counts()
expiring = int(sig_counts.get("Expiring soon", 0))
expired = int(sig_counts.get("Expired", 0))
unknown = int(sig_counts.get("Expiry unknown", 0))

c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric("YES", f"{yes}")
c2.metric("NO", f"{no}")
c3.metric("N/A", f"{na}")
c4.metric("Expiring soon", f"{expiring}")
c5.metric("Expired", f"{expired}")
c6.metric("Expiry unknown", f"{unknown}")

st.caption(
    f"Matches: {len(gdf_match)} of {len(gdf_all)} municipalities.  "
    "Outline legend: 🟧 Expiring soon • ⬛ Expired • 🟨 Expiry unknown • ⬜ No expiry alert  •  Outline priority (if multiple signals): Expired > Expiring soon > Mentioned in minutes/agendas > Expiry unknown"
)

if gdf_match.empty:
    st.warning("No municipalities match the current filters.")

# ---------- Map ----------
geom_col = gdf_view.geometry.name

props_df = gdf_view[
    [
        name_field,
        "__STATUS__",
        "__COLOR__",
        "__EXPIRY__",
        "__SIGNAL__",
        "__BYLAW_NAME__",
        "__BYLAW_LINK__",
        "__LINE_COLOR__",
        "__LINE_WIDTH__",
        geom_col,
    ]
].copy()

geojson = json.loads(props_df.to_json())

layer = pdk.Layer(
    "GeoJsonLayer",
    data=geojson,
    pickable=True,
    stroked=True,
    filled=True,
    get_fill_color="properties.__COLOR__",
    get_line_color="properties.__LINE_COLOR__",
    get_line_width="properties.__LINE_WIDTH__",
    lineWidthUnits="pixels",
    lineWidthMinPixels=1,
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
detail_row = gdf_all[gdf_all[name_field].astype(str).eq(str(selected_muni))].head(1)
if len(detail_row) == 1:
    r = detail_row.iloc[0]

    st.sidebar.markdown(f"**Selected bylaw topic:** {selected_label}")
    st.sidebar.markdown(f"**Status:** {str(r.get('__STATUS__', 'N/A') or 'N/A')}")
    st.sidebar.markdown(f"**Expiry signal:** {str(r.get('__SIGNAL__', '') or '').strip() or '—'}")

    bylaw_name = str(r.get("__BYLAW_NAME__", "") or "").strip()
    enacted = str(r.get("__ENACTED__", "") or "").strip()
    expiry = str(r.get("__EXPIRY__", "") or "").strip()
    bylaw_link = str(r.get("__BYLAW_LINK__", "") or "").strip()

    if bylaw_name:
        st.sidebar.markdown(f"**Bylaw:** {bylaw_name}")
    if enacted and enacted != "N/A":
        st.sidebar.markdown(f"**Enacted:** {enacted}")
    if expiry and expiry != "N/A":
        st.sidebar.markdown(f"**Expiry:** {expiry}")
    if bylaw_link:
        st.sidebar.markdown(f"**Source:** {bylaw_link}")

# ---------- Legend ----------
with st.expander("Legend", expanded=False):
    st.markdown(
        "- **YES** = green  \n"
        "- **NO** = red  \n"
        "- **N/A** = gray  \n"
        "- **Other/blank** = blue  \n"
        "- **Orange outline** = expiring soon  \n"
        "- **Black outline** = expired  \n"
        "- **Yellow outline** = expiry unknown (bylaw exists)  \n"
        "- **Highlight mode** dims non-matches instead of removing them"
    )

# ---------- Results table + export ----------
with st.expander("Results (filtered) – table + export", expanded=False):
    table = gdf_match[
        [name_field, "__STATUS__", "__EXPIRY__", "__SIGNAL__", "__BYLAW_NAME__", "__BYLAW_LINK__"]
    ].copy()

    table = table.rename(
        columns={
            name_field: "Municipality",
            "__STATUS__": "Status",
            "__EXPIRY__": "Expiry",
            "__SIGNAL__": "Expiry alert",
            "__BYLAW_NAME__": "Bylaw",
            "__BYLAW_LINK__": "Bylaw link",
        }
    )

    st.dataframe(table, use_container_width=True, hide_index=True)

    csv_bytes = table.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
    st.download_button(
        "Download these results as CSV",
        data=csv_bytes,
        file_name="bylaw_map_results_upper.csv",
        mime="text/csv",
    )
