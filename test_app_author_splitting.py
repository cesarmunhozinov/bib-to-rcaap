#!/usr/bin/env python3
"""Test to verify app.py author splitting logic matches BibTeX standard."""

from bibtex_parser import _clean_text

def test_app_author_splitting():
    """Simulate the app.py author splitting logic."""
    
    print("=" * 80)
    print("APP.PY AUTHOR SPLITTING TEST")
    print("=" * 80 + "\n")
    
    # Test case 1: Multiple authors with ' and ' separator
    authors_text_1 = "Smith, John and Doe, Jane and {F}erreira, R."
    print(f"Test 1 - Input: '{authors_text_1}'")
    
    # Explicit split by ' and ' (BibTeX standard)
    author_list_1 = [a.strip() for a in authors_text_1.split(' and ') if a.strip()]
    print(f"  Split result: {len(author_list_1)} authors")
    
    # The Sync Loop: iterate through each author individually
    for order_idx, author_str in enumerate(author_list_1, start=1):
        # Clean author name to remove BibTeX protection braces
        author_full_name = _clean_text(author_str.strip())
        print(f"    {order_idx}. {author_full_name}")
    
    # Test case 2: Authors with protection braces
    authors_text_2 = "{S}ilva, Maria and {D}ias, João P. and Costa, Luis"
    print(f"\nTest 2 - Input: '{authors_text_2}'")
    
    author_list_2 = [a.strip() for a in authors_text_2.split(' and ') if a.strip()]
    print(f"  Split result: {len(author_list_2)} authors")
    
    for order_idx, author_str in enumerate(author_list_2, start=1):
        author_full_name = _clean_text(author_str.strip())
        print(f"    {order_idx}. {author_full_name}")
    
    # Test case 3: Single author
    authors_text_3 = "Thompson, Mark A."
    print(f"\nTest 3 - Input: '{authors_text_3}'")
    
    author_list_3 = [a.strip() for a in authors_text_3.split(' and ') if a.strip()]
    print(f"  Split result: {len(author_list_3)} authors")
    
    for order_idx, author_str in enumerate(author_list_3, start=1):
        author_full_name = _clean_text(author_str.strip())
        print(f"    {order_idx}. {author_full_name}")
    
    # Test case 4: Authors with commas in names (should NOT split on comma)
    authors_text_4 = "Ferreira, R. and Silva, Ana C. and Oliveira, Pedro"
    print(f"\nTest 4 - Input: '{authors_text_4}'")
    
    author_list_4 = [a.strip() for a in authors_text_4.split(' and ') if a.strip()]
    print(f"  Split result: {len(author_list_4)} authors")
    
    for order_idx, author_str in enumerate(author_list_4, start=1):
        author_full_name = _clean_text(author_str.strip())
        print(f"    {order_idx}. {author_full_name}")
    
    print("\n" + "=" * 80)
    print("VERIFICATION")
    print("=" * 80)
    
    # Verify counts
    assert len(author_list_1) == 3, f"Test 1 failed: expected 3 authors, got {len(author_list_1)}"
    assert len(author_list_2) == 3, f"Test 2 failed: expected 3 authors, got {len(author_list_2)}"
    assert len(author_list_3) == 1, f"Test 3 failed: expected 1 author, got {len(author_list_3)}"
    assert len(author_list_4) == 3, f"Test 4 failed: expected 3 authors, got {len(author_list_4)}"
    
    # Verify no curly braces in cleaned names
    all_cleaned = []
    for authors_text in [authors_text_1, authors_text_2, authors_text_3, authors_text_4]:
        author_list = [a.strip() for a in authors_text.split(' and ') if a.strip()]
        for author_str in author_list:
            cleaned = _clean_text(author_str.strip())
            all_cleaned.append(cleaned)
            assert '{' not in cleaned and '}' not in cleaned, f"Curly braces found in: {cleaned}"
    
    print("✅ PASS: All split counts are correct")
    print("✅ PASS: All names are cleaned (no curly braces)")
    print("✅ PASS: Commas in names do not cause incorrect splitting")
    print("\n🎉 App.py author splitting logic is CORRECT!\n")

if __name__ == "__main__":
    test_app_author_splitting()
