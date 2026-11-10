# -*- coding: utf-8 -*-
"""Step 3: Pillow verification, crop math, atomic output for render_check.py."""
from __future__ import annotations

import pathlib
import shutil
import sys
import unittest

from PIL import Image, ImageDraw

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

import render_check  # noqa: E402

TMP = ROOT / ".out" / "render-test"


def make_source(path, scale=1):
    size = 100 * scale
    image = Image.new("RGB", (size, size), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle([10 * scale, 10 * scale, 30 * scale - 1, 30 * scale - 1], fill=(255, 0, 0))
    draw.rectangle([60 * scale, 60 * scale, 80 * scale - 1, 80 * scale - 1], fill=(0, 0, 255))
    image.save(path, format="PNG")
    return path


class RenderCheckTest(unittest.TestCase):
    def setUp(self):
        if TMP.exists():
            shutil.rmtree(TMP)
        TMP.mkdir(parents=True)
        self.source = make_source(TMP / "source-s1.png", 1)
        self.source2 = make_source(TMP / "source-s2.png", 2)

    def test_crop_at_scale_one(self):
        final = TMP / "crop-s1.png"
        result = render_check.run({
            "image": str(self.source), "out": str(final), "scale": 1,
            "crop": {"x": 10, "y": 10, "w": 20, "h": 20},
        })
        self.assertTrue(result["ok"], result.get("errors"))
        self.assertEqual((20, 20), (result["width"], result["height"]))
        self.assertEqual({"x": 10, "y": 10, "w": 20, "h": 20}, result["crop"])
        pixel = Image.open(final).convert("RGB").getpixel((10, 10))
        self.assertEqual((255, 0, 0), pixel)
        self.assertFalse(list(TMP.glob("*.tmp-*")))

    def test_crop_at_scale_two(self):
        final = TMP / "crop-s2.png"
        result = render_check.run({
            "image": str(self.source2), "out": str(final), "scale": 2,
            "crop": {"x": 10, "y": 10, "w": 20, "h": 20},
        })
        self.assertTrue(result["ok"], result.get("errors"))
        self.assertEqual((40, 40), (result["width"], result["height"]))
        self.assertEqual({"x": 20, "y": 20, "w": 40, "h": 40}, result["crop"])
        pixel = Image.open(final).convert("RGB").getpixel((20, 20))
        self.assertEqual((255, 0, 0), pixel)

    def test_no_crop_copies_the_image(self):
        final = TMP / "copy.png"
        result = render_check.run({
            "image": str(self.source), "out": str(final), "scale": 2, "crop": None,
        })
        self.assertTrue(result["ok"], result.get("errors"))
        self.assertEqual((100, 100), (result["width"], result["height"]))
        self.assertEqual(self.source.read_bytes(), final.read_bytes())

    def test_crop_outside_image_fails(self):
        result = render_check.run({
            "image": str(self.source), "out": str(TMP / "outside.png"), "scale": 1,
            "crop": {"x": 500, "y": 500, "w": 20, "h": 20},
        })
        self.assertFalse(result["ok"])
        self.assertEqual("E_RENDER_FAILED", result["errors"][0]["code"])
        self.assertFalse((TMP / "outside.png").exists())

    def test_invalid_crop_size_is_argument_error(self):
        result = render_check.run({
            "image": str(self.source), "out": str(TMP / "bad.png"), "scale": 1,
            "crop": {"x": 10, "y": 10, "w": 0, "h": 20},
        })
        self.assertFalse(result["ok"])
        self.assertEqual("E_ARG_INVALID", result["errors"][0]["code"])

    def test_unreadable_image(self):
        broken = TMP / "broken.png"
        broken.write_bytes(b"not a png")
        result = render_check.run({
            "image": str(broken), "out": str(TMP / "out.png"), "scale": 1, "crop": None,
        })
        self.assertFalse(result["ok"])
        self.assertEqual("E_RENDER_FAILED", result["errors"][0]["code"])
        self.assertFalse((TMP / "out.png").exists())


if __name__ == "__main__":
    unittest.main()
