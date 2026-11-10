#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Pillow verification + optional crop for the dsh-uml-drawio render pipeline.

draw.io is always invoked with `--size page`; the exported PNG is the page at
the requested scale plus a 2px margin on the right/bottom (measured, see
test_calibration.py). Therefore page-logical crop coordinates map to pixels as
`px = round(coord * scale)` with origin (0, 0).

Request:
    {"image": "C:\\...\\render-tmp.png", "out": "C:\\...\\final.png",
     "scale": 2, "crop": {"x": 35, "y": 96, "w": 800, "h": 600} | null}

Result:
    {"ok": true, "path": ..., "width": ..., "height": ..., "bytes": ...,
     "scale": 2, "crop": {"x","y","w","h"} | null}
    {"ok": false, "errors": [{"code","message",...}]}
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import traceback

from PIL import Image, UnidentifiedImageError


def _error(code, message, path="", details=None):
    error = {"code": code, "message": message}
    if path:
        error["path"] = path
    if details:
        error["details"] = details
    return error


def _fail(errors):
    return {"ok": False, "errors": errors}


def _absolute(value):
    return isinstance(value, str) and value != "" and os.path.isabs(value)


def run(request):
    image = request.get("image")
    final = request.get("out")
    scale = request.get("scale", 1)
    crop = request.get("crop")

    if not _absolute(image):
        return _fail([_error("E_ARG_INVALID", "image must be an absolute path.")])
    if not _absolute(final):
        return _fail([_error("E_ARG_INVALID", "out must be an absolute path.")])
    try:
        scale = float(scale)
    except (TypeError, ValueError):
        return _fail([_error("E_ARG_INVALID", "scale must be a number.")])
    if not scale > 0:
        return _fail([_error("E_ARG_INVALID", "scale must be greater than 0.")])

    if crop is not None:
        if not isinstance(crop, dict):
            return _fail([_error("E_ARG_INVALID", "crop must be an object or null.")])
        try:
            crop_x = float(crop["x"])
            crop_y = float(crop["y"])
            crop_w = float(crop["w"])
            crop_h = float(crop["h"])
        except (KeyError, TypeError, ValueError):
            return _fail([_error("E_ARG_INVALID", "crop needs numeric x, y, w, h.")])
        if crop_w <= 0 or crop_h <= 0:
            return _fail([_error("E_ARG_INVALID", "crop width and height must be positive.")])

    temp_path = None
    try:
        with Image.open(image) as opened:
            opened.load()
            width, height = opened.size
            if width <= 0 or height <= 0:
                return _fail([_error("E_RENDER_FAILED", "Rendered image has zero width or height.", image)])

            if crop is None:
                result = opened.copy()
                applied_crop = None
            else:
                box = (
                    int(round(crop_x * scale)),
                    int(round(crop_y * scale)),
                    int(round((crop_x + crop_w) * scale)),
                    int(round((crop_y + crop_h) * scale)),
                )
                x0 = max(0, min(width, box[0]))
                y0 = max(0, min(height, box[1]))
                x1 = max(0, min(width, box[2]))
                y1 = max(0, min(height, box[3]))
                if x1 - x0 < 1 or y1 - y0 < 1:
                    return _fail([_error(
                        "E_RENDER_FAILED",
                        "crop box falls outside the rendered image.",
                        final,
                        {"image": [width, height], "box": list(box)},
                    )])
                result = opened.crop((x0, y0, x1, y1))
                applied_crop = {"x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0}

            os.makedirs(os.path.dirname(final) or ".", exist_ok=True)
            temp_path = final + ".tmp-%d" % os.getpid()
            result.save(temp_path, format="PNG")
            os.replace(temp_path, final)
            out_width, out_height = result.size
    except (UnidentifiedImageError, FileNotFoundError, ValueError) as exc:
        return _fail([_error("E_RENDER_FAILED", "Cannot read rendered image: %s" % (exc,), image)])
    except OSError as exc:
        return _fail([_error("E_WRITE_FAILED", "Cannot write %s: %s" % (final, exc), final)])
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass

    return {
        "ok": True,
        "path": final,
        "width": out_width,
        "height": out_height,
        "bytes": os.path.getsize(final),
        "scale": scale,
        "crop": applied_crop,
    }


def _read_request(args):
    if args.request_file:
        with open(args.request_file, "r", encoding="utf-8") as handle:
            return json.load(handle)
    return json.loads(sys.stdin.read())


def main(argv=None):
    parser = argparse.ArgumentParser(description="dsh-uml-drawio render verification")
    parser.add_argument("--request-file", default=None)
    parser.add_argument("--json-out", default=None)
    args = parser.parse_args(argv)

    try:
        result = run(_read_request(args))
    except json.JSONDecodeError as exc:
        result = _fail([_error("E_ARG_INVALID", "Request is not valid JSON: %s" % (exc,))])
    except FileNotFoundError as exc:
        result = _fail([_error("E_SPEC_UNREADABLE", "Cannot read request file: %s" % (exc,))])
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc(file=sys.stderr)
        result = _fail([_error("E_WRITE_FAILED", "Internal render-check error: %s" % (exc,))])

    text = json.dumps(result, ensure_ascii=False) + "\n"
    if args.json_out:
        try:
            with open(args.json_out, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(text)
        except OSError:
            traceback.print_exc(file=sys.stderr)
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
