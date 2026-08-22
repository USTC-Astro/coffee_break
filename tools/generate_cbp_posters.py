#!/usr/bin/env python3
"""Generate cbp-checked coffee-break posters for the current agenda."""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from prepare_cbp_paper import DATA_DIR, clean_inline, extract_abstract, extract_title, prepare_paper, read_text


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_MODEL = "deepseek-v4-flash"


def current_papers() -> list[dict[str, Any]]:
    papers_path = DATA_DIR / "jc_papers.json"
    if not papers_path.exists():
        return []
    return json.loads(read_text(papers_path))


def run(cmd: list[str], cwd: Path = BASE_DIR) -> None:
    subprocess.run(cmd, cwd=cwd, check=True)


def call_deepseek(api_key: str, model: str, messages: list[dict[str, str]]) -> dict[str, Any]:
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "temperature": 0.35,
        "thinking": {"type": "disabled"},
        "response_format": {"type": "json_object"},
    }
    request = urllib.request.Request(
        "https://api.deepseek.com/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"DeepSeek API error {exc.code}: {body}") from exc
    content = data["choices"][0]["message"]["content"]
    return json.loads(content)


def make_messages(arxiv_id: str, title: str, abstract: str, figures: list[dict[str, str]]) -> list[dict[str, str]]:
    figure_text = "\n".join(
        f"- idx {i}: Figure {fig['number']}: {fig['caption'][:850]}"
        for i, fig in enumerate(figures)
    )
    system = (
        "You write concise astronomy coffee-break poster copy for a broad astro audience. "
        "Return JSON only. Do not write HTML. Prefer an interesting scientific take-away over a paper-title restatement."
    )
    user = f"""
Create the editorial content for a one-screen 16:9 coffee-break poster.

arXiv: {arxiv_id}
Paper title:
{title}

Abstract:
{abstract}

Available figures:
{figure_text}

The poster sections are:
1. Background
2. Knowledge gap
3. What this paper is selling
4. Key results to remember

Hard limits:
- headline: 8 words maximum, claim-like.
- subtitle: 16 words maximum.
- paper_meta: 12 words maximum.
- background: 2 sentences maximum, 42 words maximum.
- knowledge_gap: 22 words maximum.
- selling: 2 sentences maximum, 48 words maximum.
- key_results: exactly 3 bullets, each 15 words maximum.
- figure_indices: choose exactly 2 figure idx values. Pick only figures that carry the story.
- figure_captions: each 18 words maximum and interpretive.

Return exactly this JSON schema:
{{
  "headline": "...",
  "subtitle": "...",
  "paper_meta": "...",
  "background": "...",
  "knowledge_gap": "...",
  "selling": "...",
  "key_results": ["...", "...", "..."],
  "figure_indices": [0, 1],
  "figure_captions": {{"0": "...", "1": "..."}}
}}
"""
    return [{"role": "system", "content": system}, {"role": "user", "content": textwrap.dedent(user).strip()}]


def fallback_content(arxiv_id: str, title: str) -> dict[str, Any]:
    return {
        "headline": "This paper needs a poster story",
        "subtitle": "Generated without an API key; replace with model-written copy.",
        "paper_meta": f"arXiv {arxiv_id}",
        "background": clean_inline(title)[:150],
        "knowledge_gap": "What is the key missing piece this paper addresses?",
        "selling": "This dry run validates the cbp layout, figure pipeline, and export paths.",
        "key_results": [
            "The paper directory was prepared.",
            "The cbp scaffold/check/render pipeline ran.",
            "Replace this copy with DeepSeek output.",
        ],
        "figure_indices": [0, 1],
        "figure_captions": {"0": "Main visual evidence.", "1": "Supporting context."},
    }


def coerce_indices(raw: Any, total: int) -> list[int]:
    indices: list[int] = []
    for value in raw if isinstance(raw, list) else []:
        try:
            idx = int(value)
        except (TypeError, ValueError):
            continue
        if 0 <= idx < total and idx not in indices:
            indices.append(idx)
    if not indices:
        indices = list(range(min(2, total)))
    while len(indices) < min(2, total):
        for idx in range(total):
            if idx not in indices:
                indices.append(idx)
                break
    return indices[:2]


def esc(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def replace_once(text: str, pattern: str, replacement: str, *, flags: int = 0) -> str:
    new, count = re.subn(pattern, replacement, text, count=1, flags=flags)
    if count != 1:
        raise RuntimeError(f"Expected one match for pattern: {pattern}")
    return new


def apply_coffee_theme(doc: str) -> str:
    replacements = {
        "--ink: #17212b;": "--ink: #171717;",
        "--muted: #4c5564;": "--muted: #5f5a52;",
        "--paper: #f8f8fc;": "--paper: #f8f4eb;\n      --page-bg: #e9e2d7;\n      --surface: #fffdf8;",
        "--line: rgba(150, 146, 175, 0.26);": "--line: #d8d0c2;\n      --line-strong: #c8c2b5;",
        "--accent: rgba(150, 146, 175, 0.88);": "--accent: #155a8a;",
        "--accent-2: rgba(150, 146, 175, 0.62);": "--accent-2: #a94f2b;",
        "--section-bg-1: rgba(146, 142, 170, 0.94);\n      --section-bg-2: rgba(152, 148, 176, 0.90);\n      --section-bg-3: rgba(158, 154, 184, 0.86);\n      --highlight: rgba(150, 146, 175, 0.14);": "--highlight: rgba(169, 79, 43, 0.08);",
        "--title-font: Helvetica, Arial, sans-serif;": '--title-font: Georgia, "Times New Roman", serif;',
        "--paper-font: Helvetica, Arial, sans-serif;": '--paper-font: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;',
        "--text-font: Helvetica, Arial, sans-serif;": '--text-font: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;',
        "--body-gap: 34px;": "--body-gap: 28px;",
        "--text-fr: 0.9fr;": "--text-fr: 1.15fr;",
        "--figure-fr: 1.85fr;": "--figure-fr: 1.55fr;",
        "--result-text-size: 17px;": "--result-text-size: 22px;",
        "background: var(--paper);\n      color: var(--ink);": "background: var(--page-bg);\n      color: var(--ink);",
        "background:\n        linear-gradient(135deg, rgba(150, 146, 175, 0.12), transparent 38%),\n        radial-gradient(circle at 85% 6%, rgba(150, 146, 175, 0.08), transparent 22%),\n        linear-gradient(180deg, rgba(150, 146, 175, 0.14) 0%, rgba(150, 146, 175, 0.05) 58%, rgba(150, 146, 175, 0.12) 100%),\n        var(--paper);": "background: var(--paper);",
        "transform-origin: top left;": "transform-origin: top left;\n      border: 1px solid var(--line-strong);\n      box-shadow: 0 18px 50px rgba(0, 0, 0, 0.08);",
        "height: 10px;\n      border-radius: 999px;\n      background: linear-gradient(90deg, rgba(255, 255, 255, 0.92), rgba(255, 255, 255, 0.42) 38%, rgba(255, 255, 255, 0.92));\n      box-shadow: 0 5px 18px rgba(44, 35, 128, 0.1);": "height: 4px;\n      border-radius: 0;\n      background: var(--ink);\n      box-shadow: none;",
        "font-size: 52px;": "font-size: 60px;",
        "color: rgba(23, 33, 43, 0.9);": "color: var(--muted);",
        "color: rgba(23, 33, 43, 0.82);": "color: var(--muted);",
        "border: 1px solid rgba(150, 146, 175, 0.38);\n      border-radius: 8px;\n      background: rgba(255, 255, 255, 0.86);": "border: 1px solid var(--line-strong);\n      border-radius: 6px;\n      background: var(--surface);",
        "gap: 20px;": "gap: 18px;",
        "background: transparent;\n      border: 2px solid var(--line);\n      border-radius: 18px;": "background: transparent;\n      border: 0;\n      border-top: 2px solid var(--line);\n      border-radius: 0;",
        "padding: 11px 22px 12px;\n      color: #ffffff;": "padding: 14px 0 8px;\n      color: var(--accent);",
        "text-transform: uppercase;\n      letter-spacing: 0.02em;": "text-transform: none;\n      letter-spacing: 0;\n      background: transparent;\n      border-bottom: 0;",
        "background: linear-gradient(90deg, var(--section-bg-1), rgba(153, 149, 178, 0.82));": "background: transparent;",
        "background: linear-gradient(90deg, var(--section-bg-2), rgba(159, 155, 183, 0.80));": "background: transparent;",
        "background: linear-gradient(90deg, var(--section-bg-3), rgba(165, 161, 188, 0.78));": "background: transparent;",
        "padding: 20px 23px 22px;": "padding: 0 0 0;",
        "margin: 0 23px 20px;": "margin: 14px 0 0;",
        "border-radius: 14px;": "border-radius: 6px;",
        "border-left: 6px solid var(--accent);": "border-left: 6px solid var(--accent-2);",
        "color: #2f2a7b;": "color: var(--ink);",
        "padding-left: 48px;": "padding-left: 31px;",
        "padding-top: 16px;\n      padding-bottom: 16px;": "padding-top: 0;\n      padding-bottom: 0;",
        "background: transparent;\n      border: 2px solid rgba(150, 146, 175, 0.24);\n      border-radius: 18px;": "background: var(--surface);\n      border: 1px solid var(--line);\n      border-radius: 6px;",
        "padding: 12px;\n      gap: 8px;": "padding: 8px;\n      gap: 8px;",
        "color: rgba(76, 85, 100, 0.92);": "color: var(--muted);",
    }
    for old, new in replacements.items():
        doc = doc.replace(old, new)
    return doc


def edit_poster(paper_dir: Path, arxiv_id: str, paper_title: str, content: dict[str, Any], figures: list[dict[str, str]]) -> None:
    poster_path = paper_dir / "poster.html"
    doc = poster_path.read_text(encoding="utf-8")
    doc = apply_coffee_theme(doc)

    selected = coerce_indices(content.get("figure_indices"), len(figures))
    captions = content.get("figure_captions") if isinstance(content.get("figure_captions"), dict) else {}
    fig_html = []
    for idx in selected:
        fig = figures[idx]
        caption = captions.get(str(idx)) or fig.get("caption") or f"Figure {fig['number']}"
        fig_html.append(
            f'''<figure class="figure-card" data-role="figure-card">
  <img src="assets/{esc(fig["filename"])}" alt="Figure {esc(fig["number"])}">
  <figcaption><strong>Fig. {esc(fig["number"])}.</strong> {esc(caption)}</figcaption>
</figure>'''
        )

    key_results = content.get("key_results") if isinstance(content.get("key_results"), list) else []
    key_results_html = "".join(f"<li>{esc(item)}</li>" for item in key_results[:3])

    doc = replace_once(doc, r"<title>.*?</title>", f"<title>{esc(content.get('headline') or paper_title)}</title>", flags=re.DOTALL)
    doc = replace_once(doc, r'<h1 class="headline" data-role="headline">.*?</h1>', f'<h1 class="headline" data-role="headline">{esc(content.get("headline"))}</h1>', flags=re.DOTALL)
    doc = replace_once(doc, r'<p class="subtitle">.*?</p>', f'<p class="subtitle">{esc(content.get("subtitle"))}</p>', flags=re.DOTALL)
    doc = replace_once(doc, r"<strong>.*?</strong>", f"<strong>{esc(content.get('paper_meta') or f'arXiv {arxiv_id}')}</strong>", flags=re.DOTALL)
    doc = replace_once(doc, r'<section class="text-card text-card-background">\s*<h2>Background</h2>\s*<p>.*?</p>\s*<div class="knowledge-gap">.*?</div>\s*</section>', f'''<section class="text-card text-card-background">
            <h2>Background</h2>
            <p>{esc(content.get("background"))}</p>
            <div class="knowledge-gap">{esc(content.get("knowledge_gap"))}</div>
          </section>''', flags=re.DOTALL)
    doc = replace_once(doc, r'<section class="text-card text-card-selling">\s*<h2>What this paper is selling</h2>\s*<p>.*?</p>\s*</section>', f'''<section class="text-card text-card-selling">
            <h2>What this paper is selling</h2>
            <p>{esc(content.get("selling"))}</p>
          </section>''', flags=re.DOTALL)
    doc = replace_once(doc, r'<section class="text-card text-card-results">\s*<h2>Key results to remember</h2>\s*<ul>.*?</ul>\s*</section>', f'''<section class="text-card text-card-results">
            <h2>Key results to remember</h2>
            <ul>{key_results_html}</ul>
          </section>''', flags=re.DOTALL)
    doc = replace_once(doc, r'<section class="figure-panel" data-role="figure-panel"[^>]*>.*?</section>', f'''<section class="figure-panel" data-role="figure-panel" data-layout="hero-1">
          {"".join(fig_html)}
        </section>''', flags=re.DOTALL)
    poster_path.write_text(doc, encoding="utf-8")


def publish_outputs(paper_dir: Path, arxiv_id: str, rank: int) -> dict[str, str]:
    generated_root = DATA_DIR / "generated_posters" / arxiv_id
    if generated_root.exists():
        shutil.rmtree(generated_root)
    shutil.copytree(paper_dir / "assets", generated_root / "assets")
    for name in ["poster.html", "poster_preview.png", "poster.pdf", "layout.json"]:
        src = paper_dir / name
        if src.exists():
            shutil.copy2(src, generated_root / name)

    carousel_dir = DATA_DIR / "posters" / "current"
    carousel_dir.mkdir(parents=True, exist_ok=True)
    preview_name = f"{rank:02d}_{arxiv_id}.png"
    shutil.copy2(paper_dir / "poster_preview.png", carousel_dir / preview_name)
    return {
        "name": preview_name,
        "url": f"data/posters/current/{preview_name}",
        "poster_url": f"data/generated_posters/{arxiv_id}/poster.html",
        "arxiv_id": arxiv_id,
    }


def generate_one(paper: dict[str, Any], args: argparse.Namespace, api_key: str | None, rank: int) -> dict[str, str] | None:
    arxiv_id = paper["arxiv_id"]
    md_path = DATA_DIR / f"{arxiv_id}.md"
    if not md_path.exists():
        print(f"skip {arxiv_id}: missing {md_path}", file=sys.stderr)
        return None
    raw = read_text(md_path)
    title = extract_title(raw)
    abstract = extract_abstract(raw)
    paper_dir = prepare_paper(arxiv_id, args.workdir)
    figures = json.loads((paper_dir / "figures.json").read_text(encoding="utf-8"))
    if len(figures) < 1:
        print(f"skip {arxiv_id}: no figures", file=sys.stderr)
        return None

    if api_key and not args.dry_run:
        content = call_deepseek(api_key, args.model, make_messages(arxiv_id, title, abstract, figures))
    else:
        content = fallback_content(arxiv_id, title)

    figure_count = min(2, max(1, len(figures)))
    run(["cbp", "scaffold", str(paper_dir), "--figure-count", str(figure_count), "--overwrite"])
    edit_poster(paper_dir, arxiv_id, title, content, figures)
    run(["cbp", "check", str(paper_dir / "poster.html"), "--json-out", str(paper_dir / "layout.json")])
    run(["cbp", "render", str(paper_dir / "poster.html"), "--png", "--pdf"])
    return publish_outputs(paper_dir, arxiv_id, rank)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate cbp posters for current agenda papers.")
    parser.add_argument("--all-current", action="store_true", help="Generate all papers from data/jc_papers.json.")
    parser.add_argument("--arxiv-id", default="", help="Generate one arXiv id.")
    parser.add_argument("--workdir", default="cbp_work", help="Local cbp work directory.")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--dry-run", action="store_true", help="Skip DeepSeek and use placeholder copy.")
    args = parser.parse_args()

    papers = current_papers()
    if args.arxiv_id:
        papers = [paper for paper in papers if paper.get("arxiv_id") == args.arxiv_id] or [{"arxiv_id": args.arxiv_id, "votes": 0}]
    elif not args.all_current:
        papers = papers[:1]
    if not papers:
        raise SystemExit("No papers to generate.")

    carousel_dir = DATA_DIR / "posters" / "current"
    if carousel_dir.exists():
        shutil.rmtree(carousel_dir)
    carousel_dir.mkdir(parents=True, exist_ok=True)

    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not api_key and not args.dry_run:
        raise SystemExit("Set DEEPSEEK_API_KEY or run with --dry-run.")

    manifest_items = []
    for rank, paper in enumerate(papers, start=1):
        item = generate_one(paper, args, api_key, rank)
        if item:
            manifest_items.append(item)

    (carousel_dir / "manifest.json").write_text(
        json.dumps({"images": manifest_items}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"Generated {len(manifest_items)} poster(s).")


if __name__ == "__main__":
    main()
