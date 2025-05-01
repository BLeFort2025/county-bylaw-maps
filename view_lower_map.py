import streamlit as st

# Set page title
st.set_page_config(page_title="Lower Tier Bylaw Exemptions Map", layout="wide")

# Embed the existing HTML file
st.markdown("## Lower Tier Bylaw Exemptions Map")
with open("Bylaw_Exemptions_Map_LowerTier.html", "r", encoding="utf-8") as f:
    html_string = f.read()
st.components.v1.html(html_string, height=800, scrolling=True)
