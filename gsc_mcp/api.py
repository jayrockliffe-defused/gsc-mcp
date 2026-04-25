"""Google Search Console API wrapper.

Thin layer over `googleapiclient.discovery.build("searchconsole", "v1")`. All
calls are synchronous (the google-api-python-client does not expose async);
tool wrappers that need concurrency should offload via `asyncio.to_thread`.
"""

from __future__ import annotations

import logging
from typing import Any

from googleapiclient.discovery import Resource, build

from .auth import get_credentials

logger = logging.getLogger(__name__)

_service_cache: Resource | None = None


def get_service() -> Resource:
    """Return a cached, authenticated Search Console API client.

    The service is built lazily on first use and reused across tool calls for
    the lifetime of the MCP server process. If credentials are invalid or
    revoked, the caller will receive an HttpError from a subsequent call and
    can direct the user to re-auth.
    """
    global _service_cache
    if _service_cache is None:
        creds = get_credentials(interactive=True)
        _service_cache = build(
            "searchconsole",
            "v1",
            credentials=creds,
            cache_discovery=False,
        )
    return _service_cache


def reset_service() -> None:
    """Clear the cached service (used after re-auth)."""
    global _service_cache
    _service_cache = None


# ---------------------------------------------------------------------------
# Sites
# ---------------------------------------------------------------------------

def list_sites() -> list[dict[str, Any]]:
    """Return all Search Console properties the authenticated user owns."""
    response = get_service().sites().list().execute()
    return response.get("siteEntry", [])


def site_exists(site_url: str) -> bool:
    """Check whether `site_url` is among the authenticated user's verified sites."""
    sites = list_sites()
    return any(s.get("siteUrl") == site_url for s in sites)


# ---------------------------------------------------------------------------
# Search Analytics
# ---------------------------------------------------------------------------

def query_search_analytics(
    site_url: str,
    start_date: str,
    end_date: str,
    dimensions: list[str] | None = None,
    row_limit: int = 25,
    start_row: int = 0,
    search_type: str = "web",
    dimension_filter_groups: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Query the Search Analytics endpoint.

    Args:
        site_url: Property in GSC format ('https://example.com/' or 'sc-domain:example.com').
        start_date: ISO date YYYY-MM-DD.
        end_date: ISO date YYYY-MM-DD.
        dimensions: Any of 'query', 'page', 'country', 'device', 'date', 'searchAppearance'.
        row_limit: Max rows to return (1-25000, API max).
        start_row: Pagination offset.
        search_type: 'web' (default), 'image', 'video', 'news', or 'discover'.
        dimension_filter_groups: Optional filters per API spec.

    Returns:
        Dict with 'rows' (list) and 'responseAggregationType' keys.
    """
    body: dict[str, Any] = {
        "startDate": start_date,
        "endDate": end_date,
        "rowLimit": max(1, min(row_limit, 25000)),
        "startRow": max(0, start_row),
        "type": search_type,
    }
    if dimensions:
        body["dimensions"] = dimensions
    if dimension_filter_groups:
        body["dimensionFilterGroups"] = dimension_filter_groups

    return (
        get_service()
        .searchanalytics()
        .query(siteUrl=site_url, body=body)
        .execute()
    )


# ---------------------------------------------------------------------------
# URL Inspection
# ---------------------------------------------------------------------------

def inspect_url(site_url: str, inspection_url: str, language_code: str = "en-US") -> dict[str, Any]:
    """Run the URL Inspection API for a specific URL on a property.

    Args:
        site_url: Property that owns the URL.
        inspection_url: The fully-qualified URL to inspect.
        language_code: BCP-47 code for returned messages (default 'en-US').

    Returns:
        Inspection result dict with indexStatusResult, mobileUsabilityResult,
        richResultsResult, etc.
    """
    body = {
        "inspectionUrl": inspection_url,
        "siteUrl": site_url,
        "languageCode": language_code,
    }
    return (
        get_service()
        .urlInspection()
        .index()
        .inspect(body=body)
        .execute()
    )


# ---------------------------------------------------------------------------
# Sitemaps
# ---------------------------------------------------------------------------

def list_sitemaps(site_url: str) -> list[dict[str, Any]]:
    """List all sitemaps registered for a property."""
    response = get_service().sitemaps().list(siteUrl=site_url).execute()
    return response.get("sitemap", [])
