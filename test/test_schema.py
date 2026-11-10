# -*- coding: utf-8 -*-
"""Step 1 gate: schema accepts the 3 fixtures, rejects the 5 bad specs, and the
schema file never grows beyond the keyword subset the validator implements."""
from __future__ import annotations

import copy
import json
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

import schema_validate  # noqa: E402
import semantics  # noqa: E402

SCHEMA = schema_validate.load_schema(ROOT / "schema" / "uml-seq.spec.schema.json")


def load_fixture(name):
    return json.loads((ROOT / "fixtures" / name).read_text(encoding="utf-8"))


def codes(errors):
    return [error["code"] for error in errors]


def nested_fragments(depth):
    """Build `depth` nested opt fragments with one message inside."""
    node = {"type": "message", "kind": "call", "from": "alice", "to": "api", "label": "x"}
    node = {
        "type": "fragment", "kind": "opt", "guard": "[g]",
        "branches": [{"guard": None, "events": [node]}],
    }
    for _ in range(depth - 1):
        node = {
            "type": "fragment", "kind": "opt", "guard": "[g]",
            "branches": [{"guard": None, "events": [node]}],
        }
    return node


class SchemaWhitelistTest(unittest.TestCase):
    def test_schema_uses_only_supported_keywords(self):
        used = schema_validate.collect_keywords(SCHEMA)
        unknown = sorted(used - schema_validate.SUPPORTED_KEYWORDS)
        self.assertEqual([], unknown, "schema uses keywords the validator does not implement: %r" % unknown)
        self.assertEqual(
            [],
            sorted(schema_validate.unsupported_keywords(SCHEMA)),
            "unsupported_keywords() must agree with the whitelist",
        )


class FixtureTest(unittest.TestCase):
    def test_fixtures_pass_schema(self):
        for name in ("minimal.json", "cjk-long-label.json", "prototype.json"):
            with self.subTest(name=name):
                spec = load_fixture(name)
                self.assertEqual([], schema_validate.validate(SCHEMA, spec))

    def test_fixtures_pass_semantics(self):
        for name in ("minimal.json", "cjk-long-label.json", "prototype.json"):
            with self.subTest(name=name):
                spec = load_fixture(name)
                self.assertEqual([], semantics.validate_spec(spec, SCHEMA))

    def test_prototype_stats(self):
        stats = semantics.spec_stats(load_fixture("prototype.json"))
        self.assertEqual(7, stats["participants"])
        self.assertEqual(50, stats["messages"])
        self.assertEqual(5, stats["fragments"])
        self.assertEqual(4, stats["topLevelFragments"])
        self.assertEqual(2, stats["maxDepth"])
        # The prototype's last fragment ("[gameOver = true]") has a single operand;
        # the locked rule "alt >= 2 branches" makes it an opt, not an alt.
        self.assertEqual({"alt": 1, "opt": 3, "loop": 1}, stats["fragmentsByKind"])
        self.assertEqual(1, stats["notes"])

    def test_cjk_fixture_stats(self):
        stats = semantics.spec_stats(load_fixture("cjk-long-label.json"))
        self.assertEqual(5, stats["participants"])
        self.assertEqual(10, stats["messages"])

    def test_minimal_fixture_stats(self):
        stats = semantics.spec_stats(load_fixture("minimal.json"))
        self.assertEqual(3, stats["participants"])
        self.assertEqual(6, stats["messages"])


class BadSpecTest(unittest.TestCase):
    def test_missing_version(self):
        spec = load_fixture("minimal.json")
        spec.pop("version")
        self.assertIn("E_SCHEMA_VALIDATION", codes(semantics.validate_spec(spec, SCHEMA)))

    def test_unknown_participant(self):
        spec = load_fixture("minimal.json")
        spec["events"].append({"type": "message", "kind": "call", "from": "ghost", "to": "api", "label": "boo()"})
        self.assertIn("E_PARTICIPANT_UNKNOWN", codes(semantics.validate_spec(spec, SCHEMA)))

    def test_opt_with_two_branches(self):
        spec = load_fixture("minimal.json")
        fragment = next(event for event in spec["events"] if event.get("type") == "fragment")
        fragment["kind"] = "opt"
        fragment["branches"].append({
            "guard": "[other]",
            "events": [{"type": "message", "kind": "call", "from": "api", "to": "db", "label": "x()"}],
        })
        self.assertIn("E_FRAGMENT_BRANCH", codes(semantics.validate_spec(spec, SCHEMA)))

    def test_empty_branch(self):
        spec = load_fixture("minimal.json")
        fragment = next(event for event in spec["events"] if event.get("type") == "fragment")
        fragment["branches"][0]["events"] = []
        self.assertIn("E_SCHEMA_VALIDATION", codes(semantics.validate_spec(spec, SCHEMA)))

    def test_create_kind(self):
        spec = load_fixture("minimal.json")
        spec["events"].append({"type": "message", "kind": "create", "from": "api", "to": "db", "label": "new()"})
        self.assertIn("E_UNSUPPORTED_KIND", codes(semantics.validate_spec(spec, SCHEMA)))

    def test_wrong_version(self):
        spec = load_fixture("minimal.json")
        spec["version"] = 2
        self.assertEqual(["E_SPEC_VERSION"], codes(semantics.validate_spec(spec, SCHEMA)))

    def test_duplicate_stable_key(self):
        spec = load_fixture("minimal.json")
        spec["events"][0]["stableKey"] = "dup"
        spec["events"][1]["stableKey"] = "dup"
        self.assertIn("E_ID_DUPLICATE", codes(semantics.validate_spec(spec, SCHEMA)))

    def test_alt_with_one_branch(self):
        spec = load_fixture("minimal.json")
        fragment = next(event for event in spec["events"] if event.get("type") == "fragment")
        fragment["branches"] = fragment["branches"][:1]
        self.assertIn("E_FRAGMENT_BRANCH", codes(semantics.validate_spec(spec, SCHEMA)))

    def test_depth_limit(self):
        spec = load_fixture("minimal.json")
        spec["events"] = [nested_fragments(6)]
        self.assertEqual([], semantics.validate_spec(spec, SCHEMA))
        spec["events"] = [nested_fragments(7)]
        self.assertIn("E_DEPTH_EXCEEDED", codes(semantics.validate_spec(spec, SCHEMA)))

    def test_second_branch_without_guard(self):
        spec = load_fixture("minimal.json")
        fragment = next(event for event in spec["events"] if event.get("type") == "fragment")
        fragment["branches"][1]["guard"] = None
        self.assertIn("E_FRAGMENT_BRANCH", codes(semantics.validate_spec(spec, SCHEMA)))

    def test_unknown_property(self):
        spec = copy.deepcopy(load_fixture("minimal.json"))
        spec["events"][0]["stereotype"] = "removed-in-v1"
        self.assertIn("E_SCHEMA_VALIDATION", codes(semantics.validate_spec(spec, SCHEMA)))


class OneOfDiagnosticsTest(unittest.TestCase):
    """An event that breaks one variant must report that variant's real problem.

    Before the discriminator fix, a note without `text` came back as
    "exactly one variant must match, got 0; first failure: missing required
    property 'kind'", which points at a property the author never wrote.
    """

    def _errors(self, event):
        spec = load_fixture("minimal.json")
        spec["events"].append(event)
        path = "/events/%d" % (len(spec["events"]) - 1)
        return schema_validate.validate(SCHEMA, spec), path

    def test_note_without_text(self):
        errors, path = self._errors({"type": "note", "target": "api", "position": "left"})
        self.assertEqual(1, len(errors), errors)
        self.assertEqual("required", errors[0]["keyword"])
        self.assertIn("'text'", errors[0]["message"])
        self.assertEqual(path, errors[0]["path"])

    def test_text_event_without_text(self):
        errors, path = self._errors({"type": "text", "width": 400})
        self.assertEqual("required", errors[0]["keyword"])
        self.assertIn("'text'", errors[0]["message"])
        self.assertEqual(path, errors[0]["path"])

    def test_message_without_label(self):
        errors, path = self._errors({"type": "message", "kind": "call", "from": "api", "to": "db"})
        self.assertEqual("required", errors[0]["keyword"])
        self.assertIn("'label'", errors[0]["message"])
        self.assertEqual(path, errors[0]["path"])

    def test_fragment_with_unknown_property(self):
        errors, path = self._errors({
            "type": "fragment", "kind": "opt", "guard": "[g]", "operands": [],
        })
        self.assertEqual("required", errors[0]["keyword"])
        self.assertIn("'branches'", errors[0]["message"])
        self.assertEqual(path, errors[0]["path"])

    def test_unknown_type_still_falls_back(self):
        errors, path = self._errors({"type": "callout", "text": "hi"})
        self.assertEqual(1, len(errors), errors)
        self.assertEqual("oneOf", errors[0]["keyword"])
        self.assertIn("closest failure", errors[0]["message"])
        self.assertEqual(path, errors[0]["path"])

    def test_valid_events_stay_clean(self):
        for event in (
            {"type": "message", "kind": "call", "from": "api", "to": "db", "label": "x()"},
            {"type": "note", "target": "api", "position": "left", "text": "n"},
            {"type": "text", "text": "t"},
            {"type": "fragment", "kind": "opt", "guard": "[g]", "branches": [
                {"guard": None, "events": [
                    {"type": "message", "kind": "call", "from": "api", "to": "db", "label": "x()"},
                ]},
            ]},
        ):
            with self.subTest(event=event["type"]):
                errors, _ = self._errors(event)
                self.assertEqual([], errors, errors)


if __name__ == "__main__":
    unittest.main()
