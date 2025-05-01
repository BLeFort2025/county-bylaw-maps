import streamlit as st
import streamlit.components.v1 as components
import os

# Set page title
st.set_page_config(page_title="Upper Tier Bylaw Exemptions Map", layout="wide")

st.title("Upper Tier Bylaw Exemptions Map")

# Use the filename (it's inside the same folder as this script)
html_file_path = os.path.join(os.path.dirname(__file__), "Bylaw_Exemptions_Map_UpperTier.html")

# Read the HTML content
with open(html_file_path, "r", encoding="utf-8") as f:
    html_content = f.read()

# Render the HTML in the app
components.html(html_content, height=800, scrolling=True)
