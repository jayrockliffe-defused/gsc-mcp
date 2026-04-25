"""Response formatters.

Each tool supports both 'markdown' (human-readable tables) and 'json'
(machine-readable full data) formats. Markdown trims verbose metadata;
JSON preserves everything the API returned.
"""

from __future__ import annotations

import json
from enum import Enum
from typing import Any


class ResponseFormat(str, Enum):
    """Output format for tool responses."""

    MARKDOWN = "markdown"
    JSON = "json"


def _fmt_float(value: float | int | None, decimals: int = 2) -> str:
    if value is None:
        return "—"
    return f"{value:.{decimals}f}"


def _fmt_int(value: int | None) -> str:
    if value is None:
        return "—"
    return f"{value:,}"


def _fmt_pct(value: float | None) -> str:
    """Format a 0-1 ratio as a percentage."""
    if value is None:
        return "—"
    return f"{value * 100:.2f}%"


# ---------------------------------------------------------------------------
# Sites
# ---------------------------------------------------------------------------

def format_sites(sites: list[dict[str, Any]], fmt: ResponseFormat) -> str:
    if fmt == ResponseFormat.JSON:
        return json.dumps(sites, indent=2)

    if not sites:
        return "No verified sites found for the authenticated user."

    lines = [
        f"Found {len(sites)} verified site(s):",
        "",
        "| Site URL | Permission Level |",
        "| --- | --- |",
    ]
    for s in sites:
        lines.append(f"| `{s.get('siteUrl', '')}` | {s.get('permissionLevel', '')} |")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Search Analytics
# ---------------------------------------------------------------------------

def format_search_analytics(
    result: dict[str, Any],
    dimensions: list[str],
    fmt: ResponseFormat,
) -> str:
    if fmt == ResponseFormat.JSON:
        return json.dumps(result, indent=2)

    rows = result.get("rows", [])
    if not rows:
        return "No data returned for the given date range and filters."

    header_cols = [*dimensions, "Clicks", "Impressions", "CTR", "Position"]
    lines = [
        f"Returned {len(rows)} row(s).",
        "",
        "| " + " | ".join(header_cols) + " |",
        "| " + " | ".join(["---"] * len(header_cols)) + " |",
    ]
    for row in rows:
        keys = row.get("keys", [])
        dim_cells = [str(k) for k in keys]
        # Pad if fewer keys than dimensions (shouldn't happen, but defensive)
        while len(dim_cells) < len(dimensions):
            dim_cells.append("—")
        lines.append(
            "| "
            + " | ".join(
                dim_cells
                + [
                    _fmt_int(row.get("clicks")),
                    _fmt_int(row.get("impressions")),
                    _fmt_pct(row.get("ctr")),
                    _fmt_float(row.get("position")),
                ]
            )
            + " |"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# URL Inspection
# ---------------------------------------------------------------------------

def format_inspection(result: dict[str, Any], inspection_url: str, fmt: ResponseFormat) -> str:
    if fmt == ResponseFormat.JSON:
        return json.dumps(result, indent=2)

    inspection = result.get("inspectionResult", {})
    index_status = inspection.get("indexStatusResult", {})
    mobile = inspection.get("mobileUsabilityResult", {})
    rich = inspection.get("richResultsResult", {})

    lines = [
        f"## URL inspection: {inspection_url}",
        "",
        "### Indexing",
        f"- **Verdict:** {index_status.get('verdict', '—')}",
        f"- **Coverage state:** {index_status.get('coverageState', '—')}",
        f"- **Robots.txt state:** {index_status.get('robotsTxtState', '—')}",
        f"- **Indexing state:** {index_status.get('indexingState', '—')}",
        f"- **Last crawl:** {index_status.get('lastCrawlTime', '—')}",
        f"- **Crawled as:** {index_status.get('crawledAs', '—')}",
        f"- **Page fetch state:** {index_status.get('pageFetchState', '—')}",
        f"- **Google-canonical URL:** {index_status.get('googleCanonical', '—')}",
        f"- **User-declared canonical:** {index_status.get('userCanonical', '—')}",
    ]

    ref_urls = index_status.get("referringUrls") or []
    if ref_urls:
        lines.extend(["", "### Referring URLs"])
        lines.extend(f"- {u}" for u in ref_urls[:10])
        if len(ref_urls) > 10:
            lines.append(f"- …and {len(ref_urls) - 10} more")

    if mobile:
        lines.extend([
            "",
            "### Mobile usability",
            f"- **Verdict:** {mobile.get('verdict', '—')}",
        ])
        issues = mobile.get("issues") or []
        if issues:
            lines.append("- **Issues:**")
            for issue in issues:
                lines.append(f"  - {issue.get('issueType', '—')}: {issue.get('message', '')}")

    if rich:
        lines.extend([
            "",
            "### Rich results",
            f"- **Verdict:** {rich.get('verdict', '—')}",
        ])
        detected = rich.get("detectedItems") or []
        for item in detected:
            lines.append(f"- {item.get('richResultType', '—')}")

    link = inspection.get("inspectionResultLink")
    if link:
        lines.extend(["", f"[Open in Search Console]({link})"])

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Sitemaps
# ---------------------------------------------------------------------------

def format_sitemaps(sitemaps: list[dict[str, Any]], fmt: ResponseFormat) -> str:
    if fmt == ResponseFormat.JSON:
        return json.dumps(sitemaps, indent=2)

    if not sitemaps:
        return "No sitemaps registered for this site."

    lines = [
        f"Found {len(sitemaps)} sitemap(s):",
        "",
        "| Path | Type | Last submitted | Warnings | Errors | Pending |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for s in sitemaps:
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{s.get('path', '')}`",
                    s.get("type", "—"),
                    s.get("lastSubmitted", "—"),
                    _fmt_int(int(s.get("warnings", 0))) if s.get("warnings") else "0",
                    _fmt_int(int(s.get("errors", 0))) if s.get("errors") else "0",
                    "yes" if s.get("isPending") else "no",
                ]
            )
            + " |"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

def format_health(
    token_valid: bool,
    credentials_path: str,
    token_path: str,
    sites_count: int | None,
    error: str | None,
    fmt: ResponseFormat,
) -> str:
    payload = {
        "token_valid": token_valid,
        "credentials_path": credentials_path,
        "token_path": token_path,
        "sites_accessible": sites_count,
        "error": error,
    }
    if fmt == ResponseFormat.JSON:
        return json.dumps(payload, indent=2)

    status = "✅ healthy" if (token_valid and error is None) else "❌ needs attention"
    lines = [
        f"## GSC MCP health: {status}",
        "",
        f"- **Credentials file:** `{credentials_path}`",
        f"- **Token file:** `{token_path}`",
        f"- **Token valid:** {'yes' if token_valid else 'no'}",
        f"- **Sites accessible:** {sites_count if sites_count is not None else '—'}",
    ]
    if error:
        lines.extend(["", f"**Error:** {error}"])
    return "\n".join(lines)
