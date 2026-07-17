"""Bank Statements → Xero — migrated from the bank-statement converter repos.

Converts Indonesian bank statement exports into a Xero-friendly CSV. Two
converters (both CSV → CSV), preserving each repo's original parsing logic:

- Mandiri  (from convert-mandiri-bank-statements-for-xero)
- BCA Business / Corporate  (from convert-BCA-Business-Bank-Statements-For-Xero)

Note: statements contain sensitive financial data. Files are processed
in-memory for the session and are never stored. Errors are kept generic so
transaction data isn't written to server logs.

Python dep: pandas.
"""

from __future__ import annotations

import io
import re
from pathlib import Path

import pandas as pd
import streamlit as st

from auth import require_auth

st.set_page_config(page_title="Bank Statements · FL Toolkit", page_icon="🏦", layout="centered")
require_auth()

ASSETS = Path(__file__).resolve().parent.parent / "assets"


def _safe_name(value: str) -> str:
    """Sanitize a value for use as a download filename."""
    value = re.sub(r'[\\/:"*?<>|\x00-\x1f]', "", str(value)).strip()
    return value or "bank_statement"


# ── Mandiri (CSV → Xero) ─────────────────────────────────────────────────────

def convert_mandiri(data: bytes) -> tuple[str, bytes]:
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


# ── UI ───────────────────────────────────────────────────────────────────────

st.title("🏦 Bank Statements → Xero")
st.write("Convert a bank statement export into a Xero-friendly CSV.")
st.info("🔒 Statements are processed in-memory for your session only and are "
        "never stored on the server.")

bank = st.selectbox("Bank", ["Mandiri", "BCA Business / Corporate"])

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

else:  # BCA Business / Corporate
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

if "bank_out" in st.session_state:
    name, data, rows = st.session_state["bank_out"]
    st.divider()
    st.success(f"✅ Converted {rows} transaction(s) → **{name}**")
    st.download_button("⬇️ Download Xero CSV", data=data, file_name=name,
                       mime="text/csv", type="primary", key="bank_dl")
