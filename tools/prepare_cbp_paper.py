#!/usr/bin/env python3
"""Prepare existing coffee-break data as a cbp paper directory."""

from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def latest_arxiv_id() -> str:
    papers = json.loads(read_text(DATA_DIR / "jc_papers.json"))
    if not papers:
        raise SystemExit("data/jc_papers.json is empty.")
    return papers[0]["arxiv_id"]


def clean_inline(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\*\*", "", text)
    text = re.sub(r"\\(?:vspace|hspace)\{[^}]*\}", " ", text)
    text = re.sub(r"(?<![\w.])-?\d+(?:\.\d+)?\s*cm\b", " ", text)
    text = text.replace(r"\Insights", " Insights")
    text = text.replace(r"\&", "&")
    text = re.sub(r":(?=\S)", ": ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def extract_block(raw: str, block_id: str) -> str:
    pattern = re.compile(
        rf'<div id="{re.escape(block_id)}"[^>]*>(.*?)</div>',
        re.DOTALL | re.IGNORECASE,
    )
    match = pattern.search(raw)
    return match.group(1).strip() if match else ""


def extract_title(raw: str) -> str:
    title_block = extract_block(raw, "title")
    match = re.search(r"^\s*#\s+(.+)$", title_block, re.MULTILINE)
    return clean_inline(match.group(1) if match else "Untitled paper")


def extract_abstract(raw: str) -> str:
    abstract = extract_block(raw, "abstract")
    abstract = re.sub(r"^\*\*Abstract:\*\*\s*", "", abstract.strip())
    return clean_inline(abstract)


def extract_figures(raw: str) -> list[dict[str, str]]:
    figures: list[dict[str, str]] = []
    pattern = re.compile(
        r'<div id="div_fig\d+"[^>]*>.*?'
        r'<img\s+src="(?P<src>[^"]+)"[^>]*>.*?'
        r'\*\*Figure\s+(?P<number>[^.]+)\.\s*-\*\*\s*(?P<caption>.*?)'
        r"</div>",
        re.DOTALL | re.IGNORECASE,
    )
    for match in pattern.finditer(raw):
        src = match.group("src").strip()
        rel = src.lstrip("/")
        path = BASE_DIR / rel
        if not path.exists():
            continue
        figures.append(
            {
                "number": clean_inline(match.group("number")),
                "caption": clean_inline(match.group("caption")),
                "source": str(path),
                "filename": path.name,
            }
        )
    return figures


def prepare_paper(arxiv_id: str, output_dir: str = "cbp_work") -> Path:
    raw_path = DATA_DIR / f"{arxiv_id}.md"
    if not raw_path.exists():
        raise FileNotFoundError(f"Cannot find {raw_path}")

    raw = read_text(raw_path)
    title = extract_title(raw)
    abstract = extract_abstract(raw)
    figures = extract_figures(raw)
    if not figures:
        raise ValueError(f"No figures found in {raw_path}")

    paper_dir = (BASE_DIR / output_dir / arxiv_id).resolve()
    image_dir = paper_dir / "images"
    image_dir.mkdir(parents=True, exist_ok=True)

    for fig in figures:
        shutil.copy2(fig["source"], image_dir / fig["filename"])

    figure_md = "\n\n".join(
        f"![Figure {fig['number']}](images/{fig['filename']})\n\n"
        f"Figure {fig['number']}. {fig['caption']}"
        for fig in figures
    )
    paper_md = f"""# {title}

[arXiv:{arxiv_id}](https://arxiv.org/abs/{arxiv_id})

## Abstract

{abstract}

## Figures

{figure_md}
"""
    (paper_dir / "paper.md").write_text(paper_md, encoding="utf-8")
    (paper_dir / "source.json").write_text(
        json.dumps(
            {
                "arxiv_id": arxiv_id,
                "url": f"https://arxiv.org/abs/{arxiv_id}",
                "source_markdown": str(raw_path),
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (paper_dir / "figures.json").write_text(
        json.dumps(figures, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return paper_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare a cbp paper directory from data/<arxiv_id>.md.")
    parser.add_argument("--arxiv-id", default="", help="Defaults to first paper in data/jc_papers.json.")
    parser.add_argument("--output-dir", default="cbp_work", help="Output root for cbp paper directories.")
    args = parser.parse_args()

    arxiv_id = args.arxiv_id or latest_arxiv_id()
    paper_dir = prepare_paper(arxiv_id, args.output_dir)
    print(paper_dir)


if __name__ == "__main__":
    main()
