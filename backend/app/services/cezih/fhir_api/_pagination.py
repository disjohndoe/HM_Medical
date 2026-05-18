"""FHIR Bundle pagination helper for CEZIH search responses.

CEZIH HAPI returns paginated Bundles when results exceed the page size
(default ~50). The next page URL is in `Bundle.link[]` where
`relation == "next"`. This helper walks those links and returns every
entry across all pages.

No silent truncation: when the safety cap is hit, raises CezihError so
the caller learns about it instead of returning a partial list.
"""

from __future__ import annotations

import logging

from app.services.cezih.client import CezihFhirClient
from app.services.cezih.exceptions import CezihError

logger = logging.getLogger(__name__)

_DEFAULT_MAX_PAGES = 20


def _extract_next_url(bundle: dict) -> str | None:
    for link in bundle.get("link", []) or []:
        if link.get("relation") == "next":
            url = link.get("url")
            if url:
                return str(url)
    return None


async def collect_all_pages(
    client: CezihFhirClient,
    first_response: dict,
    *,
    max_pages: int = _DEFAULT_MAX_PAGES,
) -> list[dict]:
    """Concatenate Bundle.entry[] across link[rel=next] pages.

    Args:
        client: CEZIH FHIR client (used for follow-up GETs).
        first_response: The first page Bundle already fetched by the caller.
        max_pages: Safety cap on the number of pages to follow. With CEZIH's
            default page size of ~50 this allows ~1000 entries per patient,
            which is well above any realistic outpatient record count.

    Returns:
        Flat list of every `entry` across all pages, in CEZIH order.

    Raises:
        CezihError: if the cap is reached. We refuse to silently truncate -
            hitting the cap signals a loop, malformed next link, or wrong
            query, not a legitimate >1000-record patient.
    """
    if first_response.get("resourceType") != "Bundle":
        return []

    entries: list[dict] = list(first_response.get("entry") or [])
    next_url = _extract_next_url(first_response)
    page_count = 1

    while next_url:
        if page_count >= max_pages:
            logger.warning(
                "CEZIH pagination cap hit: %d pages followed, more next links remain (next=%s)",
                page_count,
                next_url[:200],
            )
            raise CezihError(
                f"CEZIH je vratio više od {max_pages} stranica rezultata - "
                "molim vas suzite kriterije pretrage."
            )

        logger.info("CEZIH pagination: following next link (page %d): %s", page_count + 1, next_url[:200])
        bundle = await client.get_absolute(next_url)
        if bundle.get("resourceType") != "Bundle":
            logger.warning(
                "CEZIH pagination: next link returned non-Bundle resource (%s), stopping",
                bundle.get("resourceType"),
            )
            break

        page_entries = bundle.get("entry") or []
        entries.extend(page_entries)
        page_count += 1
        next_url = _extract_next_url(bundle)

    if page_count > 1:
        logger.info(
            "CEZIH pagination: collected %d entries across %d pages",
            len(entries),
            page_count,
        )
    return entries


__all__ = ["collect_all_pages"]
