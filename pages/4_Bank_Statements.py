"""Bank Statements → Xero — migrated from the bank-statement converter repos.

Converts Indonesian bank statement exports into a Xero-friendly CSV, plus a few
credit-card statement extractors. Each converter preserves its original repo's
parsing logic:

- Mandiri                     (CSV → Xero)   convert-mandiri-bank-statements-for-xero
- BCA Business / Corporate    (CSV → Xero)   convert-BCA-Business-Bank-Statements-For-Xero
- BCA Personal                (CSV → Xero)   convert-BCA-personal-bank-statements
- OCBC / BCA / UOB Credit Card (PDF → CSV)   convert-BCA-personal-bank-statements

The credit-card extractors read a statement PDF (via pdfplumber) and output a
plain transaction CSV with Indonesian column names — not the Xero format.

Note: statements contain sensitive financial data. Files are processed
in-memory for the session and are never stored. Errors are kept generic so
transaction data isn't written to server logs.

Python deps: pandas, numpy, pdfplumber.
"""

from __future__ import annotations

import io
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pdfplumber
import streamlit as st

from auth import require_auth

st.set_page_config(page_title="Bank Statements · FL Toolkit", page_icon="🏦", layout="centered")
require_auth()

ASSETS = Path(__file__).resolve().parent.parent / "assets"

# Indonesian 3-letter month abbreviations → numeric, for the credit-card parsers.
MONTH_MAP = {
    "JAN": "01", "FEB": "02", "MAR": "03", "APR": "04", "MEI": "05", "JUN": "06",
    "JUL": "07", "AGU": "08", "SEP": "09", "OKT": "10", "NOV": "11", "DES": "12",
}


def _safe_name(value: str) -> str:
    """Sanitize a value for use as a download filename."""
    value = re.sub(r'[\\/:"*?<>|\x00-\x1f]', "", str(value)).strip()
    return value or "bank_statement"


def _pdf_lines(data: bytes) -> list[str]:
    """Flatten a PDF into a list of text lines across all pages."""
    lines: list[str] = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            lines += text.split("\n")
    return lines


# ── Mandiri (CSV → Xero) ─────────────────────────────────────────────────────

def convert_mandiri(data: bytes) -> tuple[str, bytes, int]:
    """Handle both old (semicolon) and new (comma) Mandiri CSV formats."""
    header = data.split(b"\n", 1)[0].decode("utf-8", "ignore")
    if ";" in header:
        df = pd.read_csv(io.BytesIO(data), sep=";")
        account = df.iloc[0, 0]
        date_series = pd.to_datetime(df["PostDate"]).dt.date
        desc = (df["Remarks"].fillna("").astype(str)
                .str.replace(r"\s+", " ", regex=True).str.strip())
        debit = df["Debit Amount"].astype(str).str.replace(",", "", regex=False).astype(float)
        credit = df["Credit Amount"].astype(str).str.replace(",", "", regex=False).astype(float)
    else:
        df = pd.read_csv(io.BytesIO(data))
        account = df.iloc[0, 0]
        date_series = pd.to_datetime(df["Date"], dayfirst=True).dt.date
        d1 = df["Description"].fillna("").astype(str).str.strip()
        d2 = df["Description.1"].fillna("").astype(str).str.strip()
        desc = (d1 + " " + d2).str.replace(r"\s+", " ", regex=True).str.strip()
        debit = df["Debit"].astype(str).str.replace(",", "", regex=False).astype(float)
        credit = df["Credit"].astype(str).str.replace(",", "", regex=False).astype(float)

    amount = credit.subtract(debit)
    out = pd.DataFrame({"Date": date_series, "Description": desc, "Amount": amount})
    buf = io.StringIO()
    out.to_csv(buf, index=False)
    return f"{_safe_name(account)}.csv", buf.getvalue().encode(), len(out)


# ── BCA Business / Corporate (CSV → Xero) ────────────────────────────────────

def _bca_amount(cell: str) -> float:
    """'1,500,000.00 CR' → +1500000.0 ; anything else (DB) → negative."""
    parts = str(cell).split(" ")
    value = float(parts[0].replace(",", ""))
    return value if len(parts) > 1 and parts[1] == "CR" else -value


def convert_bca_business(data: bytes, year: str) -> tuple[bytes, int]:
    # header row 6 (index 5 after blank lines are skipped); drop the 4 summary rows.
    df = pd.read_csv(io.BytesIO(data), header=5).iloc[:-4, :]
    n = len(df)
    date_series = df.iloc[:, 0].map(("{}/" + year).format)
    payee = list(range(1, n + 1))
    desc = df.iloc[:, 1]
    amount = df.iloc[:, 3].map(_bca_amount)
    balance = df.iloc[:, 4]
    out = pd.DataFrame({"Date": date_series, "Payee": payee, "Description": desc,
                        "Amount": amount, "Balance": balance})
    buf = io.StringIO()
    out.to_csv(buf, index=False)
    return buf.getvalue().encode(), n


# ── BCA Personal (CSV → Xero) ────────────────────────────────────────────────

def convert_bca_personal(data: bytes, year: str | None) -> tuple[bytes, int]:
    """Personal BCA export: header on row 4, four trailing summary rows dropped.

    Columns are read positionally: date, description, (branch), amount, DB/CR,
    balance. When the date column has no year, `year` is prepended (dd/mm/YYYY).
    """
    df = pd.read_csv(io.BytesIO(data), header=3).iloc[:-4, :]
    n = len(df)
    date_series = df.iloc[:, 0].astype(str).str.replace("^'", "", regex=True)
    if year:
        date_series = date_series.map(("{}/" + year).format)
    payee = list(range(1, n + 1))
    desc = df.iloc[:, 1]
    amount = df.iloc[:, 3].astype(str).str.replace(",", "", regex=False).astype(float).abs()
    db_cr = df.iloc[:, 4]
    amount = np.where(db_cr == "DB", -amount, amount)
    balance = df.iloc[:, 5]
    out = pd.DataFrame({"Date": date_series, "Payee": payee, "Description": desc,
                        "Amount": amount, "Balance": balance})
    buf = io.StringIO()
    out.to_csv(buf, index=False)
    return buf.getvalue().encode(), n


# ── Credit-card statement extractors (PDF → CSV) ─────────────────────────────

def convert_ocbc_cc(data: bytes) -> tuple[bytes, int]:
    """OCBC (ID) credit-card PDF → transaction CSV. CR = credit (positive)."""
    lines = _pdf_lines(data)
    start = next(i for i, v in enumerate(lines) if "LAST MONTH'S BALANCE" in v) + 1
    end = next(i for i, v in enumerate(lines) if "SUBTOTAL (IDR)" in v)

    output = []
    for entry in lines[start:end]:
        m = re.match(r"(\d{2}/\d{2})\s+(\d{2}/\d{2})\s+(.+?)\s+([\d,]+)(\s+CR)?$", entry)
        if m:
            amount = float(m.group(4).replace(",", ""))
            amount = abs(amount) if m.group(5) else -abs(amount)
            output.append([m.group(1), m.group(2), m.group(3).strip(), amount])

    df = pd.DataFrame(output, columns=["Tanggal Transaksi", "Tanggal Pembukuan",
                                       "Uraian Transaksi", "Jumlah Tagihan"])
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue().encode(), len(df)


def convert_bca_cc(data: bytes) -> tuple[bytes, int]:
    """BCA (ID) credit-card PDF → transaction CSV. Bahasa months; ID number fmt."""
    lines = _pdf_lines(data)
    start = next(i for i, v in enumerate(lines) if "SALDO SEBELUMNYA" in v) + 2
    end = next(i for i, v in enumerate(lines) if "SUBTOTAL TRANSAKSI" in v)

    output = []
    for entry in lines[start:end]:
        m = re.match(r"(\d{2})-([A-Z]{3})\s+(\d{2})-([A-Z]{3})\s+(.+?)\s+([\d.,]+)(\s+CR)?$", entry)
        if m:
            day1, month1, day2, month2, desc, amount, credit = m.groups()
            date1 = f"{day1}/{MONTH_MAP[month1]}"
            date2 = f"{day2}/{MONTH_MAP[month2]}"
            amount = float(amount.replace(".", "").replace(",", ".")) * (1 if credit else -1)
            output.append([date1, date2, desc.strip(), amount])

    df = pd.DataFrame(output, columns=["Tanggal Transaksi", "Tanggal Pembukuan",
                                       "Uraian Transaksi", "Jumlah Tagihan"])
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue().encode(), len(df)


def convert_uob_cc(data: bytes) -> tuple[bytes, int]:
    """UOB (ID) credit-card PDF → transaction CSV. Bahasa months; CR = positive."""
    lines = _pdf_lines(data)
    start = next(i for i, v in enumerate(lines) if "TAGIHAN BULAN LALU" in v) + 1
    end = next(i for i, v in enumerate(lines) if "SUB TOTAL TAGIHAN BULAN INI" in v)

    output = []
    for entry in lines[start:end]:
        m = re.match(r"(\d{2}) ([A-Z]{3}) (\d{2}) ([A-Z]{3}) (.+?) (\d[\d.,]+)(CR)?$", entry)
        if m:
            day1, month1, day2, month2, desc, amount, credit = m.groups()
            date1 = f"{day1}/{MONTH_MAP[month1]}"
            date2 = f"{day2}/{MONTH_MAP[month2]}"
            amount = float(amount.replace(",", "")) * (1 if credit else -1)
            output.append([date1, date2, desc.strip(), amount])

    df = pd.DataFrame(output, columns=["Tanggal Transaksi", "Tanggal Pembukuan",
                                       "Perincian Transaksi", "Jumlah Tagihan"])
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue().encode(), len(df)


# ── UI ───────────────────────────────────────────────────────────────────────

st.title("🏦 Bank Statements → Xero")
st.write("Convert a bank statement export into a Xero-friendly CSV, or extract "
         "credit-card transactions from a statement PDF.")
st.info("🔒 Statements are processed in-memory for your session only and are "
        "never stored on the server.")

bank = st.selectbox("Bank / statement type", [
    "Mandiri",
    "BCA Business / Corporate",
    "BCA Personal",
    "OCBC Credit Card (ID)",
    "BCA Credit Card (ID)",
    "UOB Credit Card (ID)",
])

if bank == "Mandiri":
    with st.expander("What file do I need?"):
        st.write("A Mandiri transaction CSV export (old semicolon format or new "
                 "comma format). Output columns: Date, Description, Amount "
                 "(credit positive, debit negative).")
        st.download_button("⬇️ Download sample format",
                           data=(ASSETS / "mandiri_template.csv").read_bytes(),
                           file_name="mandiri_template.csv", mime="text/csv")
    f = st.file_uploader("Mandiri CSV", type="csv", key="mnd_up")
    if st.button("Convert", type="primary", disabled=not f):
        try:
            name, data, rows = convert_mandiri(f.getvalue())
            st.session_state["bank_out"] = (name, data, rows)
        except Exception:
            st.session_state.pop("bank_out", None)
            st.error("❌ Couldn't parse this file. Check that it's a Mandiri "
                     "transaction CSV with the expected columns (see the sample).")

elif bank == "BCA Business / Corporate":
    with st.expander("What file do I need?"):
        st.write("A BCA corporate account 'Transaction Inquiry' CSV export. "
                 "The statement date shows day/month only, so pick the year below. "
                 "Output columns: Date, Payee, Description, Amount, Balance.")
        st.download_button("⬇️ Download sample format",
                           data=(ASSETS / "bca_business_template.csv").read_bytes(),
                           file_name="bca_business_template.csv", mime="text/csv")
    f = st.file_uploader("BCA corporate CSV", type="csv", key="bca_up")
    year = st.text_input("Statement year", value="2024", max_chars=4, key="bca_year")
    if st.button("Convert", type="primary", disabled=not f):
        try:
            data, rows = convert_bca_business(f.getvalue(), year.strip())
            st.session_state["bank_out"] = ("bca_business_xero.csv", data, rows)
        except Exception:
            st.session_state.pop("bank_out", None)
            st.error("❌ Couldn't parse this file. Check that it's a BCA corporate "
                     "Transaction Inquiry CSV (see the sample).")

elif bank == "BCA Personal":
    with st.expander("What file do I need?"):
        st.write("A BCA personal account statement CSV export (header on row 4, "
                 "with four Saldo/Mutasi summary rows at the bottom). If the date "
                 "column shows day/month only, untick the box below and set the year. "
                 "Output columns: Date, Payee, Description, Amount (debit negative), "
                 "Balance.")
        st.download_button("⬇️ Download sample format",
                           data=(ASSETS / "bca_personal_template.csv").read_bytes(),
                           file_name="bca_personal_template.csv", mime="text/csv")
    f = st.file_uploader("BCA personal CSV", type="csv", key="bcap_up")
    has_year = st.checkbox("Date column already includes the year",
                           value=False, key="bcap_has_year")
    year = None
    if not has_year:
        year = st.text_input("Statement year", value="2024", max_chars=4,
                             key="bcap_year").strip()
    if st.button("Convert", type="primary", disabled=not f):
        try:
            data, rows = convert_bca_personal(f.getvalue(), year or None)
            st.session_state["bank_out"] = ("bca_personal_xero.csv", data, rows)
        except Exception:
            st.session_state.pop("bank_out", None)
            st.error("❌ Couldn't parse this file. Check that it's a BCA personal "
                     "statement CSV with the expected columns (see the sample).")

else:  # credit-card PDF extractors
    _CC = {
        "OCBC Credit Card (ID)": (convert_ocbc_cc, "ocbc_cc.csv", "OCBC"),
        "BCA Credit Card (ID)": (convert_bca_cc, "bca_cc.csv", "BCA"),
        "UOB Credit Card (ID)": (convert_uob_cc, "uob_cc.csv", "UOB"),
    }
    fn, out_name, label = _CC[bank]
    with st.expander("What file do I need?"):
        st.write(f"A {label} credit-card statement **PDF** (Indonesia). "
                 "Transactions are read straight from the PDF text. Output columns: "
                 "Tanggal Transaksi, Tanggal Pembukuan, "
                 f"{'Perincian' if label == 'UOB' else 'Uraian'} Transaksi, "
                 "Jumlah Tagihan (credit positive, spend negative). This is a plain "
                 "transaction CSV, not the Xero format.")
    f = st.file_uploader(f"{label} credit-card PDF", type="pdf", key="cc_up")
    if st.button("Convert", type="primary", disabled=not f):
        try:
            data, rows = fn(f.getvalue())
            st.session_state["bank_out"] = (out_name, data, rows)
        except Exception:
            st.session_state.pop("bank_out", None)
            st.error(f"❌ Couldn't parse this file. Check that it's a {label} "
                     "credit-card statement PDF in the expected layout.")

if "bank_out" in st.session_state:
    name, data, rows = st.session_state["bank_out"]
    st.divider()
    st.success(f"✅ Converted {rows} transaction(s) → **{name}**")
    st.download_button("⬇️ Download CSV", data=data, file_name=name,
                       mime="text/csv", type="primary", key="bank_dl")
