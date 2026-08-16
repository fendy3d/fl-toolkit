"""RFID Reader — read RFID/NFC cards from an ESP32 + RC522 over USB.

The reading happens entirely in your browser via the Web Serial API (Chrome or
Edge on desktop) — the card data goes straight from the USB device to this page.
Nothing is sent to the server, and no Python serial driver is involved.

Because browsers block serial access inside embedded frames, the reader below
falls back to an "open in a new tab" button when needed; that new tab is the same
page running top-level, where USB access is allowed.

Hardware: ESP32 + RC522 (MFRC522, 13.56 MHz). Firmware and wiring are in the
expander below. No extra Python deps (all client-side).
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from auth import require_auth

st.set_page_config(page_title="RFID Reader · FL Toolkit", page_icon="📇", layout="centered")
require_auth()

ASSETS = Path(__file__).resolve().parent.parent / "assets"
READER_HTML = (ASSETS / "rfid_reader.html").read_text(encoding="utf-8")
FIRMWARE = (ASSETS / "rfid_esp32_rc522.ino").read_text(encoding="utf-8")

st.title("📇 RFID Reader")
st.write("Plug in your **ESP32 + RC522** over USB, connect below, and tap a card to "
         "see its UID, type, and full MIFARE Classic memory dump — live.")
st.info("🔒 Card data goes straight from USB to your browser (Web Serial). It never "
        "reaches the server. Works in **Chrome or Edge on desktop**.")

with st.expander("🔌 Hardware wiring & firmware (do this once)"):
    st.markdown(
        "**Wiring — RC522 → ESP32.**  ⚠️ The RC522 is a **3.3 V** module — never wire "
        "it to 5 V.\n\n"
        "| RC522 pin | ESP32 pin |\n"
        "|---|---|\n"
        "| SDA / SS | GPIO 5 |\n"
        "| SCK | GPIO 18 |\n"
        "| MOSI | GPIO 23 |\n"
        "| MISO | GPIO 19 |\n"
        "| RST | GPIO 22 |\n"
        "| 3.3V | 3V3 |\n"
        "| GND | GND |\n\n"
        "**Flash the firmware (Arduino IDE, once):**\n"
        "1. Install the **esp32** boards package (Boards Manager) and select your board.\n"
        "2. Install the **MFRC522** library by GithubCommunity (Library Manager).\n"
        "3. Open the sketch below and **Upload**.\n"
    )
    st.download_button("⬇️ Download firmware (rfid_esp32_rc522.ino)", data=FIRMWARE,
                       file_name="rfid_esp32_rc522.ino", mime="text/plain")
    with st.expander("View firmware source"):
        st.code(FIRMWARE, language="cpp")

st.subheader("Reader")
components.html(READER_HTML, height=680, scrolling=True)

st.caption("Tip: if the **Connect** button does nothing in this embedded view, use "
           "“Open reader in a new tab” above it, or download the standalone reader "
           "and open it in Chrome.")
st.download_button("⬇️ Download standalone reader (open in Chrome)", data=READER_HTML,
                   file_name="rfid_reader.html", mime="text/html")

with st.expander("Notes on the full dump"):
    st.markdown(
        "- The firmware tries the **factory-default key** `FF FF FF FF FF FF` on every "
        "sector. Sectors protected with a different key show as **locked** — that's "
        "expected; the card won't reveal them without the correct key.\n"
        "- **Sector-trailer** blocks (🔑) hold the keys and access bits. Cards always "
        "return key bytes as zeros, so you'll never see the actual keys.\n"
        "- Only **MIFARE Classic** (Mini / 1K / 4K) has a readable sector dump. Other "
        "card types (Ultralight, NTAG, etc.) show UID + type only."
    )
