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

st.sidebar.header("Actions")

uploaded = st.sidebar.file_uploader("Upload a .bib file", type=["bib"])

preview_limit = st.sidebar.number_input("Preview rows", min_value=1, max_value=500, value=50)

write_titles = st.sidebar.checkbox("Sync Titles", value=True)
write_authors = st.sidebar.checkbox("Sync Authors", value=True)
write_events = st.sidebar.checkbox("Sync Events", value=True)

st.sidebar.markdown("---")
st.sidebar.header("Search sheet")
search_query = st.sidebar.text_input("Search (Author or Title)")
search_kind = st.sidebar.radio("Search by", ["Title", "Author"])

if st.sidebar.button("Run search"):
    if not search_query.strip():
        st.sidebar.warning("Enter a search term first.")
    else:
        try:
            db = RCAAPDatabase()
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

        if st.button("Sync to Google Sheets", key="sync"):
            try:
                db = RCAAPDatabase()
                if write_titles and titles:
                    db.write_titles(titles)
                if write_authors and authors:
                    db.write_authors(authors)
                if write_events and events:
                    db.write_events(events)
                db.write_log(f"Streamlit sync: {uploaded.name} (titles={write_titles}, authors={write_authors}, events={write_events})")
                st.success("Sync complete")
            except Exception as e:
                st.error(f"Sync failed: {e}")
    except Exception as e:
        st.error(f"Failed to parse file: {e}")
else:
    st.info("Upload a .bib file from the sidebar to start.")

st.markdown("---")
st.caption("Uses service account credentials from `credentials.json` by default.")
