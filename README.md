# FL Toolkit

Internal utility web app — a single Streamlit site that bundles several
standalone tools behind one shared password. Non-technical staff open one URL,
pick a tool from the sidebar, upload a file, and download the result. No local
installs, no terminal, no GitHub.

## Live tools

| Tool | Page | Source repo | Notes |
|---|---|---|---|
| Compress PDF | `pages/1_Compress_PDF.py` | `pdfbot` | Ghostscript compression, 4 quality presets |

_Deferred (not yet migrated): Shipping Labels (uniqlo-lionParcel), Phonics
(tts-phonics), Tax Tools (tax_tools), Rename BUPOT (renameBUPOT)._

## Access control

Every page sits behind a single shared password (`auth.require_auth()`). The
password is read from Streamlit secrets — never hardcoded, never committed.

- **Local:** create `.streamlit/secrets.toml` (copy from
  `.streamlit/secrets.toml.example`) and set `app_password`.
- **Streamlit Community Cloud:** set `app_password` in the app's
  *Settings → Secrets* manager.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# also install Ghostscript system-wide (macOS: brew install ghostscript)
cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # then edit the password
streamlit run Home.py
```

## Deploy (Streamlit Community Cloud)

1. Push this repo to GitHub (must be **public** for the free tier).
2. On [share.streamlit.io](https://share.streamlit.io), create an app pointing
   at this repo with `Home.py` as the entry point.
3. Add `app_password` (and any future API keys) in the app's Secrets manager.
4. Python deps come from `requirements.txt`; system packages (Ghostscript) from
   `packages.txt`. Pushing a commit auto-redeploys.

## Adding a new tool

1. Drop a new script in `pages/` named `N_Tool_Name.py`.
2. Call `st.set_page_config(...)` then `require_auth()` at the top.
3. Replace file-path/CLI I/O with `st.file_uploader()` / `st.download_button()`.
4. Add any Python deps to `requirements.txt` and system deps to `packages.txt`.
5. Add a directory entry in `Home.py`.

## Privacy

Uploaded files are processed in-memory per session and are **not** stored on the
server. No real customer, employee, or tax data is committed to this repo.
