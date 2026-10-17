#!/usr/bin/env python3
"""Register poster images uploaded to the repository."""

from __future__ import annotations

import argparse
import json
import re
import shutil
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


def display_settings_path(data_dir: Path = DATA_DIR) -> Path:
    return data_dir / "posters" / "manual" / "display.json"


def include_generated_posters(data_dir: Path = DATA_DIR) -> bool:
    path = display_settings_path(data_dir)
    if not path.exists():
        return True
    value = json.loads(path.read_text(encoding="utf-8")).get("include_generated")
    if not isinstance(value, bool):
        raise ValueError(f"Invalid display settings: {path}")
    return value


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


def generated_posters(data_dir: Path = DATA_DIR) -> list[dict[str, str]]:
    current_dir = data_dir / "posters" / "current"
    images = []
    for path in sorted(current_dir.glob("*")):
        if not path.is_file() or path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
            continue
        match = re.search(r"\d{4}\.\d{4,5}", path.name)
        item = {"name": path.name, "url": f"data/posters/current/{path.name}"}
        if match:
            arxiv_id = match.group()
            item["arxiv_id"] = arxiv_id
            if (data_dir / "generated_posters" / arxiv_id / "poster.html").exists():
                item["poster_url"] = f"data/generated_posters/{arxiv_id}/poster.html"
        images.append(item)
    return images


def refresh_current_manifest(data_dir: Path = DATA_DIR) -> None:
    generated = generated_posters(data_dir) if include_generated_posters(data_dir) else []
    write_images(current_manifest_path(data_dir), merge_manual_posters(generated, load_manual_posters(data_dir)))


def available_images(data_dir: Path = DATA_DIR) -> list[str]:
    manual_dir = data_dir / "posters" / "manual"
    return sorted(
        path.name for path in manual_dir.iterdir()
        if path.is_file() and path.suffix.lower() in {".png", ".jpg", ".jpeg"}
    ) if manual_dir.exists() else []


def prepare_image(filename: str, data_dir: Path = DATA_DIR) -> Path:
    if Path(filename).name != filename or Path(filename).suffix.lower() not in {".png", ".jpg", ".jpeg"}:
        raise ValueError("Enter a PNG or JPG filename from data/posters/manual, without a directory")

    image_path = data_dir / "posters" / "manual" / filename
    if not image_path.is_file():
        raise FileNotFoundError(f"Upload the image first: {image_path}")
    with image_path.open("rb") as image:
        header = image.read(24)
    if len(header) >= 24 and header.startswith(PNG_SIGNATURE) and header[12:16] == b"IHDR":
        width, height = struct.unpack(">II", header[16:24])
        if width == 0 or height == 0:
            raise ValueError(f"PNG has invalid dimensions: {image_path}")
        actual_suffix = ".png"
    elif header.startswith(b"\xff\xd8\xff"):
        actual_suffix = ".jpg"
    else:
        raise ValueError(f"Unsupported image content: {image_path}")

    if image_path.suffix.lower() not in ({".jpg", ".jpeg"} if actual_suffix == ".jpg" else {".png"}):
        corrected_path = image_path.with_suffix(actual_suffix)
        if corrected_path.exists() and corrected_path.read_bytes() != image_path.read_bytes():
            raise ValueError(f"Corrected filename already exists with different content: {corrected_path}")
        shutil.copy2(image_path, corrected_path)
        image_path = corrected_path
    return image_path


def poster_item(arxiv_id: str, image_path: Path) -> dict[str, str]:
    if not ARXIV_ID_RE.fullmatch(arxiv_id):
        raise ValueError("arXiv ID must look like 2609.30441")
    return {
        "name": image_path.name,
        "url": f"data/posters/manual/{image_path.name}",
        "arxiv_id": arxiv_id,
    }


def register_image(arxiv_id: str, filename: str, data_dir: Path = DATA_DIR) -> None:
    if not ARXIV_ID_RE.fullmatch(arxiv_id):
        raise ValueError("arXiv ID must look like 2609.30441")
    image_path = prepare_image(filename, data_dir)

    previous_manual = load_manual_posters(data_dir)
    item = poster_item(arxiv_id, image_path)
    manual = [item] + [old for old in previous_manual if old["arxiv_id"] != arxiv_id]
    write_images(manual_manifest_path(data_dir), manual)
    refresh_current_manifest(data_dir)
    print(f"Published arXiv:{arxiv_id} from {image_path}")


def select_images(filenames: str, include_generated: bool, data_dir: Path = DATA_DIR) -> None:
    names = [name.strip() for name in re.split(r"[,\n]", filenames) if name.strip()]
    if len(names) != len(set(names)):
        raise ValueError("The selection contains duplicate filenames")
    selected = []
    for name in names:
        image_path = prepare_image(name, data_dir)
        match = re.search(r"\d{4}\.\d{4,5}", image_path.name)
        if not match:
            raise ValueError(f"Filename must contain an arXiv ID: {image_path.name}")
        selected.append(poster_item(match.group(), image_path))
    write_images(manual_manifest_path(data_dir), selected)
    settings = display_settings_path(data_dir)
    settings.write_text(json.dumps({"include_generated": include_generated}, indent=2) + "\n", encoding="utf-8")
    refresh_current_manifest(data_dir)
    print(f"Selected {len(selected)} manual poster(s); include generated: {include_generated}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Publish an uploaded PNG or JPG in the poster carousel.")
    parser.add_argument("--arxiv-id", required=True)
    parser.add_argument("--filename", required=True)
    args = parser.parse_args()
    register_image(args.arxiv_id, args.filename)


if __name__ == "__main__":
    main()
