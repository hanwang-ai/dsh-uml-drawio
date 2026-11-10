# -*- coding: utf-8 -*-
"""Step 2: layout defaults, three passes, fragment bounds, label degradation."""
from __future__ import annotations

import json
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

import ids  # noqa: E402
import layout  # noqa: E402
import emit  # noqa: E402

FONTS = {
    "cjk": r"C:\Windows\Fonts\msyh.ttc",
    "latin": r"C:\Windows\Fonts\arial.ttf",
}


def load_fixture(name):
    return json.loads((ROOT / "fixtures" / name).read_text(encoding="utf-8"))


def build(spec):
    return layout.layout_spec(ids.normalize_spec(spec), FONTS)


class DefaultsTest(unittest.TestCase):
    def test_minimal_shape_uses_code_defaults(self):
        spec = {
            "version": 1,
            "participants": [{"id": "a", "name": "A"}, {"id": "b", "name": "B"}, {"id": "c", "name": "C"}],
            "events": [{"type": "message", "kind": "call", "from": "a", "to": "c", "label": "x()"}],
        }
        result = build(spec)
        self.assertTrue(result["ok"], result["errors"])
        expected_pitch = (1600.0 - 35.0 - 35.0) / 3.0
        self.assertAlmostEqual(expected_pitch, result["pitch"], places=6)
        self.assertEqual([290.0, 800.0, 1310.0], [round(p["x"], 6) for p in result["participants"]])
        self.assertEqual(1600.0, result["page"]["width"])

    def test_page_overflow_when_pitch_too_small(self):
        participants = [{"id": "p%d" % i, "name": "P%d" % i} for i in range(12)]
        spec = {
            "version": 1,
            "participants": participants,
            "events": [{"type": "message", "kind": "call", "from": "p0", "to": "p1", "label": "x()"}],
        }
        result = build(spec)
        self.assertFalse(result["ok"])
        self.assertIn("E_PAGE_OVERFLOW", [error["code"] for error in result["errors"]])


class PrototypeLayoutTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = build(load_fixture("prototype.json"))

    def test_counts(self):
        self.assertTrue(self.result["ok"], self.result["errors"])
        stats = self.result["stats"]
        self.assertEqual(7, stats["participants"])
        self.assertEqual(50, stats["messages"])
        self.assertEqual(5, stats["fragments"])
        self.assertEqual(4, stats["topLevelFragments"])
        self.assertEqual(2, stats["maxDepth"])

    def test_frame_nesting_and_bounds(self):
        frames = self.result["frames"]
        self.assertEqual(5, len(frames))
        alt = next(frame for frame in frames if frame["kind"] == "alt")
        loop = next(frame for frame in frames if frame["kind"] == "loop")
        xs = {participant["id"]: participant["x"] for participant in self.result["participants"]}
        self.assertAlmostEqual(xs["player"] - 60.0, alt["left"], places=6)
        self.assertAlmostEqual(xs["sm"] + 60.0, alt["right"], places=6)
        self.assertAlmostEqual(xs["gb"] - 60.0, loop["left"], places=6)
        self.assertAlmostEqual(xs["ee"] + 60.0, loop["right"], places=6)
        self.assertGreater(loop["top"], alt["top"])
        self.assertLess(loop["bottom"], alt["bottom"])
        self.assertEqual("alt", frames[0]["kind"], "outer frames must be emitted first")

    def test_every_message_has_a_label(self):
        self.assertEqual(50, len(self.result["messages"]))
        for message in self.result["messages"]:
            self.assertIsNotNone(message["label"], message["path"])
            self.assertIn(message["level"], (1, 2))
        levels = self.result["stats"]["labelLevels"]
        self.assertEqual(50, levels["1"] + levels["2"])

    def test_self_message_geometry(self):
        message = next(item for item in self.result["messages"] if item["self"])
        xs = {participant["id"]: participant["x"] for participant in self.result["participants"]}
        self.assertEqual("ee", message["from"])
        self.assertAlmostEqual(xs["ee"] - 42.0, message["label"]["x"] + message["label"]["w"], places=6)
        self.assertEqual("right", message["label"]["align"])

    def test_note_geometry(self):
        note = next(item for item in self.result["notes"] if item["targets"] == ["ee"])
        xs = {participant["id"]: participant["x"] for participant in self.result["participants"]}
        self.assertAlmostEqual(xs["ee"] + 18.0, note["box"]["x"], places=6)
        self.assertIsNotNone(note["anchor"])
        self.assertAlmostEqual(xs["ee"], note["anchor"]["x2"], places=6)
        self.assertAlmostEqual(note["box"]["y"] + note["box"]["h"] / 2.0, note["anchor"]["y2"], places=6)

    def test_page_height_and_life_bottom(self):
        self.assertGreater(self.result["page"]["height"], 0)
        self.assertGreater(self.result["life_bottom"], self.result["page"]["height"] - 100)
        self.assertGreater(self.result["page"]["height"], self.result["life_bottom"])

    def test_no_warnings_for_clean_prototype(self):
        self.assertEqual([], self.result["warnings"])


class CjkLayoutTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = load_fixture("cjk-long-label.json")
        cls.result = build(cls.spec)

    def test_long_message_uses_level_two(self):
        self.assertTrue(self.result["ok"], self.result["errors"])
        long_message = next(item for item in self.result["messages"] if item["path"] == "/events/5")
        self.assertEqual(2, long_message["level"])
        self.assertIsNotNone(long_message["bg"])
        self.assertLessEqual(long_message["label"]["w"], 220.0 + 4.0)
        codes = [warning["code"] for warning in self.result["warnings"]]
        self.assertIn("W_LABEL_OVER_LIFELINE", codes)

    def test_counts(self):
        stats = self.result["stats"]
        self.assertEqual(5, stats["participants"])
        self.assertEqual(10, stats["messages"])
        self.assertEqual(1, stats["fragments"])


class MinimalLayoutTest(unittest.TestCase):
    def test_minimal_is_clean(self):
        result = build(load_fixture("minimal.json"))
        self.assertTrue(result["ok"], result["errors"])
        self.assertEqual([], result["warnings"])
        self.assertEqual(6, result["stats"]["messages"])


class LabelPlacementUnitTest(unittest.TestCase):
    """Synthetic conflict boxes cover the E_LABEL_IMPOSSIBLE code path."""

    XS = [100.0, 300.0]
    X_INDEX = {100.0: 0, 300.0: 1}

    def test_level_one_fits_the_gap(self):
        placement = layout.place_message_label(
            100.0, 300.0, 500.0, 100.0, 20.0,
            self.XS, self.X_INDEX, [], 100.0, 1000.0, 800.0,
        )
        self.assertEqual(1, placement["level"])
        self.assertGreaterEqual(placement["box"]["x"], 106.0 - 0.001)
        self.assertLessEqual(placement["box"]["x"] + 100.0, 294.0 + 0.001)

    def test_level_two_when_the_gap_is_too_narrow(self):
        placement = layout.place_message_label(
            100.0, 300.0, 500.0, 250.0, 20.0,
            self.XS, self.X_INDEX, [], 100.0, 1000.0, 800.0,
        )
        self.assertEqual(2, placement["level"])
        self.assertAlmostEqual(75.0, placement["box"]["x"], places=6)

    def test_impossible_when_level_two_is_blocked(self):
        occupied = [{"x": 0.0, "y": 300.0, "w": 500.0, "h": 300.0}]
        placement = layout.place_message_label(
            100.0, 300.0, 500.0, 250.0, 20.0,
            self.XS, self.X_INDEX, occupied, 100.0, 1000.0, 800.0,
        )
        self.assertIsNone(placement)

    def test_container_blocks_labels_outside_a_fragment(self):
        container = {"left": 200.0, "right": 250.0, "top": 100.0, "bottom": 900.0}
        placement = layout.place_message_label(
            100.0, 300.0, 500.0, 100.0, 20.0,
            self.XS, self.X_INDEX, [], 100.0, 1000.0, 800.0, container,
        )
        # Level 1 clamps to x=150 (outside the container), level 2 centers at x=75.
        self.assertIsNone(placement)


class BoundsOverrideTest(unittest.TestCase):
    def test_bounds_override_replaces_participant_span(self):
        spec = load_fixture("minimal.json")
        fragment = next(event for event in spec["events"] if event.get("type") == "fragment")
        fragment["bounds"] = {"left": 40.0, "right": 760.0}
        result = build(spec)
        self.assertTrue(result["ok"], result["errors"])
        frame = result["frames"][0]
        self.assertEqual(40.0, frame["left"])
        self.assertEqual(760.0, frame["right"])


class FirstBranchGuardTest(unittest.TestCase):
    """The first operand's guard must never be silently dropped."""

    def _spec(self, first_guard):
        spec = load_fixture("minimal.json")
        fragment = next(event for event in spec["events"] if event.get("type") == "fragment")
        fragment["branches"][0]["guard"] = first_guard
        return spec

    def test_explicit_first_guard_renders_its_own_strip(self):
        spec = self._spec("[valid]")
        result = build(spec)
        self.assertTrue(result["ok"], result["errors"])
        frame = result["frames"][0]
        first = frame["branches"][0]
        self.assertEqual("[valid]", first["guard"])
        self.assertIsNotNone(first["strip"])
        self.assertIsNotNone(first["guard_box"])
        xml, _ = emit.emit_xml(result, spec.get("title"))
        self.assertIn('value="[valid]"', xml)
        self.assertIn('_b0_guard"', xml)
        self.assertIn('_b0_strip"', xml)

    def test_first_guard_equal_to_frame_guard_is_not_duplicated(self):
        spec = load_fixture("minimal.json")
        fragment = next(event for event in spec["events"] if event.get("type") == "fragment")
        fragment["branches"][0]["guard"] = fragment["guard"]
        result = build(spec)
        self.assertTrue(result["ok"], result["errors"])
        first = result["frames"][0]["branches"][0]
        self.assertIsNone(first["strip"])
        xml, _ = emit.emit_xml(result, spec.get("title"))
        self.assertNotIn('_b0_guard"', xml)
        self.assertEqual(1, xml.count('value="%s"' % fragment["guard"]))

    def test_null_first_guard_inherits_the_frame_guard(self):
        spec = load_fixture("minimal.json")
        result = build(spec)
        self.assertTrue(result["ok"], result["errors"])
        first = result["frames"][0]["branches"][0]
        self.assertIsNone(first["guard"])
        self.assertIsNone(first["strip"])
        xml, _ = emit.emit_xml(result, spec.get("title"))
        self.assertNotIn('_b0_guard"', xml)

    def test_explicit_first_guard_adds_vertical_room(self):
        plain = build(self._spec(None))
        explicit = build(self._spec("[valid]"))
        self.assertTrue(plain["ok"] and explicit["ok"])
        self.assertAlmostEqual(
            layout.FIRST_GUARD_EXTRA,
            explicit["page"]["height"] - plain["page"]["height"],
            places=6,
        )


if __name__ == "__main__":
    unittest.main()
