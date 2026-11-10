# -*- coding: utf-8 -*-
"""Deterministic, uncompressed draw.io XML emitter for dsh-uml-drawio.

Emit order is the locked Z order:
    lifelines -> frame borders -> tabs/guards/dividers -> message edges ->
    level-2 white backgrounds -> message labels -> notes -> participant headers
    -> title/subtitle/free text.

No timestamps, no host versions, no random values; every geometry coordinate is
formatted with "%.1f", newlines inside XML attributes become "&#10;".
"""
from __future__ import annotations

import math
import xml.etree.ElementTree as ET

ST_LIFE = "endArrow=none;dashed=1;html=0;strokeColor=#8C8C8C;strokeWidth=1;"
ST_CALL = (
    "endArrow=block;endFill=1;endSize=7;html=0;rounded=0;edgeStyle=none;"
    "strokeColor=#000000;strokeWidth=1;"
)
ST_ASYNC = (
    "endArrow=open;endFill=0;endSize=7;html=0;rounded=0;edgeStyle=none;"
    "strokeColor=#000000;strokeWidth=1;"
)
ST_REPLY = (
    "endArrow=open;endFill=0;endSize=7;dashed=1;html=0;rounded=0;edgeStyle=none;"
    "strokeColor=#000000;strokeWidth=1;"
)
ST_FRAME = "rounded=0;whiteSpace=wrap;html=0;fillColor=none;strokeColor=#000000;strokeWidth=1;"
ST_TAB = "rounded=0;whiteSpace=wrap;html=0;fillColor=#FFFFFF;strokeColor=#000000;strokeWidth=1;"
ST_KW = (
    "text;html=0;whiteSpace=nowrap;align=center;verticalAlign=middle;fontSize=11;"
    "fontStyle=1;fontFamily=Helvetica;fontColor=#000000;"
)
ST_GUARD = (
    "text;html=0;whiteSpace=nowrap;align=left;verticalAlign=middle;fontSize=11;"
    "fontFamily=%s;fontColor=#000000;spacingLeft=2;"
)
ST_DIV = "endArrow=none;dashed=1;html=0;strokeColor=#000000;strokeWidth=1;"
ST_NOTE = (
    "shape=note;size=14;whiteSpace=wrap;html=0;fillColor=#FFE6CC;strokeColor=#D79B00;"
    "fontSize=10;fontFamily=%s;align=left;verticalAlign=top;spacingLeft=4;spacingTop=2;"
    "spacingRight=4;fontColor=#000000;"
)
ST_ANCHOR = "endArrow=none;dashed=1;html=0;strokeColor=#D79B00;strokeWidth=1;"
# F3: the white level-2 background is a separate rect; no labelBackgroundColor here.
ST_LABEL = (
    "text;html=0;whiteSpace=nowrap;align=%s;verticalAlign=middle;fontSize=11;"
    "fontFamily=%s;fontColor=#000000;"
)
ST_BG = "rounded=0;whiteSpace=wrap;html=0;fillColor=#FFFFFF;strokeColor=none;"
ST_HEADER = (
    "rounded=0;whiteSpace=wrap;html=0;fillColor=#DAE8FC;strokeColor=#6C8EBF;"
    "fontColor=#000000;fontSize=12;fontStyle=1;fontFamily=%s;"
)
ST_TITLE = (
    "text;html=0;whiteSpace=wrap;align=center;verticalAlign=middle;fontSize=16;"
    "fontStyle=1;fontFamily=%s;fontColor=#000000;"
)
ST_SUBTITLE = (
    "text;html=0;whiteSpace=wrap;align=center;verticalAlign=middle;fontSize=10;"
    "fontFamily=%s;fontColor=#595959;"
)
ST_TEXT = (
    "text;html=0;whiteSpace=wrap;align=%s;verticalAlign=top;fontSize=11;"
    "fontFamily=%s;fontColor=#000000;"
)

_ESCAPES = (("&", "&amp;"), ("<", "&lt;"), (">", "&gt;"), ('"', "&quot;"))


def esc(value):
    """XML attribute escape; newlines must survive as &#10;."""
    text = str(value if value is not None else "")
    text = text.replace("\r", "")
    for source, target in _ESCAPES:
        text = text.replace(source, target)
    return text.replace("\n", "&#10;")


def num(value):
    """Every geometry coordinate uses %.1f; -0.0 is normalised to 0.0."""
    rounded = round(float(value), 1)
    if rounded == 0.0:
        rounded = 0.0
    return "%.1f" % rounded


def _vertex(cell_id, value, style, box):
    return (
        '<mxCell id="%s" value="%s" style="%s" vertex="1" parent="1">'
        '<mxGeometry x="%s" y="%s" width="%s" height="%s" as="geometry"/>'
        "</mxCell>"
        % (
            esc(cell_id), esc(value), esc(style),
            num(box["x"]), num(box["y"]), num(box["w"]), num(box["h"]),
        )
    )


def _edge(cell_id, style, points):
    source = points[0]
    target = points[-1]
    geometry = '<mxGeometry relative="1" as="geometry">'
    geometry += '<mxPoint x="%s" y="%s" as="sourcePoint"/>' % (num(source[0]), num(source[1]))
    geometry += '<mxPoint x="%s" y="%s" as="targetPoint"/>' % (num(target[0]), num(target[1]))
    if len(points) > 2:
        geometry += '<Array as="points">'
        for x, y in points[1:-1]:
            geometry += '<mxPoint x="%s" y="%s"/>' % (num(x), num(y))
        geometry += "</Array>"
    geometry += "</mxGeometry>"
    return (
        '<mxCell id="%s" value="" style="%s" edge="1" parent="1">%s</mxCell>'
        % (esc(cell_id), esc(style), geometry)
    )


def _message_style(kind):
    if kind == "async":
        return ST_ASYNC
    if kind == "reply":
        return ST_REPLY
    return ST_CALL


def _text_value(lines):
    return "\n".join(lines)


def _white_unit_lifelines(box, lifelines):
    """Lifelines strictly inside a white unit (tab or else-guard strip).

    Those segments are redrawn after the white rect (and before the unit text)
    so the lifeline never looks broken behind a tab or guard strip. Level-2
    label backgrounds are deliberately exempt: they carry
    W_LABEL_OVER_LIFELINE and must be allowed to cover lifelines.
    """
    left = box["x"]
    right = box["x"] + box["w"]
    return [(participant_id, x) for participant_id, x in lifelines if left + 0.01 < x < right - 0.01]


def emit_xml(layout, diagram_title):
    """Return (xml_text, element_count) for a successful layout."""
    page = layout["page"]
    page_width = page["width"]
    page_height = page["height"]

    cells = []
    lifelines = [(participant["id"], participant["x"]) for participant in layout["participants"]]

    # 1. lifelines
    for participant in layout["participants"]:
        cells.append(_edge(
            "l_" + participant["id"], ST_LIFE,
            [(participant["x"], layout["life_top"]), (participant["x"], layout["life_bottom"])],
        ))

    # 2. frame borders (outer first)
    for frame in layout["frames"]:
        cells.append(_vertex(
            frame["id"] + "_border", "", ST_FRAME,
            {
                "x": frame["left"], "y": frame["top"],
                "w": frame["right"] - frame["left"],
                "h": frame["bottom"] - frame["top"],
            },
        ))

    # 3. tabs, keywords, top guards, branch strips/guards/dividers
    for frame in layout["frames"]:
        cells.append(_vertex(frame["id"] + "_tab", "", ST_TAB, frame["tab"]))
        # P0: a white tab/flap must never look like it cuts the lifeline.
        for participant_id, lifeline_x in _white_unit_lifelines(frame["tab"], lifelines):
            cells.append(_edge(
                "%s_tab_life_%s" % (frame["id"], participant_id), ST_LIFE,
                [(lifeline_x, frame["tab"]["y"]),
                 (lifeline_x, frame["tab"]["y"] + frame["tab"]["h"])],
            ))
        cells.append(_vertex(frame["id"] + "_kw", frame["kind"], ST_KW, frame["kw"]))
        cells.append(_vertex(
            frame["id"] + "_guard", frame["guard"], ST_GUARD % frame["family"], frame["guard_box"],
        ))
        for branch_index, branch in enumerate(frame["branches"]):
            if branch["strip"] is None:
                continue
            cells.append(_vertex(
                "%s_b%d_strip" % (frame["id"], branch_index), "", ST_BG, branch["strip"],
            ))
            for participant_id, lifeline_x in _white_unit_lifelines(branch["strip"], lifelines):
                cells.append(_edge(
                    "%s_b%d_strip_life_%s" % (frame["id"], branch_index, participant_id), ST_LIFE,
                    [(lifeline_x, branch["strip"]["y"]),
                     (lifeline_x, branch["strip"]["y"] + branch["strip"]["h"])],
                ))
            cells.append(_vertex(
                "%s_b%d_guard" % (frame["id"], branch_index),
                branch["guard"], ST_GUARD % branch["family"], branch["guard_box"],
            ))
            # The first operand has no divider line; only later branches do.
            if branch["divider_y"] is not None:
                cells.append(_edge(
                    "%s_b%d_div" % (frame["id"], branch_index), ST_DIV,
                    [(frame["left"], branch["divider_y"]), (frame["right"], branch["divider_y"])],
                ))

    # 4. message edges
    for message in layout["messages"]:
        style = _message_style(message["kind"])
        if message["self"]:
            x = message["x1"]
            y = message["y"]
            points = [(x, y), (x - 34.0, y), (x - 34.0, y + 24.0), (x, y + 24.0)]
        else:
            points = [(message["x1"], message["y"]), (message["x2"], message["y"])]
        cells.append(_edge(message["id"], style, points))

    # 5. level-2 white backgrounds
    for message in layout["messages"]:
        if message["bg"] is not None:
            cells.append(_vertex(message["id"] + "_bg", "", ST_BG, message["bg"]))

    # 6. message labels
    for message in layout["messages"]:
        if message["label"] is None:
            continue
        style = ST_LABEL % (message["label"]["align"], message["label"]["family"])
        cells.append(_vertex(
            message["id"] + "_label", _text_value(message["lines"]), style, message["label"],
        ))

    # 7. notes + anchors
    for note in layout["notes"]:
        if note["anchor"] is not None:
            cells.append(_edge(
                note["id"] + "_anchor", ST_ANCHOR,
                [(note["anchor"]["x1"], note["anchor"]["y1"]),
                 (note["anchor"]["x2"], note["anchor"]["y2"])],
            ))
        cells.append(_vertex(
            note["id"], _text_value(note["lines"]), ST_NOTE % note["family"], note["box"],
        ))

    # 8. participant headers
    for participant in layout["participants"]:
        cells.append(_vertex(
            "p_" + participant["id"], participant["name"],
            ST_HEADER % participant["family"], participant["header"],
        ))

    # 9. title, subtitle, free text
    if layout["title"] is not None:
        title = layout["title"]
        cells.append(_vertex(
            "t_title", _text_value(title["lines"]), ST_TITLE % title["family"],
            {"x": title["x"], "y": title["y"], "w": title["w"], "h": title["h"]},
        ))
    if layout["subtitle"] is not None:
        subtitle = layout["subtitle"]
        cells.append(_vertex(
            "t_subtitle", _text_value(subtitle["lines"]), ST_SUBTITLE % subtitle["family"],
            {"x": subtitle["x"], "y": subtitle["y"], "w": subtitle["w"], "h": subtitle["h"]},
        ))
    for text in layout["texts"]:
        cells.append(_vertex(
            text["id"], _text_value(text["lines"]), ST_TEXT % (text["align"], text["family"]),
            text["box"],
        ))

    body = "\n".join("        " + cell for cell in cells)
    xml_text = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<mxfile host="app.diagrams.net" type="device">\n'
        '  <diagram id="%s" name="%s">\n'
        '    <mxGraphModel grid="0" gridSize="10" guides="1" tooltips="1" connect="1" '
        'arrows="1" fold="1" page="1" pageScale="1" pageWidth="%.0f" pageHeight="%.0f" '
        'math="0" shadow="0">\n'
        "      <root>\n"
        '        <mxCell id="0"/>\n'
        '        <mxCell id="1" parent="0"/>\n'
        "%s\n"
        "      </root>\n"
        "    </mxGraphModel>\n"
        "  </diagram>\n"
        "</mxfile>\n"
        % (
            esc(layout["diagram_id"]),
            esc(diagram_title or "Sequence Diagram"),
            page_width,
            math.ceil(page_height),
            body,
        )
    )
    return xml_text, len(cells)


def self_check(xml_text, layout):
    """Structural assertions run before any file is written."""
    root = ET.fromstring(xml_text)
    assert root.tag == "mxfile", "root must be mxfile"
    diagrams = list(root)
    assert len(diagrams) == 1 and diagrams[0].tag == "diagram", "exactly one diagram expected"
    model = diagrams[0].find("mxGraphModel")
    assert model is not None, "mxGraphModel must be a child of diagram"
    assert abs(float(model.get("pageWidth")) - layout["page"]["width"]) < 0.51
    assert abs(float(model.get("pageHeight")) - layout["page"]["height"]) < 1.01

    cells = list(model.iter("mxCell"))
    ids = [cell.get("id") for cell in cells]
    assert len(ids) == len(set(ids)), "duplicate cell ids"
    assert "0" in ids and "1" in ids, "base cells missing"

    lowered = xml_text.lower()
    for marker in ("modified=", "etag=", "hostversion=", "base64"):
        assert marker not in lowered, "forbidden marker in output: %s" % marker
    assert xml_text.endswith("\n"), "file must end with a newline"
    return len(cells) - 2
