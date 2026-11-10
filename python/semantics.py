# -*- coding: utf-8 -*-
"""Structural/semantic checks for dsh-uml-drawio specs.

Order (see the design checklist):
    version -> JSON Schema -> duplicate participants -> unknown references ->
    unsupported kinds -> fragment branch rules -> nesting depth -> duplicate
    stable keys.

Layout-level checks (page overflow, label placement, auto-id collisions) live
in layout.py / ids.py and run after these.
"""
from __future__ import annotations

import schema_validate

SUPPORTED_MESSAGE_KINDS = frozenset({"call", "async", "reply"})
RESERVED_MESSAGE_KINDS = frozenset({"create", "delete"})
SUPPORTED_FRAGMENT_KINDS = frozenset({"alt", "opt", "loop"})
RESERVED_FRAGMENT_KINDS = frozenset({"par", "break", "critical"})
MAX_DEPTH = 6
MAX_SCHEMA_ERRORS = 20


def make_error(code, message, path="", details=None):
    error = {"code": code, "message": message}
    if path:
        error["path"] = path
    if details:
        error["details"] = details
    return error


# ------------------------------------------------------------------ traversal

def walk_events(events, base="/events"):
    """Yield (path, event) in document order, descending into fragment branches."""
    for index, event in enumerate(events or []):
        path = "%s/%d" % (base, index)
        yield path, event
        if isinstance(event, dict) and event.get("type") == "fragment":
            for branch_index, branch in enumerate(event.get("branches") or []):
                branch_base = "%s/branches/%d/events" % (path, branch_index)
                yield from walk_events(branch.get("events") or [], branch_base)


def walk_fragments_depth(events, depth=1, base="/events"):
    """Yield (path, fragment, depth) with real nesting depth."""
    for index, event in enumerate(events or []):
        if not isinstance(event, dict) or event.get("type") != "fragment":
            continue
        path = "%s/%d" % (base, index)
        yield path, event, depth
        for branch_index, branch in enumerate(event.get("branches") or []):
            branch_base = "%s/branches/%d/events" % (path, branch_index)
            yield from walk_fragments_depth(branch.get("events") or [], depth + 1, branch_base)


# -------------------------------------------------------------------- checks

def check_version(spec):
    if "version" in spec and spec["version"] != 1:
        return [make_error(
            "E_SPEC_VERSION",
            "Unsupported spec version %r; dsh-uml-drawio v1 accepts version: 1." % (spec["version"],),
            "/version",
        )]
    return []


def check_participants(spec):
    errors = []
    seen = {}
    for index, participant in enumerate(spec.get("participants") or []):
        participant_id = participant.get("id")
        if participant_id in seen:
            errors.append(make_error(
                "E_PARTICIPANT_DUPLICATE",
                "Duplicate participant id %r (first declared at %s)." % (participant_id, seen[participant_id]),
                "/participants/%d" % (index,),
                {"id": participant_id, "firstPath": seen[participant_id]},
            ))
        else:
            seen[participant_id] = "/participants/%d" % (index,)
    return errors


def check_refs(spec):
    errors = []
    known = {participant.get("id") for participant in spec.get("participants") or []}
    for path, event in walk_events(spec.get("events") or []):
        if event.get("type") == "message":
            for side in ("from", "to"):
                if event.get(side) not in known:
                    errors.append(make_error(
                        "E_PARTICIPANT_UNKNOWN",
                        "Message %s refers to unknown participant %r." % (side, event.get(side)),
                        path,
                        {"side": side, "id": event.get(side)},
                    ))
        elif event.get("type") == "note":
            target = event.get("target")
            targets = target if isinstance(target, list) else [target]
            for item in targets:
                if item not in known:
                    errors.append(make_error(
                        "E_PARTICIPANT_UNKNOWN",
                        "Note target refers to unknown participant %r." % (item,),
                        path,
                        {"id": item},
                    ))
    return errors


def check_kinds(spec):
    errors = []
    for path, event in walk_events(spec.get("events") or []):
        if event.get("type") == "message" and event.get("kind") in RESERVED_MESSAGE_KINDS:
            errors.append(make_error(
                "E_UNSUPPORTED_KIND",
                "Message kind %r is reserved for a later version; v1 supports call/async/reply." % (event.get("kind"),),
                path,
                {"kind": event.get("kind"), "family": "message"},
            ))
        elif event.get("type") == "fragment" and event.get("kind") in RESERVED_FRAGMENT_KINDS:
            errors.append(make_error(
                "E_UNSUPPORTED_KIND",
                "Fragment kind %r is reserved for a later version; v1 supports alt/opt/loop." % (event.get("kind"),),
                path,
                {"kind": event.get("kind"), "family": "fragment"},
            ))
    return errors


def check_branches(spec):
    errors = []
    for path, fragment, _depth in walk_fragments_depth(spec.get("events") or []):
        kind = fragment.get("kind")
        branches = fragment.get("branches") or []
        if kind == "alt" and len(branches) < 2:
            errors.append(make_error(
                "E_FRAGMENT_BRANCH",
                "alt needs at least 2 branches, got %d." % (len(branches),),
                path,
                {"kind": kind, "branches": len(branches)},
            ))
        elif kind in ("opt", "loop") and len(branches) != 1:
            errors.append(make_error(
                "E_FRAGMENT_BRANCH",
                "%s needs exactly 1 branch, got %d." % (kind, len(branches)),
                path,
                {"kind": kind, "branches": len(branches)},
            ))
        for branch_index, branch in enumerate(branches):
            if branch_index > 0 and branch.get("guard") in (None, ""):
                errors.append(make_error(
                    "E_FRAGMENT_BRANCH",
                    "Branch %d needs its own guard; only the first branch may inherit the fragment guard." % (branch_index,),
                    "%s/branches/%d" % (path, branch_index),
                    {"branch": branch_index},
                ))
    return errors


def check_depth(spec):
    errors = []
    for path, _fragment, depth in walk_fragments_depth(spec.get("events") or []):
        if depth > MAX_DEPTH:
            errors.append(make_error(
                "E_DEPTH_EXCEEDED",
                "Fragment nesting depth %d exceeds the limit of %d." % (depth, MAX_DEPTH),
                path,
                {"depth": depth, "limit": MAX_DEPTH},
            ))
    return errors


def check_stable_keys(spec):
    errors = []
    seen = {}
    for path, event in walk_events(spec.get("events") or []):
        key = event.get("stableKey") if isinstance(event, dict) else None
        if not isinstance(key, str) or key == "":
            continue
        if key in seen:
            errors.append(make_error(
                "E_ID_DUPLICATE",
                "Duplicate stableKey %r (first used at %s)." % (key, seen[key]),
                path,
                {"stableKey": key, "firstPath": seen[key]},
            ))
        else:
            seen[key] = path
    return errors


# ---------------------------------------------------------------- entry point

def validate_spec(spec, schema):
    """Run version + schema + semantic checks; return a list of error dicts."""
    if not isinstance(spec, dict):
        return [make_error("E_SCHEMA_VALIDATION", "Spec must be a JSON object.")]

    version_errors = check_version(spec)
    if version_errors:
        return version_errors

    schema_errors = schema_validate.validate(schema, spec)
    if schema_errors:
        return [
            make_error(
                "E_SCHEMA_VALIDATION",
                item["message"],
                item["path"],
                {"keyword": item["keyword"]},
            )
            for item in schema_errors[:MAX_SCHEMA_ERRORS]
        ]

    errors = []
    errors.extend(check_participants(spec))
    errors.extend(check_refs(spec))
    errors.extend(check_kinds(spec))
    errors.extend(check_branches(spec))
    errors.extend(check_depth(spec))
    errors.extend(check_stable_keys(spec))
    return errors


# --------------------------------------------------------------------- stats

def spec_stats(spec):
    """Cheap structural counts used by lint output and acceptance evidence."""
    stats = {
        "participants": len(spec.get("participants") or []),
        "messages": 0,
        "messagesByKind": {},
        "fragments": 0,
        "fragmentsByKind": {},
        "topLevelFragments": 0,
        "maxDepth": 0,
        "notes": 0,
        "texts": 0,
    }
    for event in spec.get("events") or []:
        if isinstance(event, dict) and event.get("type") == "fragment":
            stats["topLevelFragments"] += 1
    for _path, event in walk_events(spec.get("events") or []):
        if not isinstance(event, dict):
            continue
        kind = event.get("type")
        if kind == "message":
            stats["messages"] += 1
            message_kind = event.get("kind")
            stats["messagesByKind"][message_kind] = stats["messagesByKind"].get(message_kind, 0) + 1
        elif kind == "fragment":
            stats["fragments"] += 1
            fragment_kind = event.get("kind")
            stats["fragmentsByKind"][fragment_kind] = stats["fragmentsByKind"].get(fragment_kind, 0) + 1
        elif kind == "note":
            stats["notes"] += 1
        elif kind == "text":
            stats["texts"] += 1
    for _path, _fragment, depth in walk_fragments_depth(spec.get("events") or []):
        stats["maxDepth"] = max(stats["maxDepth"], depth)
    return stats
