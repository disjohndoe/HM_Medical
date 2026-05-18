"""Unit tests for backend/app/services/cezih/fhir_api/_pagination.py."""

from __future__ import annotations

import pytest

from app.services.cezih.exceptions import CezihError
from app.services.cezih.fhir_api._pagination import collect_all_pages


class _FakeClient:
    """Stand-in for CezihFhirClient that serves canned pages by URL."""

    def __init__(self, pages_by_url: dict[str, dict]) -> None:
        self._pages = pages_by_url
        self.calls: list[str] = []

    async def get_absolute(self, url: str) -> dict:  # noqa: D401
        self.calls.append(url)
        if url not in self._pages:
            raise AssertionError(f"unexpected next URL: {url}")
        return self._pages[url]


def _bundle(entries: list[dict], next_url: str | None = None) -> dict:
    bundle: dict = {"resourceType": "Bundle", "entry": entries}
    if next_url:
        bundle["link"] = [{"relation": "next", "url": next_url}]
    return bundle


@pytest.mark.asyncio
async def test_returns_first_page_entries_when_no_next_link():
    first = _bundle([{"resource": {"id": "a"}}, {"resource": {"id": "b"}}])
    client = _FakeClient({})

    entries = await collect_all_pages(client, first)

    assert [e["resource"]["id"] for e in entries] == ["a", "b"]
    assert client.calls == []


@pytest.mark.asyncio
async def test_follows_next_links_concatenating_entries():
    page2 = _bundle(
        [{"resource": {"id": "c"}}],
        next_url="https://cezih.test/page3",
    )
    page3 = _bundle([{"resource": {"id": "d"}}])
    first = _bundle(
        [{"resource": {"id": "a"}}, {"resource": {"id": "b"}}],
        next_url="https://cezih.test/page2",
    )
    client = _FakeClient(
        {
            "https://cezih.test/page2": page2,
            "https://cezih.test/page3": page3,
        }
    )

    entries = await collect_all_pages(client, first)

    assert [e["resource"]["id"] for e in entries] == ["a", "b", "c", "d"]
    assert client.calls == ["https://cezih.test/page2", "https://cezih.test/page3"]


@pytest.mark.asyncio
async def test_raises_when_max_pages_cap_hit():
    looping = _bundle([{"resource": {"id": "x"}}], next_url="https://cezih.test/p")
    client = _FakeClient({"https://cezih.test/p": looping})

    with pytest.raises(CezihError, match="stranica"):
        await collect_all_pages(client, looping, max_pages=3)

    # 1 initial + 2 follow-up GETs before the cap fires on the 3rd
    assert len(client.calls) == 2


@pytest.mark.asyncio
async def test_non_bundle_first_response_returns_empty():
    not_a_bundle = {"resourceType": "OperationOutcome"}
    client = _FakeClient({})

    entries = await collect_all_pages(client, not_a_bundle)

    assert entries == []
    assert client.calls == []


@pytest.mark.asyncio
async def test_stops_when_next_page_is_not_a_bundle():
    bad_next = {"resourceType": "OperationOutcome"}
    first = _bundle([{"resource": {"id": "a"}}], next_url="https://cezih.test/oops")
    client = _FakeClient({"https://cezih.test/oops": bad_next})

    entries = await collect_all_pages(client, first)

    assert [e["resource"]["id"] for e in entries] == ["a"]
