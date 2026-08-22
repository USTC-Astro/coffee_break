#!/usr/bin/env python3
"""Build a static GitHub Pages mirror of the coffee-break site."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
TMPL_DIR = BASE_DIR / "templates"

WEEK_RE = re.compile(r"^(current|\d{4}-\d{2}-\d{2}-[A-Za-z]{3})$")
POSTER_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg"}


def load_papers(json_path: Path | None = None) -> list[dict]:
    json_file = json_path or DATA_DIR / "jc_papers.json"
    if not json_file.exists():
        return []
    papers = json.loads(json_file.read_text(encoding="utf-8"))
    for paper in papers:
        paper["has_summary"] = (DATA_DIR / f"{paper['arxiv_id']}.md").exists()
        paper["has_poster"] = (DATA_DIR / "generated_posters" / paper["arxiv_id"] / "poster.html").exists()
        paper["has_phone_poster"] = (
            DATA_DIR / "generated_posters" / paper["arxiv_id"] / "phone" / "poster.html"
        ).exists()
    return papers


def get_mtime() -> str:
    json_file = DATA_DIR / "jc_papers.json"
    if not json_file.exists():
        return "未知"
    return datetime.fromtimestamp(json_file.stat().st_mtime).strftime("%Y-%m-%d %H:%M")


def ensure_clean_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True)


def page_prefix(path_from_site_root: str) -> str:
    parent = Path(path_from_site_root).parent
    depth = 0 if str(parent) == "." else len(parent.parts)
    return "./" if depth == 0 else "../" * depth


def rewrite_html(html: str, path_from_site_root: str, coffee_api_base: str = "") -> str:
    prefix = page_prefix(path_from_site_root)
    static_css = (
        "<style>"
        ".btn-discussed,.link-discussed,.rating-dropdown,.thoughts-section{display:none!important}"
        "</style>"
    )
    config_script = (
        "<script>"
        f"window.COFFEE_API_BASE = {json.dumps(coffee_api_base.rstrip('/'))};"
        "</script>"
    )
    html = html.replace("</head>", f"{static_css}\n</head>")
    html = html.replace("</head>", f"{config_script}\n</head>")
    replacements = [
        (r'href="/"', f'href="{prefix}index.html"'),
        (r'href="/coffee_vote"', f'href="{prefix}coffee_vote/index.html"'),
        (r'href="/poster"', f'href="{prefix}poster/index.html"'),
        (r"href='/coffee_vote'", f"href='{prefix}coffee_vote/index.html'"),
        (r"href='/poster'", f"href='{prefix}poster/index.html'"),
        (r"fetch('/ratings/' + arxivId)", "Promise.resolve({json: async () => ({ratings: {}})})"),
        (r"fetch('/thoughts/' + arxivId)", "Promise.resolve({json: async () => ({entries: []})})"),
    ]
    for old, new in replacements:
        html = html.replace(old, new)

    html = re.sub(
        r'href="/paper/(\d{4}\.\d{4,5})"',
        lambda m: f'href="{prefix}paper/{m.group(1)}/index.html"',
        html,
    )
    html = re.sub(
        r"location='/paper/(\d{4}\.\d{4,5})'",
        lambda m: f"location='{prefix}paper/{m.group(1)}/index.html'",
        html,
    )
    html = re.sub(
        r'href="/history/(\d{4}-\d{2}-\d{2})"',
        lambda m: f'href="{prefix}history/{m.group(1)}/index.html"',
        html,
    )
    html = html.replace('src="/data/', f'src="{prefix}data/')
    html = html.replace('href="/data/', f'href="{prefix}data/')
    html = html.replace("location='/data/", f"location='{prefix}data/")
    html = html.replace('fetch(\'/api/posters/\'', f"fetch('{prefix}api/posters-static-disabled/'")
    html = html.replace(
        "<script>\n// ── 固定海报目录 current",
        f'<script>\nwindow.STATIC_BASE = "{prefix}";\n// ── 固定海报目录 current',
    )
    return html


def write_page(site_dir: Path, path_from_site_root: str, html: str, coffee_api_base: str = "") -> None:
    out = site_dir / path_from_site_root
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(rewrite_html(html, path_from_site_root, coffee_api_base), encoding="utf-8")


def copy_static_data(site_dir: Path) -> None:
    dst = site_dir / "data"
    if dst.exists():
        shutil.rmtree(dst)

    def ignore(_dir: str, names: list[str]) -> set[str]:
        ignored = {".DS_Store", "debug_agenda.html", "coffee_votes", "thoughts"}
        ignored.update(name for name in names if name.startswith("_src_"))
        return ignored.intersection(names)

    shutil.copytree(DATA_DIR, dst, ignore=ignore)


def build_poster_manifests(data_root: Path) -> None:
    posters_root = data_root / "posters"
    if not posters_root.exists():
        return
    for week_dir in sorted(p for p in posters_root.iterdir() if p.is_dir()):
        if not WEEK_RE.match(week_dir.name):
            continue
        files = sorted(
            [
                p for p in week_dir.iterdir()
                if p.is_file()
                and p.suffix.lower() in POSTER_EXTS
                and not p.stem.endswith("_phone")
            ],
            key=lambda p: p.name.lower(),
        )
        images = []
        for p in files:
            item = {
                "name": p.name,
                "url": f"data/posters/{week_dir.name}/{p.name}",
            }
            match = re.search(r"(\d{4}\.\d{4,5})", p.name)
            if match and (data_root / "generated_posters" / match.group(1) / "poster.html").exists():
                item["arxiv_id"] = match.group(1)
                item["poster_url"] = f"data/generated_posters/{match.group(1)}/poster.html"
                phone_preview = p.with_name(f"{p.stem}_phone{p.suffix}")
                if phone_preview.exists():
                    item["phone_url"] = f"data/posters/{week_dir.name}/{phone_preview.name}"
                if (data_root / "generated_posters" / match.group(1) / "phone" / "poster.html").exists():
                    item["phone_poster_url"] = f"data/generated_posters/{match.group(1)}/phone/poster.html"
            images.append(item)
        manifest = {"images": images}
        (week_dir / "manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


def render_site(site_dir: Path, coffee_api_base: str = "") -> None:
    env = Environment(loader=FileSystemLoader(str(TMPL_DIR)), autoescape=False)
    hist_dir = DATA_DIR / "history"
    history_dates = sorted([p.stem for p in hist_dir.glob("*.json")], reverse=True) if hist_dir.exists() else []

    index_html = env.get_template("index.html").render(
        papers=load_papers(),
        updated=get_mtime(),
        history_dates=history_dates,
        current_date=None,
    )
    write_page(site_dir, "index.html", index_html, coffee_api_base)

    for date in history_dates:
        hist_file = hist_dir / f"{date}.json"
        history_html = env.get_template("index.html").render(
            papers=load_papers(hist_file),
            updated=date,
            history_dates=history_dates,
            current_date=date,
        )
        write_page(site_dir, f"history/{date}/index.html", history_html, coffee_api_base)

    current_papers = load_papers()
    all_papers_by_id = {p["arxiv_id"]: p for p in current_papers}
    for hist_file in hist_dir.glob("*.json") if hist_dir.exists() else []:
        for paper in load_papers(hist_file):
            all_papers_by_id.setdefault(paper["arxiv_id"], paper)

    write_page(site_dir, "poster/index.html", (TMPL_DIR / "poster.html").read_text(encoding="utf-8"), coffee_api_base)
    write_page(site_dir, "coffee_vote/index.html", (TMPL_DIR / "coffee_vote.html").read_text(encoding="utf-8"), coffee_api_base)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build static GitHub Pages site")
    parser.add_argument("--output-dir", default="site", help="Output directory")
    parser.add_argument(
        "--coffee-api-base",
        default=os.environ.get("COFFEE_API_BASE", ""),
        help="Optional Worker API base URL for static coffee voting",
    )
    args = parser.parse_args()

    site_dir = (BASE_DIR / args.output_dir).resolve()
    ensure_clean_dir(site_dir)
    copy_static_data(site_dir)
    build_poster_manifests(site_dir / "data")
    render_site(site_dir, args.coffee_api_base)
    print(f"Static site written to {site_dir}")


if __name__ == "__main__":
    main()
