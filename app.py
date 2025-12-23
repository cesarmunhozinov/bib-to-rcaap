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
from enrichment import enrich_entry, validate_entry, RCAAP_TYPES, RCAAP_REQUIRED_FIELDS

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

# --- Preview rendering helpers (Google Scholar style) ---

def _format_initial(given: str) -> str:
    return (given.strip()[0] + '.') if given and given.strip() else ''


def _parse_order(val) -> int:
    try:
        return int(val)
    except Exception:
        try:
            return int(float(val))
        except Exception:
            return 0


def _format_author_name_from_parts(given: str, family: str) -> str:
    if not family and not given:
        return ''
    if not family:
        return given
    initial = _format_initial(given)
    return f"{family}, {initial}" if initial else family


def _authors_for_db_title(title_row: dict, db: RCAAPDatabase) -> str:
    try:
        at_rows = db._get_ws('Author-Title').get_all_records()
        authors_rows = db._get_ws('Authors').get_all_records()
    except Exception:
        return ''
    title_id = title_row.get('ID Title')
    links = [r for r in at_rows if r.get('ID Title') == title_id]
    ordered = sorted(links, key=lambda x: int(x.get('Order') or 0))
    id_to_author = {r.get('ID Author'): r.get('Author Name') for r in authors_rows}
    formatted = []
    for l in ordered:
        aid = l.get('ID Author')
        name = id_to_author.get(aid, '')
        if not name:
            continue
        parts = name.strip().split()
        if len(parts) == 1:
            given, family = parts[0], ''
        else:
            given, family = ' '.join(parts[:-1]), parts[-1]
        formatted.append(_format_author_name_from_parts(given, family))
    return '; '.join([f for f in formatted if f])


def _assemble_preview_row(title_row: dict, db: RCAAPDatabase | None = None, parsed_authors: list[dict] | None = None) -> dict:
    """Return a merged dict containing Title, Year, DOI, URL, Venue Name, and authors_line.

    Uses DB joins (Author-Title + Authors + Venue) when db is provided. Falls back to parsed authors and
    `journal` field for venue. Ensures placeholders for missing data (e.g., 'Unknown Venue')."""
    # Base title info
    title_text = title_row.get('Title') or title_row.get('title') or ''
    doi = (title_row.get('DOI') or title_row.get('doi') or '').strip()
    url = title_row.get('URL') or title_row.get('url') or ''
    year = title_row.get('Year') or title_row.get('year') or ''

    venue_name = ''
    authors_line = ''

    # Try DB-based assembly if db is provided
    if db is not None:
        # Venue via ID Venue
        id_venue = title_row.get('ID Venue')
        try:
            venue_rows = db._get_ws('Venue').get_all_records()
            if id_venue:
                vm = next((r for r in venue_rows if r.get('ID Venue') == id_venue), None)
                venue_name = vm.get('Venue Name') if vm else ''
            # fallback: try to match by journal name
            if not venue_name:
                journal_name = title_row.get('journal') or title_row.get('Venue') or ''
                if journal_name:
                    vm = next((r for r in venue_rows if (r.get('Venue Name') or '').strip().lower() == journal_name.strip().lower()), None)
                    venue_name = vm.get('Venue Name') if vm else ''
        except Exception:
            venue_name = ''

        # Authors via Author-Title junction
        try:
            at_rows = db._get_ws('Author-Title').get_all_records()
            authors_rows = db._get_ws('Authors').get_all_records()
            title_id = title_row.get('ID Title') or ''
            links = [r for r in at_rows if r.get('ID Title') == title_id]
            ordered = sorted(links, key=lambda x: _parse_order(x.get('Order')))
            id_to_author = {r.get('ID Author'): r.get('Author Name') for r in authors_rows}
            formatted = []
            for l in ordered:
                aid = l.get('ID Author')
                name = id_to_author.get(aid, '')
                if not name:
                    continue
                parts = name.strip().split()
                if len(parts) == 1:
                    given, family = parts[0], ''
                else:
                    given, family = ' '.join(parts[:-1]), parts[-1]
                formatted.append(_format_author_name_from_parts(given, family))
            authors_line = '; '.join([f for f in formatted if f])
        except Exception:
            authors_line = ''

    # Fallbacks when DB is not available or data not found
    if not venue_name:
        venue_name = title_row.get('journal') or title_row.get('Venue') or 'Unknown Venue'

    if not authors_line and parsed_authors is not None:
        try:
            key = title_row.get('key')
            auths = [a for a in parsed_authors if a.get('key') == key]
            auths_sorted = sorted(auths, key=lambda x: int(x.get('order', 0)))
            formatted = []
            for a in auths_sorted:
                given = a.get('given_name') or ''
                family = a.get('family_name') or ''
                if not (given or family):
                    name_norm = a.get('name_normalized') or a.get('name') or ''
                    parts = name_norm.strip().split()
                    if len(parts) == 1:
                        given, family = parts[0], ''
                    else:
                        given, family = ' '.join(parts[:-1]), parts[-1]
                formatted.append(_format_author_name_from_parts(given, family))
            authors_line = '; '.join([f for f in formatted if f])
        except Exception:
            authors_line = ''

    if not authors_line:
        authors_line = ''

    return {
        'Title': title_text,
        'Year': year,
        'DOI': doi,
        'URL': url,
        'Venue Name': venue_name,
        'authors_line': authors_line,
        # keep original ids for reference
        'ID Title': title_row.get('ID Title') or title_row.get('id') or title_row.get('key'),
        'ID Venue': title_row.get('ID Venue') or None,
    }


def _build_display_object_from_bib_entry(entry: dict) -> dict:
    """Create a display object from a raw parsed BibTeX entry using exact BibTeX keys.

    Returns a dict that matches fields consumed by `_render_article_preview`.
    """
    display_title = entry.get('title') or entry.get('Title') or 'Untitled'
    display_authors = entry.get('author') or entry.get('Author') or 'Unknown'
    display_venue = entry.get('journal') or entry.get('booktitle') or 'N/A'
    display_year = entry.get('year') or entry.get('Year') or ''
    display_doi = entry.get('doi') or entry.get('DOI') or ''
    display_url = entry.get('url') or entry.get('URL') or ''

    return {
        'Title': display_title,
        'Year': display_year,
        'DOI': display_doi,
        'URL': display_url,
        'Venue Name': display_venue,
        'authors_line': display_authors,
        'ID Title': entry.get('ID') or entry.get('id') or entry.get('key'),
        'ID Venue': None,
    }


def _render_article_preview(title_row: dict, db: RCAAPDatabase | None = None, parsed_authors: list[dict] | None = None):
    # Accept either a raw title row or a preassembled merged dict
    merged = title_row if ('Venue Name' in title_row or 'authors_line' in title_row) else _assemble_preview_row(title_row, db=db, parsed_authors=parsed_authors)

    title_text = merged.get('Title') or ''
    doi = (merged.get('DOI') or '').strip()
    url = merged.get('URL') or ''
    link = ''
    if doi:
        link = f"https://doi.org/{doi}"
    elif url:
        link = url

    esc_title = title_text.replace('[', '\\[').replace(']', '\\]')

    if link:
        st.markdown(f"### **[{esc_title}]({link})**")
    else:
        st.markdown(f"### **{esc_title}**")

    authors_line = merged.get('authors_line') or ''
    if authors_line:
        st.markdown(f"<span style='color: #006621;'>{authors_line}</span>", unsafe_allow_html=True)

    venue_name = merged.get('Venue Name') or 'Unknown Venue'
    year = merged.get('Year') or ''
    if venue_name or year:
        st.markdown(f"{venue_name} {str(year)}")

    st.markdown("<hr style='margin:8px 0;'>", unsafe_allow_html=True)


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
            for t in results[:preview_limit]:
                try:
                    merged = _assemble_preview_row(t, db=db, parsed_authors=None)
                    _render_article_preview(merged, db=db, parsed_authors=None)
                except Exception as e:
                    logger.exception("Failed to render preview for search result: %s", e)
                    st.warning(f"Preview unavailable for a search result: {e}")
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


# ---- Safe-mode parsing + display preview (zero DB) ----

def _format_author_name_safe(name: str) -> str:
    """Format a single author to "Lastname, F." using a forgiving heuristic."""
    if not name:
        return ""
    name = name.strip()
    if not name:
        return ""
    if "," in name:
        parts = [p.strip() for p in name.split(",") if p.strip()]
        family = parts[0] if parts else ""
        given = parts[1] if len(parts) > 1 else ""
    else:
        tokens = name.split()
        if not tokens:
            return ""
        family = tokens[-1]
        given = " ".join(tokens[:-1])
    initial = f" {given[0]}." if given else ""
    return f"{family},{initial}".strip()


def _format_authors_safe(raw_authors: str) -> str:
    if not raw_authors:
        return "Unknown Author"
    if raw_authors.strip().lower() == "unknown author":
        return "Unknown Author"
    parts = [a.strip() for a in raw_authors.split(" and ") if a.strip()]
    formatted = [_format_author_name_safe(p) for p in parts if _format_author_name_safe(p)]
    return "; ".join(formatted) if formatted else "Unknown Author"


def _build_display_entry(entry: dict) -> dict:
    """Map raw BibTeX entry to display_* keys with safe defaults."""
    return {
        "display_title": entry.get("title", "Untitled") or "Untitled",
        "display_authors": _format_authors_safe(entry.get("author", "Unknown Author")),
        "display_venue": entry.get("journal", entry.get("booktitle", "N/A")) or "N/A",
        "display_year": entry.get("year", "") or "",
        "display_abstract": entry.get("abstract", "No abstract in BibTeX") or "No abstract in BibTeX",
    }


def parse_bibtex_safe(text: str) -> tuple[list[dict], list[dict]]:
    """Parse raw .bib text to (raw_entries, display_entries) with zero-trust defaults."""
    parser = BibTexParser()
    parser.customization = homogenize_latex_encoding
    bibdb = bibtexparser.loads(text, parser=parser)
    raw_entries = bibdb.entries or []
    display_entries = [_build_display_entry(e) for e in raw_entries]
    return raw_entries, display_entries


def display_preview_safe(display_entries: list[dict]) -> None:
    """Render Scholar-style preview using only display_* keys, wrapped in try/except."""
    try:
        for entry in display_entries or []:
            st.markdown(f"### **{entry['display_title']}**")
            st.markdown(f"<p style=\"color: #006621;\">{entry['display_authors']}</p>", unsafe_allow_html=True)
            st.write(f"{entry['display_venue']}, {entry['display_year']}")
    except Exception as e:
        st.error(f"Preview error: {e}")


@st.cache_data
def _fetch_openalex_cached(doi: str):
    """Cached OpenAlex fetch to avoid repeated API calls."""
    from enrichment import fetch_from_openalex
    return fetch_from_openalex(doi)


# Parse uploaded file and show preview (safe-mode, zero DB)
entries: List[Dict] | None = None
display_entries: List[Dict] | None = None
if uploaded is not None:
    try:
        text = uploaded.read().decode("utf-8")
        entries, display_entries = parse_bibtex_safe(text)
        st.success(f"Parsed {len(entries)} entries")
    except Exception as e:
        st.error(f"Failed to parse file: {e}")
        entries, display_entries = [], []

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
            display_entries = [_build_display_entry(entry)]
            st.sidebar.success("Metadata fetched from Crossref")
        except Exception as e:
            st.sidebar.error(f"Crossref fetch failed: {e}")

# If we have entries (either from upload or DOI fetch), map them
titles = []
authors = []
if entries:
    titles = entries_to_titles(entries)
    authors = entries_to_authors(entries)

    # Scholar UI preview (safe mode, zero DB) using display_* keys
    if display_entries is None:
        display_entries = [_build_display_entry(e) for e in entries]
    display_preview_safe(display_entries)

    # ---- RCAAP Validation & Enrichment (Curation Layer) ----
    st.markdown("---")
    st.subheader("✏️ RCAAP Metadata Curation")
    st.write("Review and complete required fields before syncing:")

    curated_entries = []
    for idx, entry in enumerate(entries):
        with st.expander(f"📄 {entry.get('title', 'Untitled')[:50]}..."):
            # Check if entry is valid
            is_valid, missing = validate_entry(entry)
            
            if not is_valid:
                st.warning(f"⚠️ Missing required RCAAP metadata: {', '.join(missing)}")
            
            # Enrich with OpenAlex if DOI present
            enriched = entry.copy()
            doi = entry.get('doi') or entry.get('DOI', '')
            if doi:
                openalex = _fetch_openalex_cached(doi)
                if openalex and openalex.get('abstract'):
                    if not enriched.get('abstract'):
                        enriched['abstract'] = openalex['abstract']
                    if not enriched.get('language'):
                        enriched['language'] = openalex.get('language', 'en')
            
            # Editable fields
            col1, col2 = st.columns(2)
            with col1:
                title = st.text_input(f"Title", value=enriched.get('title', ''), key=f"title_{idx}")
                authors_str = st.text_input(f"Authors (semicolon-separated)", value=enriched.get('author', ''), key=f"authors_{idx}")
                year = st.text_input(f"Year", value=enriched.get('year', ''), key=f"year_{idx}")
            with col2:
                language = st.text_input(f"Language", value=enriched.get('language', 'en'), key=f"lang_{idx}")
                entry_type = st.selectbox(f"Type", RCAAP_TYPES, index=0 if enriched.get('type') not in RCAAP_TYPES else RCAAP_TYPES.index(enriched.get('type')), key=f"type_{idx}")
                doi_field = st.text_input(f"DOI", value=enriched.get('doi', ''), key=f"doi_{idx}")
            
            abstract = st.text_area(f"Abstract", value=enriched.get('abstract', 'No abstract in BibTeX'), key=f"abstract_{idx}", height=100)
            
            # Update entry with curated values
            enriched['title'] = title
            enriched['author'] = authors_str
            enriched['year'] = year
            enriched['language'] = language
            enriched['type'] = entry_type if entry_type != "Select Type..." else "other"
            enriched['doi'] = doi_field
            enriched['abstract'] = abstract
            
            curated_entries.append(enriched)
    
    # Validate before sync
    entries_for_sync = curated_entries if curated_entries else entries

    # Check validation status for acknowledgment UI
    sync_valid = True
    invalid_entries = []
    for e in entries_for_sync:
        is_valid, missing = validate_entry(e)
        if not is_valid:
            invalid_entries.append((e.get('title', 'Untitled'), missing))
            sync_valid = False
    
    # Acknowledgment checkbox for incomplete entries
    acknowledge_incomplete = False
    if not sync_valid:
        missing_str = "\n".join([f"• {title}: Missing {', '.join(m)}" for title, m in invalid_entries])
        st.warning(f"⚠️ **Some entries are incomplete for RCAAP standards:**\n{missing_str}")
        acknowledge_incomplete = st.checkbox(
            "I acknowledge that these entries are incomplete for RCAAP standards and I wish to sync them anyway.",
            key="acknowledge_incomplete"
        )

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
                    auths_sorted = [author_map[a_id] for a_id in sorted(auths, key=lambda x: x[0])]
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
    # Enable sync if: (1) all entries valid, OR (2) incomplete but acknowledged
    sync_enabled = sync_valid or acknowledge_incomplete
    
    if st.button("Sync to Google Sheets", key="sync", disabled=not sync_enabled):
        if not sync_enabled:
            st.error("Cannot sync: Please acknowledge incomplete entries or complete the missing metadata.")
        else:
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

                # Desired schema (with Status column for Title table)
                _ensure_sheet_and_header('Publisher', ['ID Publisher', 'Publisher Name'])
                _ensure_sheet_and_header('Venue', ['ID Venue', 'Venue Name', 'ID Publisher'])
                _ensure_sheet_and_header('Title', ['ID Title', 'Title', 'Year', 'ID Venue', 'DOI', 'URL', 'Abstract', 'Type', 'Language', 'Keywords', 'Status'])
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
                        'Status': title_row.get('status', 'Verified'),
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

                # Sync each curated entry to Google Sheets
                synced_count = 0
                for idx, entry in enumerate(curated_entries, 1):
                    st.write(f"🔄 Syncing entry {idx}/{len(curated_entries)}...")
                    try:
                        # Safe extraction
                        title_text = (entry.get('title') or '').strip() or 'Untitled'
                        authors_text = (entry.get('authors') or '').strip()
                        year_text = (entry.get('year') or '').strip() or '0000'
                        doi_text = (entry.get('doi') or '').strip()
                        abstract_text = (entry.get('abstract') or '').strip()
                        language_text = (entry.get('language') or '').strip() or 'en'
                        rcaap_type_text = (entry.get('type') or '').strip() or 'article'

                        # Get or create publisher and venue
                        try:
                            publisher_name = entry.get('publisher', 'Unknown Publisher')
                            venue_name = entry.get('journal', '') or entry.get('booktitle', '') or 'Unknown Venue'
                            
                            pub_id = get_or_create_publisher(publisher_name)
                            venue_id = get_or_create_venue(venue_name, pub_id)
                        except Exception as db_err:
                            st.warning(f"Database connection issue, using defaults: {db_err}")
                            pub_id = 'P001'
                            venue_id = 'V001'

                        # Determine Status based on validation
                        is_valid, _ = validate_entry(entry)
                        status = "Verified" if is_valid else "Draft/Incomplete"

                        # Create title
                        title_row = {
                            'title': title_text,
                            'year': year_text,
                            'id_venue': venue_id,
                            'doi': doi_text,
                            'url': (entry.get('url') or '').strip(),
                            'abstract': abstract_text,
                            'type': rcaap_type_text,
                            'language': language_text,
                            'keywords': (entry.get('keywords') or '').strip(),
                            'status': status,
                        }
                        title_id = create_or_get_title_id(title_row)

                        # Parse authors
                        if authors_text:
                            author_list = [a.strip() for a in authors_text.split(';') if a.strip()]
                            for order_idx, author_str in enumerate(author_list, 1):
                                try:
                                    # Parse author name
                                    author_full_name = author_str.strip()
                                    
                                    author_id = get_or_create_author(author_full_name)
                                    ensure_author_title_link(author_id, title_id, order_idx)
                                except Exception as author_err:
                                    st.warning(f"Could not link author '{author_str}': {author_err}")

                        synced_count += 1
                        st.success(f"✅ Entry {idx} synced!")
                    except Exception as sync_entry_err:
                        st.error(f"❌ Entry {idx} error: {str(sync_entry_err)}")

                st.info(f"Sync complete: {synced_count}/{len(curated_entries)} entries synced to Google Sheets.")

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

def render_scholar_ui(entry: dict):
    """Render a single entry in the Scholar UI layout (defensive and precise).

    UI rules:
    - Title in bold
    - Authors in a green/grey sub-header (small font)
    - Venue & Year on the next line (regular font)
    - Preview uses semicolon-separated authors
    """
    # Defensive extraction and fallback
    title = entry.get("Title") if entry.get("Title") is not None else "Unknown Title"
    doi = entry.get("DOI") if entry.get("DOI") is not None else None
    authors = entry.get("Authors") if entry.get("Authors") is not None else []
    venue = entry.get("Venue") if entry.get("Venue") is not None else "Unknown Venue"
    year = entry.get("Year") if entry.get("Year") is not None else "Unknown Year"

    # Title (bold). If DOI is present, make a DOI link to https://doi.org/<doi> when it's not a url
    if doi:
        doi_url = doi if doi.startswith("http") else f"https://doi.org/{doi}"
        st.markdown(f"**[{title}]({doi_url})**")
    else:
        st.markdown(f"**{title}**")

    # Authors: join with semicolons for preview per spec; small font and green/grey color
    try:
        author_line = "; ".join(authors) if authors else "Unknown Author"
    except Exception:
        author_line = "Unknown Author"
    st.markdown(f"<div style='font-size:small;color:#6c757d; margin-top:4px'>{author_line}</div>", unsafe_allow_html=True)

    # Venue & Year on the line below (regular font)
    st.markdown(f"<div style='margin-top:4px'>{venue} ({year})</div>", unsafe_allow_html=True)

# Example usage placeholder (intentionally left minimal; preview is handled above)
