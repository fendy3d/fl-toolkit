"""RFID Reader (UHF) — scan UHF (EPC Gen2) tags with a plug-in USB reader (R300).

The R300 is a USB "keyboard-wedge" reader: plugged into USB it enumerates as a
keyboard and simply *types* each scanned tag's EPC. So this page is just a focused
scan box — click it, scan a tag, and each EPC drops into the live list. No ESP32,
no firmware, no drivers, no Web Serial — and it works in any browser.

Nothing is sent to the server: the reader types straight into the page.
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from auth import require_auth

st.set_page_config(page_title="RFID UHF (USB) · FL Toolkit", page_icon="📡", layout="centered")
require_auth()

ASSETS = Path(__file__).resolve().parent.parent / "assets"
READER_HTML = (ASSETS / "rfid_reader_uhf.html").read_text(encoding="utf-8")

st.title("📡 RFID UHF Reader — USB (plug & scan)")
st.write("Plug your **R300 USB UHF reader** into the computer, click the scan box "
         "below, and scan a UHF tag to see its **EPC** — each new tag drops into the "
         "live list. UHF reads at a distance (~1–2 m).")
st.info("🔌 The R300 acts as a **keyboard** — it types each tag's EPC into the box. "
        "No drivers, no setup, no ESP32; works in any browser. Nothing is sent to "
        "the server.")

with st.expander("ℹ️ How to use"):
    st.markdown(
        "1. **Plug in** the R300 UHF reader (USB). macOS/Windows recognise it as a "
        "keyboard automatically — no driver.\n"
        "2. **Click the scan box** below so it's focused (the border turns solid and "
        "the status shows *Ready — scan a tag*).\n"
        "3. **Scan a UHF tag.** Its EPC appears as the latest tag and is added to the "
        "**Tags scanned** list (with read count and first/last-seen times).\n\n"
        "**Tips**\n"
        "- Keep the scan box focused — clicking elsewhere on this page re-focuses it "
        "automatically, but clicking outside the app (another window) will send the "
        "scan there instead.\n"
        "- The reader only reports the **EPC** (its keyboard mode doesn't send signal "
        "strength). For RSSI/read-power you'd need the reader in serial mode.\n"
        "- Tags are **UHF** (860–960 MHz, EPC Gen2 / ISO 18000-6C) — asset/warehouse "
        "labels, **not** 13.56 MHz MIFARE/NFC cards (use the HF reader for those)."
    )

st.subheader("Reader")
components.html(READER_HTML, height=560, scrolling=True)

st.download_button("⬇️ Download standalone scanner (open in any browser)", data=READER_HTML,
                   file_name="rfid_reader_uhf.html", mime="text/html")
