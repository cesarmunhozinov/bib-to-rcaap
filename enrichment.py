"""RCAAP Validation & Enrichment layer for academic metadata curation."""
from __future__ import annotations

from typing import Dict, Any, Optional
import requests


# RCAAP Official Types (from RCAAP schema)
RCAAP_TYPES = [
    "Select Type...",
    "article",
    "book",
    "bookPart",
    "conferenceObject",
    "conferenceProceeding",
    "doctoralThesis",
    "masterThesis",
    "report",
    "workingPaper",
    "dataset",
    "other",
]

# RCAAP Required Fields
RCAAP_REQUIRED_FIELDS = ["title", "authors", "year", "language"]
RCAAP_RECOMMENDED_FIELDS = ["abstract", "doi", "type"]


def fetch_from_openalex(doi: str) -> Optional[Dict[str, Any]]:
    """Fetch enriched metadata from OpenAlex API using a DOI.
    
    Returns: dict with keys: abstract, language, is_oa, venue_type, or None if not found.
    """
    if not doi:
        return None
    try:
        # Normalize DOI
        doi_clean = doi.replace("https://doi.org/", "").replace("http://doi.org/", "").strip()
        url = f"https://api.openalex.org/works?filter=doi:{doi_clean}"
        response = requests.get(url, timeout=5)
        if response.status_code != 200:
            return None
        data = response.json()
        if not data.get("results"):
            return None
        work = data["results"][0]
        return {
            "abstract": work.get("abstract", ""),
            "language": work.get("language", "en"),
            "is_oa": work.get("is_oa", False),
            "venue_type": work.get("type", ""),
        }
    except Exception:
        return None


def validate_entry(entry: Dict[str, Any]) -> tuple[bool, list[str]]:
    """Validate an entry against RCAAP requirements.
    
    Returns: (is_valid, list_of_missing_fields)
    """
    missing = []
    for field in RCAAP_REQUIRED_FIELDS:
        if not entry.get(field):
            missing.append(field)
    return len(missing) == 0, missing


def enrich_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    """Enrich an entry with OpenAlex data if DOI is present and fields are missing."""
    enriched = entry.copy()
    doi = entry.get("doi") or entry.get("DOI")
    if doi:
        openalex_data = fetch_from_openalex(doi)
        if openalex_data:
            if not enriched.get("abstract") and openalex_data.get("abstract"):
                enriched["abstract"] = openalex_data["abstract"]
            if not enriched.get("language") and openalex_data.get("language"):
                enriched["language"] = openalex_data["language"]
            enriched["is_oa"] = openalex_data.get("is_oa", False)
            enriched["venue_type"] = openalex_data.get("venue_type", "")
    return enriched
