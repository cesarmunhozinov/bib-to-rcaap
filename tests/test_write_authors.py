from database import RCAAPDatabase


class FakeWorksheet:
    def __init__(self, values=None):
        # values is a list of rows (each row is a list)
        self._values = values or []
        self.inserted = []
        self.deleted = 0
        self.appended = []

    def get_all_values(self):
        return self._values

    def insert_row(self, row, index=1):
        self._values.insert(0, row)
        self.inserted.append(row)

    def delete_rows(self, idx):
        if self._values:
            self._values.pop(0)
            self.deleted += 1

    def append_rows(self, rows, value_input_option=None):
        for r in rows:
            self.appended.append(r)
            self._values.append(r)


class FakeDB(RCAAPDatabase):
    def __init__(self, ws):
        # do not call super connect
        self._worksheets = {"Authors": ws}

    def _get_ws(self, title: str):
        return self._worksheets[title]


def test_write_authors_replaces_header_and_only_writes_four_columns():
    # Existing sheet has legacy header with extra columns
    ws = FakeWorksheet(values=[['ID', 'Name', 'key', 'name_normalized']])
    db = FakeDB(ws)

    # Incoming rows contain legacy keys and extra fields
    rows = [
        {'name': 'Alice Example', 'name_normalized': 'Alice Example', 'key': 'A1', 'orcid': '0000-0001'},
        {'Author Name': 'Bob Test', 'Affiliation': 'Inst', 'extra': 'zzz'},
    ]

    db.write_authors(rows)

    # Header must have been replaced exactly
    assert ws.get_all_values()[0] == ['ID Author', 'Author Name', 'ORCID', 'Affiliation']

    # Appended rows should have only four columns and map names correctly
    appended = ws.appended
    assert appended[0] == ['', 'Alice Example', '', '']
    assert appended[1] == ['', 'Bob Test', '', 'Inst']
