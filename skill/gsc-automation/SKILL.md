---
name: gsc-automation
description: Use this skill whenever the user mentions Google Search Console, GSC, search queries, indexing status, sitemaps, SEO performance, ranking data, impressions, CTR, search visibility, organic traffic, or asks to inspect a URL's indexing — even if they don't explicitly name the tool. Also trigger for any weekly SEO check-in, content publishing QA, or "is my page indexed" question. Calls the gsc-mcp server tools (gsc_list_sites, gsc_top_queries, gsc_top_pages, gsc_inspect_url, gsc_list_sitemaps, gsc_query_search_analytics, gsc_health_check) to answer with live Search Console data instead of guessing.
---

# Google Search Console automation

Use the `gsc-mcp` MCP server to pull live Search Console data. This skill tells you when to reach for which tool and in what order.

## Hard rules

1. **Never guess.** If the user asks about GSC data, call the tool. Don't rely on training data.
2. **Call `gsc_list_sites` first** in any new session before calling site-specific tools, unless you've already called it in this conversation. Site URL format is strict (`sc-domain:example.com` vs `https://example.com/` with trailing slash). Getting it wrong wastes a tool call.
3. **Default to a recent window.** The last 28 days, ending 3 days ago (GSC data lag), is almost always what the user wants. Don't ask them for dates unless they hint at a specific period.
4. **Summarize, don't dump.** Tools return markdown tables by default. Read the table, extract the insight, then show a trimmed view — not 25 rows of raw data unless asked.

## Setup check (first use only)

If the user has never used this skill before, or a tool call returns an auth error:

```
Call: gsc_health_check
```

If `token_valid: false` or `sites_accessible` is empty, tell the user:

> Looks like the GSC MCP server needs to be authenticated. In a terminal, run:
> `gsc-mcp auth`
> Then retry.

If credentials.json is missing entirely, point them at the README setup steps. Don't try to fix it yourself — auth happens outside the chat.

## Common workflows

### "How is my SEO doing?" (weekly check-in)

```
1. gsc_list_sites                                      → confirm site URL format
2. gsc_top_queries(site, days=28, limit=25)            → top queries by clicks
3. gsc_top_pages(site, days=28, limit=25)              → top pages by clicks
4. Surface: top 3 winning queries, top 3 declining pages,
   any pages with high impressions + low CTR (improvement targets).
```

### "Is this page indexed?" / "Why isn't this page ranking?"

```
1. gsc_inspect_url(site, url)
2. Surface: verdict (PASS/NEUTRAL/FAIL), coverage state, Google-chosen canonical
   (flag if it differs from user's declared canonical), last crawl date.
3. If FAIL or NEUTRAL, explain the specific blocker in plain language.
```

### "Did my new content get picked up?"

```
1. gsc_list_sitemaps(site)                             → confirm sitemap is clean
2. gsc_inspect_url(site, new_url)                      → indexing status
3. If not yet indexed and < 48 hours old, that's normal; tell user.
4. If > 7 days and still not indexed, diagnose (robots, canonical, quality).
```

### "Mobile vs desktop?" / "Which country drives my traffic?"

Use the flexible tool:

```
gsc_query_search_analytics(
    site_url=...,
    dimensions=["query", "device"],  # or ["page", "country"], etc.
    row_limit=50
)
```

### Comparing two time windows (winners/losers)

GSC API does not return deltas. Run two queries and compute the difference yourself:

```
1. gsc_query_search_analytics(start_date=T-28, end_date=T-0, dimensions=["query"])
2. gsc_query_search_analytics(start_date=T-56, end_date=T-29, dimensions=["query"])
3. Join on query, compute clicks_delta and position_delta, sort and surface top
   3 winners and top 3 losers.
```

## Output patterns

- **Always cite the date window** ("over the last 28 days, ending YYYY-MM-DD") so the user knows the freshness.
- **Translate API jargon** — "coverage state: INDEXED" becomes "✅ Indexed"; "verdict: FAIL" becomes "❌ Not indexed — here's why".
- **Round numbers** for human summaries — "14.3K impressions" not "14,328". Keep exact numbers in follow-up detail if asked.
- **Flag the lag** if the user asks about "today" or "yesterday" — GSC data takes 2-3 days to populate.

## Sites the user typically cares about

- `sc-domain:defusely.com` — Defusely marketing site
- `https://defusely.app/` — Defusely product (URL-prefix property, if configured that way)
- _[add River Birch domain(s) here once confirmed]_

Always verify the exact format with `gsc_list_sites` before calling site-specific tools.

## What NOT to do

- Don't invent query or impression numbers. If the tool fails, say so.
- Don't query `end_date = today` — the data will be incomplete; use today - 3 days.
- Don't bulk-inspect more than ~50 URLs in one session — daily quota is 2000 per property, and clients may time out.
- Don't paste raw JSON unless the user specifically asks. Markdown tables are the default for a reason.

## When to escalate

- User asks to **submit a sitemap** — this requires the write scope, not in v1. Tell them to submit manually in Search Console, or open an issue to request v2.
- User asks to **request indexing** for a URL — same; requires Indexing API, not in v1.
- User asks about **Google Analytics 4** data — different API. Point them at [Google's GA4 MCP](https://github.com/googleanalytics/google-analytics-mcp) as a companion.
