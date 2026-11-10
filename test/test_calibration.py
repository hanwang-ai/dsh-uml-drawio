# -*- coding: utf-8 -*-
"""Step 3 calibration: prove draw.io `--size page` mapping (s, ox, oy).

Measured on this host (see the Step 3 report):
  * `--size page` exports page * scale + 2 px on the right/bottom.
  * origin is (0, 0): px = logical * scale.
  * `--size diagram` (the default) crops to the content bbox with a variable
    stroke/AA margin, so it must never be used for absolute crop mapping.
"""
from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile
import unittest

from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

DRAWIO = pathlib.Path(r"D:\drawio\draw.io\draw.io.exe")
TMP = ROOT / ".out" / "calibration"

PROBE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<mxfile host="app.diagrams.net" type="device">
  <diagram id="probe-cal" name="Probe Calibration">
    <mxGraphModel grid="0" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="400" pageHeight="300" math="0" shadow="0">
      <root>
        <mxCell id="0"/>
        <mxCell id="1" parent="0"/>
        <mxCell id="red" value="" style="rounded=0;html=0;fillColor=#FF0000;strokeColor=none;" vertex="1" parent="1">
          <mxGeometry x="50.0" y="60.0" width="20.0" height="20.0" as="geometry"/>
        </mxCell>
        <mxCell id="blue" value="" style="rounded=0;html=0;fillColor=#0000FF;strokeColor=none;" vertex="1" parent="1">
          <mxGeometry x="300.0" y="200.0" width="20.0" height="20.0" as="geometry"/>
        </mxCell>
      </root>
    </mxGraphModel>
  </diagram>
</mxfile>
"""


def export(source, target, scale):
    result = subprocess.run(
        [str(DRAWIO), "-x", "-f", "png", "-s", str(scale), "--size", "page",
         "-b", "0", "-o", str(target), str(source)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=180,
    )
    if result.returncode != 0:
        raise AssertionError("draw.io exited with %r" % (result.returncode,))


def pure_bbox(path, channel):
    image = Image.open(path).convert("RGB")
    width, height = image.size
    pixels = image.load()
    xs, ys = [], []
    for y in range(height):
        for x in range(width):
            red, green, blue = pixels[x, y]
            if channel == "red" and red > 200 and green < 80 and blue < 80:
                xs.append(x)
                ys.append(y)
            elif channel == "blue" and blue > 200 and red < 80 and green < 80:
                xs.append(x)
                ys.append(y)
    return (min(xs), min(ys), max(xs), max(ys))


@unittest.skipUnless(DRAWIO.is_file(), "draw.io CLI not installed")
class CalibrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        TMP.mkdir(parents=True, exist_ok=True)
        cls.source = TMP / "probe-cal.drawio"
        cls.source.write_text(PROBE_XML, encoding="utf-8")
        cls.s1 = TMP / "probe-cal-s1.png"
        cls.s2 = TMP / "probe-cal-s2.png"
        export(cls.source, cls.s1, 1)
        export(cls.source, cls.s2, 2)

    def test_page_size_at_scale_one(self):
        image = Image.open(self.s1)
        self.assertEqual((402, 302), image.size)

    def test_page_size_at_scale_two(self):
        image = Image.open(self.s2)
        self.assertEqual((802, 602), image.size)

    def test_origin_is_zero_at_scale_one(self):
        red = pure_bbox(self.s1, "red")
        blue = pure_bbox(self.s1, "blue")
        self.assertEqual(51, red[0])   # geometry x=50, pixel 50 is AA
        self.assertEqual(61, red[1])   # geometry y=60
        self.assertEqual(301, blue[0])
        self.assertEqual(201, blue[1])

    def test_origin_is_zero_at_scale_two(self):
        red = pure_bbox(self.s2, "red")
        blue = pure_bbox(self.s2, "blue")
        self.assertEqual(100, red[0])  # 50 * 2
        self.assertEqual(120, red[1])  # 60 * 2
        self.assertEqual(600, blue[0]) # 300 * 2
        self.assertEqual(400, blue[1]) # 200 * 2

    def test_effective_scale_is_requested_scale(self):
        for scale, name in ((1, self.s1), (2, self.s2)):
            image = Image.open(name)
            effective = (image.size[0] - 2) / 400.0
            self.assertAlmostEqual(float(scale), effective, places=6)


if __name__ == "__main__":
    unittest.main()
