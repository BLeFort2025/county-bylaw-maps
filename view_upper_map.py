import streamlit as st

# Set page title
st.set_page_config(page_title="Upper Tier Bylaw Exemptions Map", layout="wide")

# Embed the existing HTML file
st.markdown("## Upper Tier Bylaw Exemptions Map")
with open("Bylaw_Exemptions_Map_UpperTier.html", "r", encoding="utf-8") as f:
    html_string = f.read()