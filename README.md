# bib-to-rcaap

This project converts BibTeX metadata into rows written to a Google Spreadsheet formatted for RCAAP. It supports Authors, Titles, Events and Logs tabs.

## Setup ✅

1. Create a Python virtual environment and activate it:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. For local runs: place your Google service account credentials JSON at the project root as `credentials.json` (this file is in `.gitignore` and should never be committed), or set `CREDENTIALS_PATH` to an alternate path.

4. For Streamlit Cloud: add your service account JSON to the app Secrets as `gcp_service_account` (see below). When present, the app will prefer `st.secrets["gcp_service_account"]` and will not try to read a local `credentials.json` file.

Notes on configuration:

- `SPREADSHEET_ID` — the Google spreadsheet ID (defaults to the one in the repo)
- `CREDENTIALS_PATH` — path to service account JSON (defaults to `credentials.json`, used for local runs only unless `creds_info` is not provided)

You can set these in a `.env` file or export them in your shell for local runs.
## Usage 🔧

Dry run (parses file and prints what would be written):

```bash
python parse_bib.py path/to/file.bib --dry-run --write-authors --write-titles --write-events
```

To perform actual writes:

```bash
python parse_bib.py path/to/file.bib --write-authors --write-titles --write-events
```

The CLI will always append a log entry to the `Logs` sheet recording the action.

## Mapping details ✍️

- Authors: includes `name` (original string), `name_normalized` ("Given Family"), `given_name`, `family_name`, `affiliation`, `key`, `order`, `orcid`.
- Titles: includes `key`, `title`, `year`, `journal`, `doi`, `url`, `abstract`, `pages`, `volume`, `number`, `publisher`, `keywords`, `language`.
- Events: attempts to map `booktitle` / `event` / `journal` and sets `date`, `venue`, `year`.
- Logs: timestamped entries with `level` and `message`.

## Tests ✅

Run tests with:

```bash
pytest
```

## Web UI (Streamlit) 🖥️

You can run a simple web interface to upload `.bib` files, preview parsed rows and sync to your RCAAP sheet:

```bash
streamlit run app.py
```

Notes:
- Use the sidebar to upload a `.bib` file, choose which tabs to sync and run searches on the existing sheet.
- The app uses the same `SPREADSHEET_ID` configuration as the CLI.
- On Streamlit Cloud, set your service account JSON in the app's Secrets as `gcp_service_account` (either as a TOML mapping or JSON string). The app will use `st.secrets["gcp_service_account"]` to authenticate so you don't need a local `credentials.json` file.

DOI integration:
- You can paste a DOI or a DOI-based URL in the sidebar and click **Fetch metadata from DOI**. If a DOI is detected the app will fetch metadata via Crossref and show a preview row ready to sync or export.

RCAAP export:
- After parsing or fetching, click **Download RCAAP Metadata** to generate a CSV with headers: `dc.title`, `dc.contributor.author`, `dc.date.issued`, `dc.publisher`, `dc.identifier.doi`.
- Author names are formatted as `Given Family` (normalized) and are joined with a **semicolon (;)** as required by RCAAP.

## Security notes ⚠️

- Keep `credentials.json` private and do not check it into source control.
- For production or multi-user deployment consider using a more secure credential management approach.

---

If you'd like, I can add more advanced normalisation (name parsing for non-western names), ORCID lookups, or support richer field mapping. Just tell me which feature to prioritize.