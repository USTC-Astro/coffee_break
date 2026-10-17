#!/usr/bin/env python3
"""Register PNG posters uploaded to the repository."""

from __future__ import annotations

import argparse
import json
import re
import struct
from pathlib import Path


DATA_DIR = Path(__file__).resolve().parents[1] / "data"
ARXIV_ID_RE = re.compile(r"\d{4}\.\d{4,5}\Z")
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def read_images(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    images = data.get("images")
    if not isinstance(images, list):
        raise ValueError(f"Invalid poster manifest: {path}")
    return images


def manual_manifest_path(data_dir: Path = DATA_DIR) -> Path:
    return data_dir / "posters" / "manual" / "manifest.json"


def current_manifest_path(data_dir: Path = DATA_DIR) -> Path:
    return data_dir / "posters" / "current" / "manifest.json"


def load_manual_posters(data_dir: Path = DATA_DIR) -> list[dict[str, str]]:
    return read_images(manual_manifest_path(data_dir))


def merge_manual_posters(
    generated: list[dict[str, str]], manual: list[dict[str, str]]
) -> list[dict[str, str]]:
    manual_ids = {item["arxiv_id"] for item in manual}
    return manual + [item for item in generated if item.get("arxiv_id") not in manual_ids]


def write_images(path: Path, images: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"images": images}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def register_png(arxiv_id: str, filename: str, data_dir: Path = DATA_DIR) -> None:
    if not ARXIV_ID_RE.fullmatch(arxiv_id):
        raise ValueError("arXiv ID must look like 2609.30441")
    if Path(filename).name != filename or not filename.lower().endswith(".png"):
        raise ValueError("Enter a PNG filename from data/posters/manual, without a directory")

    image_path = data_dir / "posters" / "manual" / filename
    if not image_path.is_file():
        raise FileNotFoundError(f"Upload the PNG first: {image_path}")
    with image_path.open("rb") as image:
        header = image.read(24)
    if len(header) < 24 or not header.startswith(PNG_SIGNATURE) or header[12:16] != b"IHDR":
        raise ValueError(f"Not a valid PNG: {image_path}")
    width, height = struct.unpack(">II", header[16:24])
    if width == 0 or height == 0:
        raise ValueError(f"PNG has invalid dimensions: {image_path}")

    previous_manual = load_manual_posters(data_dir)
    current_path = current_manifest_path(data_dir)
    previous_urls = {item["url"] for item in previous_manual}
    generated = [item for item in read_images(current_path) if item.get("url") not in previous_urls]
    item = {
        "name": filename,
        "url": f"data/posters/manual/{filename}",
        "arxiv_id": arxiv_id,
    }
    manual = [item] + [old for old in previous_manual if old["arxiv_id"] != arxiv_id]
    write_images(manual_manifest_path(data_dir), manual)
    write_images(current_path, merge_manual_posters(generated, manual))
    print(f"Published arXiv:{arxiv_id} from {image_path} ({width}x{height})")


def main() -> None:
    parser = argparse.ArgumentParser(description="Publish an uploaded PNG in the poster carousel.")
    parser.add_argument("--arxiv-id", required=True)
    parser.add_argument("--filename", required=True)
    args = parser.parse_args()
    register_png(args.arxiv_id, args.filename)


if __name__ == "__main__":
    main()
