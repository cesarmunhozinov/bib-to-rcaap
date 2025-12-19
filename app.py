"""Streamlit app for BibTeX -> RCAAP Google Sheets sync."""
from __future__ import annotations

import io
import logging
from typing import List, Dict

import streamlit as st
import bibtexparser
from bibtexparser.bparser import BibTexParser
from bibtexparser.customization import homogenize_latex_encoding

from bibtex_parser import entries_to_titles, entries_to_authors, entries_to_events
from database import RCAAPDatabase

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("bib-to-rcaap-app")

st.set_page_config(page_title="Bib-to-RCAAP", layout="wide")
st.title("BibTeX → RCAAP Google Sheets")

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
            titles = db._get_ws("Titles").get_all_records()
            authors = db._get_ws("Authors").get_all_records()

            if search_kind == "Title":
                results = [t for t in titles if search_query.lower() in str(t.get("title", "")).lower()]
            else:
                matches = [a for a in authors if search_query.lower() in str(a.get("name", "")).lower() or search_query.lower() in str(a.get("name_normalized", "")).lower()]
                keys = {m.get("key") for m in matches}
                results = [t for t in titles if t.get("key") in keys]

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
events = []
if entries:
    titles = entries_to_titles(entries)
    authors = entries_to_authors(entries)
    events = entries_to_events(entries)

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Titles (preview)")
        st.table(titles[:preview_limit])
    with col2:
        st.subheader("Authors (preview)")
        st.table(authors[:preview_limit])

    # RCAAP export (primary action): generate CSV and expose a download button
    def generate_rcaap_csv(titles_list, authors_list) -> str:
        import csv
        import io

        output = io.StringIO()
        writer = csv.writer(output)
        headers = ["dc.title", "dc.contributor.author", "dc.date.issued", "dc.publisher", "dc.identifier.doi"]
        writer.writerow(headers)

        for t in titles_list:
            key = t.get("key")
            # find authors for this key, prefer normalized name
            auths = [a.get("name_normalized") or a.get("name") for a in authors_list if a.get("key") == key]
            authors_joined = "; ".join(auths)
            row = [
                t.get("title", ""),
                authors_joined,
                t.get("year", ""),
                t.get("publisher", "") or "",
                t.get("doi", ""),
            ]
            writer.writerow(row)
        return output.getvalue()

    csv_data = generate_rcaap_csv(titles, authors)

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
            # Always sync all available data by default
            if titles:
                db.write_titles(titles)
            if authors:
                db.write_authors(authors)
            if events:
                db.write_events(events)
            db.write_log(f"Streamlit sync: {uploaded.name if uploaded is not None else doi_input} (synced: titles, authors, events)")
            st.success("Sync complete")
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
    st.success(f"Auth: {creds_source}")
elif "Local file" in creds_source:
    st.info(f"Auth: {creds_source}")
else:
    st.warning(creds_source)
