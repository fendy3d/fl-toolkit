"""Compress PDF — migrated from the `pdfbot` repo.

Preserves pdfbot's Ghostscript compression logic (the four /screen../prepress
quality presets) but swaps the terminal's drop-folder + menu I/O for Streamlit
widgets: st.file_uploader in, st.download_button out.

System dependency: Ghostscript (`gs`) — declared in packages.txt so Streamlit
Community Cloud installs it via apt.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

import streamlit as st

from auth import require_auth

st.set_page_config(page_title="Compress PDF · FL Toolkit", page_icon="🗜️")
require_auth()

# ── Ghostscript compression (ported from pdfbot) ─────────────────────────────

# label → Ghostscript -dPDFSETTINGS value
GS_PRESETS = {
    "Screen — smallest file, lowest quality (~72 dpi)": "/screen",
    "Ebook — small file, good for reading (~150 dpi)": "/ebook",
    "Printer — high quality (~300 dpi)": "/printer",
    "Prepress — highest quality, mild reduction": "/prepress",
}


def ghostscript_compress(src: Path, dst: Path, gs_setting: str) -> None:
    """Compress `src` into `dst` using Ghostscript. Raises RuntimeError on failure."""
    if not shutil.which("gs"):
        raise RuntimeError(
            "Ghostscript ('gs') is not installed on the server. "
            "Add `ghostscript` to packages.txt."
        )
    cmd = [
        "gs",
        "-sDEVICE=pdfwrite",
        "-dCompatibilityLevel=1.5",
        f"-dPDFSETTINGS={gs_setting}",
        "-dNOPAUSE",
        "-dQUIET",
        "-dBATCH",
        f"-sOutputFile={dst}",
        str(src),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Ghostscript error:\n{result.stderr}")


def compress_bytes(data: bytes, gs_setting: str) -> bytes:
    """Compress raw PDF bytes and return the compressed bytes."""
    with tempfile.TemporaryDirectory() as tmpdir:
        src = Path(tmpdir) / "in.pdf"
        dst = Path(tmpdir) / "out.pdf"
        src.write_bytes(data)
        ghostscript_compress(src, dst, gs_setting)
        return dst.read_bytes()


def human_size(num_bytes: int) -> str:
    kb = num_bytes / 1024
    if kb < 1024:
        return f"{kb:.1f} KB"
    return f"{kb / 1024:.2f} MB"


# ── UI ───────────────────────────────────────────────────────────────────────

st.title("🗜️ Compress PDF")
st.write("Reduce PDF file size with Ghostscript. Upload one or more PDFs, choose "
         "a quality level, then compress.")

if not shutil.which("gs"):
    st.warning("⚠️ Ghostscript isn't available on this server yet — compression "
               "will fail until `ghostscript` is installed via packages.txt.")

uploaded = st.file_uploader(
    "PDF file(s)", type="pdf", accept_multiple_files=True,
    help="You can select multiple PDFs at once.",
)

preset_label = st.selectbox(
    "Compression level", list(GS_PRESETS.keys()), index=1,  # default: Ebook
)
gs_setting = GS_PRESETS[preset_label]

if st.button("Compress", type="primary", disabled=not uploaded):
    results = []
    progress = st.progress(0.0, text="Compressing…")
    for i, f in enumerate(uploaded, 1):
        original = f.getvalue()
        try:
            compressed = compress_bytes(original, gs_setting)
            results.append({
                "name": Path(f.name).stem + "_compressed.pdf",
                "orig": len(original),
                "new": len(compressed),
                "data": compressed,
                "error": None,
            })
        except RuntimeError as exc:
            results.append({
                "name": f.name, "orig": len(original), "new": 0,
                "data": None, "error": str(exc),
            })
        progress.progress(i / len(uploaded), text=f"Compressed {i}/{len(uploaded)}")
    progress.empty()
    st.session_state["compress_results"] = results

# Render results outside the button block so download clicks (which rerun the
# script) don't wipe them.
results = st.session_state.get("compress_results", [])
if results:
    st.divider()
    st.subheader("Results")
    for i, r in enumerate(results):
        if r["error"]:
            st.error(f"❌ {r['name']}: {r['error']}")
            continue
        reduction = (1 - r["new"] / r["orig"]) * 100 if r["orig"] else 0
        col1, col2 = st.columns([3, 1])
        with col1:
            st.write(
                f"**{r['name']}** — {human_size(r['orig'])} → "
                f"{human_size(r['new'])}  (**{reduction:.0f}% smaller**)"
            )
        with col2:
            st.download_button(
                "Download", data=r["data"], file_name=r["name"],
                mime="application/pdf", key=f"dl_{i}", use_container_width=True,
            )
