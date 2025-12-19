"""Relational helpers to manage RCAAP sheets in-memory for testing and as a blueprint for the Google Sheets writes.

This module provides a simple in-memory relational representation with methods to upsert publishers, venues, titles, authors and author-title links.

IDs are generated as P001, V001, T001, A001, with zero padding.
"""

from __future__ import annotations

from typing import Dict, List, Optional


class InMemoryRelationalDB:
    def __init__(self):
        # store lists of row dicts
        self.publishers: List[Dict[str, str]] = []  # {'ID Publisher': 'P001', 'Publisher Name': 'ACME'}
        self.venues: List[Dict[str, str]] = []
        self.titles: List[Dict[str, str]] = []
        self.authors: List[Dict[str, str]] = []
        self.author_titles: List[Dict[str, str]] = []

        # counters
        self._counters = {'P': 0, 'V': 0, 'T': 0, 'A': 0}

    def _next_id(self, prefix: str) -> str:
        self._counters[prefix] += 1
        return f"{prefix}{self._counters[prefix]:03d}"

    # Publisher
    def get_publisher_by_name(self, name: str) -> Optional[Dict[str, str]]:
        name = (name or "").strip()
        for p in self.publishers:
            if p.get('Publisher Name', '').strip() == name:
                return p
        return None

    def get_or_create_publisher(self, name: str) -> str:
        name = (name or "").strip()
        p = self.get_publisher_by_name(name)
        if p:
            return p['ID Publisher']
        pid = self._next_id('P')
        row = {'ID Publisher': pid, 'Publisher Name': name}
        self.publishers.append(row)
        return pid

    # Venue
    def get_venue_by_name(self, name: str) -> Optional[Dict[str, str]]:
        name = (name or "").strip()
        for v in self.venues:
            if v.get('Venue Name', '').strip() == name:
                return v
        return None

    def get_or_create_venue(self, name: str, id_publisher: str) -> str:
        name = (name or "").strip()
        v = self.get_venue_by_name(name)
        if v:
            # ensure publisher link exists
            if v.get('ID Publisher') != id_publisher:
                v['ID Publisher'] = id_publisher
            return v['ID Venue']
        vid = self._next_id('V')
        row = {'ID Venue': vid, 'Venue Name': name, 'ID Publisher': id_publisher}
        self.venues.append(row)
        return vid

    # Title
    def create_title(self, title: str, year: str = '', id_venue: str = '', doi: str = '', url: str = '', abstract: str = '', type_: str = '', language: str = '', keywords: str = '') -> str:
        tid = self._next_id('T')
        row = {
            'ID Title': tid,
            'Title': title or "",
            'Year': year or "",
            'ID Venue': id_venue or "",
            'DOI': doi or "",
            'URL': url or "",
            'Abstract': abstract or "",
            'Type': type_ or "",
            'Language': language or "",
            'Keywords': keywords or "",
        }
        self.titles.append(row)
        return tid

    # Authors
    def get_author_by_name(self, name: str) -> Optional[Dict[str, str]]:
        name = (name or "").strip()
        for a in self.authors:
            if a.get('Author Name', '').strip() == name:
                return a
        return None

    def get_or_create_author(self, name: str, orcid: str = '', affiliation: str = '') -> str:
        name = (name or "").strip()
        a = self.get_author_by_name(name)
        if a:
            # update ORCID or affiliation if missing
            if orcid and not a.get('ORCID'):
                a['ORCID'] = orcid
            if affiliation and not a.get('Affiliation'):
                a['Affiliation'] = affiliation
            return a['ID Author']
        aid = self._next_id('A')
        row = {'ID Author': aid, 'Author Name': name, 'ORCID': orcid or "", 'Affiliation': affiliation or ""}
        self.authors.append(row)
        return aid

    # Author-Title link
    def add_author_title(self, id_author: str, id_title: str, order: int) -> None:
        # ensure no duplicate link
        for r in self.author_titles:
            if r.get('ID Author') == id_author and r.get('ID Title') == id_title:
                # update order
                r['Order'] = str(order)
                return
        self.author_titles.append({'ID Author': id_author, 'ID Title': id_title, 'Order': str(order)})

    # Export to RCAAP CSV rows
    def export_rcaap_rows(self) -> List[Dict[str, str]]:
        """Return list of rows with keys: dc.title, dc.contributor.author, dc.date.issued, dc.publisher, dc.identifier.doi"""
        out = []
        # Build lookup maps
        publisher_map = {p['ID Publisher']: p['Publisher Name'] for p in self.publishers}
        venue_map = {v['ID Venue']: v for v in self.venues}
        author_map = {a['ID Author']: a['Author Name'] for a in self.authors}

        # Build author-title map per title sorted by order
        from collections import defaultdict

        title_authors = defaultdict(list)
        for at in self.author_titles:
            title_authors[at['ID Title']].append((int(at['Order']), at['ID Author']))

        for t in self.titles:
            title_id = t['ID Title']
            title_str = t.get('Title', '')
            year = t.get('Year', '')
            doi = t.get('DOI', '')
            # Find publisher via venue
            pub_name = ''
            id_venue = t.get('ID Venue')
            if id_venue:
                v = venue_map.get(id_venue)
                if v:
                    id_pub = v.get('ID Publisher')
                    pub_name = publisher_map.get(id_pub, '')
            # authors
            auths = title_authors.get(title_id, [])
            auths_sorted = [author_map[a_id] for _, a_id in sorted(auths, key=lambda x: x[0])]
            authors_joined = '; '.join(auths_sorted)

            out.append({
                'dc.title': title_str,
                'dc.contributor.author': authors_joined,
                'dc.date.issued': year,
                'dc.publisher': pub_name,
                'dc.identifier.doi': doi,
            })
        return out


if __name__ == '__main__':
    db = InMemoryRelationalDB()
    pid = db.get_or_create_publisher('ACME')
    vid = db.get_or_create_venue('ConfX', pid)
    tid = db.create_title('My paper', '2020', vid, '10.1000/xyz')
    a1 = db.get_or_create_author('Alice')
    a2 = db.get_or_create_author('Bob')
    db.add_author_title(a1, tid, 1)
    db.add_author_title(a2, tid, 2)
    print(db.export_rcaap_rows())