"""OAuth 2.0 authentication for Google Search Console API.

Uses the InstalledAppFlow (desktop app) pattern. Credentials are loaded from
a user-supplied credentials.json (downloaded from Google Cloud Console).
Access tokens are cached to disk with chmod 600 and refreshed automatically.

Environment variables (all optional):
    GSC_MCP_CREDENTIALS  Path to OAuth client JSON. Default: ~/.config/gsc-mcp/credentials.json
    GSC_MCP_TOKEN        Path to cached access token. Default: ~/.config/gsc-mcp/token.json
"""

from __future__ import annotations

import logging
import os
import stat
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

logger = logging.getLogger(__name__)

# Read-only is sufficient for v1 (queries, inspections, sitemap listing).
# If we add sitemap submit / indexing request in v2, swap to the full scope
# and users will re-auth once.
SCOPES: list[str] = [
    "https://www.googleapis.com/auth/webmasters.readonly",
]

DEFAULT_CONFIG_DIR = Path.home() / ".config" / "gsc-mcp"
DEFAULT_CREDENTIALS_PATH = DEFAULT_CONFIG_DIR / "credentials.json"
DEFAULT_TOKEN_PATH = DEFAULT_CONFIG_DIR / "token.json"


class AuthError(RuntimeError):
    """Raised when authentication cannot be completed."""


def _credentials_path() -> Path:
    override = os.environ.get("GSC_MCP_CREDENTIALS")
    return Path(override).expanduser() if override else DEFAULT_CREDENTIALS_PATH


def _token_path() -> Path:
    override = os.environ.get("GSC_MCP_TOKEN")
    return Path(override).expanduser() if override else DEFAULT_TOKEN_PATH


def _ensure_config_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _save_token(creds: Credentials, path: Path) -> None:
    _ensure_config_dir(path)
    path.write_text(creds.to_json())
    # chmod 600 — only readable by the owner
    try:
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except OSError:  # Windows etc.
        logger.debug("chmod 600 not supported on this platform; skipping")


def _load_token(path: Path) -> Credentials | None:
    if not path.exists():
        return None
    try:
        return Credentials.from_authorized_user_file(str(path), SCOPES)
    except (ValueError, OSError) as exc:
        logger.warning("Failed to load token from %s: %s", path, exc)
        return None


def get_credentials(interactive: bool = True) -> Credentials:
    """Return valid Google OAuth credentials.

    Resolution order:
        1. Load cached token from GSC_MCP_TOKEN (default ~/.config/gsc-mcp/token.json).
        2. If expired but refreshable, refresh.
        3. Otherwise, if `interactive` is True and credentials.json exists,
           launch the browser OAuth flow and cache the new token.
        4. Raise AuthError with actionable guidance if none of the above work.

    Args:
        interactive: Whether to launch a browser for first-time auth. Set to
            False in environments where a browser cannot be opened.

    Returns:
        google.oauth2.credentials.Credentials ready to use against the API.

    Raises:
        AuthError: If credentials.json is missing or auth cannot complete.
    """
    token_path = _token_path()
    creds_path = _credentials_path()

    creds = _load_token(token_path)

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            _save_token(creds, token_path)
            return creds
        except Exception as exc:  # broad: any refresh failure falls through to re-auth
            logger.warning("Token refresh failed (%s); falling back to interactive auth", exc)

    if not interactive:
        raise AuthError(
            "No valid cached token and interactive auth is disabled. "
            f"Delete {token_path} and re-run with interactive auth enabled, "
            "or run the `gsc-mcp auth` command to refresh."
        )

    if not creds_path.exists():
        raise AuthError(
            f"OAuth client credentials not found at {creds_path}. "
            "Download the OAuth Desktop client JSON from Google Cloud Console "
            "(APIs & Services → Credentials → OAuth 2.0 Client IDs) and save it to "
            f"{creds_path}, or set GSC_MCP_CREDENTIALS to its location."
        )

    flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
    # port=0 lets the OS pick an available local port for the OAuth redirect.
    creds = flow.run_local_server(port=0, open_browser=True)
    _save_token(creds, token_path)
    return creds


def clear_cached_token() -> bool:
    """Remove the cached token. Returns True if a token was removed."""
    token_path = _token_path()
    if token_path.exists():
        token_path.unlink()
        return True
    return False
