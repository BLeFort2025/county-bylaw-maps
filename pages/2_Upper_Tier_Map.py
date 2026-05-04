import os
import sys
import json
import re
from datetime import date

# When running from pages/, resolve HERE to the project root (one level up)
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import streamlit as st
import geopandas as gpd
import pydeck as pdk
import pandas as pd

from ofa_content import get_content_for_label, BYLAW_GROUP_FOR_LABEL
from letter_engine import (
    resolve_municipality_id, get_recipient_email,
    fill_letter_template, letter_to_plain_text,
    generate_mailto_link, build_email_subject, build_fields,
    log_advocacy_action, get_advocacy_stats, build_cover_email_body
)
from db_utils import get_connection

st.set_page_config(page_title="Upper Tier Bylaw Exemptions Map", layout="wide")

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


def load_signals_data():
    """Loads signals.csv and returns a dict mapping {CanonName -> [list of signal dicts]}"""
    sig_path = os.path.join(HERE, "signals", "signals.csv")
    if not os.path.exists(sig_path):
        return {}
    try:
        df = pd.read_csv(sig_path)
        # Filter to recent signals only (90 days)
        if 'date_found' in df.columns:
            df['date_found'] = pd.to_datetime(df['date_found'], errors='coerce')
            cutoff = pd.Timestamp.now() - pd.Timedelta(days=90)
            df = df[df['date_found'] >= cutoff]
        signals_map = {}
        for _, row in df.iterrows():
            cname = canon_name(str(row['munid']))
            if cname not in signals_map:
                signals_map[cname] = []
            signals_map[cname].append(row.to_dict())
        return signals_map
    except Exception as e:
        return {}

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
    # Livestock Guardian Dogs — combined LGD + HD definition, plus individual provisions
    "LGD/HD Working Dog Definition": {
        "bylaw_name": "Bylaw Name LGD",
        "bylaw_link": "Livestock Guardian Dog bylaw link",
        "enacted": "Date Bylaw Enacted 5 (Regional)",
        "expiry": "Expiry Date 5",
    },
    "LGD and HD Exempt from License Fees": {
        "bylaw_name": "Bylaw Name LGD",
        "bylaw_link": "Livestock Guardian Dog bylaw link",
        "enacted": "Date Bylaw Enacted 5 (Regional)",
        "expiry": "Expiry Date 5",
    },
    "LGD and HD Collar and Tag Requirements": {
        "bylaw_name": "Bylaw Name LGD",
        "bylaw_link": "Livestock Guardian Dog bylaw link",
        "enacted": "Date Bylaw Enacted 5 (Regional)",
        "expiry": "Expiry Date 5",
    },
    "LGD and HD Exempt from Barking Restrictions": {
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

# --- SINGLE SOURCE OF TRUTH: Map sidebar labels -> scanner categories ---
LAYER_TO_CATEGORY = {
    "Farm Exemption for Development Charges": "DC",
    "Farm Exemption for Stormwater Charges": "STORMWATER",
    "Farm Exemption for SA": "SITE_ALT",
    "Farm Exemption - Tree Cutting Bylaw": "TREES",
    "Can you Keep Backyard Chickens": "CHICKENS",
    "Licence Required": "CHICKENS",
    "Welfare Requirements": "CHICKENS",
    "Has Livestock Guardian dog Definition": "LGD",
    "LGD/HD Working Dog Definition": "LGD",
    "LGD and HD Exempt from License Fees": "LGD",
    "LGD and HD Collar and Tag Requirements": "LGD",
    "LGD and HD Exempt from Barking Restrictions": "LGD",
    "Farm Exemption for Security fencing prohibitions": "FENCES",
    "Farm Exemption for Electrified fencing prohibitions": "FENCES",
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

    def _line_color_for_signal(sig: str) -> list[int]:
        if sig == "Expiring soon":
            return [255, 165, 0, 255]  # orange
        if sig == "Expired":
            return [0, 0, 0, 255]  # black
        return [60, 60, 60, 255]  # default gray

    line_color = signal.apply(_line_color_for_signal)

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

# --- SIGNALS INTEGRATION ---
signals_data = load_signals_data()
def check_signal(name_val):
    return canon_name(name_val) in signals_data

if name_field in gdf.columns:
    gdf["HAS_SIGNAL"] = gdf[name_field].apply(check_signal)
else:
    gdf["HAS_SIGNAL"] = False

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
filter_signals = st.sidebar.checkbox("🚨 Filter to Scanner Signals", value=False)
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

# --- Scanner Signal Filter ---
if filter_signals:
    signal_mask = gdf_all["HAS_SIGNAL"].eq(True)
    target_category = LAYER_TO_CATEGORY.get(selected_label, None)
    if target_category and signals_data:
        cat_mask = pd.Series(False, index=gdf_all.index)
        for i, row in gdf_all.iterrows():
            cname = canon_name(str(row[name_field]))
            if cname in signals_data:
                if any(h.get('category') == target_category for h in signals_data[cname]):
                    cat_mask.loc[i] = True
        match_mask &= cat_mask
    else:
        match_mask &= signal_mask

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
# COLOR LOGIC: Priority-based borders
def get_border_color(row):
    sig = row.get("__SIGNAL__")
    if sig == "Expired":
        return [0, 0, 0, 255]         # Black
    if sig == "Expiring soon":
        return [255, 165, 0, 255]     # Orange
    if sig == "Expiry unknown":
        return [255, 255, 0, 255]     # Yellow
    # Category-aware scanner signal border
    if row.get("HAS_SIGNAL") == True:
        cname = canon_name(str(row.get(name_field, "")))
        if cname in signals_data:
            current_map_category = LAYER_TO_CATEGORY.get(selected_label, None)
            if current_map_category:
                if any(h.get('category') == current_map_category for h in signals_data[cname]):
                    return [255, 69, 0, 255]   # Red-Orange (matches current layer)
            else:
                return [255, 69, 0, 255]       # Red-Orange (no category filter)
    return [100, 100, 100, 100]       # Grey

gdf_view["__BORDER_COLOR__"] = gdf_view.apply(get_border_color, axis=1)

geom_col = gdf_view.geometry.name
props_df = gdf_view[[name_field, "__STATUS__", "__COLOR__", "__EXPIRY__", "__SIGNAL__", "__BYLAW_NAME__", "__BYLAW_LINK__", "__BORDER_COLOR__", "__LINE_WIDTH__", geom_col]].copy()
geojson = json.loads(props_df.to_json())

layer = pdk.Layer(
    "GeoJsonLayer",
    geojson,
    pickable=True,
    opacity=0.5,
    stroked=True,
    filled=True,
    extruded=False,
    wireframe=True,
    get_fill_color="properties.__COLOR__",
    get_line_color="properties.__BORDER_COLOR__",
    lineWidthMinPixels=2,          # <--- Crisp borders
    auto_highlight=True,
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

    # --- Scanner Evidence Panel ---
    cname_selected = canon_name(str(selected_muni))
    if cname_selected in signals_data:
        hits_list = signals_data[cname_selected]
        target_category = LAYER_TO_CATEGORY.get(selected_label, None)
        
        target_hit = None
        if target_category:
            for h in hits_list:
                if h.get('category') == target_category:
                    target_hit = h
                    break
        if target_hit is None and hits_list:
            target_hit = hits_list[0]
        
        if target_hit:
            st.sidebar.divider()
            st.sidebar.markdown("### 🚨 Scanner Evidence Found")
            trigger = target_hit.get('trigger_keyword', 'N/A')
            date_found = target_hit.get('date_found', 'N/A')
            snippet = target_hit.get('snippet', '')
            url = target_hit.get('url', '')
            
            st.sidebar.markdown(f"**Trigger word:** `{trigger}`")
            st.sidebar.markdown(f"**Date found:** {date_found}")
            if snippet:
                st.sidebar.info(f"**Context:** _{snippet[:300]}..._" if len(str(snippet)) > 300 else f"**Context:** _{snippet}_")
            if url:
                st.sidebar.markdown(f"[View Source Document]({url})")

# ---------- OFA position + template letter + advocacy panel ----------
content = get_content_for_label(selected_label)

if content is not None:
    st.subheader(content.title)
    st.markdown(content.body_md)

    if content.letter_path:
        template_path = os.path.join(HERE, content.letter_path)
        if os.path.exists(template_path):
            with open(template_path, "rb") as f:
                st.download_button(
                    label="📄 Download blank template letter (.docx)",
                    data=f,
                    file_name=os.path.basename(template_path),
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )

            # ── Advocacy Letter Panel (only for municipalities WITHOUT an exemption) ──
            upper_muni_status = ""
            if len(detail_row) == 1:
                upper_muni_status = str(detail_row.iloc[0].get("__STATUS__", "") or "").strip().upper()

            if upper_muni_status == "YES":
                st.success(
                    f"✅ **{selected_muni}** already has a farm exemption for this bylaw. "
                    "No advocacy letter needed!"
                )
            elif upper_muni_status in ("NO", "NOT KNOWN", ""):
                with st.expander("✉️ Send Personalized Advocacy Letter", expanded=False):
                    st.markdown(
                        "Fill in your details below to generate a **personalized advocacy letter** "
                        "addressed to this municipality's clerk office. You can preview, download the "
                        "editable Word document, and open it directly in your email client."
                    )

                    # Persist user details in session state across municipality changes
                    for _key in ["advocacy_name", "advocacy_title", "advocacy_federation",
                                 "advocacy_email", "advocacy_phone"]:
                        if _key not in st.session_state:
                            st.session_state[_key] = ""

                    col_a, col_b = st.columns(2)
                    with col_a:
                        adv_name = st.text_input("Your Name *", value=st.session_state["advocacy_name"],
                                                 key="upper_adv_name", placeholder="e.g., John Smith")
                        adv_title = st.text_input("Your Title / Position *", value=st.session_state["advocacy_title"],
                                                  key="upper_adv_title", placeholder="e.g., President")
                        adv_federation = st.text_input("Organization / Affiliation (e.g., County Federation, Commodity Group, OFA Member) *",
                                                       value=st.session_state["upper_adv_federation"],
                                                       key="upper_adv_fed_input", placeholder="e.g., Huron County Federation of Agriculture")
                    with col_b:
                        adv_email = st.text_input("Your Contact Email (optional)",
                                                  value=st.session_state["advocacy_email"],
                                                  key="upper_adv_email", placeholder="e.g., john@example.com")
                        adv_phone = st.text_input("Your Contact Phone (optional)",
                                                  value=st.session_state["advocacy_phone"],
                                                  key="upper_adv_phone", placeholder="e.g., (519) 555-1234")

                    # Save to session state
                    st.session_state["advocacy_name"] = adv_name
                    st.session_state["advocacy_title"] = adv_title
                    st.session_state["advocacy_federation"] = adv_federation
                    st.session_state["advocacy_email"] = adv_email
                    st.session_state["advocacy_phone"] = adv_phone

                    # Build contact info string
                    contact_parts = []
                    if adv_email:
                        contact_parts.append(adv_email)
                    if adv_phone:
                        contact_parts.append(adv_phone)
                    contact_info = " | ".join(contact_parts) if contact_parts else ""

                    # Auto-populated municipality info
                    st.markdown("---")
                    muni_display = str(selected_muni)
                    bylaw_group = BYLAW_GROUP_FOR_LABEL.get(selected_label, selected_label)

                    # Resolve recipient from database
                    recipient_info = {"email": None, "contact_name": None}
                    muni_id = None
                    try:
                        db_conn = get_connection()
                        muni_id = resolve_municipality_id(db_conn, muni_display)
                        if muni_id:
                            recipient_info = get_recipient_email(db_conn, muni_id, muni_display)
                        db_conn.close()
                    except Exception:
                        pass

                    # Show auto-populated info
                    info_col1, info_col2 = st.columns(2)
                    with info_col1:
                        st.markdown(f"**Municipality:** {muni_display}")
                        st.markdown(f"**Bylaw Topic:** {bylaw_group}")
                    with info_col2:
                        if recipient_info["email"]:
                            st.markdown(f"**Recipient:** {recipient_info['email']}")
                        else:
                            st.warning("⚠️ No clerk email found in database for this municipality.")
                            manual_email = st.text_input("Enter recipient email manually:",
                                                         key="upper_manual_email",
                                                         placeholder="e.g., clerk@municipality.ca")
                            if manual_email:
                                recipient_info["email"] = manual_email

                    # Get the bylaw name from the sidebar detail row
                    upper_detail_row = gdf_all[gdf_all[name_field].astype(str).eq(str(selected_muni))].head(1)
                    detail_bylaw_name = ""
                    if len(upper_detail_row) == 1:
                        raw_bylaw = str(upper_detail_row.iloc[0].get("__BYLAW_NAME__", "") or "").strip()
                        # Remove any parenthetical notes e.g. "(amended by...)" to sound more natural in letters
                        detail_bylaw_name = re.sub(r'\s*\(.*?\)', '', raw_bylaw).strip()

                    # Validation
                    required_filled = all([adv_name.strip(), adv_title.strip(), adv_federation.strip()])

                    if not required_filled:
                        st.info("Please fill in all required fields (*) above to generate your letter.")
                    else:
                        # Build the template fields
                        fields = build_fields(
                            sender_name=adv_name,
                            sender_title=adv_title,
                            county_federation=adv_federation,
                            contact_info=contact_info,
                            municipality_name=muni_display,
                            bylaw_name=detail_bylaw_name,
                            address=recipient_info.get("address", ""),
                        )

                        # ── Preview ──
                        if st.button("👁️ Preview Letter", key="upper_preview_btn"):
                            preview_text = letter_to_plain_text(template_path, fields)
                            st.session_state["upper_letter_preview"] = preview_text

                        if st.session_state.get("upper_letter_preview"):
                            st.markdown("---")
                            st.markdown("**Letter Preview:**")
                            st.text_area("Letter preview", value=st.session_state["upper_letter_preview"],
                                         height=400, disabled=True, key="upper_preview_area",
                                         label_visibility="collapsed")

                        # ── Download personalized .docx ──
                        st.markdown("---")
                        personalized_doc = fill_letter_template(template_path, fields)
                        safe_muni = re.sub(r'[^\w\s-]', '', muni_display).strip().replace(' ', '_')
                        doc_filename = f"Advocacy_Letter_{safe_muni}_{bylaw_group.replace(' ', '_')}.docx"

                        if st.download_button(
                            label="📥 Download Personalized Letter (.docx)",
                            data=personalized_doc,
                            file_name=doc_filename,
                            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                            key="upper_dl_letter",
                        ):
                            try:
                                log_conn = get_connection()
                                log_advocacy_action(
                                    log_conn, muni_id, muni_display, bylaw_group,
                                    recipient_info.get("email"), adv_name, adv_federation,
                                    "letter_downloaded"
                                )
                                log_conn.close()
                            except Exception:
                                pass
                        st.caption("This Word document is fully editable — make any customizations before sending.")

                        # ── Open in Email Client (mailto:) ──
                        if recipient_info["email"]:
                            st.markdown("---")
                            st.warning(
                                "⚠️ **IMPORTANT:** Browser security prevents automatically attaching files to emails. "
                                "When the email draft opens, you **MUST manually attach the downloaded `.docx` file** before sending.",
                                icon="⚠️"
                            )
                            
                            subject = build_email_subject(muni_display, bylaw_group)
                            cover_body_text = build_cover_email_body(
                                adv_name, adv_title, adv_federation, muni_display, bylaw_group
                            )
                            mailto_url = generate_mailto_link(recipient_info["email"], subject, cover_body_text)

                            if st.download_button(
                                label="📧 Generate Letter & Open Email Draft",
                                data=personalized_doc,
                                file_name=doc_filename,
                                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                key="upper_mailto_btn"
                            ):
                                try:
                                    log_conn = get_connection()
                                    log_advocacy_action(
                                        log_conn, muni_id, muni_display, bylaw_group,
                                        recipient_info["email"], adv_name, adv_federation,
                                        "mailto_opened"
                                    )
                                    log_conn.close()
                                except Exception:
                                    pass
                                st.markdown(
                                    f'<meta http-equiv="refresh" content="0;url={mailto_url}">',
                                    unsafe_allow_html=True,
                                )
                                st.success(f"Opening email to {recipient_info['email']}... Don't forget to attach the document!")
                            
                            st.caption(
                                f"**Recipient:** {recipient_info['email']}  \n"
                                "This will open your default email client (Outlook, Gmail, etc.) with the "
                                "letter pre-filled. **Remember to attach the downloaded .docx file** for "
                                "the clerk's records."
                            )
                        else:
                            st.warning(
                                "No recipient email available. Please download the letter and send it manually."
                            )

                    # ── Usage Stats ──
                    st.markdown("---")
                    st.markdown("#### 📊 Advocacy Tool Usage")
                    try:
                        stats_conn = get_connection()
                        stats = get_advocacy_stats(stats_conn)
                        stats_conn.close()

                        if stats["total_actions"] == 0:
                            st.caption("No advocacy letters have been generated yet. Be the first!")
                        else:
                            sc1, sc2, sc3 = st.columns(3)
                            sc1.metric("Letters Generated", stats["total_downloads"])
                            sc2.metric("Emails Opened", stats["total_emails"])
                            sc3.metric("Municipalities Contacted", stats["municipalities_contacted"])

                            if stats["by_municipality"]:
                                import pandas as _pd
                                muni_df = _pd.DataFrame(stats["by_municipality"])
                                muni_df.columns = ["Municipality", "Letters"]
                                st.dataframe(muni_df, use_container_width=True, hide_index=True)

                            if stats["recent"]:
                                with st.expander("Recent activity", expanded=False):
                                    recent_df = _pd.DataFrame(stats["recent"])
                                    st.dataframe(recent_df, use_container_width=True, hide_index=True)
                    except Exception:
                        st.caption("Usage tracking will appear here after your first letter.")

            else:
                st.info(
                    f"ℹ️ **{selected_muni}** has a status of **N/A** for this bylaw category. "
                    "This means the bylaw is not applicable to this municipality, so no advocacy letter is needed."
                )

        else:
            st.info(
                "A template letter is expected for this bylaw, but the .docx file is not present in the repository."
            )
    else:
        st.info("A template letter for this bylaw type is not currently available.")

# --- Export Scanner Results ---
st.sidebar.divider()
st.sidebar.subheader("🚨 Export Scanner Results")
report_mode = st.sidebar.radio("Content:", ["Current View Only", "All Scanner Hits"], key="upper_report_mode")
if st.sidebar.button("Generate CSV Report", key="upper_csv_btn"):
    all_hits = []
    for cname, muni_hits in signals_data.items():
        all_hits.extend(muni_hits)
    
    filtered_hits = []
    for hit in all_hits:
        keep = False
        if report_mode == "All Scanner Hits":
            keep = True
        else:
            if hit.get('category') == LAYER_TO_CATEGORY.get(selected_label):
                keep = True
        if keep:
            filtered_hits.append(hit)
    
    if filtered_hits:
        export_df = pd.DataFrame(filtered_hits)
        csv_bytes = export_df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
        st.sidebar.download_button(
            f"⬇️ Download {len(filtered_hits)} Scanner Results",
            data=csv_bytes,
            file_name="scanner_results_upper.csv",
            mime="text/csv",
            key="upper_scanner_dl"
        )
    else:
        st.sidebar.info("No scanner results match the current view.")

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
        "- **Red-orange outline** = mentioned in recent council minutes/agendas  \n"
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
