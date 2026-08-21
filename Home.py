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
        "icon": "📄",
        "name": "PDF Tools",
        "page": "pages/1_PDF_Tools.py",
        "desc": "All-in-one PDF toolkit: compress, merge, split, make booklets, "
                "convert to image/Excel, unlock, and watermark.",
    },
    {
        "icon": "🏷️",
        "name": "Shipping Labels",
        "page": "pages/2_Shipping_Labels.py",
        "desc": "Generate print-ready 78×100 mm shipping labels from a Lion Parcel "
                "shipment CSV — one page per recipient.",
    },
    {
        "icon": "📄",
        "name": "Rename BUPOT",
        "page": "pages/3_Rename_BUPOT.py",
        "desc": "Batch-rename Bukti Potong (BUPOT) tax slips to a standardized "
                "filename. Upload PDFs, pick the type, download renamed copies.",
    },
    {
        "icon": "🏦",
        "name": "Bank Statements → Xero",
        "page": "pages/4_Bank_Statements.py",
        "desc": "Convert Mandiri, BCA corporate, or BCA personal statement CSVs "
                "into a Xero-friendly import format, or extract OCBC/BCA/UOB "
                "credit-card transactions from a statement PDF.",
    },
    {
        "icon": "💸",
        "name": "Payroll → BCA",
        "page": "pages/5_Payroll_BCA.py",
        "desc": "Turn the Airtable Pay Run CSV into the BCA MultiAutoTransaksi "
                "(MultiPayroll) upload file — no more CSV → xlsx step.",
    },
    {
        "icon": "📇",
        "name": "RFID HF Reader",
        "page": "pages/6_RFID_Reader_HF.py",
        "desc": "Read RFID/NFC cards from an ESP32 + RC522 over USB. Tap a card to "
                "see its type, ID, manufacturer, memory, and NDEF/version details.",
    },
    {
        "icon": "📡",
        "name": "RFID UHF Reader — USB",
        "page": "pages/7_RFID_Reader_UHF_USB.py",
        "desc": "Plug in a USB UHF reader (R300) and scan — each tag's EPC drops "
                "into a live list. No drivers, no setup; works in any browser. "
                "EPC only (no RSSI).",
    },
    {
        "icon": "📡",
        "name": "RFID UHF Reader — ESP32",
        "page": "pages/8_RFID_Reader_UHF_ESP32.py",
        "desc": "Read UHF tags from a XIAO ESP32-C3 + M5Stack UHF unit over USB "
                "(Web Serial). Sees every tag within ~1–2 m, live, with EPC and RSSI.",
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
