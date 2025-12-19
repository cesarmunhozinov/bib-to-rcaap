"""database.py
Utilities to connect to a Google Spreadsheet (RCAAP format) and write to the 5-table relational schema:
- Publisher
- Venue
- Title
- Authors
- Author-Title

Usage:
- Place your service account JSON at `credentials.json` (ignored by .gitignore)
- Optionally set SPREADSHEET_ID and CREDENTIALS_PATH in a `.env` file

Example:
from database import RCAAPDatabase
db = RCAAPDatabase()  # will use env or defaults
# Use the relational sync helpers to write Publisher, Venue, Title, Authors, and Author-Title
"""

from __future__ import annotations

import os
import time
from datetime import datetime
from typing import List, Dict, Any, Optional, Union

from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials

import json

load_dotenv()

# Defaults
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID", "1_hYnsfLbk2bD2Bivm7Inlw2kp6vSy4BA1FecHv4ZlEs")
CREDENTIALS_PATH = os.getenv("CREDENTIALS_PATH", "credentials.json")
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

REQUIRED_TABS = ["Publisher", "Venue", "Title", "Authors", "Author-Title"]


class RCAAPDatabase:
    """Class to manage connections and writes to the RCAAP-formatted Google Sheet.

    This class uses lazy connection: importing the module won't connect. Call
    `connect()` or one of the write methods to trigger the connection.

    It supports two ways to provide service-account credentials:
    - A path to a JSON file (default, via `creds_path`)
    - A service-account info `dict` or JSON string (via `creds_info`), useful when
      running on Streamlit Cloud using `st.secrets["gcp_service_account"]`.
    """

    def __init__(self, spreadsheet_id: str = SPREADSHEET_ID, creds_path: str = CREDENTIALS_PATH, creds_info: Optional[Union[dict, str]] = None):
        self.spreadsheet_id = spreadsheet_id
        self.creds_path = creds_path
        self.creds_info = creds_info
        self.client: Optional[gspread.Client] = None
        self.sheet: Optional[gspread.Spreadsheet] = None
        self._worksheets: Dict[str, gspread.Worksheet] = {}

    def connect(self) -> None:
        """Authenticate and open the spreadsheet. No-op if already connected."""
        if self.sheet is not None:
            return

        # If creds_info provided (dict or JSON string), prefer it (Streamlit Cloud st.secrets)
        creds = None
        if self.creds_info is not None:
            info = self.creds_info
            if isinstance(info, str):
                try:
                    info = json.loads(info)
                except Exception:
                    # If it's not valid JSON, leave it as-is and let from_service_account_info raise
                    pass
            creds = Credentials.from_service_account_info(info, scopes=SCOPES)
        else:
            # Fall back to file-based credentials
            if not os.path.exists(self.creds_path):
                raise FileNotFoundError(f"Credentials file not found: {self.creds_path}")
            creds = Credentials.from_service_account_file(self.creds_path, scopes=SCOPES)

        self.client = gspread.authorize(creds)
        self.sheet = self.client.open_by_key(self.spreadsheet_id)

        # Ensure required tabs exist
        existing = {ws.title for ws in self.sheet.worksheets()}
        for title in REQUIRED_TABS:
            if title not in existing:
                # Create with 100 rows and 20 cols default
                self.sheet.add_worksheet(title=title, rows=100, cols=20)

        # Cache worksheet objects
        self._worksheets = {ws.title: ws for ws in self.sheet.worksheets()}

    def _get_ws(self, title: str) -> gspread.Worksheet:
        if self.sheet is None:
            self.connect()
        ws = self._worksheets.get(title)
        if ws is None:
            ws = self.sheet.worksheet(title)
            self._worksheets[title] = ws
        return ws

    def _ensure_header(self, ws: gspread.Worksheet, headers: List[str]) -> List[str]:
        """Make sure the worksheet has a header row. Return the header as list.
        If the worksheet is empty, write the header.
        """
        values = ws.get_all_values()
        if not values or not any(values):
            ws.insert_row(headers, index=1)
            return headers
        return values[0]

    def _append_dicts(self, title: str, rows: List[Dict[str, Any]]) -> None:
        if not rows:
            return
        ws = self._get_ws(title)
        headers = list(rows[0].keys())
        existing_header = self._ensure_header(ws, headers)

        # If existing header differs, merge columns: union
        if existing_header != headers:
            # compute final header order
            final_headers = list(dict.fromkeys(existing_header + headers))
            # rewrite header (we keep it simple, not migrating rows)
            ws.delete_rows(1)
            ws.insert_row(final_headers, index=1)
            existing_header = final_headers

        # Map dicts to rows according to existing_header
        to_append = []
        for d in rows:
            row = [d.get(col, "") for col in existing_header]
            to_append.append(row)

        ws.append_rows(to_append, value_input_option="USER_ENTERED")

    def write_authors(self, rows: List[Dict[str, Any]]) -> None:
        """Write author entries to `Authors` tab.

        This enforces an exact 4-column schema: 'ID Author', 'Author Name', 'ORCID', 'Affiliation'.
        Any incoming rows will be mapped to these keys (e.g., 'name' or 'name_normalized' -> 'Author Name')
        to avoid appending legacy/extra columns to the sheet.
        """
        if not rows:
            return
        ws = self._get_ws("Authors")
        headers = ["ID Author", "Author Name", "ORCID", "Affiliation"]
        # Replace header exactly if it differs to enforce schema
        existing = ws.get_all_values()
        if not existing or not any(existing):
            ws.insert_row(headers, index=1)
        else:
            current_header = existing[0]
            if current_header != headers:
                try:
                    ws.delete_rows(1)
                except Exception:
                    pass
                ws.insert_row(headers, index=1)

        to_append = []
        for r in rows:
            author_name = r.get('Author Name') or r.get('name_normalized') or r.get('name') or ''
            row = [r.get('ID Author', ''), author_name, r.get('ORCID', ''), r.get('Affiliation', '')]
            to_append.append(row)

        ws.append_rows(to_append, value_input_option="USER_ENTERED")

    # Legacy single-tab writer helpers (Titles, Events, Logs) removed to enforce the
    # normalized 5-table relational schema. Use `relational_sync.sync_entries` to
    # synchronise data to 'Publisher', 'Venue', 'Title', 'Authors', and 'Author-Title'.



if __name__ == "__main__":
    # Basic friendly test (won't run automatically on import)
    print("database.py loaded. Instantiate RCAAPDatabase and call methods to write data.")
    print("Example:\n  from database import RCAAPDatabase\n  db = RCAAPDatabase()\n  # Use relational sync helpers to write Publisher/Venue/Title/Authors/Author-Title")
