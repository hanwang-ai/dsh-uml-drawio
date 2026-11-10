#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""dsh-uml-drawio Python worker.

Reads one request object (JSON) from stdin (or --spec-file), writes one result
object (JSON) to stdout (and optionally --json-out FILE). Logs go to stderr.

Request:
    {"mode": "lint" | "generate",
     "spec": {...},
     "out": "C:\\...\\x.drawio",          # generate only, absolute
     "fonts": {"cjk": "...", "latin": "..."}}

Result (always exit 0; the Node layer maps crashes to E_PYTHON_ENV):
    {"ok": true, "mode": ..., "page": {...}, "stats": {...}, "warnings": [...]}
    {"ok": false, "mode": ..., "errors": [...]}
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import emit  # noqa: E402
import ids  # noqa: E402
import layout  # noqa: E402
import schema_validate  # noqa: E402
import semantics  # noqa: E402

ROOT = HERE.parent
SCHEMA_PATH = ROOT / "schema" / "uml-seq.spec.schema.json"
DEFAULT_FONTS = {
    "cjk": r"C:\Windows\Fonts\msyh.ttc",
    "latin": r"C:\Windows\Fonts\arial.ttf",
}


def _fail(mode, errors):
    return {"ok": False, "mode": mode, "errors": errors}


def _error(code, message, path="", details=None):
    return semantics.make_error(code, message, path, details)


def spec_hash(spec):
    """sha256 of the NFC-normalized canonical JSON (sidecar change detection)."""
    canonical = json.dumps(spec, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def load_schema():
    return schema_validate.load_schema(str(SCHEMA_PATH))


def run(request, schema):
    mode = request.get("mode") or "lint"
    if mode not in ("lint", "generate"):
        return _fail(mode, [_error("E_ARG_INVALID", "Unknown mode %r; use lint or generate." % (mode,))])

    spec = request.get("spec")
    if not isinstance(spec, dict):
        return _fail(mode, [_error("E_SCHEMA_VALIDATION", "Request must contain a spec object.")])

    spec = ids.normalize_spec(spec)
    errors = semantics.validate_spec(spec, schema)
    if errors:
        return _fail(mode, errors)

    font_paths = dict(DEFAULT_FONTS)
    font_paths.update(request.get("fonts") or {})

    result = layout.layout_spec(spec, font_paths)
    if not result["ok"]:
        return {
            "ok": False,
            "mode": mode,
            "errors": result["errors"],
            "warnings": result.get("warnings") or [],
        }

    base = {
        "ok": True,
        "mode": mode,
        "page": result["page"],
        "pitch": result["pitch"],
        "stats": result["stats"],
        "warnings": result["warnings"],
    }
    if mode == "lint":
        return base

    out = request.get("out")
    if not isinstance(out, str) or not out:
        return _fail(mode, [_error("E_ARG_INVALID", "generate requires an absolute out path.")])
    if not os.path.isabs(out):
        return _fail(mode, [_error("E_OUT_PATH", "out must be an absolute path: %r" % (out,))])

    try:
        xml_text, element_count = emit.emit_xml(result, spec.get("title"))
        emit.self_check(xml_text, result)
    except AssertionError as exc:
        return _fail(mode, [_error("E_WRITE_FAILED", "Emitted XML failed self-check: %s" % (exc,))])

    data = xml_text.encode("utf-8")
    try:
        os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
        temp_path = out + ".tmp-%d" % os.getpid()
        with open(temp_path, "wb") as handle:
            handle.write(data)
        os.replace(temp_path, out)
    except OSError as exc:
        return _fail(mode, [_error("E_WRITE_FAILED", "Cannot write %s: %s" % (out, exc))])

    base.update({
        "path": out,
        "bytes": len(data),
        "cells": element_count,
        "md5": hashlib.md5(data).hexdigest(),
        "sha256": hashlib.sha256(data).hexdigest(),
        "specHash": spec_hash(spec),
    })
    return base


def _read_request(args):
    if args.spec_file:
        with open(args.spec_file, "r", encoding="utf-8") as handle:
            return json.load(handle)
    return json.loads(sys.stdin.read())


def _build_parser():
    parser = argparse.ArgumentParser(description="dsh-uml-drawio Python worker")
    parser.add_argument("--mode", choices=("lint", "generate"), default=None)
    parser.add_argument("--out", default=None)
    parser.add_argument("--spec-file", default=None, help="read the request JSON from a file (test channel)")
    parser.add_argument("--json-out", default=None, help="also write the result JSON to this file")
    return parser


def main(argv=None):
    args = _build_parser().parse_args(argv)
    try:
        request = _read_request(args)
        if args.mode:
            request["mode"] = args.mode
        if args.out:
            request["out"] = args.out
        schema = load_schema()
        result = run(request, schema)
    except json.JSONDecodeError as exc:
        result = _fail(getattr(args, "mode", None) or "lint", [
            _error("E_SCHEMA_VALIDATION", "Request is not valid JSON: %s" % (exc,)),
        ])
    except FileNotFoundError as exc:
        result = _fail(getattr(args, "mode", None) or "lint", [
            _error("E_SPEC_UNREADABLE", "Cannot read request file: %s" % (exc,)),
        ])
    except Exception as exc:  # noqa: BLE001 - the worker must always answer in JSON
        traceback.print_exc(file=sys.stderr)
        result = _fail(getattr(args, "mode", None) or "lint", [
            _error("E_WRITE_FAILED", "Internal worker error: %s" % (exc,)),
        ])

    text = json.dumps(result, ensure_ascii=False) + "\n"
    if args.json_out:
        try:
            Path(args.json_out).write_text(text, encoding="utf-8", newline="\n")
        except OSError:
            traceback.print_exc(file=sys.stderr)
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
