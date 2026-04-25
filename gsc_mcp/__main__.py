"""Entry point for the gsc-mcp server.

Invoked by MCP clients via:
    python -m gsc_mcp          # run the stdio MCP server (default)
    gsc-mcp                    # same, via the installed console script

Useful CLI subcommands:
    python -m gsc_mcp auth     # force interactive OAuth (browser flow)
    python -m gsc_mcp info     # print config paths and token status
"""

from __future__ import annotations

import logging
import sys

from . import __version__
from .auth import (
    AuthError,
    _credentials_path,
    _token_path,
    clear_cached_token,
    get_credentials,
)
from .server import mcp


def _configure_logging() -> None:
    # MCP uses stdio for the protocol — logs must go to stderr, never stdout.
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )


def _cmd_auth() -> int:
    """Force-refresh auth by clearing any cached token and running the browser flow."""
    cleared = clear_cached_token()
    if cleared:
        print(f"Removed cached token at {_token_path()}")
    try:
        creds = get_credentials(interactive=True)
    except AuthError as exc:
        print(f"Authentication failed: {exc}", file=sys.stderr)
        return 1
    print(f"Authenticated. Token saved to {_token_path()}")
    print(f"Access token valid: {bool(creds and creds.valid)}")
    return 0


def _cmd_info() -> int:
    """Print current configuration and auth status (no network call)."""
    cred_path = _credentials_path()
    tok_path = _token_path()
    print(f"gsc-mcp version: {__version__}")
    print(f"Credentials path: {cred_path}  (exists: {cred_path.exists()})")
    print(f"Token path:       {tok_path}  (exists: {tok_path.exists()})")
    return 0


def main() -> int:
    _configure_logging()

    # Subcommand dispatch; any unknown arg falls through to MCP server mode
    # so the installed console script `gsc-mcp` works as the MCP stdio entry.
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd in {"-h", "--help"}:
            print(__doc__)
            return 0
        if cmd in {"-v", "--version"}:
            print(__version__)
            return 0
        if cmd == "auth":
            return _cmd_auth()
        if cmd == "info":
            return _cmd_info()
        # Unknown subcommand — show help and exit non-zero so misconfig is obvious.
        if cmd != "serve":
            print(f"Unknown command: {cmd}", file=sys.stderr)
            print(__doc__, file=sys.stderr)
            return 2

    # Default: run the MCP server over stdio
    mcp.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
