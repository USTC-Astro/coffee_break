# USTC Astro Coffee Break Migration Plan

## Goals

- Keep the current server version working while the GitHub version is prepared.
- Publish a read-only GitHub Pages version for papers, history, summaries, figures, and posters.
- Automate agenda refresh and poster generation with GitHub Actions.
- Keep interactive features behind a backend or serverless service.
- Make every deployment rollback-friendly with git commits, tags, and archived data.

## Architecture

### GitHub Pages

Hosts the static public site:

- current agenda
- history pages
- paper summary pages
- poster slideshow
- static JSON/image assets

### GitHub Actions

Runs scheduled maintenance:

- fetch Benty-Fields agenda
- generate or update paper summaries and figures
- generate coffee-break posters
- write poster manifests
- build the static site
- deploy GitHub Pages

Secrets needed:

- `BENTY_PASSWORD`
- optional `OPENAI_API_KEY` or equivalent LLM key if poster generation uses a model

### Dynamic Backend

Needed only for write operations:

- coffee voting
- rating/thought submission
- marking papers as discussed in Benty-Fields
- Luckin order creation/admin checkout

This can remain on the current server, or later move to a serverless backend such as Cloudflare Workers + D1 or Supabase.

## Rollback

- Tag the current server baseline before public migration, e.g. `server-current-2026-08-22`.
- Tag each stable GitHub Pages release, e.g. `pages-v1`.
- Keep `data/history/` and `data/posters/archive/` as content-level archives.
- GitHub Pages can roll back by redeploying a previous commit or tag.

## Phases

1. Make the repository safe for GitHub.
   - remove hard-coded credentials
   - add `.gitignore`
   - add dependency list

2. Build static mirror.
   - generate `site/` from existing templates and data
   - copy static data assets
   - rewrite links for GitHub Pages project paths

3. Static poster support.
   - generate `data/posters/<week>/manifest.json`
   - let poster page read the manifest in static mode

4. GitHub Actions.
   - scheduled agenda refresh
   - scheduled poster generation
   - static build and Pages deployment

5. Interactions.
   - keep current FastAPI backend initially
   - add vote passcode/rate limiting if staying on server
   - evaluate serverless replacement later

6. Luckin admin tool.
   - aggregate votes
   - preview order via Luckin MCP
   - require human confirmation before creating the order
   - require human payment confirmation
