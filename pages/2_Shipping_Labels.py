"""Shipping Labels — migrated from the `uniqlo-lionParcel` repo.

Preserves the original fpdf2 label-layout logic (78×100 mm label, one page per
recipient, last-4-phone-digits box in the top-right corner, centered content
block) but swaps CSV-path in / PDF-path out for Streamlit widgets.

Reads a Lion Parcel shipment export CSV and produces a print-ready PDF of
labels. Only these columns are used:
    Nama Penerima, Telepon Penerima, Kecamatan, Alamat Penerima

Python deps: pandas, fpdf2. Font asset: assets/Glyseric.otf.
"""

from __future__ import annotations

import io
from pathlib import Path

import pandas as pd
import streamlit as st
from fpdf import FPDF

from auth import require_auth

st.set_page_config(page_title="Shipping Labels · FL Toolkit", page_icon="🏷️")
require_auth()

# Font shipped with the repo (single style, used for all label text).
FONT_PATH = str(Path(__file__).resolve().parent.parent / "assets" / "Glyseric.otf")
TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "assets" / "shipment_template.csv"

REQUIRED_COLS = ["Nama Penerima", "Telepon Penerima", "Kecamatan", "Alamat Penerima"]


# ── Label generation (ported from uniqlo-lionParcel) ─────────────────────────

def wrap_text(pdf: FPDF, text: str, max_width_mm: float) -> list[str]:
    """Manually wrap text to fit within max_width_mm."""
    words = text.split()
    lines: list[str] = []
    current_line = ""
    for word in words:
        test_line = (current_line + " " + word).strip()
        if pdf.get_string_width(test_line) <= max_width_mm:
            current_line = test_line
        else:
            if current_line:
                lines.append(current_line)
            current_line = word
    if current_line:
        lines.append(current_line)
    return lines


def generate_labels_pdf(df: pd.DataFrame, sender_label: str) -> bytes:
    """Build the labels PDF from `df` and return it as bytes."""
    page_w, page_h = 78, 100
    margin_x = 6
    margin_top = 16  # start below the last-4-digits box so text never overlaps it
    line_h = 6
    font_size = 11

    pdf = FPDF(unit="mm", format=(page_w, page_h))
    pdf.set_auto_page_break(auto=False)
    pdf.add_font("Glyseric", "", FONT_PATH)

    for _, row in df.iterrows():
        pdf.add_page()

        phone_str = str(row["Telepon Penerima"])
        last4 = phone_str[-4:]

        # --- Last 4 digits box (top-right corner) ---
        box_font_size = 16
        pdf.set_font("Glyseric", size=box_font_size)
        pad_x, pad_y = 4, 3
        text_w = pdf.get_string_width(last4)
        text_h = box_font_size * 0.352778 * 0.7  # approx cap height in mm
        box_w = text_w + 2 * pad_x
        box_h = text_h + 2 * pad_y
        box_x = page_w - margin_x - box_w
        box_y = 3

        pdf.set_line_width(0.7)
        pdf.rect(box_x, box_y, box_w, box_h)
        text_x = box_x + (box_w - text_w) / 2
        text_y = box_y + (box_h - text_h) / 2
        pdf.set_xy(text_x, text_y)
        pdf.cell(text_w, text_h, last4, align="C")

        # --- Main label content (centered block) ---
        max_text_w = page_w - 2 * margin_x
        records: list[tuple[str, int, float, float]] = []

        def add_label_value(label: str, value) -> None:
            pdf.set_font("Glyseric", size=font_size)
            indent = pdf.get_string_width(label)
            lines = wrap_text(pdf, label + str(value), max_text_w)
            for i, line in enumerate(lines):
                ind = 0 if i == 0 else indent
                if ind and pdf.get_string_width(line) > max_text_w - ind:
                    ind = 0
                records.append((line, font_size, ind, 0))

        add_label_value("Nama: ", row["Nama Penerima"])
        add_label_value("No HP: ", row["Telepon Penerima"])
        add_label_value("Kecamatan: ", row["Kecamatan"])

        records.append(("Alamat lengkap:", font_size, 0, 0))
        pdf.set_font("Glyseric", size=font_size)
        for line in wrap_text(pdf, str(row["Alamat Penerima"]), max_text_w):
            records.append((line, font_size, 0, 0))

        records.append((f"From: {sender_label}", 10, 0, line_h * 1.5))

        # Pass 1: widest line → block width.
        block_w = 0.0
        for text, size, indent, _ in records:
            pdf.set_font("Glyseric", size=size)
            block_w = max(block_w, indent + pdf.get_string_width(text))
        block_x = max(margin_x, (page_w - block_w) / 2)

        # Pass 2: render.
        y = margin_top
        for text, size, indent, gap_before in records:
            y += gap_before
            pdf.set_font("Glyseric", size=size)
            pdf.set_xy(block_x + indent, y)
            pdf.cell(0, line_h, text)
            y += line_h

    return bytes(pdf.output())


def read_csv_any_encoding(data: bytes) -> pd.DataFrame:
    """Decode a CSV trying several encodings (matches the original script)."""
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return pd.read_csv(io.BytesIO(data), encoding=encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("Could not decode the CSV file. Please save it as UTF-8.")


# ── UI ───────────────────────────────────────────────────────────────────────

st.title("🏷️ Shipping Labels")
st.write("Upload a Lion Parcel shipment CSV and generate a print-ready PDF of "
         "78×100 mm labels — one page per recipient.")

with st.expander("What CSV do I need?"):
    st.write("A CSV containing at least these columns: "
             f"{', '.join('`' + c + '`' for c in REQUIRED_COLS)}. "
             "A standard Lion Parcel export already has them.")
    st.download_button(
        "⬇️ Download template CSV",
        data=TEMPLATE_PATH.read_bytes(),
        file_name="shipment_template.csv",
        mime="text/csv",
    )

uploaded = st.file_uploader("Shipment CSV", type="csv")
sender_label = st.text_input("Sender label (printed as “From: …”)", value="Euniqeu Jastip")

if uploaded is not None:
    try:
        df = read_csv_any_encoding(uploaded.getvalue())
    except ValueError as exc:
        st.error(f"❌ {exc}")
        st.stop()

    missing = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing:
        st.error(f"❌ CSV is missing required column(s): {', '.join(missing)}.\n\n"
                 f"Found: {', '.join(df.columns)}")
        st.stop()

    # Drop rows with no recipient name (e.g. trailing blank lines).
    df = df[df["Nama Penerima"].notna() & (df["Nama Penerima"].astype(str).str.strip() != "")]
    st.success(f"✅ Loaded {len(df)} recipient(s).")
    st.dataframe(df[REQUIRED_COLS], use_container_width=True, hide_index=True)

    if st.button("Generate labels", type="primary", disabled=df.empty):
        with st.spinner("Building PDF…"):
            pdf_bytes = generate_labels_pdf(df, sender_label.strip() or "Euniqeu Jastip")
        st.session_state["labels_pdf"] = pdf_bytes
        st.session_state["labels_count"] = len(df)

pdf_bytes = st.session_state.get("labels_pdf")
if pdf_bytes:
    st.divider()
    st.download_button(
        f"⬇️ Download {st.session_state.get('labels_count', 0)} label(s) (PDF)",
        data=pdf_bytes,
        file_name="shipment_labels.pdf",
        mime="application/pdf",
        type="primary",
    )
