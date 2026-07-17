"""Shared password gate for FL Toolkit.

Every page (including Home.py) calls `require_auth()` at the top, right after
`st.set_page_config(...)`. The password lives in Streamlit secrets under
`app_password` — never hardcoded, never committed. Locally that means
`.streamlit/secrets.toml`; on Streamlit Community Cloud it's the Secrets
manager in the app dashboard.
"""

from __future__ import annotations

import streamlit as st

# Key used to remember that this browser session already authenticated.
_SESSION_KEY = "fl_authenticated"


def _expected_password() -> str:
    """Read the shared password from secrets, with a clear error if missing."""
    try:
        return st.secrets["app_password"]
    except (KeyError, FileNotFoundError):
        st.error(
            "🔧 **App password is not configured.**\n\n"
            "Add an `app_password` entry to your secrets:\n"
            "- **Local:** `.streamlit/secrets.toml`\n"
            "- **Streamlit Cloud:** the app's *Settings → Secrets* manager\n\n"
            "Example:\n```toml\napp_password = \"your-shared-password\"\n```"
        )
        st.stop()


def require_auth() -> None:
    """Block the current page until the shared password is entered correctly.

    Call once at the top of every page script. If the session is already
    authenticated, this just renders the sidebar log-out control and returns.
    Otherwise it renders the login form and halts the script with `st.stop()`.
    """
    if st.session_state.get(_SESSION_KEY):
        _render_logout()
        return

    st.title("🔒 FL Toolkit")
    st.caption("Internal tools — enter the shared password to continue.")

    with st.form("fl_login", clear_on_submit=False):
        entered = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Enter")

    if submitted:
        if entered == _expected_password():
            st.session_state[_SESSION_KEY] = True
            st.rerun()
        else:
            st.error("😕 Incorrect password. Please try again.")

    # Nothing below the gate should run until authenticated.
    st.stop()


def _render_logout() -> None:
    """Small log-out button in the sidebar, shown on every authenticated page."""
    with st.sidebar:
        st.divider()
        if st.button("Log out", use_container_width=True):
            st.session_state[_SESSION_KEY] = False
            st.rerun()
