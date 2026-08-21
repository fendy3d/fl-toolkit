"""RFID Reader (UHF) — read UHF (EPC Gen2) tags from a XIAO ESP32-C3 + R300 UHF
RFID module over USB.

The reading happens entirely in your browser via
the Web Serial API (Chrome or Edge on desktop) — tag data goes straight from
the USB device to this page. Nothing is sent to the server, and no Python
serial driver is involved.

Because browsers block serial access inside embedded frames, the reader below
falls back to an "open in a new tab" button when needed; that new tab is the
same page running top-level, where USB access is allowed.

Hardware: Seeed XIAO ESP32-C3 + R300 UHF RFID module (R200/JRD-4035 family,
860–960 MHz). Firmware and wiring are in the expander below. No extra Python deps.
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from auth import require_auth

st.set_page_config(page_title="RFID UHF Reader · FL Toolkit", page_icon="📡", layout="centered")
require_auth()

ASSETS = Path(__file__).resolve().parent.parent / "assets"
READER_HTML = (ASSETS / "rfid_reader_uhf.html").read_text(encoding="utf-8")
FIRMWARE = (ASSETS / "rfid_xiao_uhf.ino").read_text(encoding="utf-8")

st.title("📡 RFID UHF Reader")
st.write("Plug in your **XIAO ESP32-C3 + R300 UHF RFID module** over USB, connect "
         "below, and bring a UHF tag in range to see its **EPC**, signal strength "
         "(RSSI), and read count — live. UHF reads at a distance (~1–2 m) and "
         "picks up **every** tag in range at once.")
st.info("🔒 Tag data goes straight from USB to your browser (Web Serial). It never "
        "reaches the server. Works in **Chrome or Edge on desktop**.")

with st.expander("🔌 Hardware wiring & firmware (do this once)"):
    st.markdown(
        "**Parts:** Seeed XIAO ESP32-C3 · R300 UHF RFID module · breadboard · "
        "4 jumper wires (the R300 exposes VCC / GND / TXD / RXD header pins).\n\n"
        "**Wiring — R300 module → XIAO ESP32-C3.** The R300 talks plain UART at "
        "115200 baud (same R200/JRD-4035 protocol), so it's just four wires:\n\n"
        "| R300 pin | XIAO ESP32-C3 pin |\n"
        "|---|---|\n"
        "| GND | GND |\n"
        "| VCC | **5V** (or **3V3** — match your R300's rated voltage) |\n"
        "| TXD (R300 data out) | **D7** (GPIO20, RX) |\n"
        "| RXD (R300 data in) | **D6** (GPIO21, TX) |\n\n"
        "D6/D7 are the two pins at the bottom of the right-hand column, just above "
        "5V/GND.\n\n"
        "**Good to know:**\n"
        "- **Power / voltage:** match VCC to your R300's rating — **check the number "
        "printed on the board** (many R300 boards accept 3.3–5 V). The XIAO's 5V pin "
        "is USB passthrough. UHF transmit pulls current in bursts, so if the module "
        "resets or misses reads, feed it a solid **5 V** supply rather than USB "
        "passthrough.\n"
        "- **Logic levels:** the R300's UART is **3.3 V logic** — safe with the "
        "XIAO, no level shifter needed.\n"
        "- **No data?** The single most likely cause is TXD/RXD being swapped. Flip "
        "them — it won't damage anything.\n\n"
        "**Flash the firmware (Arduino IDE, once):**\n"
        "1. Install the **esp32** boards package (Boards Manager) and select "
        "**XIAO_ESP32C3**.\n"
        "2. Check Tools → **USB CDC On Boot: Enabled** (default for this board).\n"
        "3. Open the sketch below and **Upload**. No extra libraries needed.\n"
    )
    st.download_button("⬇️ Download firmware (rfid_xiao_uhf.ino)", data=FIRMWARE,
                       file_name="rfid_xiao_uhf.ino", mime="text/plain")
    with st.expander("View firmware source"):
        st.code(FIRMWARE, language="cpp")

st.subheader("Reader")
components.html(READER_HTML, height=680, scrolling=True)

st.caption("Tip: if the **Connect** button does nothing in this embedded view, use "
           "“Open reader in a new tab” above it, or download the standalone reader "
           "and open it in Chrome.")
st.download_button("⬇️ Download standalone reader (open in Chrome)", data=READER_HTML,
                   file_name="rfid_reader_uhf.html", mime="text/html")

with st.expander("What you'll see"):
    st.markdown(
        "- **Latest tag:** its EPC (the tag's unique identity, usually 96-bit), "
        "signal strength (RSSI), PC word, and CRC.\n"
        "- **Tags in range:** a live table of every tag the reader can see — EPC, "
        "bit length, RSSI, total reads, and **first/last read timestamps**. Tags "
        "dim after 3 s out of range.\n"
        "- **Read rate:** the dropdown in the toolbar sets how often the reader "
        "polls — Default (0.15 s), 0.1 s, 0.5 s, or 1 s. It applies on connect "
        "and resets to Default when the reader is unplugged or rebooted.\n"
        "- **Range:** roughly 1–2 m with the R300's onboard antenna, more if your "
        "board has a u.FL connector and you fit an external UHF antenna. RSSI closer "
        "to 0 (e.g. −35 dBm) means the tag is near; −70 dBm and below means it's "
        "at the edge of range.\n"
        "- This reads **UHF** (860–960 MHz, EPC Gen2 / ISO 18000-6C) tags — "
        "warehouse/asset/library-style labels — **not** 13.56 MHz MIFARE/NFC cards."
    )
