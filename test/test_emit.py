# -*- coding: utf-8 -*-
"""Step 2: XML emit order, structure, escaping, determinism, no timestamps."""
from __future__ import annotations

import hashlib
import json
import pathlib
import sys
import unittest
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

import emit  # noqa: E402
import ids  # noqa: E402
import layout  # noqa: E402

FONTS = {
    "cjk": r"C:\Windows\Fonts\msyh.ttc",
    "latin": r"C:\Windows\Fonts\arial.ttf",
}


def load_fixture(name):
    return json.loads((ROOT / "fixtures" / name).read_text(encoding="utf-8"))


def build(spec):
    return layout.layout_spec(ids.normalize_spec(spec), FONTS)


class PrototypeEmitTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = load_fixture("prototype.json")
        cls.layout_result = build(cls.spec)
        assert cls.layout_result["ok"], cls.layout_result["errors"]
        cls.xml, cls.cells = emit.emit_xml(cls.layout_result, cls.spec["title"])
        cls.root = ET.fromstring(cls.xml)

    def test_structure(self):
        self.assertEqual("mxfile", self.root.tag)
        diagrams = list(self.root)
        self.assertEqual(1, len(diagrams))
        self.assertEqual("diagram", diagrams[0].tag)
        model = diagrams[0].find("mxGraphModel")
        self.assertIsNotNone(model)
        self.assertEqual(1600.0, float(model.get("pageWidth")))
        self.assertLess(abs(float(model.get("pageHeight")) - self.layout_result["page"]["height"]), 1.01)

    def test_unique_ids_and_base_cells(self):
        cells = list(self.root.iter("mxCell"))
        ids_list = [cell.get("id") for cell in cells]
        self.assertEqual(len(ids_list), len(set(ids_list)))
        self.assertIn("0", ids_list)
        self.assertIn("1", ids_list)

    def test_z_order(self):
        cells = list(self.root.iter("mxCell"))

        def first_index(predicate):
            for index, cell in enumerate(cells):
                if predicate(cell):
                    return index
            return -1

        life = first_index(lambda cell: (cell.get("id") or "").startswith("l_"))
        border = first_index(lambda cell: (cell.get("id") or "").endswith("_border"))
        tab = first_index(lambda cell: (cell.get("id") or "").endswith("_tab"))
        message_ids = {message["id"] for message in self.layout_result["messages"]}
        message = first_index(
            lambda cell: cell.get("id") in message_ids and cell.get("edge") == "1")
        self.assertGreaterEqual(life, 0)
        self.assertGreaterEqual(border, 0)
        self.assertGreaterEqual(tab, 0)
        self.assertGreaterEqual(message, 0)
        self.assertLess(life, border, "lifelines must come before frame borders")
        self.assertLess(border, tab, "frame borders must come before tabs")
        self.assertLess(tab, message, "tabs must come before messages")

    def test_no_forbidden_markers(self):
        lowered = self.xml.lower()
        for marker in ("modified=", "etag=", "hostversion=", "base64"):
            self.assertNotIn(marker, lowered)
        self.assertTrue(self.xml.endswith("\n"))

    def test_no_label_background_color_on_text_vertices(self):
        # F3: level-2 background is a real rect, not labelBackgroundColor.
        self.assertNotIn("labelBackgroundColor", self.xml)

    def test_message_edge_count(self):
        message_ids = {message["id"] for message in self.layout_result["messages"]}
        edges = [cell for cell in self.root.iter("mxCell") if cell.get("id") in message_ids]
        self.assertEqual(50, len(edges))

    def test_self_check_counts_cells(self):
        self.assertEqual(self.cells, emit.self_check(self.xml, self.layout_result))


class EscapingTest(unittest.TestCase):
    LABEL = 'A & B < C > D "E" \'F\'\nsecond line'

    def test_special_characters_and_newlines_round_trip(self):
        spec = {
            "version": 1,
            "participants": [{"id": "a", "name": "A"}, {"id": "b", "name": "B"}],
            "events": [{"type": "message", "kind": "call", "from": "a", "to": "b", "label": self.LABEL}],
        }
        result = build(spec)
        self.assertTrue(result["ok"], result["errors"])
        xml_text, _cells = emit.emit_xml(result, None)
        self.assertIn("&#10;", xml_text)
        self.assertIn("&amp;", xml_text)
        self.assertIn("&lt;", xml_text)
        self.assertIn("&gt;", xml_text)
        self.assertIn("&quot;", xml_text)
        root = ET.fromstring(xml_text)
        label_id = result["messages"][0]["id"] + "_label"
        cell = next(cell for cell in root.iter("mxCell") if cell.get("id") == label_id)
        self.assertEqual(self.LABEL, cell.get("value"))

    def test_determinism(self):
        spec = load_fixture("minimal.json")
        first_layout = build(spec)
        second_layout = build(spec)
        first_xml, _ = emit.emit_xml(first_layout, spec["title"])
        second_xml, _ = emit.emit_xml(second_layout, spec["title"])
        self.assertEqual(first_xml, second_xml)
        self.assertEqual(hashlib.md5(first_xml.encode("utf-8")).hexdigest(),
                         hashlib.md5(second_xml.encode("utf-8")).hexdigest())


class WhiteUnitRepairTest(unittest.TestCase):
    """P0: every white tab/strip that crosses a lifeline gets a repair segment."""

    @classmethod
    def setUpClass(cls):
        spec = load_fixture("prototype.json")
        cls.result = build(spec)
        cls.xml, _cells = emit.emit_xml(cls.result, spec["title"])
        root = ET.fromstring(cls.xml)
        cls.cells = list(root.iter("mxCell"))
        cls.index = {cell.get("id"): index for index, cell in enumerate(cls.cells)}
        cls.lifelines = {}
        for cell in cls.cells:
            cell_id = cell.get("id") or ""
            if cell_id.startswith("l_"):
                source = cell.find("mxGeometry").find("mxPoint")
                cls.lifelines[cell_id[2:]] = float(source.get("x"))

    @staticmethod
    def geometry(cell):
        box = cell.find("mxGeometry")
        return {
            "x": float(box.get("x")),
            "y": float(box.get("y")),
            "w": float(box.get("width")),
            "h": float(box.get("height")),
        }

    def white_units(self):
        return [
            cell for cell in self.cells
            if (cell.get("id") or "").endswith(("_tab", "_strip"))
            and "fillColor=#FFFFFF" in (cell.get("style") or "")
        ]

    def test_every_crossing_white_unit_has_a_repair(self):
        units = self.white_units()
        self.assertGreaterEqual(len(units), 2)
        crossings = 0
        for unit in units:
            unit_id = unit.get("id")
            box = self.geometry(unit)
            covered = [
                (participant_id, lifeline_x)
                for participant_id, lifeline_x in self.lifelines.items()
                if box["x"] + 0.01 < lifeline_x < box["x"] + box["w"] - 0.01
            ]
            for participant_id, lifeline_x in covered:
                crossings += 1
                repair_id = "%s_life_%s" % (unit_id, participant_id)
                self.assertIn(repair_id, self.index, "missing repair for %s" % repair_id)
                self.assertGreater(self.index[repair_id], self.index[unit_id],
                                   "repair must be drawn after the white unit")
                repair = self.cells[self.index[repair_id]]
                source, target = repair.find("mxGeometry").findall("mxPoint")
                self.assertAlmostEqual(lifeline_x, float(source.get("x")), places=3)
                self.assertAlmostEqual(box["y"], float(source.get("y")), places=3)
                self.assertAlmostEqual(box["y"] + box["h"], float(target.get("y")), places=3)
        self.assertGreater(crossings, 0, "prototype must exercise white-unit/lifeline crossings")

    def test_repair_is_drawn_before_the_unit_text(self):
        frame = next(frame for frame in self.result["frames"] if frame["kind"] == "alt")
        player = self.lifelines["player"]
        tab = frame["tab"]
        self.assertTrue(tab["x"] < player < tab["x"] + tab["w"])
        repair_id = "%s_tab_life_player" % frame["id"]
        self.assertIn(repair_id, self.index)
        self.assertLess(self.index[repair_id], self.index["%s_kw" % frame["id"]])
        self.assertLess(self.index[repair_id], self.index["%s_guard" % frame["id"]])

    def test_level_two_backgrounds_are_exempt(self):
        spec = load_fixture("cjk-long-label.json")
        result = build(spec)
        xml_text, _cells = emit.emit_xml(result, spec["title"])
        root = ET.fromstring(xml_text)
        backgrounds = [cell for cell in root.iter("mxCell") if (cell.get("id") or "").endswith("_bg")]
        self.assertEqual(1, len(backgrounds))
        for background in backgrounds:
            prefix = background.get("id") + "_life_"
            self.assertFalse(
                any((cell.get("id") or "").startswith(prefix) for cell in root.iter("mxCell")),
                "level-2 label backgrounds must not get a lifeline repair",
            )


if __name__ == "__main__":
    unittest.main()
