# -*- coding: utf-8 -*-
"""Step 2: Python worker CLI, --json-out test channel, atomic write, md5."""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

import uml_seq  # noqa: E402

FONTS = {
    "cjk": r"C:\Windows\Fonts\msyh.ttc",
    "latin": r"C:\Windows\Fonts\arial.ttf",
}
TMP = ROOT / ".out" / "worker-test"


def load_fixture(name):
    return json.loads((ROOT / "fixtures" / name).read_text(encoding="utf-8"))


class WorkerTest(unittest.TestCase):
    def setUp(self):
        TMP.mkdir(parents=True, exist_ok=True)
        for path in TMP.iterdir():
            path.unlink()

    def _request(self, name, mode="generate"):
        return {
            "mode": mode,
            "spec": load_fixture(name),
            "fonts": FONTS,
            "out": str(TMP / (name.replace(".json", "") + ".drawio")),
        }

    def test_generate_writes_atomic_file_with_hashes(self):
        request = self._request("minimal.json")
        result = uml_seq.run(request, uml_seq.load_schema())
        self.assertTrue(result["ok"], result.get("errors"))
        path = pathlib.Path(result["path"])
        self.assertTrue(path.is_file())
        data = path.read_bytes()
        self.assertEqual(len(data), result["bytes"])
        self.assertEqual(hashlib.md5(data).hexdigest(), result["md5"])
        self.assertEqual(hashlib.sha256(data).hexdigest(), result["sha256"])
        self.assertFalse(list(TMP.glob("*.tmp-*")), "temp file must not survive")

    def test_two_generations_are_byte_identical(self):
        first = uml_seq.run(self._request("minimal.json"), uml_seq.load_schema())
        second_out = TMP / "minimal-2.drawio"
        request = self._request("minimal.json")
        request["out"] = str(second_out)
        second = uml_seq.run(request, uml_seq.load_schema())
        self.assertTrue(first["ok"] and second["ok"])
        self.assertEqual(first["md5"], second["md5"])

    def test_json_out_channel(self):
        request_path = TMP / "request.json"
        out_json = TMP / "result.json"
        request = self._request("minimal.json", mode="lint")
        request_path.write_text(json.dumps(request, ensure_ascii=False), encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()):
            code = uml_seq.main(["--spec-file", str(request_path), "--json-out", str(out_json)])
        self.assertEqual(0, code)
        payload = json.loads(out_json.read_text(encoding="utf-8"))
        self.assertTrue(payload["ok"], payload.get("errors"))
        self.assertEqual("lint", payload["mode"])

    def test_unreadable_spec_file(self):
        out_json = TMP / "missing.json"
        with contextlib.redirect_stdout(io.StringIO()):
            code = uml_seq.main(["--spec-file", str(TMP / "nope.json"), "--json-out", str(out_json)])
        self.assertEqual(0, code)
        payload = json.loads(out_json.read_text(encoding="utf-8"))
        self.assertFalse(payload["ok"])
        self.assertIn("E_SPEC_UNREADABLE", [error["code"] for error in payload["errors"]])

    def test_unknown_mode_is_argument_error(self):
        request = self._request("minimal.json", mode="bogus")
        result = uml_seq.run(request, uml_seq.load_schema())
        self.assertFalse(result["ok"])
        self.assertEqual("E_ARG_INVALID", result["errors"][0]["code"])

    def test_lint_never_writes(self):
        request = self._request("minimal.json", mode="lint")
        request.pop("out")
        result = uml_seq.run(request, uml_seq.load_schema())
        self.assertTrue(result["ok"], result.get("errors"))
        self.assertFalse(list(TMP.glob("*.drawio")))


if __name__ == "__main__":
    unittest.main()
