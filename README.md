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

## Automatic agenda refresh

Configure the repository secret:

- `BENTY_PASSWORD`

Then run `.github/workflows/update-agenda.yml` manually or on its weekly
schedule. It refreshes `data/`, rebuilds static manifests, and commits changed
data back to the repository.

## Rollback

Recommended tags:

```bash
git tag server-current-2026-08-22 0eb72c2
git tag pages-v1
```

GitHub Pages can be rolled back by redeploying a previous commit or tag.
