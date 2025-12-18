"""Simple CLI to parse a .bib file and optionally push to the RCAAP Google Sheet."""
from __future__ import annotations

import argparse
import logging
from typing import List

from bibtex_parser import parse_bib_file, entries_to_titles, entries_to_authors, entries_to_events
from database import RCAAPDatabase


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("parse_bib")


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Parse a .bib and write to RCAAP sheet")
    parser.add_argument("bibfile", help="Path to the .bib file to parse")
    parser.add_argument("--dry-run", action="store_true", help="Don't write to the sheet; just show what would be written")
    parser.add_argument("--write-authors", action="store_true", help="Write Authors tab")
    parser.add_argument("--write-titles", action="store_true", help="Write Titles tab")
    parser.add_argument("--write-events", action="store_true", help="Write Events tab")
    args = parser.parse_args(argv)

    entries = parse_bib_file(args.bibfile)

    titles = entries_to_titles(entries)
    authors = entries_to_authors(entries)
    events = entries_to_events(entries)

    if args.dry_run:
        print("=== Titles ===")
        for t in titles:
            print(t)
        print("=== Authors ===")
        for a in authors[:50]:
            print(a)
        print("=== Events ===")
        for ev in events:
            print(ev)
        print("Dry run complete. No data written to the sheet.")
        return 0

    db = RCAAPDatabase()

    if args.write_titles:
        logger.info("Writing %d title rows", len(titles))
        db.write_titles(titles)

    if args.write_authors:
        logger.info("Writing %d author rows", len(authors))
        db.write_authors(authors)

    if args.write_events:
        logger.info("Writing %d event rows", len(events))
        db.write_events(events)

    # Always log an action
    db.write_log(f"Parsed {args.bibfile} and wrote: titles={args.write_titles}, authors={args.write_authors}, events={args.write_events}")
    logger.info("Done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
