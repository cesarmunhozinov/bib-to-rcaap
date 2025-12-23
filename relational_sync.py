"""Functions to sync parsed entries to either an RCAAPDatabase (Google Sheets) or an InMemoryRelationalDB.

sync_entries(db, titles, authors, source=None)
- db may be an instance of InMemoryRelationalDB or RCAAPDatabase (duck-typed)
- titles: list of title dicts as returned by `entries_to_titles`
- authors: list of author dicts as returned by `entries_to_authors`
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


def sync_entries(db: Any, titles: List[Dict[str, Any]], authors: List[Dict[str, Any]], source: Optional[str] = None) -> None:
    """Synchronise parsed titles/authors to the relational schema.

    Works with InMemoryRelationalDB (preferred for tests) or RCAAPDatabase.
    """
    # Detect InMemory vs RCAAPDatabase by presence of convenience methods
    inmemory = hasattr(db, "get_or_create_publisher") and hasattr(db, "create_title")

    if inmemory:
        # use simple API
        for t in titles:
            pub_name = t.get("publisher", "")
            id_pub = db.get_or_create_publisher(pub_name) if pub_name else ""
            venue_name = t.get("journal", "")
            id_venue = db.get_or_create_venue(venue_name, id_pub) if venue_name else ""
            id_title = db.create_title(
                title=t.get("title", ""),
                year=t.get("year", ""),
                id_venue=id_venue,
                doi=t.get("doi", ""),
                url=t.get("url", ""),
                abstract=t.get("abstract", ""),
                type_=t.get("type", ""),
                language=t.get("language", ""),
                keywords=t.get("keywords", ""),
            )
            # authors associated with this title
            auths_for = [a for a in authors if a.get("key") == t.get("key")]

            def _parse_order_local(val) -> int:
                try:
                    return int(val)
                except Exception:
                    try:
                        return int(float(val))
                    except Exception:
                        return 0

            for a in sorted(auths_for, key=lambda x: _parse_order_local(x.get("order"))):
                id_author = db.get_or_create_author(a.get("name"), a.get("orcid", ""), a.get("affiliation", ""))
                db.add_author_title(id_author, id_title, _parse_order_local(a.get("order")))
        # Return for in-memory DB (no external Logs sheet writes)
        return

    # Otherwise assume RCAAPDatabase and operate directly on worksheets
    # Helper functions using db._get_ws and db._append_dicts
    def _ensure_sheet_and_header(title: str, headers: List[str]):
        ws = db._get_ws(title)
        # If header differs from desired, replace it to enforce exact schema (avoid legacy extra columns)
        existing = ws.get_all_values()
        if not existing or not any(existing):
            ws.insert_row(headers, index=1)
        else:
            current_header = existing[0]
            if current_header != headers:
                # Replace header row exactly
                try:
                    ws.delete_rows(1)
                except Exception:
                    pass
                ws.insert_row(headers, index=1)


    def _next_id(existing_ids: List[str], prefix: str) -> str:
        nums = [int(s.lstrip(prefix)) for s in existing_ids if s and s.startswith(prefix) and s.lstrip(prefix).isdigit()]
        maxn = max(nums) if nums else 0
        return f"{prefix}{(maxn+1):03d}"

    def _clean(val: Any) -> str:
        return "" if val is None else val

    def get_or_create_publisher(name: str) -> str:
        name = (name or "").strip()
        ws = db._get_ws('Publisher')
        rows = ws.get_all_records()
        for r in rows:
            if r.get('Publisher Name', '').strip() == name:
                return r.get('ID Publisher')
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
                if orcid and not r.get('ORCID'):
                    r['ORCID'] = orcid
                if affiliation and not r.get('Affiliation'):
                    r['Affiliation'] = affiliation
                return r.get('ID Author')
        existing_ids = [r.get('ID Author', '') for r in rows]
        nid = _next_id(existing_ids, 'A')
        db._append_dicts('Authors', [{'ID Author': nid, 'Author Name': name, 'ORCID': orcid or '', 'Affiliation': affiliation or ''}])
        return nid

    def create_or_get_title_id(title_row: Dict[str, Any]) -> str:
        ws = db._get_ws('Title')
        rows = ws.get_all_records()
        doi = (title_row.get('doi') or '').strip()
        for r in rows:
            if doi and r.get('DOI', '').strip().lower() == doi.lower():
                return r.get('ID Title')
        existing_ids = [r.get('ID Title', '') for r in rows]
        nid = _next_id(existing_ids, 'T')
        db._append_dicts('Title', [{
            'ID Title': nid,
            'Title': _clean(title_row.get('title', '')),
            'Year': _clean(title_row.get('year', '')),
            'ID Venue': _clean(title_row.get('id_venue', '')),
            'DOI': _clean(title_row.get('doi', '')),
            'URL': _clean(title_row.get('url', '')),
            'Abstract': _clean(title_row.get('abstract', '')),
            'Type': _clean(title_row.get('type', '')),
            'Language': _clean(title_row.get('language', '')),
            'Keywords': _clean(title_row.get('keywords', '')),
        }])
        return nid

    def ensure_author_title_link(id_author: str, id_title: str, order: int) -> None:
        ws = db._get_ws('Author-Title')
        rows = ws.get_all_records()
        for r in rows:
            if r.get('ID Author') == id_author and r.get('ID Title') == id_title:
                try:
                    current_order = int(r.get('Order') or 0)
                except Exception:
                    try:
                        current_order = int(float(r.get('Order')))
                    except Exception:
                        current_order = 0
                if current_order != order:
                    r['Order'] = str(order)
                return
        db._append_dicts('Author-Title', [{'ID Author': id_author, 'ID Title': id_title, 'Order': str(order)}])

    # Ensure headers exist
    _ensure_sheet_and_header('Publisher', ['ID Publisher', 'Publisher Name'])
    _ensure_sheet_and_header('Venue', ['ID Venue', 'Venue Name', 'ID Publisher'])
    _ensure_sheet_and_header('Title', ['ID Title', 'Title', 'Year', 'ID Venue', 'DOI', 'URL', 'Abstract', 'Type', 'Language', 'Keywords'])
    _ensure_sheet_and_header('Authors', ['ID Author', 'Author Name', 'ORCID', 'Affiliation'])
    _ensure_sheet_and_header('Author-Title', ['ID Author', 'ID Title', 'Order'])

    for t in titles:
        pub_name = t.get('publisher', '')
        id_pub = get_or_create_publisher(pub_name) if pub_name else ''
        venue_name = t.get('journal', '')
        id_venue = get_or_create_venue(venue_name, id_pub) if venue_name else ''
        trow = t.copy()
        trow['id_venue'] = id_venue
        id_title = create_or_get_title_id(trow)

        auths_for = [a for a in authors if a.get('key') == t.get('key')]

        def _parse_order_sheet(val) -> int:
            try:
                return int(val)
            except Exception:
                try:
                    return int(float(val))
                except Exception:
                    return 0

        for a in sorted(auths_for, key=lambda x: _parse_order_sheet(a.get('order'))):
            id_author = get_or_create_author(a.get('name'), a.get('orcid', ''), a.get('affiliation', ''))
            ensure_author_title_link(id_author, id_title, _parse_order_sheet(a.get('order')))

    # Log locally only; do not write to a Logs sheet to keep to the 5-table relational schema
    import logging

    logger = logging.getLogger("rcaap-relational-sync")
    logger.info("Sync Complete.")
