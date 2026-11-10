# -*- coding: utf-8 -*-
"""Sequence-diagram layout: defaults, three passes, fragment bounds, labels.

Coordinate system: page origin top-left, x right, y down, units are drawio
logical pixels. Page height is computed here and never accepted from the spec.

Passes (locked):
  1. measure: wrap every label (NFC text already), compute fragment x bounds;
     then post-order heights (`_measure_heights`).
  2. place (pre-order): assign absolute y via a cursor, build fragments, tabs,
     branches, notes and free text.
  3. labels + emit prep: place message labels with the 3-level degradation,
     then hand the geometry to emit.py.
"""
from __future__ import annotations

import metrics
import ids as ids_module
import semantics

# ---------------------------------------------------------------- constants

DEFAULT_PAGE = {"width": 1600.0, "leftMargin": 35.0, "rightMargin": 35.0}
DEFAULT_LABEL_WIDTH = 220.0
DEFAULT_FRAME_MARGIN = 60.0
DEFAULT_NOTE_WIDTH = 160.0
MIN_PITCH = 162.0

TITLE_Y = 18.0
TITLE_H = 26.0
SUBTITLE_Y = 46.0
SUBTITLE_H = 20.0
HEAD_Y = 96.0
HEAD_W = 150.0
HEAD_H = 46.0
LIFE_TOP = 142.0
FIRST_MSG_Y = 180.0

MESSAGE_GAP = 27.0
LINE_EXTRA = metrics.LINE_STEP  # 14.0
SELF_EXTRA = 24.0
SELF_LOOP_W = 34.0
SELF_LOOP_H = 24.0
SELF_LABEL_GAP = 8.0

FRAME_TAB_H = 24.0
FRAME_HEAD = 16.0
FRAME_BOTTOM_PAD = 14.0
FRAME_GAP = 14.0
BRANCH_SEP = 40.0
TAB_KW_W = 46.0
TAB_PAD = 14.0
# Vertical room taken by an explicit first-operand guard strip (22px strip + 6px gap).
FIRST_GUARD_EXTRA = 28.0

LABEL_GAP = 3.0
LIFELINE_CLEAR = 6.0
LABEL_BOX_PAD = 2.0

NOTE_GAP = 18.0
NOTE_PAD_X = 4.0
NOTE_PAD_Y = 6.0
NOTE_OVER_PAD = 30.0
NOTE_VGAP = 14.0

TEXT_GAP = 12.0
LIFE_BOTTOM_PAD = 34.0
PAGE_BOTTOM_PAD = 34.0

MESSAGE_FONT_SIZE = 11
HEADER_FONT_SIZE = 12
GUARD_FONT_SIZE = 11
NOTE_FONT_SIZE = 10
TITLE_FONT_SIZE = 16
SUBTITLE_FONT_SIZE = 10
TEXT_FONT_SIZE = 11


def _error(code, message, path="", details=None):
    return semantics.make_error(code, message, path, details)


def _warning(code, message, path="", details=None):
    return semantics.make_error(code, message, path, details)


class FontBook:
    """Resolves the CJK/Latin font for a text run and caches by (family, size)."""

    def __init__(self, paths):
        self._paths = paths
        self._cache = {}

    def get(self, text, size):
        family = "cjk" if metrics.needs_cjk_font(text) else "latin"
        key = (family, int(size))
        if key not in self._cache:
            self._cache[key] = metrics.load_font(self._paths[family], key[1], index=0)
        return self._cache[key]


# --------------------------------------------------------------- defaults

def resolve_options(spec):
    """Merge spec overrides onto the locked defaults (code-side fallbacks)."""
    page = dict(DEFAULT_PAGE)
    overrides = spec.get("page") or {}
    for key in ("width", "leftMargin", "rightMargin"):
        if overrides.get(key) is not None:
            page[key] = float(overrides[key])
    defaults = {"labelWidth": DEFAULT_LABEL_WIDTH, "frameMargin": DEFAULT_FRAME_MARGIN}
    for key in ("labelWidth", "frameMargin"):
        value = (spec.get("defaults") or {}).get(key)
        if value is not None:
            defaults[key] = float(value)
    return page, defaults


# --------------------------------------------------------------- measuring

def _measure_text_run(text, width, size, fonts):
    font = fonts.get(text, size)
    lines = metrics.wrap_text(text, width, font)
    return {
        "lines": lines,
        "w": metrics.text_width(lines, font) + 2.0 * LABEL_BOX_PAD,
        "h": metrics.text_height(lines, font),
        "family": metrics.font_family(text),
    }


def _measure_events(events, base, x_by_id, page, defaults, fonts, measures, bounds, errors):
    """Pre-order measure: text wrapping for every node + fragment x bounds."""
    used = []
    for index, event in enumerate(events):
        path = "%s/%d" % (base, index)
        kind = event.get("type")
        if kind == "message":
            label_width = event.get("labelWidth") or defaults["labelWidth"]
            measures[path] = _measure_text_run(event["label"], label_width, MESSAGE_FONT_SIZE, fonts)
            used.extend([x_by_id[event["from"]], x_by_id[event["to"]]])
        elif kind == "note":
            target = event.get("target")
            targets = target if isinstance(target, list) else [target]
            target_xs = [x_by_id[item] for item in targets]
            label_width = event.get("labelWidth") or DEFAULT_NOTE_WIDTH
            span = max(target_xs) - min(target_xs)
            if event["position"] == "over" and len(targets) > 1:
                outer_width = max(label_width, span + 2.0 * NOTE_OVER_PAD)
            else:
                outer_width = label_width
            font = fonts.get(event["text"], NOTE_FONT_SIZE)
            inner_width = max(20.0, outer_width - 2.0 * NOTE_PAD_X)
            lines = metrics.wrap_text(event["text"], inner_width, font)
            if event["position"] == "over" and len(targets) > 1:
                width = outer_width
            else:
                width = max(60.0, min(outer_width, metrics.text_width(lines, font) + 2.0 * NOTE_PAD_X))
            measures[path] = {
                "lines": lines,
                "w": width,
                "h": metrics.text_height(lines, font) + 2.0 * NOTE_PAD_Y,
                "family": metrics.font_family(event["text"]),
            }
            used.extend(target_xs)
        elif kind == "text":
            width = event.get("width") or (page["width"] - page["leftMargin"] - page["rightMargin"])
            measures[path] = _measure_text_run(event["text"], float(width), TEXT_FONT_SIZE, fonts)
            measures[path]["w"] = float(width)
        elif kind == "fragment":
            child_used = []
            for branch_index, branch in enumerate(event.get("branches") or []):
                child_used.extend(_measure_events(
                    branch.get("events") or [],
                    "%s/branches/%d/events" % (path, branch_index),
                    x_by_id, page, defaults, fonts, measures, bounds, errors,
                ))
            margin = defaults["frameMargin"]
            if child_used:
                left = min(child_used) - margin
                right = max(child_used) + margin
            else:
                left = page["leftMargin"]
                right = page["width"] - page["rightMargin"]
            overrides = event.get("bounds") or {}
            if overrides.get("left") is not None:
                left = float(overrides["left"])
            if overrides.get("right") is not None:
                right = float(overrides["right"])
            if not (0.0 <= left < right <= page["width"]):
                errors.append(_error(
                    "E_PAGE_OVERFLOW",
                    "Fragment bounds [%.1f, %.1f] fall outside the page [0, %.1f] or are inverted."
                    % (left, right, page["width"]),
                    path,
                    {"left": left, "right": right, "pageWidth": page["width"]},
                ))
            bounds[path] = (left, right)
            used.extend(child_used)
    return used


def _measure_heights(events, base, measures, heights):
    """Post-order height pass; returns the total advance of `events`."""
    total = 0.0
    for index, event in enumerate(events):
        path = "%s/%d" % (base, index)
        kind = event.get("type")
        if kind == "message":
            lines = measures[path]["lines"]
            advance = LINE_EXTRA * (len(lines) - 1) + MESSAGE_GAP
            if event["from"] == event["to"]:
                advance += SELF_EXTRA
        elif kind == "note":
            advance = measures[path]["h"] + NOTE_VGAP
        elif kind == "text":
            advance = measures[path]["h"] + TEXT_GAP
        elif kind == "fragment":
            branches = event.get("branches") or []
            child_total = 0.0
            for branch_index, branch in enumerate(branches):
                child_total += _measure_heights(
                    branch.get("events") or [],
                    "%s/branches/%d/events" % (path, branch_index),
                    measures, heights,
                )
            advance = (
                FRAME_TAB_H + FRAME_HEAD
                + child_total
                + BRANCH_SEP * (len(branches) - 1)
                + FRAME_BOTTOM_PAD + FRAME_GAP
            )
        else:
            advance = 0.0
        heights[path] = {"advance": advance, "frameHeight": advance - FRAME_GAP if kind == "fragment" else 0.0}
        total += advance
    return total


# --------------------------------------------------------------- placement

def _place_events(events, base, cursor, ctx, frame_stack):
    """Pre-order placement: assign absolute y, build fragments/notes/texts."""
    for index, event in enumerate(events):
        path = "%s/%d" % (base, index)
        kind = event.get("type")
        if kind == "message":
            item = ctx["measures"][path]
            lines = item["lines"]
            y = cursor + LINE_EXTRA * (len(lines) - 1)
            self_message = event["from"] == event["to"]
            ctx["messages"].append({
                "id": ctx["ids"][path],
                "path": path,
                "kind": event["kind"],
                "from": event["from"],
                "to": event["to"],
                "x1": ctx["x_by_id"][event["from"]],
                "x2": ctx["x_by_id"][event["to"]],
                "y": y,
                "self": self_message,
                "w": item["w"],
                "h": item["h"],
                "lines": lines,
                "family": item["family"],
                "frames": tuple(frame_stack),
                "level": None,
                "label": None,
                "bg": None,
            })
            cursor = y + MESSAGE_GAP + (SELF_EXTRA if self_message else 0.0)
        elif kind == "note":
            item = ctx["measures"][path]
            target = event.get("target")
            targets = target if isinstance(target, list) else [target]
            target_xs = [ctx["x_by_id"][item] for item in targets]
            position = event["position"]
            width = item["w"]
            height = item["h"]
            if position == "right":
                x = max(target_xs) + NOTE_GAP
            elif position == "left":
                x = min(target_xs) - NOTE_GAP - width
            else:
                x = (min(target_xs) + max(target_xs)) / 2.0 - width / 2.0
            box = {"x": x, "y": cursor, "w": width, "h": height}
            anchor = None
            if position in ("left", "right"):
                anchor_x = max(target_xs) if position == "right" else min(target_xs)
                anchor = {
                    "x1": box["x"] if position == "right" else box["x"] + width,
                    "y1": cursor + height / 2.0,
                    "x2": anchor_x,
                    "y2": cursor + height / 2.0,
                }
            if (x < ctx["page"]["leftMargin"]
                    or x + width > ctx["page"]["width"] - ctx["page"]["rightMargin"]):
                ctx["errors"].append(_error(
                    "E_PAGE_OVERFLOW",
                    "Note box [%.1f, %.1f] falls outside the page margins." % (x, x + width),
                    path,
                    {"x": x, "width": width},
                ))
            ctx["notes"].append({
                "id": ctx["ids"][path],
                "path": path,
                "targets": targets,
                "position": position,
                "text": event["text"],
                "lines": item["lines"],
                "family": item["family"],
                "box": box,
                "anchor": anchor,
            })
            cursor += height + NOTE_VGAP
        elif kind == "text":
            item = ctx["measures"][path]
            width = item["w"]
            box = {"x": ctx["page"]["leftMargin"], "y": cursor, "w": width, "h": item["h"]}
            if box["x"] + width > ctx["page"]["width"] - ctx["page"]["rightMargin"]:
                ctx["errors"].append(_error(
                    "E_PAGE_OVERFLOW",
                    "Free text box exceeds the page width.",
                    path,
                    {"x": box["x"], "width": width},
                ))
            ctx["texts"].append({
                "id": ctx["ids"][path],
                "path": path,
                "text": event["text"],
                "lines": item["lines"],
                "family": item["family"],
                "align": event.get("align") or "left",
                "box": box,
            })
            cursor += item["h"] + TEXT_GAP
        elif kind == "fragment":
            left, right = ctx["bounds"][path]
            top = cursor
            cursor += FRAME_TAB_H + FRAME_HEAD
            guard = event["guard"]
            guard_font = ctx["fonts"].get(guard, GUARD_FONT_SIZE)
            tab_width = TAB_KW_W + metrics.measure_text(guard_font, guard) + TAB_PAD
            frame = {
                "id": ctx["ids"][path],
                "path": path,
                "kind": event["kind"],
                "guard": guard,
                "top": top,
                "bottom": None,
                "left": left,
                "right": right,
                "family": metrics.font_family(guard),
                "tab": {"x": left, "y": top, "w": tab_width, "h": FRAME_TAB_H},
                "kw": {"x": left, "y": top, "w": TAB_KW_W, "h": FRAME_TAB_H},
                "guard_box": {
                    "x": left + TAB_KW_W,
                    "y": top,
                    "w": max(10.0, tab_width - TAB_KW_W),
                    "h": FRAME_TAB_H,
                },
                "frames": tuple(frame_stack),
                "branches": [],
            }
            ctx["frames"].append(frame)
            stack = frame_stack + [frame]
            branches = event.get("branches") or []
            for branch_index, branch in enumerate(branches):
                entry = {
                    "guard": branch.get("guard"),
                    "divider_y": None,
                    "strip": None,
                    "guard_box": None,
                    "family": None,
                }
                if branch_index == 0:
                    # The first operand's guard is normally inherited from the frame
                    # guard (shown in the tab). When it is declared explicitly and
                    # differs, it still has to be drawn as its own strip -- otherwise
                    # that condition would be silently dropped from the diagram.
                    branch_guard = branch.get("guard")
                    if branch_guard not in (None, "") and branch_guard != guard:
                        branch_font = ctx["fonts"].get(branch_guard, GUARD_FONT_SIZE)
                        guard_width = metrics.measure_text(branch_font, branch_guard)
                        strip_y = cursor + 2.0
                        entry["strip"] = {
                            "x": left + 4.0,
                            "y": strip_y,
                            "w": guard_width + 24.0,
                            "h": 22.0,
                        }
                        entry["guard_box"] = {
                            "x": left + 8.0,
                            "y": strip_y,
                            "w": guard_width + 16.0,
                            "h": 22.0,
                        }
                        entry["family"] = metrics.font_family(branch_guard)
                        cursor += FIRST_GUARD_EXTRA
                else:
                    divider_y = cursor + 8.0
                    branch_guard = branch["guard"]
                    branch_font = ctx["fonts"].get(branch_guard, GUARD_FONT_SIZE)
                    guard_width = metrics.measure_text(branch_font, branch_guard)
                    entry["divider_y"] = divider_y
                    entry["strip"] = {
                        "x": left + 4.0,
                        "y": divider_y + 3.0,
                        "w": guard_width + 24.0,
                        "h": 22.0,
                    }
                    entry["guard_box"] = {
                        "x": left + 8.0,
                        "y": divider_y + 3.0,
                        "w": guard_width + 16.0,
                        "h": 22.0,
                    }
                    entry["family"] = metrics.font_family(branch_guard)
                    cursor += BRANCH_SEP
                frame["branches"].append(entry)
                cursor = _place_events(
                    branch.get("events") or [],
                    "%s/branches/%d/events" % (path, branch_index),
                    cursor, ctx, stack,
                )
            bottom = cursor + FRAME_BOTTOM_PAD
            frame["bottom"] = bottom
            cursor = bottom + FRAME_GAP
    return cursor


# ------------------------------------------------------------ label placement

def _rects_overlap(a, b):
    return (
        a["x"] < b["x"] + b["w"]
        and b["x"] < a["x"] + a["w"]
        and a["y"] < b["y"] + b["h"]
        and b["y"] < a["y"] + a["h"]
    )


def _collides(box, occupied):
    return any(_rects_overlap(box, rect) for rect in occupied)


def _inside(box, container):
    if container is None:
        return True
    return (
        box["x"] >= container["left"]
        and box["x"] + box["w"] <= container["right"]
        and box["y"] >= container["top"]
        and box["y"] + box["h"] <= container["bottom"]
    )


def _crosses_lifelines(box, xs, life_top=0.0, life_bottom=float("inf")):
    if box["y"] + box["h"] <= life_top or box["y"] >= life_bottom:
        return False
    return any(box["x"] <= x <= box["x"] + box["w"] for x in xs)


def place_message_label(x_from, x_to, y, width, height, xs, x_index, occupied,
                        life_top, life_bottom, page_width, container=None):
    """Three-level label placement for a horizontal message.

    Level 1: land in a gap between adjacent lifelines inside the message span,
             nearest the sender first. Level 2: centered over the endpoints with
             a white background (may cover lifelines). Level 3: None.
    """
    band_y = y - LABEL_GAP - height
    from_index = x_index[x_from]
    to_index = x_index[x_to]
    low, high = (from_index, to_index) if from_index <= to_index else (to_index, from_index)
    center_x = (x_from + x_to) / 2.0

    gaps = []
    for gap_index in range(low, high):
        left = xs[gap_index] + LIFELINE_CLEAR
        right = xs[gap_index + 1] - LIFELINE_CLEAR
        if right - left >= width:
            gaps.append((abs(gap_index - from_index), gap_index, left, right))
    gaps.sort()

    for _distance, _gap_index, left, right in gaps:
        for raw in (center_x - width / 2.0, left, right - width):
            x = min(max(raw, left), right - width)
            box = {"x": x, "y": band_y, "w": width, "h": height}
            if x < 0.0 or x + width > page_width:
                continue
            if not _inside(box, container):
                continue
            if _collides(box, occupied):
                continue
            if _crosses_lifelines(box, xs, life_top, life_bottom):
                continue
            return {"level": 1, "box": box}

    box = {"x": center_x - width / 2.0, "y": band_y, "w": width, "h": height}
    if (0.0 <= box["x"] and box["x"] + width <= page_width
            and _inside(box, container) and not _collides(box, occupied)):
        return {"level": 2, "box": box}
    return None


def place_self_label(x, y, width, height, xs, occupied,
                     life_top, life_bottom, page_width, container=None):
    """Self-message label: left of the loop first, then right of it."""
    center_y = y + SELF_LOOP_H / 2.0 + 4.0
    top = center_y - height / 2.0
    for side in ("left", "right"):
        if side == "left":
            box_x = x - SELF_LOOP_W - SELF_LABEL_GAP - width
            align = "right"
        else:
            box_x = x + SELF_LOOP_W + SELF_LABEL_GAP
            align = "left"
        box = {"x": box_x, "y": top, "w": width, "h": height}
        if box_x < 0.0 or box_x + width > page_width:
            continue
        if not _inside(box, container):
            continue
        if _collides(box, occupied):
            continue
        level = 2 if _crosses_lifelines(box, xs, life_top, life_bottom) else 1
        return {"level": level, "box": box, "align": align}
    return None


def _frame_container(message):
    if not message["frames"]:
        return None
    frame = message["frames"][-1]
    return {
        "left": frame["left"],
        "right": frame["right"],
        "top": frame["top"],
        "bottom": frame["bottom"],
    }


def _place_labels(ctx):
    occupied = []
    for frame in ctx["frames"]:
        left, right = frame["left"], frame["right"]
        top, bottom = frame["top"], frame["bottom"]
        occupied.extend([
            {"x": left, "y": top, "w": 1.0, "h": bottom - top, "kind": "frame"},
            {"x": right - 1.0, "y": top, "w": 1.0, "h": bottom - top, "kind": "frame"},
            {"x": left, "y": top, "w": right - left, "h": 1.0, "kind": "frame"},
            {"x": left, "y": bottom - 1.0, "w": right - left, "h": 1.0, "kind": "frame"},
        ])
        occupied.append(dict(frame["tab"], kind="tab"))
        for branch in frame["branches"]:
            if branch["strip"] is not None:
                occupied.append(dict(branch["strip"], kind="strip"))
            if branch["divider_y"] is not None:
                occupied.append({
                    "x": left,
                    "y": branch["divider_y"],
                    "w": right - left,
                    "h": 1.0,
                    "kind": "divider",
                })
    for note in ctx["notes"]:
        occupied.append(dict(note["box"], kind="note"))
    for text in ctx["texts"]:
        occupied.append(dict(text["box"], kind="text"))
    for participant in ctx["participants"]:
        occupied.append(dict(participant["header"], kind="header"))

    xs = [participant["x"] for participant in ctx["participants"]]
    x_index = {participant["x"]: index for index, participant in enumerate(ctx["participants"])}
    life_top = LIFE_TOP
    life_bottom = ctx["life_bottom"]

    for message in ctx["messages"]:
        container = _frame_container(message)
        if message["self"]:
            placement = place_self_label(
                message["x1"], message["y"], message["w"], message["h"],
                xs, occupied, life_top, life_bottom, ctx["page"]["width"], container,
            )
        else:
            placement = place_message_label(
                message["x1"], message["x2"], message["y"], message["w"], message["h"],
                xs, x_index, occupied, life_top, life_bottom, ctx["page"]["width"], container,
            )
        if placement is None:
            ctx["errors"].append(_error(
                "E_LABEL_IMPOSSIBLE",
                "No legal placement for the message label (level 1 and level 2 both blocked).",
                message["path"],
                {"width": message["w"], "height": message["h"], "y": message["y"], "self": message["self"]},
            ))
            continue
        box = placement["box"]
        message["level"] = placement["level"]
        message["label"] = {
            "x": box["x"],
            "y": box["y"],
            "w": box["w"],
            "h": box["h"],
            "align": placement.get("align", "center"),
            "family": message["family"],
        }
        if placement["level"] == 2:
            message["bg"] = {
                "x": box["x"] - 1.0,
                "y": box["y"] - 1.0,
                "w": box["w"] + 2.0,
                "h": box["h"] + 2.0,
            }
            occupied.append(dict(message["bg"], kind="label-bg"))
            ctx["label_warnings"].append(_warning(
                "W_LABEL_OVER_LIFELINE",
                "Message label placed level-2 (centered over lifelines with a white background).",
                message["path"],
                {"level": 2},
            ))
        else:
            occupied.append(dict(box, kind="label"))


# ---------------------------------------------------------------- warnings

def _return_warnings(messages):
    warnings = []
    stacks = {}
    for message in messages:
        if message["kind"] == "call":
            stacks.setdefault(message["to"], []).append(message["from"])
        elif message["kind"] == "reply":
            stack = stacks.setdefault(message["from"], [])
            if stack:
                stack.pop()
            else:
                warnings.append(_warning(
                    "W_RETURN_WITHOUT_CALL",
                    "Reply from %s has no open call to return from." % (message["from"],),
                    message["path"],
                    {"from": message["from"], "to": message["to"]},
                ))
    return warnings


def _unused_warnings(participants, messages, notes):
    used = set()
    for message in messages:
        used.add(message["from"])
        used.add(message["to"])
    for note in notes:
        used.update(note["targets"])
    return [
        _warning(
            "W_UNUSED_PARTICIPANT",
            "Participant %r is never referenced by a message or note." % (participant["id"],),
            "/participants/%d" % (index,),
            {"id": participant["id"]},
        )
        for index, participant in enumerate(participants)
        if participant["id"] not in used
    ]


def _large_warning(message_count, page_height):
    if message_count > 80 or page_height > 4000.0:
        return _warning(
            "W_LARGE_DIAGRAM",
            "Diagram is large (%d messages, page height %.0f); consider splitting it into pages."
            % (message_count, page_height),
            "",
            {"messages": message_count, "pageHeight": page_height},
        )
    return None


# ---------------------------------------------------------------- entry point

def layout_spec(spec, font_paths):
    """Run the full layout; returns a dict with geometry or `errors`."""
    page, defaults = resolve_options(spec)
    result = {
        "ok": False,
        "errors": [],
        "warnings": [],
        "page": {"width": page["width"], "height": 0.0},
        "pitch": 0.0,
        "participants": [],
        "life_top": LIFE_TOP,
        "life_bottom": 0.0,
        "title": None,
        "subtitle": None,
        "frames": [],
        "messages": [],
        "notes": [],
        "texts": [],
        "stats": {},
        "diagram_id": ids_module.diagram_id(spec.get("title")),
    }

    participants_spec = spec.get("participants") or []
    count = len(participants_spec)
    pitch = (page["width"] - page["leftMargin"] - page["rightMargin"]) / count
    result["pitch"] = pitch
    if pitch < MIN_PITCH:
        result["errors"].append(_error(
            "E_PAGE_OVERFLOW",
            "Participant pitch %.1f is below the minimum %.1f; widen page.width to at least %.0f."
            % (pitch, MIN_PITCH, count * MIN_PITCH + page["leftMargin"] + page["rightMargin"]),
            "/page/width",
            {"pitch": pitch, "minPitch": MIN_PITCH, "participants": count},
        ))
        return result

    xs = [page["leftMargin"] + pitch * (index + 0.5) for index in range(count)]
    x_by_id = {participant["id"]: xs[index] for index, participant in enumerate(participants_spec)}

    id_map, id_errors = ids_module.assign_ids(spec)
    if id_errors:
        result["errors"] = id_errors
        return result

    try:
        fonts = FontBook(font_paths)
        measures = {}
        bounds = {}
        measure_errors = []
        _measure_events(
            spec.get("events") or [], "/events", x_by_id, page, defaults,
            fonts, measures, bounds, measure_errors,
        )
        if measure_errors:
            result["errors"] = measure_errors
            return result

        heights = {}
        _measure_heights(spec.get("events") or [], "/events", measures, heights)

        result["participants"] = [
            {
                "id": participant["id"],
                "name": participant["name"],
                "x": xs[index],
                "family": metrics.font_family(participant["name"]),
                "header": {"x": xs[index] - HEAD_W / 2.0, "y": HEAD_Y, "w": HEAD_W, "h": HEAD_H},
            }
            for index, participant in enumerate(participants_spec)
        ]

        ctx = {
            "page": page,
            "defaults": defaults,
            "fonts": fonts,
            "ids": id_map,
            "bounds": bounds,
            "measures": measures,
            "x_by_id": x_by_id,
            "participants": result["participants"],
            "messages": result["messages"],
            "frames": result["frames"],
            "notes": result["notes"],
            "texts": result["texts"],
            "errors": result["errors"],
            "label_warnings": [],
            "life_bottom": 0.0,
        }
        cursor = _place_events(spec.get("events") or [], "/events", FIRST_MSG_Y, ctx, [])
        life_bottom = cursor + LIFE_BOTTOM_PAD
        page_height = life_bottom + PAGE_BOTTOM_PAD
        result["life_bottom"] = life_bottom
        result["page"]["height"] = page_height
        ctx["life_bottom"] = life_bottom

        margin = page["leftMargin"]
        content_width = page["width"] - page["leftMargin"] - page["rightMargin"]
        if spec.get("title"):
            title_text = spec["title"]
            title_font = fonts.get(title_text, TITLE_FONT_SIZE)
            result["title"] = {
                "text": title_text,
                "lines": metrics.wrap_text(title_text, content_width, title_font),
                "family": metrics.font_family(title_text),
                "x": margin,
                "y": TITLE_Y,
                "w": content_width,
                "h": TITLE_H,
            }
        if spec.get("subtitle"):
            subtitle_text = spec["subtitle"]
            subtitle_font = fonts.get(subtitle_text, SUBTITLE_FONT_SIZE)
            result["subtitle"] = {
                "text": subtitle_text,
                "lines": metrics.wrap_text(subtitle_text, content_width, subtitle_font),
                "family": metrics.font_family(subtitle_text),
                "x": margin,
                "y": SUBTITLE_Y,
                "w": content_width,
                "h": SUBTITLE_H,
            }

        _place_labels(ctx)

        if result["errors"]:
            return result

        label_levels = {"1": 0, "2": 0, "self": 0}
        for message in result["messages"]:
            if message["self"]:
                label_levels["self"] += 1
            if message["level"] == 1:
                label_levels["1"] += 1
            elif message["level"] == 2:
                label_levels["2"] += 1

        stats = semantics.spec_stats(spec)
        stats["labelLevels"] = label_levels
        stats["page"] = {"width": page["width"], "height": page_height}
        result["stats"] = stats

        warnings = []
        warnings.extend(_unused_warnings(result["participants"], result["messages"], result["notes"]))
        warnings.extend(_return_warnings(result["messages"]))
        warnings.extend(ctx["label_warnings"])
        large = _large_warning(len(result["messages"]), page_height)
        if large is not None:
            warnings.append(large)
        result["warnings"] = warnings
        result["ok"] = True
        return result
    except metrics.FontMissing as exc:
        result["errors"].append(_error("E_FONT_MISSING", str(exc), "", {"path": exc.path}))
        return result
