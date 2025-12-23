"""bibtex_parser.py
Helpers to parse a .bib file and map BibTeX entries to rows suitable for the RCAAP sheet.
"""
from __future__ import annotations

from typing import List, Dict, Any
import bibtexparser
from bibtexparser.bparser import BibTexParser
from bibtexparser.customization import homogenize_latex_encoding


def parse_bib_file(path: str) -> List[Dict[str, Any]]:
    """Parse a BibTeX file and return a list of raw entry dicts.

    Each dict contains standard BibTeX fields (lowercased keys) plus the 'ID' (key).
    """
    with open(path, "r", encoding="utf-8") as fh:
        parser = BibTexParser()
        parser.customization = homogenize_latex_encoding
        bibdb = bibtexparser.load(fh, parser=parser)
    return bibdb.entries


def entries_to_titles(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Map BibTeX entries to a list of title dicts suitable for the `Titles` tab with extra fields.

    Example output keys: key, title, year, journal, doi, url, abstract, pages, volume, number, publisher, keywords, language
    """
    out = []
    for e in entries:
        title = _clean_text(e.get("title", ""))
        pages = e.get("pages", "")
        if isinstance(pages, str):
            pages = pages.replace("--", "-")
        d = {
            "key": e.get("ID") or e.get("id") or e.get("key"),
            "title": title,
            "year": e.get("year", ""),
            "journal": _clean_text(e.get("journal", e.get("booktitle", ""))),
            "doi": e.get("doi", ""),
            "url": e.get("url", ""),
            "abstract": _clean_text(e.get("abstract", "")),
            "type": e.get("ENTRYTYPE", e.get("type", "")),
            "pages": pages,
            "volume": e.get("volume", ""),
            "number": e.get("number", ""),
            "publisher": e.get("publisher", ""),
            "keywords": e.get("keywords", e.get("keywords", "")),
            "language": e.get("language", ""),
        }
        out.append(d)
    return out


def _dedupe_rows(rows: List[Dict[str, Any]], key_fields: List[str]) -> List[Dict[str, Any]]:
    """Deduplicate rows preserving first occurrence using tuple of key_fields."""
    seen = set()
    out = []
    for r in rows:
        key = tuple(r.get(f, None) for f in key_fields)
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def entries_to_authors(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return authors as rows. Each row contains name, affiliation (if available), key, order, and orcid if present.

    We split the BibTeX `author` field by " and ".
    Example output keys: name, affiliation, key, order, orcid
    """
    out = []
    for e in entries:
        key = e.get("ID") or e.get("id") or e.get("key")
        authors_field = e.get("author", "")
        if not authors_field:
            continue
        # split by ' and ' which is BibTeX author separator
        authors = [a.strip() for a in authors_field.split(" and ") if a.strip()]
        for idx, a in enumerate(authors, start=1):
            name_norm = _normalize_author_name(a)
            given, family = _split_name(name_norm)
            orcid = _extract_orcid(a)
            out.append({
                "name": a.strip(),  # original representation
                "name_normalized": name_norm,
                "given_name": given,
                "family_name": family,
                "affiliation": e.get("affiliation", e.get("institution", "")),
                "key": key,
                "order": idx,
                "orcid": orcid,
            })

    # Deduplicate authors by normalized name + key + orcid
    out = _dedupe_rows(out, ["name_normalized", "key", "orcid"])
    return out


def _clean_text(s: str) -> str:
    """Simple cleaning: remove braces, normalize whitespace, trim whitespace."""
    if not s:
        return ""
    s = s.strip()
    # Remove all braces that often wrap titles in BibTeX
    s = s.replace("{", "").replace("}", "")
    # collapse multiple spaces
    import re

    s = re.sub(r"\s+", " ", s).strip()
    return s


def _normalize_author_name(name: str) -> str:
    """Normalize author name. Handle "Last, First" -> "First Last" and trim whitespace.

    Returns a single string in the form "Given Family".
    """
    if not name:
        return ""
    name = name.strip()
    # remove ORCID tokens from display name
    orcid = _extract_orcid(name)
    if orcid:
        # strip the orcid pattern/uri from the name
        name = name.replace(orcid, "").replace("https://orcid.org/", "").replace("orcid.org/", "")
        name = name.replace("()", "")
    # If comma present assume "Last, First" format
    if "," in name:
        parts = [p.strip() for p in name.split(",") if p.strip()]
        if len(parts) >= 2:
            given = " ".join(parts[1:])
            return f"{given} {parts[0]}".strip()
    # else assume already "First Last"
    return name


def _split_name(name: str) -> tuple[str, str]:
    """Split normalized name into (given, family)."""
    if not name:
        return "", ""
    parts = name.strip().split()
    if len(parts) == 1:
        return parts[0], ""
    # family name is the last token, given is the rest
    return " ".join(parts[:-1]), parts[-1]


def _extract_orcid(s: str) -> str:
    """Extract ORCID if it appears in the string (pattern 0000-0000-0000-0000)."""
    import re

    if not s:
        return ""
    m = re.search(r"(\d{4}-\d{4}-\d{4}-\d{3}[\dXx])", s)
    if m:
        return m.group(1)
    # or full URI
    m = re.search(r"orcid\.org/(\d{4}-\d{4}-\d{4}-\d{3}[\dXx])", s)
    if m:
        return m.group(1)
    return ""


def entries_to_events(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Map conference-related entries to event rows.

    We look for booktitle (conference), event fields or journal and produce a mapping with additional fields.
    Example output keys: key, event, venue, date, year
    """
    out = []
    for e in entries:
        key = e.get("ID") or e.get("id") or e.get("key")
        event = _clean_text(e.get("booktitle", "") or e.get("event", ""))
        if not event:
            # treat journal papers as events with the journal as event
            event = _clean_text(e.get("journal", ""))
        if not event:
            continue
        # construct a date if month+year are present
        month = e.get("month", "")
        year = e.get("year", "")
        date = e.get("date", "")
        if not date and month and year:
            date = f"{month} {year}"

        d = {
            "key": key,
            "event": event,
            "venue": _clean_text(e.get("venue", "")),
            "date": _clean_text(date),
            "year": year,
        }
        out.append(d)
    return out


def map_bibtex_to_paper_object(entry: Dict[str, Any]) -> Dict[str, Any]:
    """Map a BibTeX entry to a standardized Paper Object for the database."""
    paper = {
        "Title": _clean_text(entry.get("title", "Unknown Title")),
        "Year": entry.get("year", "Unknown Year"),
        "Venue": _clean_text(entry.get("journal", entry.get("booktitle", "Unknown Venue"))),
        "DOI": entry.get("doi", None),
        "URL": entry.get("url", None),
        "Abstract": _clean_text(entry.get("abstract", "")),
        "Type": entry.get("ENTRYTYPE", "Unknown Type"),
        "Language": entry.get("language", "Unknown Language"),
        "Keywords": entry.get("keywords", ""),
        "Authors": [],
    }

    authors_field = entry.get("author", "")
    if authors_field:
        authors = [a.strip() for a in authors_field.split(" and ") if a.strip()]
        paper["Authors"] = authors

    return paper


if __name__ == "__main__":
    print("bibtex_parser: provide parse_bib_file(), entries_to_titles(), entries_to_authors(), entries_to_events()")
