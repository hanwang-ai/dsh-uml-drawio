# -*- coding: utf-8 -*-
"""Font metrics and line wrapping for dsh-uml-drawio.

Locked rules:
  * CJK text -> msyh.ttc (index 0) + drawio fontFamily "Microsoft YaHei";
    everything else -> arial.ttf + "Helvetica".
  * width = font.getlength(text) * 1.03 (never getbbox()[2]).
  * height = bbox[3] - bbox[1] per line; +4px between lines.
  * explicit "\\n" forces a break; labelWidth triggers wrapping; CJK without
    spaces breaks per character.
"""
from __future__ import annotations

import os
import re

from PIL import ImageFont

# Locked detection range (see the design checklist).
CJK_RE = re.compile(r"[\u4e00-\u9fa5\u3000-\u303f\uff00-\uffef]")
WIDTH_FACTOR = 1.03
# Locked layout rule: every extra label line advances the message pitch by 14px.
# The same 14px is the line step used for a multi-line label box, so the box
# always fits the space reserved before the message line.
LINE_STEP = 14.0
CJK_FAMILY = "Microsoft YaHei"
LATIN_FAMILY = "Helvetica"

_FONT_CACHE = {}


class FontMissing(Exception):
    """Raised when a configured font file cannot be loaded."""

    def __init__(self, path, detail):
        super().__init__("font unavailable: %s (%s)" % (path, detail))
        self.path = path
        self.detail = detail


def needs_cjk_font(text):
    """True when `text` must be rendered with the CJK font."""
    return bool(CJK_RE.search(text or ""))


def font_family(text):
    """drawio fontFamily for a text run."""
    return CJK_FAMILY if needs_cjk_font(text) else LATIN_FAMILY


def load_font(path, size, index=0):
    """Load (and cache) a TrueType/TrueType-Collection font.

    `layout_engine=BASIC` keeps measurements independent of whether libraqm is
    present, so two machines with the same font files produce the same widths.
    """
    key = (os.fspath(path), int(size), int(index))
    cached = _FONT_CACHE.get(key)
    if cached is not None:
        return cached
    if not os.path.isfile(path):
        raise FontMissing(os.fspath(path), "file not found")
    try:
        font = ImageFont.truetype(
            os.fspath(path),
            int(size),
            index=int(index),
            layout_engine=ImageFont.Layout.BASIC,
        )
    except Exception as exc:  # Pillow raises OSError for most failures
        raise FontMissing(os.fspath(path), str(exc)) from exc
    _FONT_CACHE[key] = font
    return font


def measure_text(font, text):
    """Advance width of `text` with the locked 1.03 safety factor."""
    return float(font.getlength(text or "")) * WIDTH_FACTOR


def line_ink_height(font, line):
    """bbox[3]-bbox[1] for one line; empty lines use the 'Ag' reference."""
    sample = line if line != "" else "Ag"
    box = font.getbbox(sample)
    return max(1.0, float(box[3] - box[1]))


def text_height(lines, font):
    """Painted height: first-line ink + LINE_STEP per extra line.

    Using the same 14px step as the message-pitch rule keeps a wrapped label
    inside the space reserved before its message line.
    """
    if not lines:
        return 0.0
    return max(line_ink_height(font, line) for line in lines) + LINE_STEP * (len(lines) - 1)


def text_width(lines, font):
    """Widest wrapped line."""
    if not lines:
        return 0.0
    return max(measure_text(font, line) for line in lines)


def _tokenize(paragraph):
    """Split into wrapping tokens: CJK per character, runs of spaces, Latin words."""
    tokens = []
    buffer = []
    for char in paragraph:
        if CJK_RE.match(char):
            if buffer:
                tokens.append("".join(buffer))
                buffer = []
            tokens.append(char)
        elif char.isspace():
            if buffer:
                tokens.append("".join(buffer))
                buffer = []
            tokens.append(" ")
        else:
            buffer.append(char)
    if buffer:
        tokens.append("".join(buffer))
    return tokens


def _split_prefix(line, max_width, font):
    """Longest prefix of `line` that fits; always consumes at least one char."""
    low, high = 1, len(line) - 1
    best = 1
    while low <= high:
        middle = (low + high) // 2
        if measure_text(font, line[:middle]) <= max_width:
            best = middle
            low = middle + 1
        else:
            high = middle - 1
    return line[:best], line[best:]


def wrap_text(text, max_width, font):
    """Wrap on explicit newlines, spaces and (for CJK) characters.

    Every returned line fits `max_width` unless a single character is wider
    than the budget, in which case it occupies one line by itself.
    """
    max_width = float(max_width)
    result = []
    for paragraph in (text or "").split("\n"):
        if paragraph == "":
            result.append("")
            continue
        if measure_text(font, paragraph) <= max_width:
            result.append(paragraph)
            continue
        line = ""
        for token in _tokenize(paragraph):
            if not line and token == " ":
                continue
            candidate = line + token
            if line and measure_text(font, candidate) > max_width:
                result.append(line.rstrip())
                line = "" if token == " " else token
            else:
                line = candidate
            while measure_text(font, line) > max_width and len(line) > 1:
                head, line = _split_prefix(line, max_width, font)
                result.append(head)
        if line:
            result.append(line.rstrip())
    return result if result else [""]


def wrap_to_width(text, max_width, font):
    """Convenience wrapper returning (lines, width, height, family)."""
    lines = wrap_text(text, max_width, font)
    return {
        "lines": lines,
        "width": text_width(lines, font),
        "height": text_height(lines, font),
        "family": font_family(text),
    }
