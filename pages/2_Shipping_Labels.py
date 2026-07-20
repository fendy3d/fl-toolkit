"""Shipping Labels — migrated from the `uniqlo-lionParcel` repo.

Preserves the original fpdf2 label-layout logic (78×100 mm label, one page per
recipient, last-4-phone-digits box in the top-right corner, centered content
block) but swaps CSV-path in / PDF-path out for Streamlit widgets.

Reads a Lion Parcel / JNT VIP shipment export CSV. Required columns:
    Nama Penerima, Telepon Penerima, Kecamatan, Alamat Penerima
Optional columns (printed when present):
    Kota / kabupaten, kode pos, Pakai Asuransi?

Column names are matched case-insensitively with flexible spacing, so both the
older and newer export layouts work.

Python deps: pandas, fpdf2. Font asset: assets/Glyseric.otf.
"""

from __future__ import annotations

import io
import math
import re
from pathlib import Path

import pandas as pd
import streamlit as st
from fpdf import FPDF

from auth import require_auth

st.set_page_config(page_title="Shipping Labels · FL Toolkit", page_icon="🏷️")
require_auth()

FONT_PATH = str(Path(__file__).resolve().parent.parent / "assets" / "Glyseric.otf")
TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "assets" / "shipment_template.csv"

# Required columns, by the candidate names we accept for each.
REQUIRED = {
    "nama": ["nama penerima"],
    "telepon": ["telepon penerima", "telfon penerima", "no hp penerima"],
    "kecamatan": ["kecamatan"],
    "alamat": ["alamat penerima"],
}
# Optional columns — printed only when the column exists (and has a value).
OPTIONAL = {
    "kota": ["kota / kabupaten", "kota/kabupaten", "kota kabupaten", "kota / kab", "kota"],
    "kodepos": ["kode pos", "kodepos", "kode_pos"],
    "asuransi": ["pakai asuransi?", "pakai asuransi", "asuransi"],
}

TRUTHY = {"ya", "y", "yes", "iya", "true", "1"}


def _norm(name: str) -> str:
    """Normalize a column name: collapse whitespace/newlines, lowercase."""
    return re.sub(r"\s+", " ", str(name)).strip().lower()


def resolve_columns(df: pd.DataFrame) -> dict[str, str | None]:
    """Map our logical field names to the actual column names in `df`."""
    lookup = {_norm(c): c for c in df.columns}
    found: dict[str, str | None] = {}
    for key, candidates in {**REQUIRED, **OPTIONAL}.items():
        found[key] = next((lookup[c] for c in candidates if c in lookup), None)
    return found


def cell(row, col: str | None) -> str:
    """Read a cell as clean text: blanks/NaN → '', floats like 14240.0 → '14240'."""
    if not col:
        return ""
    value = row.get(col)
    if value is None:
        return ""
    if isinstance(value, float):
        if math.isnan(value):
            return ""
        if value.is_integer():
            return str(int(value))
    text = str(value).strip()
    return "" if text.lower() in ("nan", "none") else text


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


def _build_records(pdf: FPDF, row, cols: dict[str, str | None], sender_label: str,
                   font_size: float, line_h: float, max_text_w: float,
                   phone_str: str) -> list[tuple[str, float, float, float]]:
    """Lay out one label's lines at a given font size.

    Returns (text, size, indent, gap_before) records.
    """
    records: list[tuple[str, float, float, float]] = []

    def add_label_value(label: str, value: str) -> None:
        pdf.set_font("Glyseric", size=font_size)
        indent = pdf.get_string_width(label)
        for i, line in enumerate(wrap_text(pdf, label + value, max_text_w)):
            ind = 0 if i == 0 else indent
            if ind and pdf.get_string_width(line) > max_text_w - ind:
                ind = 0
            records.append((line, font_size, ind, 0))

    add_label_value("Nama: ", cell(row, cols["nama"]))
    add_label_value("No HP: ", phone_str)
    add_label_value("Kecamatan: ", cell(row, cols["kecamatan"]))

    kota = cell(row, cols["kota"])
    if kota:
        add_label_value("Kota/Kab: ", kota)
    kodepos = cell(row, cols["kodepos"])
    if kodepos:
        add_label_value("Kode Pos: ", kodepos)

    records.append(("Alamat lengkap:", font_size, 0, 0))
    pdf.set_font("Glyseric", size=font_size)
    for line in wrap_text(pdf, cell(row, cols["alamat"]), max_text_w):
        records.append((line, font_size, 0, 0))

    # Insurance line — shown whenever the column exists (blank → "Tidak").
    if cols["asuransi"]:
        flag = "Ya" if cell(row, cols["asuransi"]).lower() in TRUTHY else "Tidak"
        records.append((f"Asuransi: {flag}", font_size, 0, line_h * 0.5))

    records.append((f"From: {sender_label}", font_size * 10 / 11, 0, line_h))
    return records


def _content_height(records, margin_top: float, line_h: float) -> float:
    y = margin_top
    for _, _, _, gap_before in records:
        y += gap_before + line_h
    return y


def generate_labels_pdf(df: pd.DataFrame, sender_label: str,
                        cols: dict[str, str | None]) -> bytes:
    """Build the labels PDF from `df` and return it as bytes."""
    page_w, page_h = 78, 100
    margin_x = 6
    margin_top = 16  # start below the last-4-digits box so text never overlaps it
    line_h = 6
    font_size = 11
    bottom_margin = 3
    # Progressively smaller sizes; a long address shrinks until the label fits.
    size_steps = (11, 10.5, 10, 9.5, 9, 8.5, 8, 7.5, 7)

    pdf = FPDF(unit="mm", format=(page_w, page_h))
    pdf.set_auto_page_break(auto=False)
    pdf.add_font("Glyseric", "", FONT_PATH)

    for _, row in df.iterrows():
        pdf.add_page()

        phone_str = cell(row, cols["telepon"])
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

        # Auto-fit: use the largest font size whose laid-out content fits the
        # label. Long apartment-style addresses shrink instead of overflowing.
        records = None
        used_line_h = line_h
        for size in size_steps:
            candidate_line_h = line_h * size / font_size
            candidate = _build_records(pdf, row, cols, sender_label, size,
                                       candidate_line_h, max_text_w, phone_str)
            records = candidate
            used_line_h = candidate_line_h
            if _content_height(candidate, margin_top, candidate_line_h) <= page_h - bottom_margin:
                break

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
            pdf.cell(0, used_line_h, text)
            y += used_line_h

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
st.write("Upload a Lion Parcel / JNT shipment CSV and generate a print-ready PDF "
         "of 78×100 mm labels — one page per recipient.")

with st.expander("What CSV do I need?"):
    st.write("**Required columns:** `Nama Penerima`, `Telepon Penerima`, "
             "`Kecamatan`, `Alamat Penerima`")
    st.write("**Optional (printed when present):** `Kota / kabupaten`, `kode pos`, "
             "`Pakai Asuransi?`")
    st.caption("Column names are matched ignoring case and extra spaces, so both "
               "the older and newer export layouts work.")
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

    cols = resolve_columns(df)
    missing = [k for k in REQUIRED if not cols[k]]
    if missing:
        names = ", ".join(REQUIRED[k][0] for k in missing)
        st.error(f"❌ CSV is missing required column(s): {names}.\n\n"
                 f"Found: {', '.join(str(c) for c in df.columns)}")
        st.stop()

    # Drop rows with no recipient name (e.g. trailing blank lines).
    df = df[df[cols["nama"]].notna() &
            (df[cols["nama"]].astype(str).str.strip() != "")]

    present = [cols[k] for k in ("nama", "telepon", "kecamatan", "alamat",
                                 "kota", "kodepos", "asuransi") if cols[k]]
    absent = [k for k in OPTIONAL if not cols[k]]
    st.success(f"✅ Loaded {len(df)} recipient(s).")
    if absent:
        st.info("ℹ️ Not in this file (will be left off the label): "
                + ", ".join(OPTIONAL[k][0] for k in absent))
    st.dataframe(df[present], use_container_width=True, hide_index=True)

    if st.button("Generate labels", type="primary", disabled=df.empty):
        with st.spinner("Building PDF…"):
            pdf_bytes = generate_labels_pdf(
                df, sender_label.strip() or "Euniqeu Jastip", cols)
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
