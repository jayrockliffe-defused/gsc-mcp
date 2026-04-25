"""Error handling helpers.

All tool-level exceptions are converted into actionable strings that guide the
LLM caller toward a fix. Never leak Python tracebacks to the MCP client.
"""

from __future__ import annotations

from googleapiclient.errors import HttpError

from .auth import AuthError


def format_api_error(exc: Exception) -> str:
    """Convert an exception into a short, actionable error message.

    Callers should return this string directly from their tool function when
    an error occurs, so the LLM can reason about next steps.
    """
    if isinstance(exc, AuthError):
        return f"Authentication error: {exc}"

    if isinstance(exc, HttpError):
        status = exc.resp.status if exc.resp else "unknown"
        reason = exc.reason or "unknown reason"

        if status == 401:
            return (
                "Error 401: Credentials are invalid or expired. Run the "
                "`gsc_health_check` tool or re-authenticate by deleting "
                "~/.config/gsc-mcp/token.json and retrying."
            )
        if status == 403:
            return (
                f"Error 403 ({reason}): The authenticated user does not have "
                "access to this Search Console property, or the Search Console "
                "API is not enabled in the linked Google Cloud project. Verify "
                "site ownership in Search Console and enable the API at "
                "https://console.cloud.google.com/apis/library/searchconsole.googleapis.com"
            )
        if status == 404:
            return (
                f"Error 404 ({reason}): Resource not found. Double-check the "
                "site_url matches a property you own — call `gsc_list_sites` "
                "to see the exact format (domain properties use "
                "'sc-domain:example.com')."
            )
        if status == 429:
            return (
                "Error 429: Rate limit exceeded. The Search Console API allows "
                "~2000 queries per minute per property. Wait 60 seconds and retry."
            )
        if status == 400:
            return (
                f"Error 400 ({reason}): Invalid request. Check that dates are "
                "in YYYY-MM-DD format and dimensions/filters match the Search "
                "Analytics API spec."
            )
        return f"Error {status}: {reason}"

    return f"Unexpected error ({type(exc).__name__}): {exc}"
