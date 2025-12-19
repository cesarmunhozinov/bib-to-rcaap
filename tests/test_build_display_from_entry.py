from app import _build_display_object_from_bib_entry


def test_build_display_object_from_bib_entry_minimal():
    e = {
        'title': 'My Paper',
        'author': 'Doe, J. and Smith, A.',
        'journal': 'Journal X',
        'year': '2020',
        'doi': '10.1000/xyz',
    }
    d = _build_display_object_from_bib_entry(e)
    assert d['Title'] == 'My Paper'
    assert d['authors_line'] == 'Doe, J. and Smith, A.'
    assert d['Venue Name'] == 'Journal X'
    assert d['Year'] == '2020'


def test_build_display_object_handles_missing_fields():
    e = {'title': 'No Authors'}
    d = _build_display_object_from_bib_entry(e)
    assert d['Title'] == 'No Authors'
    assert d['authors_line'] == 'Unknown'
    assert d['Venue Name'] == 'N/A'
    assert d['DOI'] == ''
