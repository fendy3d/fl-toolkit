"""FL Toolkit — landing page / tool directory.

This is the Streamlit entry point. Run with:  streamlit run Home.py
"""

import streamlit as st

from auth import require_auth

st.set_page_config(page_title="FL Toolkit", page_icon="🧰", layout="centered")
require_auth()

st.title("🧰 FL Toolkit")
st.write("Internal utilities for the team. Pick a tool from the sidebar, or below.")

st.divider()

# One entry per live tool. Add a row here whenever a new page is migrated.
TOOLS = [
    {
        "icon": "🗜️",
        "name": "Compress PDF",
        "page": "pages/1_Compress_PDF.py",
        "desc": "Shrink PDF file size with Ghostscript. Upload one or more PDFs, "
                "pick a quality level, download the compressed results.",
    },
    {
        "icon": "🏷️",
        "name": "Shipping Labels",
        "page": "pages/2_Shipping_Labels.py",
        "desc": "Generate print-ready 78×100 mm shipping labels from a Lion Parcel "
                "shipment CSV — one page per recipient.",
    },
]

for tool in TOOLS:
    with st.container(border=True):
        st.subheader(f"{tool['icon']} {tool['name']}")
        st.write(tool["desc"])
        st.page_link(tool["page"], label=f"Open {tool['name']}", icon="➡️")

st.divider()
st.caption(
    "More tools coming soon. Files you upload are processed in-memory for your "
    "session only and are not stored on the server."
)
