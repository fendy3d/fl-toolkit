"""Rename BUPOT — migrated from the `renameBUPOT` repo (2025 form layout).

Batch-renames Indonesian withholding-tax slips (Bukti Potong / BUPOT) by reading
each PDF's text and building a standardized filename from the taxpayer name,
document number, and tax period.

The terminal version renamed files in place inside a drop folder. Streamlit
can't rename the user's local files, so instead it produces renamed *copies*:
upload PDFs → download them back with the new names (individually or as a ZIP).

Parsing note: BUPOT PDFs are read at fixed line positions that depend on the
DJP form layout, which changes year to year. This page targets the **2025**
forms (same logic as the current renameBUPOT2025.py). All files in one batch
must be the SAME BUPOT type.

Python dep: pdfplumber.  No data is stored; files are processed in-memory.
"""

from __future__ import annotations

import io
import re
import zipfile

import pdfplumber
import streamlit as st

from auth import require_auth

st.set_page_config(page_title="Rename BUPOT · FL Toolkit", page_icon="📄")
require_auth()

# ── BUPOT types (2025) ───────────────────────────────────────────────────────
# key → human label shown in the picker
BUPOT_TYPES = {
    "1": "BP21",
    "2": "BPPU (Made by UJK)",
    "3": "BPPU (Made by customer)",
    "4": "SPT PPN",
    "5": "FPK",
}

MONTH_NAME_TO_NUMBER = {
    "JANUARI": "01", "FEBRUARI": "02", "MARET": "03", "APRIL": "04",
    "MEI": "05", "JUNI": "06", "JULI": "07", "AGUSTUS": "08",
    "SEPTEMBER": "09", "OKTOBER": "10", "NOVEMBER": "11", "DESEMBER": "12",
}


def _month_to_number(month_name: str) -> str:
    return MONTH_NAME_TO_NUMBER.get(month_name.strip().upper(), "??")


def extract_texts(data: bytes) -> list[str]:
    """Return non-empty text lines from every page of the PDF."""
    texts: list[str] = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text() or ""
            texts.extend(page_text.split("\n"))
    return [line for line in texts if line and line.strip()]


def new_bupot_name(texts: list[str], bupot_type: str) -> str:
    """Compute the new filename for one BUPOT PDF (2025 layout)."""
    if bupot_type == "1":  # BP21
        name = texts[9].split(": ")[-1]
        document_number = texts[6].split(" ")[0]
        month, year = texts[6].split(" ")[1].split("-")
        return f"{name}-BP21-{year}-{month}-{document_number}.pdf"

    if bupot_type == "2":  # BPPU (Made by UJK)
        name = texts[9].split(": ")[-1]
        document_number = texts[6].split(" ")[0]
        month, year = texts[6].split(" ")[1].split("-")
        return f"{year}-{month}--BPPU-{name}_{document_number}.pdf"

    if bupot_type == "3":  # BPPU (Made by customer)
        name = texts[35].split(": ")[-1]
        document_number = texts[6].split(" ")[0]
        month, year = texts[6].split(" ")[1].split("-")
        return f"{year}-{month}-BPPU-{name}_{document_number}.pdf"

    if bupot_type == "4":  # SPT PPN
        month, year = texts[6].split(" ")[0:2]
        return f"{year}-{_month_to_number(month)}-SPT_PPN.pdf"

    if bupot_type == "5":  # FPK
        document_number = texts[5].split(": ")[-1]
        date_line = [t for t in texts if "KOTA ADM. JAKARTA UTARA" in t][-1]
        month, year = date_line.split(", ")[1].split(" ")[1:3]
        month = _month_to_number(month)
        reference_number = (
            [t for t in texts if "(Referensi" in t][-1]
            .split(": ")[-1]
            .replace(")", "")
        )
        return f"{year}-{month}-{document_number}-{reference_number}.pdf"

    raise ValueError(f"Unknown BUPOT type: {bupot_type}")


def sanitize_filename(name: str) -> str:
    """Strip path separators and illegal characters so the name is safe inside
    a ZIP (prevents path traversal / accidental subfolders)."""
    name = name.replace("\\", "-").replace("/", "-")
    name = re.sub(r'[\x00-\x1f<>:"|?*]', "", name).strip()
    if not name.lower().endswith(".pdf"):
        name += ".pdf"
    return name or "unnamed.pdf"


def dedupe(name: str, used: set[str]) -> str:
    """Ensure `name` is unique within `used`, appending _2, _3, … if needed."""
    if name not in used:
        used.add(name)
        return name
    stem, ext = name.rsplit(".", 1)
    i = 2
    while f"{stem}_{i}.{ext}" in used:
        i += 1
    final = f"{stem}_{i}.{ext}"
    used.add(final)
    return final


# ── UI ───────────────────────────────────────────────────────────────────────

st.title("📄 Rename BUPOT")
st.write("Rename Bukti Potong (BUPOT) tax slips to a standardized filename. "
         "Upload PDFs, pick their type, and download the renamed copies.")

st.warning("⚠️ All PDFs in one batch must be the **same BUPOT type**. "
           "Parsing is calibrated for the **2025** DJP form layout.")

type_label = st.selectbox(
    "BUPOT type", list(BUPOT_TYPES.values()),
)
bupot_type = next(k for k, v in BUPOT_TYPES.items() if v == type_label)

uploaded = st.file_uploader(
    "BUPOT PDF(s)", type="pdf", accept_multiple_files=True,
    help="Select all files of the chosen type.",
)

if st.button("Rename", type="primary", disabled=not uploaded):
    results = []
    used_names: set[str] = set()
    progress = st.progress(0.0, text="Reading PDFs…")
    for idx, f in enumerate(uploaded, 1):
        try:
            texts = extract_texts(f.getvalue())
            raw_name = new_bupot_name(texts, bupot_type)
            new_name = dedupe(sanitize_filename(raw_name), used_names)
            results.append({
                "old": f.name, "new": new_name, "data": f.getvalue(), "error": None,
            })
        except Exception:
            # Deliberately generic: never surface parsed taxpayer names / NPWP
            # into the UI or Cloud logs.
            results.append({
                "old": f.name, "new": None, "data": None,
                "error": "Couldn't parse this PDF — is it the selected BUPOT "
                         "type and a 2025-layout form?",
            })
        progress.progress(idx / len(uploaded), text=f"Processed {idx}/{len(uploaded)}")
    progress.empty()
    st.session_state["bupot_results"] = results

results = st.session_state.get("bupot_results", [])
if results:
    st.divider()
    st.subheader("Results")

    ok_results = [r for r in results if not r["error"]]
    if len(ok_results) > 1:
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for r in ok_results:
                zf.writestr(r["new"], r["data"])
        st.download_button(
            f"⬇️ Download all {len(ok_results)} renamed (ZIP)",
            data=zip_buf.getvalue(), file_name="renamed_bupot.zip",
            mime="application/zip", type="primary", key="dl_all",
        )

    for i, r in enumerate(results):
        if r["error"]:
            st.error(f"❌ **{r['old']}** — {r['error']}")
            continue
        col1, col2 = st.columns([3, 1])
        with col1:
            st.write(f"**{r['old']}**  →  `{r['new']}`")
        with col2:
            st.download_button(
                "Download", data=r["data"], file_name=r["new"],
                mime="application/pdf", key=f"dl_{i}", use_container_width=True,
            )
