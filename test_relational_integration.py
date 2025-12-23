#!/usr/bin/env python3
"""Test to verify relational sync with multiple authors."""

from bibtex_parser import parse_bib_file, entries_to_titles, entries_to_authors
from rcaap_relational import InMemoryRelationalDB
from relational_sync import sync_entries

def test_relational_sync():
    """Test that sync creates individual author records with correct linkage."""
    
    print("=" * 80)
    print("RELATIONAL SYNC TEST - Multiple Authors")
    print("=" * 80 + "\n")
    
    # Parse test file
    entries = parse_bib_file("test_multiple_authors.bib")
    titles = entries_to_titles(entries)
    authors = entries_to_authors(entries)
    
    # Create in-memory database
    db = InMemoryRelationalDB()
    
    # Sync to database
    sync_entries(db, titles, authors)
    
    # Verify Authors table
    print("📋 AUTHORS TABLE")
    print("-" * 80)
    authors_table = db.authors
    print(f"Total unique authors: {len(authors_table)}")
    for author_data in sorted(authors_table, key=lambda x: x['ID Author']):
        print(f"  {author_data['ID Author']}: {author_data['Author Name']}")
        if author_data.get('ORCID'):
            print(f"       ORCID: {author_data['ORCID']}")
    
    # Verify Title table
    print(f"\n📚 TITLE TABLE")
    print("-" * 80)
    title_table = db.titles
    print(f"Total titles: {len(title_table)}")
    for title_data in sorted(title_table, key=lambda x: x['ID Title']):
        print(f"  {title_data['ID Title']}: {title_data['Title'][:60]}...")
    
    # Verify Author-Title junction table
    print(f"\n🔗 AUTHOR-TITLE JUNCTION TABLE")
    print("-" * 80)
    junction_table = db.author_titles
    print(f"Total author-title links: {len(junction_table)}")
    
    # Group by title to show author order
    by_title = {}
    for link_data in junction_table:
        title_id = link_data['ID Title']
        if title_id not in by_title:
            by_title[title_id] = []
        by_title[title_id].append(link_data)
    
    # Create lookup map for easier access
    author_map = {a['ID Author']: a['Author Name'] for a in authors_table}
    title_map = {t['ID Title']: t for t in title_table}
    
    for title_id, links in sorted(by_title.items()):
        title_data = title_map[title_id]
        print(f"\n  Title: {title_id} - {title_data['Title'][:50]}...")
        print(f"  Authors in order:")
        for link in sorted(links, key=lambda x: int(x['Order'])):
            author_id = link['ID Author']
            author_name = author_map[author_id]
            print(f"    {link['Order']}. {author_id} - {author_name}")
    
    # Verification checks
    print("\n" + "=" * 80)
    print("VERIFICATION CHECKS")
    print("=" * 80)
    
    # Check: Each author should have unique ID
    author_ids = [a['ID Author'] for a in authors_table]
    unique_ids = len(set(author_ids))
    if unique_ids == len(author_ids):
        print("✅ PASS: All authors have unique IDs")
    else:
        print(f"❌ FAIL: Duplicate author IDs found")
    
    # Check: Author count matches expected
    expected_author_count = 8  # 3 + 4 + 1 from three papers
    actual_author_count = len(authors_table)
    if actual_author_count == expected_author_count:
        print(f"✅ PASS: Correct number of unique authors ({actual_author_count})")
    else:
        print(f"❌ FAIL: Expected {expected_author_count} authors, got {actual_author_count}")
    
    # Check: Title count matches expected
    expected_title_count = 3
    actual_title_count = len(title_table)
    if actual_title_count == expected_title_count:
        print(f"✅ PASS: Correct number of titles ({actual_title_count})")
    else:
        print(f"❌ FAIL: Expected {expected_title_count} titles, got {actual_title_count}")
    
    # Check: Junction table has correct number of links
    expected_links = 8  # Total authors across all papers
    actual_links = len(junction_table)
    if actual_links == expected_links:
        print(f"✅ PASS: Correct number of author-title links ({actual_links})")
    else:
        print(f"❌ FAIL: Expected {expected_links} links, got {actual_links}")
    
    # Check: Each title has correct number of authors
    counts_correct = True
    for title_id, links in by_title.items():
        title_data = title_map[title_id]
        # Determine expected count based on title content
        if 'Decision' in title_data['Title']:
            expected_count = 3
        elif 'Machine' in title_data['Title']:
            expected_count = 4
        elif 'Quantum' in title_data['Title']:
            expected_count = 1
        else:
            continue
        
        actual_count = len(links)
        if actual_count != expected_count:
            print(f"❌ FAIL: Title '{title_data['Title'][:30]}...' has {actual_count} authors, expected {expected_count}")
            counts_correct = False
    
    if counts_correct:
        print("✅ PASS: All titles have correct number of authors")
    
    # Check: Author order is correct (starts at 1, sequential)
    order_correct = True
    for title_id, links in by_title.items():
        orders = sorted([int(link['Order']) for link in links])
        expected_orders = list(range(1, len(links) + 1))
        if orders != expected_orders:
            print(f"❌ FAIL: Incorrect order sequence for {title_id}: {orders}")
            order_correct = False
    
    if order_correct:
        print("✅ PASS: All author orders are correct (start at 1, sequential)")
    
    # Check: All author names are clean (no braces)
    names_clean = True
    for author_data in authors_table:
        name = author_data['Author Name']
        if '{' in name or '}' in name:
            print(f"❌ FAIL: Author name contains braces: {name}")
            names_clean = False
    
    if names_clean:
        print("✅ PASS: All author names are clean (no curly braces)")
    
    # Check: Same title ID used for all authors of a paper
    linkage_correct = True
    for title_id, links in by_title.items():
        title_ids_in_links = set(link['ID Title'] for link in links)
        if len(title_ids_in_links) != 1:
            print(f"❌ FAIL: Multiple title IDs found for same paper")
            linkage_correct = False
    
    if linkage_correct:
        print("✅ PASS: ID linkage is correct (same title ID for all authors)")
    
    print("\n" + "=" * 80)
    all_passed = (unique_ids == len(author_ids) and 
                  actual_author_count == expected_author_count and
                  actual_title_count == expected_title_count and
                  actual_links == expected_links and
                  counts_correct and order_correct and names_clean and linkage_correct)
    
    if all_passed:
        print("🎉 ALL TESTS PASSED! Relational sync is working correctly.")
    else:
        print("⚠️  SOME TESTS FAILED. Please review the output above.")
    print("=" * 80 + "\n")
    
    return all_passed

if __name__ == "__main__":
    test_relational_sync()
