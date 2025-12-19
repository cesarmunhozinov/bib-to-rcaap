"""Streamlit app for BibTeX -> RCAAP Google Sheets sync."""
from __future__ import annotations

import io
import logging
from typing import List, Dict

import streamlit as st
import bibtexparser
from bibtexparser.bparser import BibTexParser
from bibtexparser.customization import homogenize_latex_encoding

from bibtex_parser import entries_to_titles, entries_to_authors
from database import RCAAPDatabase

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("bib-to-rcaap-app")

st.set_page_config(page_title="RCAAP Converter", layout="wide")
st.title("BibTeX → RCAAP Converter")

# Compact sidebar styling: reduce vertical spacing, tighter dividers, and ensure elements are comfortably laid out
st.markdown(
    """
    <style>
    /* Target the sidebar container */
    [data-testid="stSidebar"] .block-container { padding: 6px 10px; }
    /* Tighter spacing between widgets and markdown labels */
    [data-testid="stSidebar"] .stButton, [data-testid="stSidebar"] .stTextInput, [data-testid="stSidebar"] .stFileUploader, [data-testid="stSidebar"] .stRadio { margin-top: 4px; margin-bottom: 6px; }
    [data-testid="stSidebar"] .stMarkdown { margin: 4px 0 2px 0; }
    /* Compact horizontal rule for sidebar dividers */
    [data-testid="stSidebar"] hr { margin: 6px 0; border: none; border-top: 1px solid #eee; }
    /* Make sidebar buttons full width (and not cramped) */
    [data-testid="stSidebar"] .stButton>button { width:100%; }
    </style>
    """,
    unsafe_allow_html=True,
)


uploaded = st.sidebar.file_uploader("Upload a .bib file", type=["bib"])

preview_limit = 50  # fixed preview rows limit


st.sidebar.markdown("<hr style='margin:6px 0;border:none;border-top:1px solid #eee'>", unsafe_allow_html=True)
doi_input = st.sidebar.text_input("Enter DOI", placeholder="Enter DOI", label_visibility="collapsed")
fetch_doi = st.sidebar.button("Fetch metadata from DOI")

st.sidebar.markdown("<hr style='margin:6px 0;border:none;border-top:1px solid #eee'>", unsafe_allow_html=True)
search_query = st.sidebar.text_input("Search by", placeholder="Search (Author or Title)", label_visibility="collapsed")
search_kind = st.sidebar.radio("Search by", ["Title", "Author"], label_visibility="collapsed")

if st.sidebar.button("Run search"):
    if not search_query.strip():
        st.sidebar.warning("Enter a search term first.")
    else:
        try:
            # Access st.secrets safely — parsing can raise if no secrets file is present
            try:
                creds_info = st.secrets.get("gcp_service_account")
            except Exception:
                creds_info = None

            db = RCAAPDatabase(creds_info=creds_info)
            # cached through the class
            # Use the relational 'Title' sheet and 'Authors' sheet
            titles = db._get_ws("Title").get_all_records()
            authors = db._get_ws("Authors").get_all_records()

            if search_kind == "Title":
                # title sheet uses 'Title' header; fall back to lowercase 'title' if present
                results = [t for t in titles if search_query.lower() in str(t.get("Title", "") or t.get("title", "")).lower()]
            else:
                # authors sheet uses 'Author Name'
                matches = [a for a in authors if search_query.lower() in str(a.get("Author Name", "")).lower()]
                keys = {m.get("ID Author") for m in matches}
                # For author search, return titles that are linked to matching authors via the Author-Title junction
                # Load junction table and find title IDs
                try:
                    at_rows = db._get_ws('Author-Title').get_all_records()
                    title_ids = {r.get('ID Title') for r in at_rows if r.get('ID Author') in keys}
                    results = [t for t in titles if t.get('ID Title') in title_ids]
                except Exception:
                    results = []

            st.sidebar.success(f"Found {len(results)} results")
            st.subheader("Search results")
            st.table(results[:preview_limit])
        except Exception as e:
            st.sidebar.error(f"Search failed: {e}")

# helper: extract DOI from text
import re
from crossref.restful import Works


def extract_doi(text: str) -> str | None:
    """Extract a DOI from arbitrary text or a URL.

    Tries several patterns:
    - DOI in a doi.org URL (e.g. https://doi.org/10.1234/abc)
    - DOI as a query parameter (?doi=10.xxx/...)
    - Generic DOI pattern anywhere in the text
    Returns the DOI without surrounding punctuation, or None if not found.
    """
    if not text:
        return None
    text = text.strip()
    # Try doi.org path
    m = re.search(r"doi\.org/(?P<doi>10\.\d{4,9}/[^\s\"'<>]+)", text, re.I)
    if not m:
        # DOI in query param
        m = re.search(r"[?&]doi=(?P<doi>10\.\d{4,9}/[^&\s]+)", text, re.I)
    if not m:
        # generic DOI anywhere
        m = re.search(r"(10\.\d{4,9}/[-._;()/:A-Z0-9]+)", text, re.I)
    if not m:
        return None
    doi = m.group(1)
    # strip trailing punctuation that commonly appears after DOIs in text
    return doi.rstrip(").,;\"'")


# Parse uploaded file and show preview
entries: List[Dict] | None = None
if uploaded is not None:
    try:
        text = uploaded.read().decode("utf-8")
        parser = BibTexParser()
        parser.customization = homogenize_latex_encoding
        bibdb = bibtexparser.loads(text, parser=parser)
        entries = bibdb.entries
        st.success(f"Parsed {len(entries)} entries")

    except Exception as e:
        st.error(f"Failed to parse file: {e}")

# If DOI fetch requested, try to fetch metadata
if doi_input and fetch_doi:
    doi = extract_doi(doi_input)
    if not doi:
        # If the user pasted a URL but we couldn't find a DOI inside it, show a helpful message
        if re.search(r"https?://|^www\.|doi\.org", doi_input, re.I):
            st.sidebar.error("No DOI found. Please paste a DOI (e.g., 10.3390/joitmc7010070) or a DOI-based URL.")
        else:
            st.sidebar.error("No DOI detected in the input. Please paste a DOI like 10.3390/joitmc7010070.")
    else:
        try:
            works = Works()
            msg = works.doi(doi)
            # build an entry compatible with the parser functions
            title = msg.get("title")
            if isinstance(title, list):
                title = title[0] if title else ""
            authors_list = []
            for a in msg.get("author", []):
                fam = a.get("family", "")
                giv = a.get("given", "")
                if fam and giv:
                    authors_list.append(f"{fam}, {giv}")
                elif fam:
                    authors_list.append(fam)
                elif giv:
                    authors_list.append(giv)
            author_field = " and ".join(authors_list)
            entry = {
                "ID": doi.replace("/", "_"),
                "title": title,
                "author": author_field,
                "year": str(msg.get("issued", {}).get("date-parts", [[""]])[0][0]) if msg.get("issued") else "",
                "journal": msg.get("container-title", [""])[0] if msg.get("container-title") else "",
                "doi": doi,
                "url": msg.get("URL", ""),
                "publisher": msg.get("publisher", ""),
            }
            entries = [entry]
            st.sidebar.success("Metadata fetched from Crossref")
        except Exception as e:
            st.sidebar.error(f"Crossref fetch failed: {e}")

# If we have entries (either from upload or DOI fetch), map them
titles = []
authors = []
if entries:
    titles = entries_to_titles(entries)
    authors = entries_to_authors(entries)

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Titles (preview)")
        st.table(titles[:preview_limit])
    with col2:
        st.subheader("Authors (preview)")
        st.table(authors[:preview_limit])

    # RCAAP export (primary action): generate CSV from the relational sheets if available (fallback to local parsed rows)
    def generate_rcaap_csv(db: RCAAPDatabase | None, titles_list, authors_list) -> str:
        import csv
        import io

        output = io.StringIO()
        writer = csv.writer(output)
        headers = ["dc.title", "dc.contributor.author", "dc.date.issued", "dc.publisher", "dc.identifier.doi"]
        writer.writerow(headers)

        # Attempt to use the relational sheets if a DB was provided and connected
        if db is not None:
            try:
                # Read relational sheets
                try:
                    title_rows = db._get_ws('Title').get_all_records()
                except Exception:
                    title_rows = []
                try:
                    venue_rows = db._get_ws('Venue').get_all_records()
                except Exception:
                    venue_rows = []
                try:
                    publisher_rows = db._get_ws('Publisher').get_all_records()
                except Exception:
                    publisher_rows = []
                try:
                    author_rows = db._get_ws('Authors').get_all_records()
                except Exception:
                    author_rows = []
                try:
                    author_title_rows = db._get_ws('Author-Title').get_all_records()
                except Exception:
                    author_title_rows = []

                # build maps
                pub_map = {p.get('ID Publisher'): p.get('Publisher Name') for p in publisher_rows}
                venue_map = {v.get('ID Venue'): v for v in venue_rows}
                author_map = {a.get('ID Author'): a.get('Author Name') for a in author_rows}

                # group author-title by title
                from collections import defaultdict

                tt = defaultdict(list)
                for at in author_title_rows:
                    tt[at.get('ID Title', '')].append((int(at.get('Order') or 0), at.get('ID Author')))

                for t in title_rows:
                    id_title = t.get('ID Title')
                    title_str = t.get('Title', '')
                    year = t.get('Year', '')
                    doi = t.get('DOI', '')
                    pub_name = ''
                    id_venue = t.get('ID Venue', '')
                    if id_venue:
                        v = venue_map.get(id_venue)
                        if v:
                            id_pub = v.get('ID Publisher')
                            pub_name = pub_map.get(id_pub, '')
                    auths = tt.get(id_title, [])
                    auths_sorted = [author_map[a_id] for _, a_id in sorted(auths, key=lambda x: x[0])]
                    authors_joined = '; '.join(auths_sorted)

                    writer.writerow([title_str, authors_joined, year, pub_name, doi])

                return output.getvalue()
            except Exception:
                # fallback to local
                pass

        # Fallback: use local parsed lists passed in
        for t in titles_list:
            key = t.get("key")
            auths = [a.get("name_normalized") or a.get("name") for a in authors_list if a.get("key") == key]
            authors_joined = "; ".join(auths)
            writer.writerow([
                t.get("title", ""),
                authors_joined,
                t.get("year", ""),
                t.get("publisher", "") or "",
                t.get("doi", ""),
            ])
        return output.getvalue()

    # Try to create a DB connection and prefer relational export if possible
    try:
        try:
            creds_info = st.secrets.get("gcp_service_account")
        except Exception:
            creds_info = None
        db_for_export = RCAAPDatabase(creds_info=creds_info)
    except Exception:
        db_for_export = None

    csv_data = generate_rcaap_csv(db_for_export, titles, authors)

    # Primary: RCAAP export (download)
    st.download_button(
        "Download RCAAP Metadata",
        data=csv_data,
        file_name="rcaap_metadata.csv",
        mime="text/csv",
        key="rcaap_export",
    )

    # Secondary: sync to Google Sheets
    if st.button("Sync to Google Sheets", key="sync"):
        try:
            try:
                creds_info = st.secrets.get("gcp_service_account")
            except Exception:
                creds_info = None
            db = RCAAPDatabase(creds_info=creds_info)

            # Ensure relational sheets and headers exist
            def _ensure_sheet_and_header(title: str, headers: list[str]):
                try:
                    ws = db._get_ws(title)
                except Exception:
                    # create worksheet if missing
                    db.sheet.add_worksheet(title=title, rows=100, cols=20)
                    db._worksheets = {ws.title: ws for ws in db.sheet.worksheets()}
                    ws = db._get_ws(title)
                db._ensure_header(ws, headers)

            # Desired schema
            _ensure_sheet_and_header('Publisher', ['ID Publisher', 'Publisher Name'])
            _ensure_sheet_and_header('Venue', ['ID Venue', 'Venue Name', 'ID Publisher'])
            _ensure_sheet_and_header('Title', ['ID Title', 'Title', 'Year', 'ID Venue', 'DOI', 'URL', 'Abstract', 'Type', 'Language', 'Keywords'])
            _ensure_sheet_and_header('Authors', ['ID Author', 'Author Name', 'ORCID', 'Affiliation'])
            _ensure_sheet_and_header('Author-Title', ['ID Author', 'ID Title', 'Order'])

            # helper getters / creators that operate on the sheet data
            def _next_id(existing_ids: list[str], prefix: str) -> str:
                nums = [int(s.lstrip(prefix)) for s in existing_ids if s.startswith(prefix) and s.lstrip(prefix).isdigit()]
                maxn = max(nums) if nums else 0
                return f"{prefix}{(maxn+1):03d}"

            def get_or_create_publisher(name: str) -> str:
                name = (name or "").strip()
                ws = db._get_ws('Publisher')
                rows = ws.get_all_records()
                for r in rows:
                    if r.get('Publisher Name', '').strip() == name:
                        return r.get('ID Publisher')
                # create new
                existing_ids = [r.get('ID Publisher', '') for r in rows]
                nid = _next_id(existing_ids, 'P')
                db._append_dicts('Publisher', [{'ID Publisher': nid, 'Publisher Name': name}])
                return nid

            def get_or_create_venue(name: str, id_publisher: str) -> str:
                name = (name or "").strip()
                ws = db._get_ws('Venue')
                rows = ws.get_all_records()
                for r in rows:
                    if r.get('Venue Name', '').strip() == name:
                        # ensure publisher link
                        if r.get('ID Publisher') != id_publisher:
                            r['ID Publisher'] = id_publisher
                        return r.get('ID Venue')
                existing_ids = [r.get('ID Venue', '') for r in rows]
                nid = _next_id(existing_ids, 'V')
                db._append_dicts('Venue', [{'ID Venue': nid, 'Venue Name': name, 'ID Publisher': id_publisher}])
                return nid

            def get_or_create_author(name: str, orcid: str = '', affiliation: str = '') -> str:
                name = (name or "").strip()
                ws = db._get_ws('Authors')
                rows = ws.get_all_records()
                for r in rows:
                    if r.get('Author Name', '').strip() == name:
                        # update missing info
                        if orcid and not r.get('ORCID'):
                            r['ORCID'] = orcid
                        if affiliation and not r.get('Affiliation'):
                            r['Affiliation'] = affiliation
                        return r.get('ID Author')
                existing_ids = [r.get('ID Author', '') for r in rows]
                nid = _next_id(existing_ids, 'A')
                db._append_dicts('Authors', [{'ID Author': nid, 'Author Name': name, 'ORCID': orcid or '', 'Affiliation': affiliation or ''}])
                return nid

            def create_or_get_title_id(title_row: dict) -> str:
                # Prefer matching by DOI if present, else by Title text
                ws = db._get_ws('Title')
                rows = ws.get_all_records()
                doi = (title_row.get('doi') or '').strip()
                for r in rows:
                    if doi and r.get('DOI', '').strip().lower() == doi.lower():
                        return r.get('ID Title')
                # Not found -> create
                existing_ids = [r.get('ID Title', '') for r in rows]
                nid = _next_id(existing_ids, 'T')
                db._append_dicts('Title', [{
                    'ID Title': nid,
                    'Title': title_row.get('title', ''),
                    'Year': title_row.get('year', ''),
                    'ID Venue': title_row.get('id_venue', ''),
                    'DOI': title_row.get('doi', ''),
                    'URL': title_row.get('url', ''),
                    'Abstract': title_row.get('abstract', ''),
                    'Type': title_row.get('type', ''),
                    'Language': title_row.get('language', ''),
                    'Keywords': title_row.get('keywords', ''),
                }])
                return nid

            def ensure_author_title_link(id_author: str, id_title: str, order: int) -> None:
                ws = db._get_ws('Author-Title')
                rows = ws.get_all_records()
                for r in rows:
                    if r.get('ID Author') == id_author and r.get('ID Title') == id_title:
                        # update order
                        if int(r.get('Order') or 0) != order:
                            r['Order'] = str(order)
                        return
                db._append_dicts('Author-Title', [{'ID Author': id_author, 'ID Title': id_title, 'Order': str(order)}])

            # Build relational rows by calling the sync helper
            from relational_sync import sync_entries
            sync_entries(db, titles, authors, source=(uploaded.name if uploaded is not None else doi_input))
            st.success('Sync Complete.')
        except Exception as e:
            st.error(f"Sync failed: {e}")
else:
    st.info("Upload a .bib file from the sidebar to start, or fetch metadata by DOI.")

st.markdown("---")
# Show which credentials source is in use
import os
creds_source = None
try:
    creds_info_probe = st.secrets.get("gcp_service_account")
except Exception:
    creds_info_probe = None

if creds_info_probe:
    creds_source = "Streamlit secrets (gcp_service_account)"
elif os.path.exists("credentials.json"):
    creds_source = "Local file: credentials.json"
else:
    creds_source = "No credentials found (set st.secrets['gcp_service_account'] on Streamlit Cloud or provide credentials.json locally)"

if "Streamlit secrets" in creds_source:
    # intentionally do not display a success message to keep the UI clean
    pass
elif "Local file" in creds_source:
    st.info(f"Auth: {creds_source}")
else:
    st.warning(creds_source)
