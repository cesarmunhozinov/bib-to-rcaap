"""Simple CLI to parse a .bib file and optionally push to the RCAAP Google Sheet."""
from __future__ import annotations

import argparse
import logging
from typing import List

from bibtex_parser import parse_bib_file, entries_to_titles, entries_to_authors
from database import RCAAPDatabase


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("parse_bib")


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Parse a .bib and write to RCAAP sheet")
    parser.add_argument("bibfile", help="Path to the .bib file to parse")
    parser.add_argument("--dry-run", action="store_true", help="Don't write to the sheet; just show what would be written")
    parser.add_argument("--write-authors", action="store_true", help="Write Authors tab")
    # Note: Titles/Events write flags removed; use the relational sync helpers for relational writes.
    args = parser.parse_args(argv)

    entries = parse_bib_file(args.bibfile)

    titles = entries_to_titles(entries)
    authors = entries_to_authors(entries)

    if args.dry_run:
        print("=== Titles ===")
        for t in titles:
            print(t)
        print("=== Authors ===")
        for a in authors[:50]:
            print(a)
        print("Dry run complete. No data written to the sheet.")
        return 0

    db = RCAAPDatabase()

    if args.write_authors:
        logger.info("Writing %d author rows", len(authors))
        db.write_authors(authors)

    # Note: Titles/Events writes and Logs are removed. Use relational sync helpers for relational writes.
    logger.info("Done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
