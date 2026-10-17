import struct
import tempfile
import unittest
from pathlib import Path

from build_static import build_poster_manifests
from tools.manual_posters import (
    current_manifest_path,
    include_generated_posters,
    load_manual_posters,
    merge_manual_posters,
    read_images,
    register_image,
    select_images,
    write_images,
)


class ManualPosterTests(unittest.TestCase):
    def test_publish_and_preserve_manual_override(self):
        with tempfile.TemporaryDirectory() as temp:
            data_dir = Path(temp)
            manual_dir = data_dir / "posters" / "manual"
            manual_dir.mkdir(parents=True)
            image_path = manual_dir / "2609.30441.png"
            image_path.write_bytes(
                b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR"
                + struct.pack(">II", 1920, 1080) + b"\x08\x02\x00\x00\x00"
            )
            generated = [
                {"name": "01_2609.30441.png", "arxiv_id": "2609.30441", "url": "data/posters/current/01_2609.30441.png"},
                {"name": "02_2609.33198.png", "arxiv_id": "2609.33198", "url": "data/posters/current/02_2609.33198.png"},
            ]
            current_dir = data_dir / "posters" / "current"
            current_dir.mkdir(parents=True)
            for item in generated:
                (current_dir / Path(item["url"]).name).write_bytes(b"preview")
            write_images(current_manifest_path(data_dir), generated)

            register_image("2609.30441", image_path.name, data_dir)
            manual = load_manual_posters(data_dir)
            current = read_images(current_manifest_path(data_dir))
            build_poster_manifests(data_dir)
            self.assertEqual(read_images(current_manifest_path(data_dir)), current)
            self.assertEqual(current, merge_manual_posters(generated, manual))
            self.assertEqual([item["arxiv_id"] for item in current], ["2609.30441", "2609.33198"])
            self.assertEqual(current[0]["url"], "data/posters/manual/2609.30441.png")

            register_image("2609.30441", image_path.name, data_dir)
            self.assertEqual(read_images(current_manifest_path(data_dir)), current)
            self.assertEqual(len(load_manual_posters(data_dir)), 1)

            next_week = [{"arxiv_id": "2610.12345", "url": "data/posters/current/01_2610.12345.png"}]
            self.assertEqual(merge_manual_posters(next_week, manual)[0], manual[0])

            select_images("", True, data_dir)
            self.assertEqual(load_manual_posters(data_dir), [])
            self.assertEqual(read_images(current_manifest_path(data_dir)), generated)

    def test_reject_missing_or_non_png(self):
        with tempfile.TemporaryDirectory() as temp:
            data_dir = Path(temp)
            with self.assertRaises(FileNotFoundError):
                register_image("2609.30441", "missing.png", data_dir)
            with self.assertRaises(ValueError):
                register_image("2609.30441", "../poster.png", data_dir)
            image_path = data_dir / "posters" / "manual" / "fake.png"
            image_path.parent.mkdir(parents=True)
            image_path.write_text("not a png")
            with self.assertRaises(ValueError):
                register_image("2609.30441", image_path.name, data_dir)
            self.assertFalse((image_path.parent / "manifest.json").exists())

    def test_png_with_jpg_extension_gets_correct_url(self):
        with tempfile.TemporaryDirectory() as temp:
            data_dir = Path(temp)
            manual_dir = data_dir / "posters" / "manual"
            manual_dir.mkdir(parents=True)
            uploaded = manual_dir / "2610.17559.jpg"
            uploaded.write_bytes(
                b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR"
                + struct.pack(">II", 1920, 1080) + b"\x08\x02\x00\x00\x00"
            )

            register_image("2610.17559", uploaded.name, data_dir)

            self.assertEqual((manual_dir / "2610.17559.png").read_bytes(), uploaded.read_bytes())
            self.assertEqual(load_manual_posters(data_dir)[0]["url"], "data/posters/manual/2610.17559.png")

    def test_multiple_selection_and_generated_toggle(self):
        with tempfile.TemporaryDirectory() as temp:
            data_dir = Path(temp)
            manual_dir = data_dir / "posters" / "manual"
            current_dir = data_dir / "posters" / "current"
            manual_dir.mkdir(parents=True)
            current_dir.mkdir(parents=True)
            image_bytes = (
                b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR"
                + struct.pack(">II", 1920, 1080) + b"\x08\x02\x00\x00\x00"
            )
            for name in ("2610.11111.png", "2610.22222.png"):
                (manual_dir / name).write_bytes(image_bytes)
            (current_dir / "01_2610.33333.png").write_bytes(b"preview")

            select_images("2610.11111.png, 2610.22222.png", False, data_dir)
            self.assertFalse(include_generated_posters(data_dir))
            self.assertEqual(
                [item["arxiv_id"] for item in read_images(current_manifest_path(data_dir))],
                ["2610.11111", "2610.22222"],
            )
            select_images("2610.22222.png", True, data_dir)
            self.assertEqual(
                [item["arxiv_id"] for item in read_images(current_manifest_path(data_dir))],
                ["2610.22222", "2610.33333"],
            )
            self.assertTrue((manual_dir / "2610.11111.png").exists())


if __name__ == "__main__":
    unittest.main()
