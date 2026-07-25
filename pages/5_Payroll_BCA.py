"""Payroll → BCA — build the BCA MultiAutoTransaksi payroll upload file.

Replaces the whole manual chain (Airtable CSV → xlsx → BCA MultiAutoTransaksi
tool → BCA Checksum tool): upload the Airtable "Pay Run" CSV and download BOTH
the MultiPayroll .txt ("file A") and its Checksum .txt, ready to upload to BCA.

Both file layouts were reverse-engineered and verified byte-for-byte against 3
real pay runs. The checksum matches BCA's official CHECKSUM tool exactly (its
algorithm was recovered from that tool's C# source).

Note: payroll data is sensitive. Files are processed in-memory for the session
and are never stored.

Python deps: pandas.
"""

from __future__ import annotations

import datetime
import io
from decimal import Decimal, InvalidOperation

import pandas as pd
import streamlit as st

from auth import require_auth

st.set_page_config(page_title="Payroll → BCA · FL Toolkit", page_icon="💸", layout="centered")
require_auth()

# Header field names + defaults, matching BCA's official MultiAutoTransaksi
# converter (field mapping recovered from that tool's decompiled source). The
# header line is:
#   0|PY|<Corporate ID>|<Company Code>|<Header ID>|<Effective Date>|
#     <Effective Time>|<Debited Account>|<count>|<Business Type>|<Remarks1>|<Remarks2>
# Header ID, Effective Date, Effective Time and count are set per run in the UI;
# the rest identify the BCA payroll account and rarely change.
HEADER_DEFAULTS = {
    "service": "PY",              # transaction-type code (fixed for Multi Payroll)
    "corporate_id": "IBSYAYNEOP",
    "company_code": "04080175",
    "debit_account": "4083597979",
    "effective_time": "07",       # BCA effective-time slot code (cboTime)
    "business_type": "09",        # BCA business-type code (cboBusiness)
    "remarks1": "",
    "remarks2": "",
}

# Logical field → candidate CSV column names (exact match first, then substring).
COLUMN_CANDIDATES = {
    "txn": ["Transaction ID"],
    "ttype": ["Transfer Type (from Employee)", "Transfer Type"],
    "acct": ["Bank Account Number (from Employee)", "Bank Account Number"],
    "name": ["Nama Lengkap (from Employee)", "Nama Lengkap"],
    "amount": ["Take Home Pay (exclude THR)", "Take Home Pay"],
    "remark": ["Remark"],
    "email": ["Email (work) (from Employee)", "Email (work)", "Email"],
    "swift": ["Receiver Swift Code (from Employee)", "Receiver Swift Code"],
    "ctype": ["Receiver Cust Type (from Employee)", "Receiver Cust Type"],
    "cres": ["Receiver Cust Residence (from Employee)", "Receiver Cust Residence"],
}


def _resolve_columns(columns: list[str]) -> dict[str, str | None]:
    """Map each logical field to an actual CSV column (exact, then substring)."""
    resolved: dict[str, str | None] = {}
    for key, candidates in COLUMN_CANDIDATES.items():
        match = None
        for cand in candidates:
            match = next((c for c in columns if c.strip() == cand), None)
            if match:
                break
        if not match:
            for cand in candidates:
                match = next((c for c in columns if cand.lower() in c.lower()), None)
                if match:
                    break
        resolved[key] = match
    return resolved


def build_multipayroll(csv_bytes: bytes, run_date: datetime.date,
                       header: dict) -> tuple[str, int, Decimal]:
    """Return (file_text, transaction_count, total_amount)."""
    df = pd.read_csv(io.BytesIO(csv_bytes), dtype=str).fillna("")
    df.columns = [c.strip() for c in df.columns]
    cols = _resolve_columns(list(df.columns))

    required = ["txn", "ttype", "acct", "name", "amount", "remark", "email"]
    missing = [k for k in required if not cols[k]]
    if missing:
        raise ValueError(f"missing columns: {missing}")

    def val(row, key):
        col = cols[key]
        return str(row[col]).strip() if col else ""

    n = len(df)
    header_line = "|".join([
        "0", header["service"], header["corporate_id"], header["company_code"],
        header["header_id"], run_date.strftime("%Y%m%d"), header["effective_time"],
        header["debit_account"], f"{n:05d}", header["business_type"],
        header["remarks1"], header["remarks2"],
    ])

    lines = [header_line]
    total = Decimal("0")
    for _, row in df.iterrows():
        ttype = val(row, "ttype")
        amount_raw = val(row, "amount")
        amount = Decimal(amount_raw)  # raises InvalidOperation on bad data
        total += amount
        # Swift / cust type / residence only for non-BCA (interbank/LLG) transfers.
        if ttype.upper() == "BCA":
            swift = ctype = cres = ""
        else:
            swift, ctype, cres = val(row, "swift"), val(row, "ctype"), val(row, "cres")
        lines.append("|".join([
            "1", val(row, "txn").zfill(18), ttype, "", val(row, "acct"),
            val(row, "name"), f"{amount:.2f}", "", val(row, "remark"),
            val(row, "email"), swift, ctype, cres,
        ]))

    return "\n".join(lines) + "\n", n, total


# BCA's checksum algorithm, reverse-engineered from its official CHECKSUM tool's
# C# source (mtdCalculateAutoCollect + INT_SEED). Verified to reproduce BCA's
# Checksum_MultiPayroll files byte-for-byte across 3 independent pay runs.
CHECKSUM_TABLE = "XRVZK2TS7QFG0CHELA4OPM9IDYUWJNBo5cx1t3hwry8knabq7efuvijmlpsgzd!@#$%&*()-+=\\:;\"<>,.?/ '"
CHECKSUM_ADDER = 3371
CHECKSUM_SEED = 3751517


def bca_checksum(text: str) -> str:
    """BCA payroll-file checksum of the MultiPayroll text. Each line is trimmed;
    for every character, scan the char table and accumulate the bank's formula."""
    total = 0
    table = CHECKSUM_TABLE
    tlen = len(table)
    segments = text.split("\n")
    for idx, seg in enumerate(segments):
        if idx == len(segments) - 1 and seg == "":
            continue  # trailing empty line after the final newline
        line = seg.strip()
        for x in range(1, len(line) + 1):
            m = 0
            ch = line[x - 1]
            for y in range(1, tlen + 1):
                if table[y - 1] == ch:
                    z = x + y
                    m = z % CHECKSUM_ADDER
                    total += (z + CHECKSUM_ADDER * (CHECKSUM_ADDER + x)
                              + CHECKSUM_ADDER * (CHECKSUM_ADDER + y) + m * m)
                else:
                    total += CHECKSUM_ADDER * x + m * m
    return str(total + CHECKSUM_SEED)


# ── UI ───────────────────────────────────────────────────────────────────────

st.title("💸 Payroll → BCA")
st.write("Upload the Airtable **Pay Run** CSV and download the BCA "
         "MultiAutoTransaksi (MultiPayroll) upload file — no more CSV → xlsx step.")
st.info("🔒 Payroll data is processed in-memory for your session only and is "
        "never stored on the server.")

f = st.file_uploader("Pay Run CSV (from Airtable)", type="csv", key="pay_csv")
c_date, c_time, c_hdr = st.columns(3)
with c_date:
    run_date = st.date_input("Effective Date", value=datetime.date.today(), key="pay_date")
with c_time:
    _TIME_OPTS = [f"{h:02d}" for h in range(24)]  # BCA cboTime: hour 00–23
    effective_time = st.selectbox(
        "Effective Time", _TIME_OPTS,
        index=_TIME_OPTS.index(HEADER_DEFAULTS["effective_time"]),
        format_func=lambda c: f"{c}:00", key="pay_time",
        help="Hour the payroll takes effect (BCA's Effective Time / cboTime). "
             "Your sample files use 07:00.")
with c_hdr:
    seq = st.number_input("Header ID", min_value=0, value=13, step=1, key="pay_seq",
                          help="BCA increments this by 1 for every payroll file it "
                               "generates (samples were 10, 11, 12). It must not repeat "
                               "within 3 months. Confirm the next value with BCA.")

with st.expander("Advanced — BCA header settings"):
    st.caption("Labels match BCA's MultiAutoTransaksi converter. These identify your "
               "BCA payroll account and rarely change. Effective Date, Effective Time, "
               "Header ID, and the transaction count are set above / filled automatically.")
    cfg = {}
    c1, c2 = st.columns(2)
    with c1:
        cfg["corporate_id"] = st.text_input("Corporate ID", HEADER_DEFAULTS["corporate_id"])
        cfg["company_code"] = st.text_input("Company Code", HEADER_DEFAULTS["company_code"])
        cfg["debit_account"] = st.text_input("Debited Account", HEADER_DEFAULTS["debit_account"])
        cfg["business_type"] = st.text_input("Business Type", HEADER_DEFAULTS["business_type"])
    with c2:
        cfg["service"] = st.text_input("Transaction code", HEADER_DEFAULTS["service"])
        cfg["remarks1"] = st.text_input("Remarks 1", HEADER_DEFAULTS["remarks1"], max_chars=18)
        cfg["remarks2"] = st.text_input("Remarks 2", HEADER_DEFAULTS["remarks2"], max_chars=18)
    cfg["effective_time"] = effective_time
    cfg["header_id"] = f"{int(seq):08d}"

if st.button("Build BCA files", type="primary", disabled=not f):
    try:
        text, n, total = build_multipayroll(f.getvalue(), run_date, cfg)
        fname = f"MultiPayroll-{run_date:%d-%b-%Y}.txt"
        checksum = bca_checksum(text)
        st.session_state["pay_out"] = (fname, text, checksum, n, str(total))
    except (ValueError, InvalidOperation, KeyError):
        st.session_state.pop("pay_out", None)
        st.error("❌ Couldn't build the file. Check that this is the Airtable Pay "
                 "Run CSV with the expected columns (Transaction ID, Transfer Type, "
                 "Bank Account Number, Nama Lengkap, Take Home Pay, Remark, Email).")
    except Exception:
        st.session_state.pop("pay_out", None)
        st.error("❌ Couldn't build the file from this CSV.")

if "pay_out" in st.session_state:
    fname, text, checksum, n, total = st.session_state["pay_out"]
    st.divider()
    st.success(f"✅ Built **{fname}** — {n} transaction(s), total "
               f"Rp {Decimal(total):,.2f}")
    d1, d2 = st.columns(2)
    with d1:
        st.download_button("⬇️ MultiPayroll .txt", data=text.encode(),
                           file_name=fname, mime="text/plain", type="primary",
                           key="pay_dl", use_container_width=True)
    with d2:
        st.download_button(f"⬇️ Checksum .txt", data=checksum.encode(),
                           file_name=f"Checksum_{fname}", mime="text/plain",
                           type="primary", key="pay_cksum_dl", use_container_width=True)
    st.caption(f"🧮 Checksum: `{checksum}`  ·  upload **both** files to BCA.")
    with st.expander("Preview MultiPayroll (first lines)"):
        st.code("\n".join(text.splitlines()[:6]), language="text")
