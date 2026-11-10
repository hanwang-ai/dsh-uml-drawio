# -*- coding: utf-8 -*-
"""Deterministic element ids for dsh-uml-drawio.

Locked message formula (D2):
    id = "c_" + sha1("<kind>|<from>|<to>|<label>|<ordinal>")[:10]
where `ordinal` is the document-order occurrence of the same content key. A
unique inserted message therefore never shifts its neighbours' ids.

Every other node type has its own content key; `stableKey` always wins.
All strings are NFC-normalized before hashing (see normalize_spec()).
"""
from __future__ import annotations

import hashlib
import unicodedata


def nfc(text):
    return unicodedata.normalize("NFC", text)


def normalize_spec(value):
    """Deep-copy with every string NFC-normalized (keys included)."""
    if isinstance(value, str):
        return nfc(value)
    if isinstance(value, list):
        return [normalize_spec(item) for item in value]
    if isinstance(value, dict):
        return {
            (nfc(key) if isinstance(key, str) else key): normalize_spec(item)
            for key, item in value.items()
        }
    return value


def sha1_hex(text):
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def make_id(text):
    return "c_" + sha1_hex(text)[:10]


def diagram_id(title):
    return "d_" + sha1_hex(nfc(title or "Sequence Diagram"))[:12]


class IdAllocator:
    """Assigns ids in document order and flags collisions."""

    def __init__(self):
        self._counts = {}
        self._used = {}
        self.errors = []

    def _ordinal(self, base):
        number = self._counts.get(base, 0) + 1
        self._counts[base] = number
        return number

    def _register(self, element_id, path):
        if element_id in self._used:
            self.errors.append({
                "code": "E_ID_DUPLICATE",
                "message": "Generated id %s collides with %s." % (element_id, self._used[element_id]),
                "path": path,
                "details": {"id": element_id, "firstPath": self._used[element_id]},
            })
        else:
            self._used[element_id] = path
        return element_id

    def stable(self, stable_key, path):
        return self._register(make_id(nfc(stable_key)), path)

    def message(self, kind, source, target, label, path):
        base = "|".join([kind, source, target, label])
        ordinal = self._ordinal("m:" + base)
        return self._register(make_id("%s|%d" % (base, ordinal)), path)

    def fragment(self, kind, guard, path):
        base = "fragment|%s|%s" % (kind, guard)
        ordinal = self._ordinal("f:" + base)
        return self._register(make_id("%s|%d" % (base, ordinal)), path)

    def note(self, targets, text, path):
        # `position` is deliberately excluded: presentation must not change identity.
        base = "note|%s|%s" % (targets, text)
        ordinal = self._ordinal("n:" + base)
        return self._register(make_id("%s|%d" % (base, ordinal)), path)

    def text(self, text, path):
        base = "text|%s" % (text,)
        ordinal = self._ordinal("t:" + base)
        return self._register(make_id("%s|%d" % (base, ordinal)), path)


def normalize_targets(target):
    """Stable string form of a note target (string or array)."""
    if isinstance(target, list):
        return ",".join(sorted(set(target)))
    return target or ""


def assign_ids(spec):
    """Return ({path: id}, errors) for every event in document order."""
    ids = {}
    allocator = IdAllocator()

    def visit(events, base):
        for index, event in enumerate(events or []):
            path = "%s/%d" % (base, index)
            stable = event.get("stableKey")
            if isinstance(stable, str) and stable:
                element_id = allocator.stable(stable, path)
            else:
                element_type = event.get("type")
                if element_type == "message":
                    element_id = allocator.message(
                        event["kind"], event["from"], event["to"], event["label"], path)
                elif element_type == "fragment":
                    element_id = allocator.fragment(event["kind"], event["guard"], path)
                elif element_type == "note":
                    element_id = allocator.note(
                        normalize_targets(event.get("target")), event.get("text", ""), path)
                elif element_type == "text":
                    element_id = allocator.text(event.get("text", ""), path)
                else:
                    element_id = None
            if element_id is not None:
                ids[path] = element_id
            if event.get("type") == "fragment":
                for branch_index, branch in enumerate(event.get("branches") or []):
                    visit(
                        branch.get("events") or [],
                        "%s/branches/%d/events" % (path, branch_index),
                    )

    visit(spec.get("events") or [], "/events")
    return ids, allocator.errors
