import struct
import tempfile
import unittest
from pathlib import Path

from build_static import build_poster_manifests
from tools.manual_posters import (
    current_manifest_path,
    load_manual_posters,
    merge_manual_posters,
    read_images,
    register_png,
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
                {"arxiv_id": "2609.30441", "url": "data/posters/current/01_2609.30441.png"},
                {"arxiv_id": "2609.33198", "url": "data/posters/current/02_2609.33198.png"},
            ]
            write_images(current_manifest_path(data_dir), generated)

            register_png("2609.30441", image_path.name, data_dir)
            manual = load_manual_posters(data_dir)
            current = read_images(current_manifest_path(data_dir))
            build_poster_manifests(data_dir)
            self.assertEqual(read_images(current_manifest_path(data_dir)), current)
            self.assertEqual(current, merge_manual_posters(generated, manual))
            self.assertEqual([item["arxiv_id"] for item in current], ["2609.30441", "2609.33198"])
            self.assertEqual(current[0]["url"], "data/posters/manual/2609.30441.png")

            register_png("2609.30441", image_path.name, data_dir)
            self.assertEqual(read_images(current_manifest_path(data_dir)), current)
            self.assertEqual(len(load_manual_posters(data_dir)), 1)

            next_week = [{"arxiv_id": "2610.12345", "url": "data/posters/current/01_2610.12345.png"}]
            self.assertEqual(merge_manual_posters(next_week, manual)[0], manual[0])

    def test_reject_missing_or_non_png(self):
        with tempfile.TemporaryDirectory() as temp:
            data_dir = Path(temp)
            with self.assertRaises(FileNotFoundError):
                register_png("2609.30441", "missing.png", data_dir)
            with self.assertRaises(ValueError):
                register_png("2609.30441", "../poster.png", data_dir)
            image_path = data_dir / "posters" / "manual" / "fake.png"
            image_path.parent.mkdir(parents=True)
            image_path.write_text("not a png")
            with self.assertRaises(ValueError):
                register_png("2609.30441", image_path.name, data_dir)
            self.assertFalse((image_path.parent / "manifest.json").exists())


if __name__ == "__main__":
    unittest.main()
