"""PDF Tools — migrated from the `pdfbot` repo (all 8 tools).

pdfbot was a terminal menu with 8 PDF utilities. This page keeps the same
single-menu design: pick an operation, upload file(s), download the result.
Each tool preserves pdfbot's original processing logic; only the drop-folder /
menu I/O is replaced with Streamlit widgets.

System deps (packages.txt): ghostscript (compress/watermark), poppler-utils
(PDF→image).  Python deps: pypdf, reportlab, pillow, numpy, pikepdf, pdfplumber,
openpyxl, pandas.
"""

from __future__ import annotations

import io
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

import streamlit as st

from auth import require_auth

st.set_page_config(page_title="PDF Tools · FL Toolkit", page_icon="📄", layout="centered")
require_auth()


# ── shared helpers ───────────────────────────────────────────────────────────

def human_size(num_bytes: int) -> str:
    kb = num_bytes / 1024
    return f"{kb:.1f} KB" if kb < 1024 else f"{kb / 1024:.2f} MB"


def make_zip(files: list[tuple[str, bytes]]) -> bytes:
    """Bundle (name, bytes) pairs into a ZIP, de-duplicating names."""
    buf = io.BytesIO()
    used: set[str] = set()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in files:
            final = name
            if final in used:
                stem, _, ext = final.rpartition(".")
                i = 2
                while f"{stem}_{i}.{ext}" in used:
                    i += 1
                final = f"{stem}_{i}.{ext}"
            used.add(final)
            zf.writestr(final, data)
    return buf.getvalue()


GS_PRESETS = {
    "Screen — smallest file, lowest quality (~72 dpi)": "/screen",
    "Ebook — small file, good for reading (~150 dpi)": "/ebook",
    "Printer — high quality (~300 dpi)": "/printer",
    "Prepress — highest quality, mild reduction": "/prepress",
}


def ghostscript_compress(data: bytes, gs_setting: str) -> bytes:
    if not shutil.which("gs"):
        raise RuntimeError("Ghostscript ('gs') is not installed on the server "
                           "(add `ghostscript` to packages.txt).")
    with tempfile.TemporaryDirectory() as tmp:
        src, dst = Path(tmp) / "in.pdf", Path(tmp) / "out.pdf"
        src.write_bytes(data)
        cmd = ["gs", "-sDEVICE=pdfwrite", "-dCompatibilityLevel=1.5",
               f"-dPDFSETTINGS={gs_setting}", "-dNOPAUSE", "-dQUIET", "-dBATCH",
               f"-sOutputFile={dst}", str(src)]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"Ghostscript error:\n{r.stderr}")
        return dst.read_bytes()


# ── 1. Make Booklets ─────────────────────────────────────────────────────────

def tool_booklet() -> None:
    from pypdf import PdfReader, PdfWriter, PageObject, Transformation

    st.write("Turn PDFs into 2-up booklet-imposed layouts. Page count must be a "
             "multiple of 4.")
    files = st.file_uploader("PDF file(s)", type="pdf", accept_multiple_files=True,
                             key="bk_up")
    if st.button("Make booklets", type="primary", disabled=not files):
        outputs, msgs = [], []
        for f in files:
            try:
                reader = PdfReader(io.BytesIO(f.getvalue()))
                num_pages = len(reader.pages)
                if num_pages % 4 != 0:
                    msgs.append(f"⚠️ Skipped **{f.name}** — {num_pages} pages "
                                "(must be a multiple of 4).")
                    continue
                fp = reader.pages[0]
                src_w = float(fp.mediabox.width)
                if src_w < 500:
                    canvas_w, canvas_h, offset_x = 841.89, 595.27, 420.94
                else:
                    canvas_w, canvas_h, offset_x = 1190.55, 841.89, 595.27
                sheets, pages, n = [], reader.pages, num_pages // 4
                for i in range(n):
                    front = PageObject.create_blank_page(width=canvas_w, height=canvas_h)
                    front.merge_page(pages[num_pages - 1 - 2 * i])
                    front.merge_transformed_page(pages[2 * i],
                                                 Transformation().translate(tx=offset_x, ty=0))
                    sheets.append(front)
                    back = PageObject.create_blank_page(width=canvas_w, height=canvas_h)
                    back.merge_page(pages[1 + 2 * i])
                    back.merge_transformed_page(pages[num_pages - 2 - 2 * i],
                                                Transformation().translate(tx=offset_x, ty=0))
                    sheets.append(back)
                writer = PdfWriter()
                for s in sheets:
                    writer.add_page(s)
                out = io.BytesIO()
                writer.write(out)
                outputs.append((f"BKLT - {f.name}", out.getvalue()))
            except Exception as e:
                msgs.append(f"❌ **{f.name}**: {e}")
        st.session_state["bk_out"] = outputs
        st.session_state["bk_msg"] = msgs

    for m in st.session_state.get("bk_msg", []):
        st.warning(m) if m.startswith("⚠️") else st.error(m)
    outputs = st.session_state.get("bk_out", [])
    if outputs:
        _render_downloads(outputs, zip_name="booklets.zip")


# ── 2. Merge PDF ─────────────────────────────────────────────────────────────

def tool_merge() -> None:
    from pypdf import PdfReader, PdfWriter

    st.write("Combine multiple PDFs into one. Files are merged in the order shown.")
    files = st.file_uploader("PDF files (2 or more)", type="pdf",
                             accept_multiple_files=True, key="mg_up")
    if files:
        st.caption("Merge order: " + "  →  ".join(f.name for f in files))
    out_name = st.text_input("Output filename", value="merged.pdf", key="mg_name")
    if st.button("Merge", type="primary", disabled=not files or len(files) < 2):
        writer = PdfWriter()
        total = 0
        for f in files:
            reader = PdfReader(io.BytesIO(f.getvalue()))
            for p in reader.pages:
                writer.add_page(p)
            total += len(reader.pages)
        out = io.BytesIO()
        writer.write(out)
        name = out_name if out_name.lower().endswith(".pdf") else out_name + ".pdf"
        st.session_state["mg_out"] = (name, out.getvalue(), total)

    if "mg_out" in st.session_state:
        name, data, total = st.session_state["mg_out"]
        st.success(f"✅ Merged {total} pages → **{name}** ({human_size(len(data))})")
        st.download_button("⬇️ Download", data=data, file_name=name,
                           mime="application/pdf", type="primary", key="mg_dl")


# ── 3. Split PDF ─────────────────────────────────────────────────────────────

def tool_split() -> None:
    from pypdf import PdfReader, PdfWriter

    st.write("Split a PDF into individual pages, a page range, or fixed-size chunks.")
    f = st.file_uploader("PDF file", type="pdf", key="sp_up")
    if not f:
        return
    reader = PdfReader(io.BytesIO(f.getvalue()))
    total = len(reader.pages)
    st.caption(f"{f.name} — {total} pages")
    mode = st.radio("Split mode", ["Every page → individual files",
                                   "Extract a page range", "Fixed-size chunks"],
                    key="sp_mode")
    base = Path(f.name).stem
    start = end = chunk = None
    if mode == "Extract a page range":
        c1, c2 = st.columns(2)
        start = c1.number_input("From page", 1, total, 1, key="sp_s")
        end = c2.number_input("To page", 1, total, total, key="sp_e")
    elif mode == "Fixed-size chunks":
        chunk = st.number_input("Pages per chunk", 1, total, min(10, total), key="sp_c")

    if st.button("Split", type="primary"):
        outputs = []
        if mode.startswith("Every"):
            for i, page in enumerate(reader.pages):
                w = PdfWriter(); w.add_page(page)
                b = io.BytesIO(); w.write(b)
                outputs.append((f"{base}_page_{i+1}.pdf", b.getvalue()))
        elif mode == "Extract a page range":
            s, e = int(start), int(end)
            w = PdfWriter()
            for i in range(s - 1, e):
                w.add_page(reader.pages[i])
            b = io.BytesIO(); w.write(b)
            outputs.append((f"{base}_pages_{s}-{e}.pdf", b.getvalue()))
        else:
            ch = int(chunk)
            for part, i in enumerate(range(0, total, ch), 1):
                w = PdfWriter()
                for j in range(i, min(i + ch, total)):
                    w.add_page(reader.pages[j])
                b = io.BytesIO(); w.write(b)
                outputs.append((f"{base}_part_{part}.pdf", b.getvalue()))
        st.session_state["sp_out"] = outputs

    outputs = st.session_state.get("sp_out", [])
    if outputs:
        _render_downloads(outputs, zip_name=f"{base}_split.zip")


# ── 4. Compress PDF ──────────────────────────────────────────────────────────

def tool_compress() -> None:
    st.write("Reduce PDF file size with Ghostscript.")
    if not shutil.which("gs"):
        st.warning("⚠️ Ghostscript isn't available on this server — compression "
                   "will fail until `ghostscript` is installed via packages.txt.")
    files = st.file_uploader("PDF file(s)", type="pdf", accept_multiple_files=True,
                             key="cp_up")
    label = st.selectbox("Compression level", list(GS_PRESETS.keys()), index=1,
                         key="cp_lvl")
    if st.button("Compress", type="primary", disabled=not files):
        results = []
        for f in files:
            original = f.getvalue()
            try:
                comp = ghostscript_compress(original, GS_PRESETS[label])
                results.append({"name": Path(f.name).stem + "_compressed.pdf",
                                "orig": len(original), "data": comp, "error": None})
            except RuntimeError as e:
                results.append({"name": f.name, "orig": len(original),
                                "data": None, "error": str(e)})
        st.session_state["cp_out"] = results

    results = st.session_state.get("cp_out", [])
    if results:
        ok = [(r["name"], r["data"]) for r in results if not r["error"]]
        if len(ok) > 1:
            st.download_button(f"⬇️ Download all {len(ok)} as ZIP",
                               data=make_zip(ok), file_name="compressed_pdfs.zip",
                               mime="application/zip", type="primary", key="cp_zip")
        for i, r in enumerate(results):
            if r["error"]:
                st.error(f"❌ {r['name']}: {r['error']}"); continue
            red = (1 - len(r["data"]) / r["orig"]) * 100 if r["orig"] else 0
            c1, c2 = st.columns([3, 1])
            c1.write(f"**{r['name']}** — {human_size(r['orig'])} → "
                     f"{human_size(len(r['data']))} (**{red:.0f}% smaller**)")
            c2.download_button("Download", data=r["data"], file_name=r["name"],
                               mime="application/pdf", key=f"cp_dl_{i}",
                               use_container_width=True)


# ── 5. PDF to JPG/PNG ────────────────────────────────────────────────────────

def tool_to_image() -> None:
    try:
        from pdf2image import convert_from_bytes
    except ImportError:
        st.error("`pdf2image` isn't installed."); return

    st.write("Convert each PDF page into an image.")
    f = st.file_uploader("PDF file", type="pdf", key="im_up")
    c1, c2 = st.columns(2)
    dpi = c1.select_slider("DPI (quality)", [72, 150, 300], value=150, key="im_dpi")
    fmt = c2.radio("Format", ["JPG", "PNG"], key="im_fmt")
    if st.button("Convert", type="primary", disabled=not f):
        try:
            images = convert_from_bytes(f.getvalue(), dpi=dpi)
        except Exception as e:
            st.error(f"❌ Conversion failed: {e}\n\nMake sure `poppler-utils` is in "
                     "packages.txt.")
            return
        base = Path(f.name).stem
        outputs = []
        for i, img in enumerate(images, 1):
            b = io.BytesIO()
            if fmt == "JPG":
                img.save(b, "JPEG", quality=90); ext = "jpg"
            else:
                img.save(b, "PNG"); ext = "png"
            outputs.append((f"{base}_page_{i}.{ext}", b.getvalue()))
        st.session_state["im_out"] = outputs

    outputs = st.session_state.get("im_out", [])
    if outputs:
        st.success(f"✅ {len(outputs)} image(s) created.")
        _render_downloads(outputs, zip_name="pdf_images.zip", mime="image/*")


# ── 6. PDF to Excel ──────────────────────────────────────────────────────────

def tool_to_excel() -> None:
    import pandas as pd
    try:
        import pdfplumber
        import openpyxl  # noqa: F401  (engine for to_excel)
    except ImportError:
        st.error("`pdfplumber` and `openpyxl` are required."); return

    st.write("Extract tables (or all text) from a PDF into an .xlsx file.")
    f = st.file_uploader("PDF file", type="pdf", key="xl_up")
    mode = st.radio("Extract", ["Tables only", "All text (one row per line)"], key="xl_mode")
    if st.button("Extract", type="primary", disabled=not f):
        all_data: list[list] = []
        with pdfplumber.open(io.BytesIO(f.getvalue())) as pdf:
            for i, page in enumerate(pdf.pages, 1):
                if mode == "Tables only":
                    for t_idx, table in enumerate(page.extract_tables(), 1):
                        if not table:
                            continue
                        all_data.append([f"--- Page {i}, Table {t_idx} ---"])
                        for r in table:
                            all_data.append([c if c is not None else "" for c in r])
                else:
                    text = page.extract_text()
                    if text:
                        all_data.append([f"=== Page {i} ==="])
                        all_data.extend([[line] for line in text.split("\n")])
                        all_data.append([""])
        if not all_data:
            st.warning("⚠️ No data extracted — the PDF may be scanned (image-only).")
            return
        max_cols = max(len(r) for r in all_data)
        padded = [r + [""] * (max_cols - len(r)) for r in all_data]
        buf = io.BytesIO()
        pd.DataFrame(padded).to_excel(buf, index=False, header=False, engine="openpyxl")
        st.session_state["xl_out"] = (Path(f.name).stem + ".xlsx", buf.getvalue(), len(all_data))

    if "xl_out" in st.session_state:
        name, data, rows = st.session_state["xl_out"]
        st.success(f"✅ Extracted {rows} rows → **{name}**")
        st.download_button("⬇️ Download .xlsx", data=data, file_name=name,
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           type="primary", key="xl_dl")


# ── 7. Unlock PDF ────────────────────────────────────────────────────────────

def tool_unlock() -> None:
    try:
        import pikepdf
    except ImportError:
        st.error("`pikepdf` isn't installed."); return

    st.write("Remove password protection from a PDF (you must know the password).")
    f = st.file_uploader("Locked PDF", type="pdf", key="ul_up")
    pwd = st.text_input("PDF password", type="password", key="ul_pw")
    if st.button("Unlock", type="primary", disabled=not f):
        try:
            with pikepdf.open(io.BytesIO(f.getvalue()), password=pwd) as pdf:
                out = io.BytesIO()
                pdf.save(out)
            st.session_state["ul_out"] = (Path(f.name).stem + "_unlocked.pdf", out.getvalue())
        except pikepdf.PasswordError:
            st.session_state.pop("ul_out", None)
            st.error("❌ Wrong password. Please try again.")
        except Exception as e:
            st.session_state.pop("ul_out", None)
            st.error(f"❌ Error: {e}")

    if "ul_out" in st.session_state:
        name, data = st.session_state["ul_out"]
        st.success(f"✅ Password removed → **{name}**")
        st.download_button("⬇️ Download", data=data, file_name=name,
                           mime="application/pdf", type="primary", key="ul_dl")


# ── 8. Watermark & Compress ──────────────────────────────────────────────────

GRADIENT_OPACITY = 0.30


def _apply_watermark(data: bytes) -> bytes:
    import numpy as np
    from PIL import Image
    from reportlab.pdfgen import canvas as rl_canvas
    from reportlab.lib.utils import ImageReader
    from pypdf import PdfReader, PdfWriter

    def gradient_png(w_pt, h_pt, dpi=150):
        px_w, px_h = max(1, int(w_pt * dpi / 72)), max(1, int(h_pt * dpi / 72))
        r = np.tile(np.linspace(255, 50, px_w, dtype=np.uint8), (px_h, 1))
        g = np.tile(np.linspace(50, 220, px_w, dtype=np.uint8), (px_h, 1))
        b = np.full((px_h, px_w), 50, dtype=np.uint8)
        buf = io.BytesIO()
        Image.fromarray(np.stack([r, g, b], axis=2), mode="RGB").save(buf, "PNG")
        return buf.getvalue()

    def gradient_page(w_pt, h_pt):
        buf = io.BytesIO()
        c = rl_canvas.Canvas(buf, pagesize=(w_pt, h_pt))
        c.saveState(); c.setFillAlpha(GRADIENT_OPACITY)
        c.drawImage(ImageReader(io.BytesIO(gradient_png(w_pt, h_pt))), 0, 0,
                    width=w_pt, height=h_pt, mask="auto")
        c.restoreState(); c.save(); buf.seek(0)
        return PdfReader(buf).pages[0]

    reader = PdfReader(io.BytesIO(data))
    writer = PdfWriter()
    for page in reader.pages:
        gp = gradient_page(float(page.mediabox.width), float(page.mediabox.height))
        gp.merge_page(page)
        writer.add_page(gp)
    out = io.BytesIO(); writer.write(out)
    return out.getvalue()


def tool_watermark() -> None:
    st.write("Add a gradient watermark and/or compress PDFs.")
    do_wm = st.checkbox("Add watermark", value=True, key="wm_wm")
    do_cp = st.checkbox("Compress", value=False, key="wm_cp")
    gs_setting = "/ebook"
    if do_cp:
        gs_setting = GS_PRESETS[st.selectbox("Compression level", list(GS_PRESETS.keys()),
                                             index=1, key="wm_lvl")]
    files = st.file_uploader("PDF file(s)", type="pdf", accept_multiple_files=True, key="wm_up")
    if st.button("Process", type="primary", disabled=not files or not (do_wm or do_cp)):
        suffix = " - WM COMP" if do_wm and do_cp else (" - WM" if do_wm else " - COMP")
        outputs, msgs = [], []
        for f in files:
            try:
                data = f.getvalue()
                if do_wm:
                    data = _apply_watermark(data)
                if do_cp:
                    data = ghostscript_compress(data, gs_setting)
                outputs.append((Path(f.name).stem + suffix + ".pdf", data))
            except Exception as e:
                msgs.append(f"❌ **{f.name}**: {e}")
        st.session_state["wm_out"] = outputs
        st.session_state["wm_msg"] = msgs

    for m in st.session_state.get("wm_msg", []):
        st.error(m)
    outputs = st.session_state.get("wm_out", [])
    if outputs:
        _render_downloads(outputs, zip_name="watermarked.zip")


# ── shared multi-file download renderer ──────────────────────────────────────

def _render_downloads(outputs: list[tuple[str, bytes]], zip_name: str,
                      mime: str = "application/pdf") -> None:
    if len(outputs) > 1:
        st.download_button(f"⬇️ Download all {len(outputs)} as ZIP",
                           data=make_zip(outputs), file_name=zip_name,
                           mime="application/zip", type="primary", key=f"zip_{zip_name}")
    for i, (name, data) in enumerate(outputs):
        c1, c2 = st.columns([3, 1])
        c1.write(f"`{name}`  ({human_size(len(data))})")
        c2.download_button("Download", data=data, file_name=name, mime=mime,
                           key=f"dl_{zip_name}_{i}", use_container_width=True)


# ── dispatch ─────────────────────────────────────────────────────────────────

TOOLS = {
    "🗜️ Compress PDF": tool_compress,
    "🔗 Merge PDF": tool_merge,
    "✂️ Split PDF": tool_split,
    "📖 Make Booklets": tool_booklet,
    "🖼️ PDF to JPG/PNG": tool_to_image,
    "📊 PDF to Excel": tool_to_excel,
    "🔓 Unlock PDF": tool_unlock,
    "💧 Watermark & Compress": tool_watermark,
}

st.title("📄 PDF Tools")
choice = st.selectbox("Choose a tool", list(TOOLS.keys()))
st.divider()
TOOLS[choice]()
