# -*- coding: utf-8 -*-
"""Step 1 gate: CJK/ASCII width samples match an independent Pillow calculation
(tolerance 0.01px), plus wrapping/height sanity checks."""
from __future__ import annotations

import pathlib
import sys
import unittest

from PIL import Image, ImageDraw

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

import metrics  # noqa: E402

MSYH = r"C:\Windows\Fonts\msyh.ttc"
ARIAL = r"C:\Windows\Fonts\arial.ttf"
FONT_SIZE = 11

CJK_SAMPLES = [
    "中文标签测试",
    "落子与围困判定",
    "请把当前玩家选择的格子坐标",
]
ASCII_SAMPLES = [
    "ClickCell(x, y)",
    "RefreshBoard(board, scores)",
    "POST /login",
]


def independent_width(font, text):
    """Independent API path: ImageDraw.textlength (advance width) * 1.03."""
    image = Image.new("RGB", (8, 8), "white")
    return float(ImageDraw.Draw(image).textlength(text, font=font)) * metrics.WIDTH_FACTOR


class WidthSampleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cjk = metrics.load_font(MSYH, FONT_SIZE, index=0)
        cls.latin = metrics.load_font(ARIAL, FONT_SIZE)

    def _row(self, kind, font, text):
        measured = metrics.measure_text(font, text)
        reference = independent_width(font, text)
        return kind, text, measured, reference, abs(measured - reference)

    def test_width_samples(self):
        rows = []
        for text in CJK_SAMPLES:
            rows.append(self._row("cjk", self.cjk, text))
        for text in ASCII_SAMPLES:
            rows.append(self._row("ascii", self.latin, text))

        print("\n| kind | sample | measured | independent | diff |")
        print("|---|---|---|---|---|")
        for kind, text, measured, reference, diff in rows:
            print("| %s | %s | %.4f | %.4f | %.6f |" % (kind, text, measured, reference, diff))
            self.assertLessEqual(diff, 0.01, "width mismatch for %r" % text)

    def test_measured_width_covers_ink(self):
        for font, samples in ((self.cjk, CJK_SAMPLES), (self.latin, ASCII_SAMPLES)):
            for text in samples:
                box = font.getbbox(text)
                ink = float(box[2] - box[0])
                self.assertLessEqual(ink, metrics.measure_text(font, text) + 0.01, text)

    def test_font_detection(self):
        self.assertTrue(metrics.needs_cjk_font("中文标签"))
        self.assertFalse(metrics.needs_cjk_font("ClickCell(x, y)"))
        self.assertEqual("Microsoft YaHei", metrics.font_family("中文标签"))
        self.assertEqual("Helvetica", metrics.font_family("ClickCell(x, y)"))


class HeightTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.latin = metrics.load_font(ARIAL, FONT_SIZE)

    def test_single_line_height_is_bbox_height(self):
        box = self.latin.getbbox("Ag")
        self.assertAlmostEqual(float(box[3] - box[1]), metrics.line_ink_height(self.latin, "Ag"), places=6)

    def test_multiline_height_adds_line_step(self):
        one = metrics.line_ink_height(self.latin, "Ag")
        self.assertAlmostEqual(one + metrics.LINE_STEP, metrics.text_height(["Ag", "Ag"], self.latin), places=6)

    def test_empty_line_uses_reference(self):
        self.assertAlmostEqual(
            metrics.line_ink_height(self.latin, "Ag"),
            metrics.line_ink_height(self.latin, ""),
            places=6,
        )


class WrapTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.latin = metrics.load_font(ARIAL, FONT_SIZE)
        cls.cjk = metrics.load_font(MSYH, FONT_SIZE, index=0)

    def test_explicit_newline_is_forced(self):
        self.assertEqual(["a", "b"], metrics.wrap_text("a\nb", 1000, self.latin))

    def test_latin_wraps_on_spaces(self):
        lines = metrics.wrap_text("Refresh board after capture", 90, self.latin)
        self.assertGreater(len(lines), 1)
        for line in lines:
            self.assertLessEqual(metrics.measure_text(self.latin, line), 90 + 0.01)

    def test_cjk_wraps_per_character(self):
        text = "请把当前玩家选择的格子坐标连同棋盘版本号当前回合数"
        lines = metrics.wrap_text(text, 60, self.cjk)
        self.assertGreater(len(lines), 1)
        for line in lines:
            self.assertLessEqual(metrics.measure_text(self.cjk, line), 60 + 0.01)
        self.assertEqual(text, "".join(lines))

    def test_unbreakable_token_is_hard_split(self):
        text = "A" * 40
        lines = metrics.wrap_text(text, 60, self.latin)
        self.assertGreater(len(lines), 1)
        self.assertEqual(text, "".join(lines))
        for line in lines:
            self.assertLessEqual(metrics.measure_text(self.latin, line), 60 + 0.01)

    def test_wrap_result_carries_family_and_size(self):
        result = metrics.wrap_to_width("中文标签", 200, self.cjk)
        self.assertEqual("Microsoft YaHei", result["family"])
        self.assertEqual(1, len(result["lines"]))


if __name__ == "__main__":
    unittest.main()
