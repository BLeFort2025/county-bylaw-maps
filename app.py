import streamlit as st

st.set_page_config(
    page_title="Ontario Municipal Bylaw Database",
    page_icon="🏛️",
    layout="wide",
)

st.title("🏛️ Ontario Municipal Bylaw Database")
st.subheader("Ontario Federation of Agriculture – Intelligence Engine")

st.markdown("""
Welcome to the **Municipal Bylaw Database & Interactive Map**. This tool tracks
agricultural exemptions, policy changes and specific municipal bylaws across
Ontario's 444 municipalities.

### 🗺️ Choose a Map

Use the **sidebar** on the left to navigate between the two map views:

| Page | What it shows |
|------|--------------|
| **Lower Tier Map** | All 414 lower-tier (local) municipalities — towns, townships, cities |
| **Upper Tier Map** | All 33 upper-tier (regional) municipalities — counties, regions, districts |

### 🚨 Intelligence Engine

The weekly scanner automatically searches municipal council agendas and minutes
for keywords related to bylaw changes that may affect farmers. Municipalities
with recent scanner hits are highlighted with a **red-orange border** on the map.

### Quick Links
- Toggle the **🚨 Filter to Scanner Signals** checkbox to see only municipalities
  with recent scanner activity
- Use the **Expiry alert** dropdown to find bylaws that are expiring soon
- Click any municipality on the map to view detailed bylaw information in the sidebar
""")

st.divider()
st.caption("Built for the Ontario Federation of Agriculture · Data updated weekly")
