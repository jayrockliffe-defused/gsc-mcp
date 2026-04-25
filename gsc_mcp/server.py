"""Google Search Console MCP server.

Registers seven tools with the MCP protocol:

    gsc_list_sites              - enumerate verified properties
    gsc_query_search_analytics  - flexible analytics query (all dimensions/filters)
    gsc_top_queries             - convenience: top search queries for a site
    gsc_top_pages               - convenience: top landing pages for a site
    gsc_inspect_url             - URL inspection (indexing status, canonical, etc.)
    gsc_list_sitemaps           - registered sitemaps for a property
    gsc_health_check            - auth + reachability diagnostic

All tools are read-only and idempotent. The underlying
`google-api-python-client` is synchronous, so API calls are offloaded to a
thread via `asyncio.to_thread` to keep the MCP event loop responsive.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta
from typing import Optional

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field, field_validator

from . import api
from .auth import AuthError, _credentials_path, _token_path, get_credentials
from .errors import format_api_error
from .formatters import (
    ResponseFormat,
    format_health,
    format_inspection,
    format_search_analytics,
    format_sitemaps,
    format_sites,
)

logger = logging.getLogger(__name__)

# MCP server name follows the `{service}_mcp` convention required by the
# MCP builder standard.
mcp = FastMCP("gsc_mcp")


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

DEFAULT_LOOKBACK_DAYS = 28
DATA_LAG_DAYS = 3  # GSC data typically lags 2-3 days behind real time.


def _default_date_range() -> tuple[str, str]:
    """Return (start_date, end_date) for a sensible default window.

    End date is `today - DATA_LAG_DAYS` because GSC data is not fresh for the
    most recent ~3 days. Start date is `DEFAULT_LOOKBACK_DAYS` before that.
    """
    end = date.today() - timedelta(days=DATA_LAG_DAYS)
    start = end - timedelta(days=DEFAULT_LOOKBACK_DAYS)
    return start.isoformat(), end.isoformat()


async def _verify_site(site_url: str) -> Optional[str]:
    """Return None if the site is verified for this user, else an error message."""
    try:
        sites = await asyncio.to_thread(api.list_sites)
    except Exception as exc:
        return format_api_error(exc)

    if not any(s.get("siteUrl") == site_url for s in sites):
        available = ", ".join(f"'{s.get('siteUrl')}'" for s in sites) or "(none)"
        return (
            f"Site '{site_url}' is not a verified property for the authenticated "
            f"user. Available properties: {available}. Domain properties use the "
            "'sc-domain:example.com' format; URL-prefix properties use the full URL "
            "with trailing slash like 'https://example.com/'."
        )
    return None


# ---------------------------------------------------------------------------
# Tool: gsc_list_sites
# ---------------------------------------------------------------------------

class ListSitesInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format: 'markdown' for a human-readable table, 'json' for raw data.",
    )


@mcp.tool(
    name="gsc_list_sites",
    annotations={
        "title": "List verified Search Console sites",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def gsc_list_sites(params: ListSitesInput) -> str:
    """List every Google Search Console property the authenticated user can access.

    Returns a table of site URLs and permission levels. Use the exact siteUrl
    string returned here when calling other tools — the format matters (domain
    properties use 'sc-domain:example.com' prefix).
    """
    try:
        sites = await asyncio.to_thread(api.list_sites)
        return format_sites(sites, params.response_format)
    except Exception as exc:
        return format_api_error(exc)


# ---------------------------------------------------------------------------
# Tool: gsc_query_search_analytics
# ---------------------------------------------------------------------------

class SearchAnalyticsInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    site_url: str = Field(
        ...,
        description=(
            "Property URL in GSC format. Examples: 'https://example.com/' "
            "(URL-prefix property, must have trailing slash), 'sc-domain:example.com' "
            "(domain property). Use gsc_list_sites to see the exact format."
        ),
        min_length=1,
    )
    start_date: Optional[str] = Field(
        default=None,
        description="Start date as YYYY-MM-DD. Defaults to 28 days before end_date.",
    )
    end_date: Optional[str] = Field(
        default=None,
        description=(
            "End date as YYYY-MM-DD. Defaults to today minus 3 days (GSC data lag). "
            "Use a date at least 2 days in the past for reliable numbers."
        ),
    )
    dimensions: list[str] = Field(
        default_factory=lambda: ["query"],
        description=(
            "Dimensions to group by. Any combination of: 'query', 'page', 'country', "
            "'device', 'date', 'searchAppearance'. Default ['query']."
        ),
        max_length=5,
    )
    row_limit: int = Field(
        default=25,
        description="Maximum rows to return. API max is 25000.",
        ge=1,
        le=25000,
    )
    start_row: int = Field(
        default=0,
        description="Pagination offset. Use in combination with row_limit.",
        ge=0,
    )
    search_type: str = Field(
        default="web",
        description="Search type: 'web' (default), 'image', 'video', 'news', 'discover'.",
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format: 'markdown' or 'json'.",
    )

    @field_validator("start_date", "end_date")
    @classmethod
    def validate_date(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        try:
            date.fromisoformat(v)
        except ValueError as exc:
            raise ValueError(f"Date must be YYYY-MM-DD format; got '{v}'") from exc
        return v

    @field_validator("dimensions")
    @classmethod
    def validate_dimensions(cls, v: list[str]) -> list[str]:
        allowed = {"query", "page", "country", "device", "date", "searchAppearance"}
        bad = [d for d in v if d not in allowed]
        if bad:
            raise ValueError(
                f"Invalid dimension(s): {bad}. Allowed: {sorted(allowed)}"
            )
        return v

    @field_validator("search_type")
    @classmethod
    def validate_search_type(cls, v: str) -> str:
        allowed = {"web", "image", "video", "news", "discover"}
        if v not in allowed:
            raise ValueError(f"search_type must be one of {sorted(allowed)}; got '{v}'")
        return v


@mcp.tool(
    name="gsc_query_search_analytics",
    annotations={
        "title": "Query Search Console analytics (flexible)",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def gsc_query_search_analytics(params: SearchAnalyticsInput) -> str:
    """Run a flexible Search Analytics query against a property.

    This is the general-purpose analytics tool. For common cases, prefer the
    convenience tools `gsc_top_queries` or `gsc_top_pages`. Use this tool when
    you need multi-dimensional grouping (e.g. query x device x country) or
    non-default search types (image, video, news, discover).

    Returns clicks, impressions, CTR and average position per row.
    """
    error = await _verify_site(params.site_url)
    if error:
        return error

    start = params.start_date
    end = params.end_date
    if start is None or end is None:
        default_start, default_end = _default_date_range()
        start = start or default_start
        end = end or default_end

    try:
        result = await asyncio.to_thread(
            api.query_search_analytics,
            site_url=params.site_url,
            start_date=start,
            end_date=end,
            dimensions=params.dimensions,
            row_limit=params.row_limit,
            start_row=params.start_row,
            search_type=params.search_type,
        )
        return format_search_analytics(result, params.dimensions, params.response_format)
    except Exception as exc:
        return format_api_error(exc)


# ---------------------------------------------------------------------------
# Tool: gsc_top_queries
# ---------------------------------------------------------------------------

class TopQueriesInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    site_url: str = Field(..., description="Property URL (see gsc_list_sites for format).", min_length=1)
    days: int = Field(
        default=28,
        description="Lookback window in days (ending 3 days ago to account for GSC data lag).",
        ge=1,
        le=490,  # GSC retains up to 16 months
    )
    limit: int = Field(default=25, description="Number of queries to return.", ge=1, le=1000)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


@mcp.tool(
    name="gsc_top_queries",
    annotations={
        "title": "Top search queries for a site",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def gsc_top_queries(params: TopQueriesInput) -> str:
    """Return the top N search queries for a site over a recent period.

    Convenience wrapper over gsc_query_search_analytics. Use this when you
    want a quick ranking of which queries are driving impressions/clicks —
    ideal for weekly SEO check-ins.
    """
    error = await _verify_site(params.site_url)
    if error:
        return error

    end = date.today() - timedelta(days=DATA_LAG_DAYS)
    start = end - timedelta(days=params.days)

    try:
        result = await asyncio.to_thread(
            api.query_search_analytics,
            site_url=params.site_url,
            start_date=start.isoformat(),
            end_date=end.isoformat(),
            dimensions=["query"],
            row_limit=params.limit,
        )
        return format_search_analytics(result, ["query"], params.response_format)
    except Exception as exc:
        return format_api_error(exc)


# ---------------------------------------------------------------------------
# Tool: gsc_top_pages
# ---------------------------------------------------------------------------

class TopPagesInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    site_url: str = Field(..., description="Property URL (see gsc_list_sites for format).", min_length=1)
    days: int = Field(default=28, description="Lookback window in days.", ge=1, le=490)
    limit: int = Field(default=25, description="Number of pages to return.", ge=1, le=1000)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


@mcp.tool(
    name="gsc_top_pages",
    annotations={
        "title": "Top landing pages for a site",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def gsc_top_pages(params: TopPagesInput) -> str:
    """Return the top N landing pages for a site over a recent period.

    Convenience wrapper over gsc_query_search_analytics. Use this to spot
    which URLs drive the most organic traffic and which are underperforming.
    """
    error = await _verify_site(params.site_url)
    if error:
        return error

    end = date.today() - timedelta(days=DATA_LAG_DAYS)
    start = end - timedelta(days=params.days)

    try:
        result = await asyncio.to_thread(
            api.query_search_analytics,
            site_url=params.site_url,
            start_date=start.isoformat(),
            end_date=end.isoformat(),
            dimensions=["page"],
            row_limit=params.limit,
        )
        return format_search_analytics(result, ["page"], params.response_format)
    except Exception as exc:
        return format_api_error(exc)


# ---------------------------------------------------------------------------
# Tool: gsc_inspect_url
# ---------------------------------------------------------------------------

class InspectUrlInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    site_url: str = Field(..., description="Property URL that owns the page being inspected.", min_length=1)
    inspection_url: str = Field(
        ...,
        description="Fully-qualified URL to inspect (must belong to site_url).",
        min_length=1,
    )
    language_code: str = Field(
        default="en-US",
        description="BCP-47 language code for returned messages.",
    )
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


@mcp.tool(
    name="gsc_inspect_url",
    annotations={
        "title": "Inspect a URL's indexing status",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def gsc_inspect_url(params: InspectUrlInput) -> str:
    """Run the URL Inspection API for a specific page.

    Returns indexing verdict, coverage state, last crawl time, Google-chosen
    canonical, mobile usability, rich results — everything the Inspect URL
    panel in Search Console shows. Use this to diagnose why a page isn't
    ranking, confirm indexing after a publish, or spot canonical mismatches.

    Rate limit: ~2000 calls per property per day. For bulk inspections,
    add a sleep between calls (a future bulk tool will handle this).
    """
    error = await _verify_site(params.site_url)
    if error:
        return error

    try:
        result = await asyncio.to_thread(
            api.inspect_url,
            site_url=params.site_url,
            inspection_url=params.inspection_url,
            language_code=params.language_code,
        )
        return format_inspection(result, params.inspection_url, params.response_format)
    except Exception as exc:
        return format_api_error(exc)


# ---------------------------------------------------------------------------
# Tool: gsc_list_sitemaps
# ---------------------------------------------------------------------------

class ListSitemapsInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    site_url: str = Field(..., description="Property URL (see gsc_list_sites for format).", min_length=1)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


@mcp.tool(
    name="gsc_list_sitemaps",
    annotations={
        "title": "List registered sitemaps for a site",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def gsc_list_sitemaps(params: ListSitemapsInput) -> str:
    """List every sitemap registered for a property, with status and error counts.

    Useful for: verifying a sitemap was accepted, spotting sitemaps that have
    parse errors, and confirming fresh submission dates.
    """
    error = await _verify_site(params.site_url)
    if error:
        return error

    try:
        sitemaps = await asyncio.to_thread(api.list_sitemaps, params.site_url)
        return format_sitemaps(sitemaps, params.response_format)
    except Exception as exc:
        return format_api_error(exc)


# ---------------------------------------------------------------------------
# Tool: gsc_health_check
# ---------------------------------------------------------------------------

class HealthCheckInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


@mcp.tool(
    name="gsc_health_check",
    annotations={
        "title": "Check GSC MCP auth and API reachability",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def gsc_health_check(params: HealthCheckInput) -> str:
    """Diagnostic: confirm the OAuth token is valid and the Search Console API is reachable.

    Run this first when setting up the server or after errors to determine
    whether the issue is auth, network, or a specific site.
    """
    token_valid = False
    sites_count: int | None = None
    error: str | None = None

    try:
        # Non-interactive so we don't pop a browser on a health check.
        creds = await asyncio.to_thread(get_credentials, False)
        token_valid = bool(creds and creds.valid)
    except AuthError as exc:
        error = str(exc)
    except Exception as exc:  # noqa: BLE001
        error = f"{type(exc).__name__}: {exc}"

    if token_valid and error is None:
        try:
            sites = await asyncio.to_thread(api.list_sites)
            sites_count = len(sites)
        except Exception as exc:
            error = format_api_error(exc)

    return format_health(
        token_valid=token_valid,
        credentials_path=str(_credentials_path()),
        token_path=str(_token_path()),
        sites_count=sites_count,
        error=error,
        fmt=params.response_format,
    )
