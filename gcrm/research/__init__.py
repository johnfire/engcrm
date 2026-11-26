"""Company research dossier — evidence-backed crawling and extraction."""

from gcrm.research.dossier import (
    CompanyResearchFetcher,
    Crawl4AIFetcher,
    get_existing_dossier,
    get_or_create_dossier,
)

__all__ = [
    "CompanyResearchFetcher",
    "Crawl4AIFetcher",
    "get_existing_dossier",
    "get_or_create_dossier",
]
