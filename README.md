# gsc-mcp

[![PyPI version](https://badge.fury.io/py/gsc-mcp.svg)](https://pypi.org/project/gsc-mcp/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Glama MCP server](https://glama.ai/mcp/servers/jayrockliffe-defused/gsc-mcp/badges/score.svg)](https://glama.ai/mcp/servers/jayrockliffe-defused/gsc-mcp)

**Google Search Console as MCP tools** — query search analytics, inspect URLs, and monitor SEO performance from any MCP-compatible AI client (Claude Desktop, Claude Code, Claude.ai, Gemini CLI, Cursor, etc.).

Zero vendor middleware. Zero ongoing cost. Each user authenticates with their own Google account against Google's free Search Console API.

---

## Why this exists

Pulling GSC data into an AI client normally means either (a) manual CSV exports, (b) a paid data-pipeline vendor like Windsor or Coupler, or (c) building your own script and glue. This is option (d): a small, self-contained MCP server you install once and use from anywhere. Pairs naturally with [Google's Analytics MCP](https://github.com/googleanalytics/google-analytics-mcp) for a complete SEO + user behavior picture.

---

## Tools

All tools are read-only. No writes in v1.

| Tool | What it does |
| --- | --- |
| `gsc_list_sites` | Enumerate every verified Search Console property for the authenticated user |
| `gsc_query_search_analytics` | Flexible analytics query — any combination of dimensions (query, page, country, device, date, searchAppearance) and filters |
| `gsc_top_queries` | Convenience: top N search queries for a site over a recent window |
| `gsc_top_pages` | Convenience: top N landing pages for a site over a recent window |
| `gsc_inspect_url` | URL inspection — indexing verdict, coverage state, Google-chosen canonical, last crawl, mobile usability, rich results |
| `gsc_list_sitemaps` | List registered sitemaps with status, errors, warnings, last submitted date |
| `gsc_health_check` | Auth + API reachability diagnostic (use this first when something breaks) |

---

## Setup

Three steps. ~15 minutes total.

### 1. Google Cloud — create an OAuth client

1. Open [Google Cloud Console](https://console.cloud.google.com/).
2. Create (or reuse) a project. Name it something like `gsc-mcp`.
3. Enable the Search Console API: [one-click link](https://console.cloud.google.com/apis/library/searchconsole.googleapis.com).
4. Go to **APIs & Services → Credentials**.
5. If you haven't already, configure the OAuth consent screen:
    - User type: **External**.
    - App name: `gsc-mcp`, support email: your email, developer email: your email.
    - Add yourself as a **Test user** (under "Audience" / "Test users").
6. Click **Create Credentials → OAuth client ID**.
    - Application type: **Desktop app**.
    - Name: `gsc-mcp-local`.
7. **Download JSON.** Move the downloaded file to:
   ```
   ~/.config/gsc-mcp/credentials.json
   ```
   (Create the directory if it doesn't exist: `mkdir -p ~/.config/gsc-mcp`)

### 2. Install the server

```bash
pipx install gsc-mcp
```

Or with pip:

```bash
pip install gsc-mcp
```

This installs the `gsc-mcp` console command and the `gsc_mcp` Python module.

### 3. Authenticate once

```bash
gsc-mcp auth
```

A browser window opens. Sign in with the Google account that owns your Search Console properties. You'll see a "Google hasn't verified this app" screen — that's expected because the app is for your personal use; click **Advanced → Go to gsc-mcp (unsafe)** and continue.

The token is saved to `~/.config/gsc-mcp/token.json` (chmod 600) and refreshed automatically from here on.

Verify everything works:

```bash
gsc-mcp info
# gsc-mcp version: 0.1.0
# Credentials path: /Users/you/.config/gsc-mcp/credentials.json  (exists: True)
# Token path:       /Users/you/.config/gsc-mcp/token.json  (exists: True)
```

---

## Connect it to a client

### Claude Desktop

Edit `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or the equivalent path on Linux/Windows, and add:

```json
{
  "mcpServers": {
    "gsc": {
      "command": "gsc-mcp"
    }
  }
}
```

Restart Claude Desktop. Type `/mcp` in a chat — you should see `gsc` listed with 7 tools.

### Claude Code

```bash
claude mcp add gsc -- gsc-mcp
```

Or edit `~/.claude.json` / the project `.claude/mcp.json` directly:

```json
{
  "mcpServers": {
    "gsc": {
      "command": "gsc-mcp"
    }
  }
}
```

### Claude.ai

1. Settings → Connectors → **Add custom connector**.
2. Name: `GSC`. Command: `gsc-mcp`.
3. Enable it.

### Cursor, Windsurf, Gemini CLI, etc.

Any MCP-compatible client accepts the same stdio server config. Command: `gsc-mcp`. No args.

---

## Example prompts once connected

```
What verified sites do I have in Search Console?

Show me the top 20 search queries for defusely.com over the last 30 days.

Which pages on defusely.app have the biggest impression-to-click gap?

Inspect https://defusely.com/pricing — is it indexed, what's the canonical, when
was it last crawled?

List all sitemaps registered for defusely.com and flag any with errors.

Compare CTR on mobile vs desktop for the top 10 queries on defusely.com this month.
```

---

## Configuration

All paths are overrideable via environment variables:

| Variable | Default | Purpose |
| --- | --- | --- |
| `GSC_MCP_CREDENTIALS` | `~/.config/gsc-mcp/credentials.json` | OAuth client JSON from Google Cloud |
| `GSC_MCP_TOKEN` | `~/.config/gsc-mcp/token.json` | Cached access token (auto-managed) |

---

## Troubleshooting

**`Error 403` on every call** — the Search Console API isn't enabled on your Google Cloud project, or the authenticated Google account doesn't own the property. Enable the API at the [Search Console API library page](https://console.cloud.google.com/apis/library/searchconsole.googleapis.com) and verify site ownership in Search Console.

**`Error 401` / token refresh fails** — your refresh token was revoked (Google does this after ~6 months of non-use or on password change). Delete the token and re-auth:
```bash
rm ~/.config/gsc-mcp/token.json
gsc-mcp auth
```

**Site not found** — call `gsc_list_sites` first to see the exact siteUrl format. Domain properties use `sc-domain:example.com`; URL-prefix properties use `https://example.com/` with the trailing slash.

**URL inspection returns "quota exceeded"** — the URL Inspection API is capped at ~2000 calls per property per day. Wait 24 hours or use bulk URL inspection sparingly.

**Data looks stale** — Search Console data typically lags real-time by 2-3 days. The default date range in this server ends 3 days ago for this reason. Don't query `end_date = today` and expect full data.

---

## License

Apache 2.0 — see [LICENSE](./LICENSE).

## Contributing

Issues and PRs welcome. This is deliberately small; keep changes focused on the GSC API surface.
