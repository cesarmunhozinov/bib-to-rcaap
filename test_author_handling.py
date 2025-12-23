#!/usr/bin/env python3
"""Test script to verify author splitting, cleaning, and ordering."""

from bibtex_parser import parse_bib_file, entries_to_titles, entries_to_authors

def test_author_handling():
    """Test that authors are correctly split, cleaned, and ordered."""
    
    # Parse the test file
    entries = parse_bib_file("test_multiple_authors.bib")
    
    # Get authors
    authors = entries_to_authors(entries)
    
    print("=" * 80)
    print("AUTHOR PARSING TEST")
    print("=" * 80)
    
    # Group authors by paper key
    by_key = {}
    for a in authors:
        key = a['key']
        if key not in by_key:
            by_key[key] = []
        by_key[key].append(a)
    
    # Display results for each paper
    for key, auths in sorted(by_key.items()):
        print(f"\n📄 Paper: {key}")
        print(f"   Total authors: {len(auths)}")
        print(f"   Authors (in order):")
        
        # Sort by order to show correct sequence
        for a in sorted(auths, key=lambda x: x['order']):
            print(f"      {a['order']}. {a['name']}")
            print(f"         - Normalized: {a['name_normalized']}")
            print(f"         - Given: {a['given_name']}")
            print(f"         - Family: {a['family_name']}")
            if a.get('orcid'):
                print(f"         - ORCID: {a['orcid']}")
    
    print("\n" + "=" * 80)
    print("VERIFICATION CHECKS")
    print("=" * 80)
    
    # Verify no curly braces in names
    has_braces = False
    for a in authors:
        if '{' in a['name'] or '}' in a['name']:
            print(f"❌ FAIL: Found curly braces in author name: {a['name']}")
            has_braces = True
    
    if not has_braces:
        print("✅ PASS: All author names are free of curly braces")
    
    # Verify order starts at 1 and increments correctly
    order_correct = True
    for key, auths in by_key.items():
        sorted_auths = sorted(auths, key=lambda x: x['order'])
        expected_order = 1
        for a in sorted_auths:
            if a['order'] != expected_order:
                print(f"❌ FAIL: Order mismatch in {key}. Expected {expected_order}, got {a['order']}")
                order_correct = False
            expected_order += 1
    
    if order_correct:
        print("✅ PASS: All authors have correct sequential ordering")
    
    # Verify correct number of authors per paper
    expected_counts = {
        'ferreira2024': 3,  # Ferreira, Silva, Dias
        'santos2023': 4,     # Santos, Oliveira, Costa, Martins
        'single2025': 1      # Thompson
    }
    
    count_correct = True
    for key, expected in expected_counts.items():
        actual = len(by_key.get(key, []))
        if actual != expected:
            print(f"❌ FAIL: Expected {expected} authors for {key}, got {actual}")
            count_correct = False
    
    if count_correct:
        print("✅ PASS: All papers have correct author counts")
    
    # Verify names are properly split and cleaned
    test_cases = [
        ('ferreira2024', 'Ferreira, R.', 'R. Ferreira'),
        ('santos2023', 'Santos, Ana C.', 'Ana C. Santos'),
        ('single2025', 'Thompson, Mark A.', 'Mark A. Thompson'),
    ]
    
    name_correct = True
    for key, original, expected_normalized in test_cases:
        auths = by_key.get(key, [])
        found = False
        for a in auths:
            # The original might have braces, so check cleaned version
            if expected_normalized in a['name_normalized']:
                found = True
                break
        if not found:
            print(f"❌ FAIL: Could not find normalized name '{expected_normalized}' in {key}")
            name_correct = False
    
    if name_correct:
        print("✅ PASS: Author names are correctly normalized")
    
    print("\n" + "=" * 80)
    if not has_braces and order_correct and count_correct and name_correct:
        print("🎉 ALL TESTS PASSED! Author handling is working correctly.")
    else:
        print("⚠️  SOME TESTS FAILED. Please review the output above.")
    print("=" * 80 + "\n")

if __name__ == "__main__":
    test_author_handling()
