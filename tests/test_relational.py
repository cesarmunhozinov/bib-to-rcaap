import pytest

from rcaap_relational import InMemoryRelationalDB


def test_publisher_venue_title_author_linking():
    db = InMemoryRelationalDB()

    # Create publisher and venue
    pid = db.get_or_create_publisher('ACME Publishing')
    assert pid == 'P001'
    pid2 = db.get_or_create_publisher('ACME Publishing')
    assert pid2 == pid  # idempotent

    vid = db.get_or_create_venue('ConfX 2024', pid)
    assert vid == 'V001'

    # Create title linked to venue
    tid = db.create_title('A study on testing', '2024', id_venue=vid, doi='10.1000/abc', url='https://example.org', abstract='An abstract')
    assert tid == 'T001'

    # Create authors and links in order
    a1 = db.get_or_create_author('Smith, Alice', orcid='0000-0001-2345-6789', affiliation='Uni X')
    a2 = db.get_or_create_author('Doe, Bob', affiliation='Uni Y')
    assert a1 == 'A001'
    assert a2 == 'A002'

    db.add_author_title(a1, tid, 1)
    db.add_author_title(a2, tid, 2)

    # Export rows and assert DC mapping
    rows = db.export_rcaap_rows()
    assert len(rows) == 1
    row = rows[0]
    assert row['dc.title'] == 'A study on testing'
    assert row['dc.date.issued'] == '2024'
    assert row['dc.identifier.doi'] == '10.1000/abc'
    # Authors in order
    assert row['dc.contributor.author'] == 'Smith, Alice; Doe, Bob'
    # Publisher via venue linkage
    assert row['dc.publisher'] == 'ACME Publishing'


def test_authors_sheet_columns_and_junction():
    db = InMemoryRelationalDB()
    # Add authors via sync helper simulation
    a1 = db.get_or_create_author('Alice', orcid='0000-0001-2345-6789', affiliation='Uni')
    a2 = db.get_or_create_author('Bob', affiliation='Inst')
    # Authors sheet should only have the exact 4 columns
    for a in db.authors:
        assert set(a.keys()) == {'ID Author', 'Author Name', 'ORCID', 'Affiliation'}

    # Create a title and link authors
    vid = db.get_or_create_venue('V', db.get_or_create_publisher('P'))
    tid = db.create_title('T1', '2025', id_venue=vid)
    db.add_author_title(a1, tid, 1)
    db.add_author_title(a2, tid, 2)
    # Junction table rows should have ID Author, ID Title, Order
    for at in db.author_titles:
        assert set(at.keys()) == {'ID Author', 'ID Title', 'Order'}


def test_author_deduplication_and_order_update():
    db = InMemoryRelationalDB()
    pid = db.get_or_create_publisher('P')
    vid = db.get_or_create_venue('V', pid)
    tid = db.create_title('Title1', '2020', vid)

    a1 = db.get_or_create_author('Alice')
    a1b = db.get_or_create_author('Alice')
    assert a1 == a1b

    db.add_author_title(a1, tid, 2)
    # Update order to 1
    db.add_author_title(a1, tid, 1)
    # Ensure author_titles has one entry with Order=1
    matches = [r for r in db.author_titles if r['ID Author'] == a1 and r['ID Title'] == tid]
    assert len(matches) == 1
    assert matches[0]['Order'] == '1'
