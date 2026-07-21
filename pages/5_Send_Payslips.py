"""Send Payslips — migrated from the `sendpayslips` repo.

Takes a combined payslips PDF (one employee per page), reads each page's email
address, splits that page into its own PDF, and emails it to that employee via
Gmail SMTP.

Differences from the original CLI script, all for safety:
- Credentials are read from Streamlit secrets (`payslip_sender_email` and
  `payslip_app_password`) — never hardcoded or committed.
- Recipients are parsed and shown for review *before* anything is sent, behind
  an explicit confirmation. Sending real payroll email can't be undone.
- Each page is split in-memory; no PDF is ever written to the server disk.

Python deps: pypdf (already used by PDF Tools). smtplib / email are stdlib.
"""

from __future__ import annotations

import datetime
import io
import re
import smtplib
from email.message import EmailMessage

import streamlit as st
from pypdf import PdfReader, PdfWriter

from auth import require_auth

st.set_page_config(page_title="Send Payslips · FL Toolkit", page_icon="📧", layout="centered")
require_auth()

MONTHS = {
    1: "January", 2: "February", 3: "March", 4: "April", 5: "May", 6: "June",
    7: "July", 8: "August", 9: "September", 10: "October", 11: "November", 12: "December",
}

# Matches "Email: someone@example.com" anywhere in a page's text.
EMAIL_RE = re.compile(r"Email:\s*([\w\.-]+@[\w\.-]+)", re.IGNORECASE)


def _get_creds() -> tuple[str | None, str | None]:
    """Gmail sender + App Password from secrets, or (None, None) if unset."""
    try:
        return st.secrets["payslip_sender_email"], st.secrets["payslip_app_password"]
    except (KeyError, FileNotFoundError):
        return None, None


def parse_recipients(pdf_bytes: bytes) -> list[dict]:
    """One row per page: {page, index, email|None}."""
    reader = PdfReader(io.BytesIO(pdf_bytes))
    rows = []
    for i, page in enumerate(reader.pages):
        raw = page.extract_text() or ""
        clean = " ".join(raw.replace('"', "").replace("\r", "").split())
        m = EMAIL_RE.search(clean)
        rows.append({"page": i + 1, "index": i, "email": m.group(1).strip() if m else None})
    return rows


def _page_pdf_bytes(reader: PdfReader, index: int) -> bytes:
    """Extract a single page as its own PDF, in-memory."""
    writer = PdfWriter()
    writer.add_page(reader.pages[index])
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def send_payslips(pdf_bytes: bytes, recipients: list[tuple[int, str]],
                  sender_email: str, app_password: str, sender_name: str,
                  month_name: str, year: str) -> tuple[list[tuple[str, bool, str]], str | None]:
    """Email one page to each recipient. Returns (per-recipient results, fatal_error)."""
    reader = PdfReader(io.BytesIO(pdf_bytes))
    try:
        server = smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30)
        server.login(sender_email, app_password)
    except Exception as exc:  # noqa: BLE001 — surface a friendly message, not a traceback
        return [], f"Couldn't connect to or sign in to Gmail ({type(exc).__name__})."

    results: list[tuple[str, bool, str]] = []
    try:
        for index, email in recipients:
            try:
                attachment = _page_pdf_bytes(reader, index)
                msg = EmailMessage()
                msg["Subject"] = f"Payslip - {month_name} {year}"
                msg["From"] = f"{sender_name} <{sender_email}>"
                msg["To"] = email
                msg.set_content(
                    f"Dear employee,\n\n"
                    f"Please find your payslip for {month_name} {year} attached.\n\n"
                    f"Best regards,\n{sender_name}"
                )
                msg.add_attachment(attachment, maintype="application", subtype="pdf",
                                   filename=f"Payslip_{month_name}_{year}.pdf")
                server.send_message(msg)
                results.append((email, True, ""))
            except Exception as exc:  # noqa: BLE001
                results.append((email, False, type(exc).__name__))
    finally:
        try:
            server.quit()
        except Exception:  # noqa: BLE001
            pass
    return results, None


# ── UI ───────────────────────────────────────────────────────────────────────

st.title("📧 Send Payslips")
st.write("Upload a combined payslips PDF (one employee per page). The tool reads "
         "each page's email address, splits it into its own PDF, and emails that "
         "page to the employee.")
st.warning("⚠️ This sends **real emails** with payroll attachments and can't be "
           "undone. Review the detected recipients below before sending.")

sender_email, app_password = _get_creds()
if not sender_email:
    st.error("🔧 **Gmail sender isn't configured.** Add these to the app secrets "
             "(`.streamlit/secrets.toml` locally, or *Settings → Secrets* on "
             "Streamlit Cloud):\n\n"
             "```toml\npayslip_sender_email = \"you@gmail.com\"\n"
             "payslip_app_password = \"your 16-char app password\"\n```\n"
             "You can still upload and preview recipients below — sending stays "
             "disabled until this is set.")

f = st.file_uploader("Payslips PDF", type="pdf", key="ps_pdf")

col1, col2 = st.columns(2)
with col1:
    month_num = st.selectbox("Month", list(range(1, 13)),
                             index=datetime.date.today().month - 1,
                             format_func=lambda m: MONTHS[m], key="ps_month")
with col2:
    year = st.text_input("Year", value=str(datetime.date.today().year),
                         max_chars=4, key="ps_year")
sender_name = st.text_input("Sender display name", value="Neo Academy", key="ps_name")

if st.button("Parse recipients", disabled=not f):
    try:
        rows = parse_recipients(f.getvalue())
        st.session_state["ps_parsed"] = {"pdf": f.getvalue(), "rows": rows}
    except Exception:
        st.session_state.pop("ps_parsed", None)
        st.error("❌ Couldn't read this PDF. Make sure it's a text-based payslips PDF.")

if "ps_parsed" in st.session_state:
    rows = st.session_state["ps_parsed"]["rows"]
    detected = [r for r in rows if r["email"]]
    missing = [r for r in rows if not r["email"]]
    month_name = MONTHS[month_num]

    st.divider()
    st.subheader("Detected recipients")
    st.dataframe(
        [{"Page": r["page"], "Email": r["email"] or "— none detected —"} for r in rows],
        use_container_width=True, hide_index=True,
    )
    if missing:
        st.warning(f"{len(missing)} page(s) had no detectable email and will be "
                   f"skipped: page(s) {', '.join(str(r['page']) for r in missing)}.")
    st.caption(f"{len(detected)} payslip(s) will be sent.")

    with st.expander("Preview the email each employee receives"):
        st.text(f"From:    {sender_name} <{sender_email or 'not configured'}>")
        st.text(f"Subject: Payslip - {month_name} {year}")
        st.text(f"Attach:  Payslip_{month_name}_{year}.pdf")
        st.divider()
        st.text(f"Dear employee,\n\nPlease find your payslip for {month_name} {year} "
                f"attached.\n\nBest regards,\n{sender_name}")

    confirm = st.checkbox("I've reviewed the recipients above and want to email each "
                          "their payslip.")
    ready = bool(sender_email and confirm and detected and year.strip())
    if st.button(f"📨 Send {len(detected)} payslip(s)", type="primary", disabled=not ready):
        recipients = [(r["index"], r["email"]) for r in detected]
        with st.spinner("Sending payslips…"):
            results, fatal = send_payslips(
                st.session_state["ps_parsed"]["pdf"], recipients,
                sender_email, app_password, sender_name, month_name, year.strip(),
            )
        if fatal:
            st.error(f"❌ {fatal} Check the sender email / app password in secrets.")
        else:
            sent = [e for e, ok, _ in results if ok]
            failed = [(e, err) for e, ok, err in results if not ok]
            if sent:
                st.success(f"✅ Sent {len(sent)} payslip(s).")
            for email, err in failed:
                st.error(f"❌ Failed to send to {email} ({err}).")
