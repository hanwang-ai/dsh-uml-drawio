# -*- coding: utf-8 -*-
"""Minimal JSON Schema Draft 2020-12 subset validator for dsh-uml-drawio.

The plugin ships one schema file and must validate without third-party packages
(the host Python has Pillow only; adding `jsonschema` would add a runtime
dependency). This module implements exactly the keywords the schema uses:

    $defs $ref type required properties additionalProperties items oneOf
    enum const pattern minLength maxLength minimum maximum minItems maxItems

plus metadata keywords ($schema/$id/title/description) that are ignored.
`collect_keywords()` exists so a test can assert the schema never grows beyond
this subset.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

SUPPORTED_KEYWORDS = frozenset({
    "$schema", "$id", "title", "description", "$defs", "$ref",
    "type", "required", "properties", "additionalProperties",
    "items", "oneOf", "enum", "const",
    "pattern", "minLength", "maxLength",
    "minimum", "maximum", "minItems", "maxItems",
})

_IGNORED_KEYWORDS = frozenset({"$schema", "$id", "title", "description"})


# --------------------------------------------------------------------------- io

def load_schema(path):
    """Load a schema document from disk (UTF-8)."""
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


# ------------------------------------------------------------------ validation

def validate(schema, instance):
    """Validate `instance` against `schema`; return a list of error dicts.

    Each error is {"path": JSON pointer, "keyword": str, "message": str}.
    An empty list means valid.
    """
    return _walk(schema, instance, "", schema)


def _err(path, keyword, message):
    return {"path": path, "keyword": keyword, "message": message}


def _join(path, token):
    text = str(token).replace("~", "~0").replace("/", "~1")
    return path + "/" + text


def _resolve_ref(root, ref):
    if not isinstance(ref, str) or not ref.startswith("#/"):
        raise ValueError("unsupported $ref: %r" % (ref,))
    node = root
    for part in ref[2:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        node = node[part]
    return node


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _type_ok(value, name):
    if name == "object":
        return isinstance(value, dict)
    if name == "array":
        return isinstance(value, list)
    if name == "string":
        return isinstance(value, str)
    if name == "number":
        return _is_number(value)
    if name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if name == "boolean":
        return isinstance(value, bool)
    if name == "null":
        return value is None
    raise ValueError("unsupported type keyword: %r" % (name,))


def _walk(node, value, path, root):
    if not isinstance(node, dict):
        return []

    if "$ref" in node:
        return _walk(_resolve_ref(root, node["$ref"]), value, path, root)

    errors = []

    declared = node.get("type")
    if declared is not None:
        names = [declared] if isinstance(declared, str) else list(declared)
        if not any(_type_ok(value, name) for name in names):
            return [_err(path, "type", "expected %s, got %s" % (
                "|".join(names), type(value).__name__))]

    if "const" in node and value != node["const"]:
        errors.append(_err(path, "const", "expected %r" % (node["const"],)))
        return errors

    if "enum" in node and value not in node["enum"]:
        errors.append(_err(path, "enum", "expected one of %r" % (node["enum"],)))
        return errors

    if isinstance(value, str):
        if "minLength" in node and len(value) < node["minLength"]:
            errors.append(_err(path, "minLength", "length %d < %d" % (len(value), node["minLength"])))
        if "maxLength" in node and len(value) > node["maxLength"]:
            errors.append(_err(path, "maxLength", "length %d > %d" % (len(value), node["maxLength"])))
        if "pattern" in node and re.search(node["pattern"], value) is None:
            errors.append(_err(path, "pattern", "does not match %r" % (node["pattern"],)))

    if _is_number(value):
        if "minimum" in node and value < node["minimum"]:
            errors.append(_err(path, "minimum", "%r < %r" % (value, node["minimum"])))
        if "maximum" in node and value > node["maximum"]:
            errors.append(_err(path, "maximum", "%r > %r" % (value, node["maximum"])))

    if isinstance(value, dict):
        for key in node.get("required", []):
            if key not in value:
                errors.append(_err(path, "required", "missing required property %r" % (key,)))
        properties = node.get("properties", {})
        additional = node.get("additionalProperties", True)
        for key, item in value.items():
            child = _join(path, key)
            if key in properties:
                errors.extend(_walk(properties[key], item, child, root))
            elif additional is False:
                errors.append(_err(child, "additionalProperties", "unexpected property %r" % (key,)))
            elif isinstance(additional, dict):
                errors.extend(_walk(additional, item, child, root))

    if isinstance(value, list):
        if "minItems" in node and len(value) < node["minItems"]:
            errors.append(_err(path, "minItems", "%d items < %d" % (len(value), node["minItems"])))
        if "maxItems" in node and len(value) > node["maxItems"]:
            errors.append(_err(path, "maxItems", "%d items > %d" % (len(value), node["maxItems"])))
        items = node.get("items")
        if isinstance(items, dict):
            for index, item in enumerate(value):
                errors.extend(_walk(items, item, _join(path, index), root))

    if "oneOf" in node:
        errors.extend(_one_of_errors(node["oneOf"], value, path, root))

    return errors


def _variant_discriminator(variant, root):
    """Return (property, const) for the variant's `type` discriminator, if any."""
    node = variant
    if "$ref" in node:
        node = _resolve_ref(root, node["$ref"])
    properties = node.get("properties") if isinstance(node, dict) else None
    if not isinstance(properties, dict):
        return None
    for key, spec in properties.items():
        if isinstance(spec, dict) and "const" in spec:
            return key, spec["const"]
    return None


def _closest_failure(evaluated):
    """First error of the variant with the fewest complaints (best guess)."""
    best = None
    for variant_errors in evaluated:
        if not variant_errors:
            continue
        if best is None or len(variant_errors) < len(best):
            best = variant_errors
    return best[0] if best else None


def _one_of_errors(variants, value, path, root):
    """Validate oneOf, and diagnose it through the discriminator when possible.

    Every event variant pins a `type` const, so when the value carries one the
    intended variant is known. Reporting that variant's own errors keeps the
    message actionable: a note without `text` used to surface as "first
    failure: missing required property 'kind'", i.e. the first variant's
    complaint instead of the real one.
    """
    evaluated = [_walk(variant, value, path, root) for variant in variants]
    matches = sum(1 for variant_errors in evaluated if not variant_errors)
    if matches == 1:
        return []

    if isinstance(value, dict):
        for index, variant in enumerate(variants):
            discriminator = _variant_discriminator(variant, root)
            if discriminator is not None and value.get(discriminator[0]) == discriminator[1]:
                chosen = evaluated[index]
                if chosen:
                    return chosen
                break

    detail = "exactly one variant must match, got %d" % (matches,)
    closest = _closest_failure(evaluated)
    if closest is not None:
        detail += "; closest failure: %s (%s)" % (closest["message"], closest["path"] or "/")
    return [_err(path, "oneOf", detail)]


# --------------------------------------------------------------- introspection

def collect_keywords(schema):
    """Return every keyword used at a schema node (recursively)."""
    used = set()

    def walk(node):
        if not isinstance(node, dict):
            return
        used.update(node.keys())
        properties = node.get("properties")
        if isinstance(properties, dict):
            for sub in properties.values():
                walk(sub)
        definitions = node.get("$defs")
        if isinstance(definitions, dict):
            for sub in definitions.values():
                walk(sub)
        items = node.get("items")
        if isinstance(items, dict):
            walk(items)
        variants = node.get("oneOf")
        if isinstance(variants, list):
            for sub in variants:
                walk(sub)
        additional = node.get("additionalProperties")
        if isinstance(additional, dict):
            walk(additional)

    walk(schema)
    return used


def unsupported_keywords(schema):
    """Return keywords the schema uses that this validator does not implement."""
    return {key for key in collect_keywords(schema) if key not in SUPPORTED_KEYWORDS}
