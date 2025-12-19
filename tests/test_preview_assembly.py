from app import _assemble_preview_row


class FakeWorksheet:
    def __init__(self, values=None):
        self._values = values or []

    def get_all_records(self):
        return self._values


class FakeDB:
    def __init__(self, ws_map):
        self._ws = ws_map

    def _get_ws(self, name):
        return self._ws.get(name, FakeWorksheet([]))


def test_assemble_preview_handles_missing_venue_and_non_numeric_order():
    # Title referencing a venue that doesn't exist
    title_row = {
        'ID Title': 'T001',
        'ID Venue': 'V-MISSING',
        'Title': 'A Sample Paper',
        'Year': '2021',
        'DOI': '10.1000/xyz'
    }

    # Author-Title has one row with non-numeric order and one with numeric
    at_ws = FakeWorksheet(values=[
        {'ID Title': 'T001', 'ID Author': 'A1', 'Order': 'first'},
        {'ID Title': 'T001', 'ID Author': 'A2', 'Order': '2'},
    ])

    # Authors sheet contains two authors
    authors_ws = FakeWorksheet(values=[
        {'ID Author': 'A1', 'Author Name': 'Alice Example'},
        {'ID Author': 'A2', 'Author Name': 'Bob Tester'},
    ])

    db = FakeDB({'Author-Title': at_ws, 'Authors': authors_ws, 'Venue': FakeWorksheet([])})

    merged = _assemble_preview_row(title_row, db=db, parsed_authors=None)

    assert merged['Venue Name'] == 'Unknown Venue'
    # Non-numeric order should be treated as 0 and come before '2'
    # so authors_line should contain 'Example, A.' before 'Tester, B.' (family, initial format)
    assert 'Example, A.' in merged['authors_line'] and 'Tester, B.' in merged['authors_line']
    assert merged['authors_line'].split(';')[0].strip().startswith('Example, A.')
