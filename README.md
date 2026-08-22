# USTC Astro Coffee Break

This repository contains the migration-ready version of the USTC Astro Coffee
Break site.

## Modes

- `app.py` keeps the existing FastAPI server mode for voting, ratings, notes,
  Benty-Fields updates, and admin actions.
- `build_static.py` exports a read-only GitHub Pages version under `site/`.

The static site includes papers, history, summary pages, figures, and poster
slideshows. Write actions are hidden in the static build.

## Local static build

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-static.txt
.venv/bin/python build_static.py
```

Open `site/index.html` to inspect the static mirror.

## GitHub Pages

Enable Pages with GitHub Actions as the source. The workflow
`.github/workflows/pages.yml` builds `site/` and deploys it on every push to
`main`.

If the Cloudflare Worker voting API is deployed, add this repository variable:

- `COFFEE_API_BASE`, for example `https://coffee-break-api.<subdomain>.workers.dev`

## Automatic agenda refresh

Configure the repository secret:

- `BENTY_PASSWORD`

Then run `.github/workflows/update-agenda.yml` manually or on its weekly
schedule. It refreshes `data/`, rebuilds static manifests, and commits changed
data back to the repository.

## Coffee voting backend

The static GitHub Pages site can keep the in-page voting experience through a
Cloudflare Worker + D1 backend under `worker/`.

Cloudflare setup:

```bash
cd worker
cp wrangler.toml.example wrangler.toml
# Fill database_id after creating the D1 database.
npx wrangler d1 create coffee-break-db
npx wrangler d1 migrations apply coffee-break-db --remote
```

GitHub repository secrets for `Deploy Cloudflare Worker`:

- `CLOUDFLARE_API_TOKEN`
- `CLOUDFLARE_ACCOUNT_ID`

Cloudflare Worker variables/secrets:

- `ALLOWED_ORIGINS`: include the GitHub Pages URL
- `COFFEE_VOTE_CODE`: optional weekly passcode
- `ADMIN_TOKEN`: optional admin refresh token
- `IP_HASH_SECRET`: optional salt for IP-based rate limiting
- `MAX_VOTES_PER_MINUTE`: optional, defaults to `12`

The Worker implements:

- `GET /coffee_votes/current`
- `POST /coffee_votes/current`
- `POST /coffee_votes/current/cancel`
- `POST /admin/refresh_votes?token=...`

Responses match the old FastAPI shape, so the same coffee vote page works in
server mode and static GitHub Pages mode.

## Poster generation

`coffee_break_poster` is currently a Codex skill, not a command that GitHub
Actions can call directly. To run it in Actions, convert the skill workflow into
a repository script that accepts paper IDs, reads `data/*.md` and
`data/figs/<arxiv_id>/`, calls a model API with the poster prompt, and writes
poster images or HTML into `data/posters/current/`.

The current repository already supports static poster display through
`data/posters/<week>/manifest.json`; the missing piece is the generator script.

## Rollback

Recommended tags:

```bash
git tag server-current-2026-08-22 0eb72c2
git tag pages-v1
```

GitHub Pages can be rolled back by redeploying a previous commit or tag.
