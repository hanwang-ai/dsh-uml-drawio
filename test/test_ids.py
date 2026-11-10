# -*- coding: utf-8 -*-
"""Step 2: deterministic ids, ordinal traversal, NFC, stableKey, note identity."""
from __future__ import annotations

import copy
import json
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

import ids  # noqa: E402


def load_fixture(name):
    return json.loads((ROOT / "fixtures" / name).read_text(encoding="utf-8"))


def message_ids(spec):
    """Map (kind|from|to|label, ordinal) -> id, walking document order."""
    normalized = ids.normalize_spec(spec)
    id_map, errors = ids.assign_ids(normalized)
    result = {}
    counters = {}

    def visit(events, base):
        for index, event in enumerate(events):
            path = "%s/%d" % (base, index)
            if event.get("type") == "message":
                key = "|".join([event["kind"], event["from"], event["to"], event["label"]])
                ordinal = counters.get(key, 0) + 1
                counters[key] = ordinal
                result[(key, ordinal)] = id_map[path]
            if event.get("type") == "fragment":
                for branch_index, branch in enumerate(event.get("branches") or []):
                    visit(branch.get("events") or [],
                          "%s/branches/%d/events" % (path, branch_index))

    visit(normalized["events"], "/events")
    return result, errors


class OrdinalTest(unittest.TestCase):
    def test_ordinal_counts_same_key_in_document_order(self):
        spec = {
            "version": 1,
            "participants": [{"id": "a", "name": "A"}, {"id": "b", "name": "B"}],
            "events": [
                {"type": "message", "kind": "call", "from": "a", "to": "b", "label": "x()"},
                {"type": "fragment", "kind": "opt", "guard": "[g]", "branches": [
                    {"guard": None, "events": [
                        {"type": "message", "kind": "call", "from": "a", "to": "b", "label": "x()"},
                    ]},
                ]},
                {"type": "message", "kind": "call", "from": "a", "to": "b", "label": "x()"},
            ],
        }
        mapping, errors = message_ids(spec)
        self.assertEqual([], errors)
        self.assertEqual(3, len(mapping))
        self.assertEqual(3, len(set(mapping.values())))
        base = "call|a|b|x()"
        self.assertEqual(ids.make_id(base + "|1"), mapping[(base, 1)])
        self.assertEqual(ids.make_id(base + "|2"), mapping[(base, 2)])
        self.assertEqual(ids.make_id(base + "|3"), mapping[(base, 3)])

    def test_unique_insertion_keeps_neighbour_ids(self):
        base_spec = load_fixture("minimal.json")
        inserted = copy.deepcopy(base_spec)
        inserted["events"].insert(2, {
            "type": "message", "kind": "call", "from": "api", "to": "db", "label": "BEGIN TX",
        })
        base_map, base_errors = message_ids(base_spec)
        new_map, new_errors = message_ids(inserted)
        self.assertEqual([], base_errors)
        self.assertEqual([], new_errors)
        self.assertEqual(len(base_map) + 1, len(new_map))
        for key, value in base_map.items():
            self.assertEqual(value, new_map[key], "id changed for %r" % (key,))
        self.assertNotIn("call|api|db|BEGIN TX|1", base_map)

    def test_identical_insertion_shifts_only_later_duplicates(self):
        spec = load_fixture("minimal.json")
        spec["events"].insert(0, {
            "type": "message", "kind": "call", "from": "alice", "to": "api", "label": "POST /login",
        })
        mapping, errors = message_ids(spec)
        self.assertEqual([], errors)
        # The pre-existing POST /login message becomes ordinal 2; nothing else shifts.
        self.assertIn(("call|alice|api|POST /login", 1), mapping)
        self.assertIn(("call|alice|api|POST /login", 2), mapping)
        self.assertIn(("call|api|db|SELECT user", 1), mapping)


class NfcTest(unittest.TestCase):
    def test_decomposed_label_hashes_like_composed(self):
        composed = load_fixture("minimal.json")
        composed["events"][0]["label"] = "\u00e9t\u00e9"
        decomposed = copy.deepcopy(composed)
        decomposed["events"][0]["label"] = "e\u0301te\u0301"
        self.assertNotEqual(composed["events"][0]["label"], decomposed["events"][0]["label"])
        first, _ = message_ids(composed)
        second, _ = message_ids(decomposed)
        self.assertEqual(first, second)
        self.assertEqual("\u00e9t\u00e9", ids.normalize_spec(decomposed["events"][0]["label"]))

    def test_normalize_spec_is_deep_and_copies(self):
        original = {"a": ["e\u0301", {"b": "x\u0301"}]}
        normalized = ids.normalize_spec(original)
        self.assertEqual("\u00e9", normalized["a"][0])
        self.assertEqual("x\u0301", normalized["a"][1]["b"])
        self.assertIsNot(original["a"], normalized["a"])


class StableKeyTest(unittest.TestCase):
    def test_stable_key_wins(self):
        spec = load_fixture("minimal.json")
        spec["events"][0]["stableKey"] = "login-request"
        normalized = ids.normalize_spec(spec)
        id_map, errors = ids.assign_ids(normalized)
        self.assertEqual([], errors)
        self.assertEqual(ids.make_id("login-request"), id_map["/events/0"])

    def test_duplicate_stable_key_is_an_error(self):
        spec = load_fixture("minimal.json")
        spec["events"][0]["stableKey"] = "dup"
        spec["events"][1]["stableKey"] = "dup"
        _id_map, errors = ids.assign_ids(ids.normalize_spec(spec))
        self.assertIn("E_ID_DUPLICATE", [error["code"] for error in errors])


class OtherIdentityTest(unittest.TestCase):
    def test_diagram_id_depends_on_title(self):
        self.assertEqual(ids.diagram_id("Login flow"), ids.diagram_id("Login flow"))
        self.assertNotEqual(ids.diagram_id("Login flow"), ids.diagram_id("Login Flow"))

    def test_note_identity_ignores_position_and_target_order(self):
        def build(position, targets):
            return {
                "version": 1,
                "participants": [
                    {"id": "a", "name": "A"}, {"id": "b", "name": "B"}, {"id": "c", "name": "C"},
                ],
                "events": [{
                    "type": "note", "target": targets, "position": position, "text": "same text",
                }],
            }
        id_map_left, errors_left = ids.assign_ids(ids.normalize_spec(build("left", ["a", "b"])))
        id_map_right, errors_right = ids.assign_ids(ids.normalize_spec(build("right", ["b", "a"])))
        self.assertEqual([], errors_left)
        self.assertEqual([], errors_right)
        self.assertEqual(id_map_left["/events/0"], id_map_right["/events/0"])

    def test_ids_are_unique_across_node_types(self):
        spec = load_fixture("prototype.json")
        id_map, errors = ids.assign_ids(ids.normalize_spec(spec))
        self.assertEqual([], errors)
        self.assertEqual(len(id_map), len(set(id_map.values())))


if __name__ == "__main__":
    unittest.main()
