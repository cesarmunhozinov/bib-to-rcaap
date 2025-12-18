import pytest
import sys
from pathlib import Path

# ensure project root is importable when running tests
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bibtex_parser import (
    _normalize_author_name,
    _extract_orcid,
    _clean_text,
    entries_to_titles,
    entries_to_authors,
    entries_to_events,
)


def test_normalize_author_name():
    assert _normalize_author_name('Smith, Alice') == 'Alice Smith'
    assert _normalize_author_name('Doe, John P.') == 'John P. Doe'
    assert _normalize_author_name('Alice Smith') == 'Alice Smith'


def test_extract_orcid():
    assert _extract_orcid('Alice Smith 0000-0002-1825-0097') == '0000-0002-1825-0097'
    assert _extract_orcid('https://orcid.org/0000-0002-1825-0097') == '0000-0002-1825-0097'
    assert _extract_orcid('No orcid here') == ''


def test_clean_text():
    assert _clean_text('{An} example') == 'An example'


def test_entries_mapping():
    entries = [
        {
            'ID': 'smith2025',
            'author': 'Smith, Alice 0000-0002-1825-0097 and Doe, John',
            'title': '{An} example study',
            'year': '2025',
            'journal': 'Journal of Examples',
            'doi': '10.1234/example.doi',
        }
    ]

    titles = entries_to_titles(entries)
    authors = entries_to_authors(entries)
    events = entries_to_events(entries)

    assert len(titles) == 1
    assert titles[0]['key'] == 'smith2025'
    assert len(authors) == 2
    # names contains original 'name' field (as provided) and we also have normalized
    name_norms = {a['name_normalized'] for a in authors}
    assert 'Alice Smith' in name_norms
    assert 'John Doe' in name_norms

    # confirm ORCID captured
    orcids = {a['orcid'] for a in authors}
    assert '0000-0002-1825-0097' in orcids

    # check given/family split
    for a in authors:
        if a['name_normalized'] == 'Alice Smith':
            assert a['given_name'] == 'Alice'
            assert a['family_name'] == 'Smith'

    assert len(events) == 1
    assert events[0]['event'] == 'Journal of Examples'
