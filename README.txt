dsh-uml-drawio
==============

Generate professional UML sequence diagrams as uncompressed .drawio XML from a structured JSON
spec, render them with the draw.io desktop CLI, and verify the PNG with Pillow.

Built for DeepSeek Harness. Replaces the prototype gen_seq.py with a spec -> lint -> generate ->
render pipeline that is deterministic (same spec => same bytes) and refuses to overwrite manual
edits.

Install
-------

plugin_manager install_bundle target=E:\Harness\common\dsh-uml-drawio

The profile entry id is dsh-uml-drawio; configuration stays in the plugin's settings card (or the
profile patch).

Configuration
-------------

pythonPath  C:\Program Files\Python314\python.exe   interpreter with Pillow 12.x
drawioPath  D:\drawio\draw.io\draw.io.exe           draw.io desktop executable
fontCjk     C:\Windows\Fonts\msyh.ttc               CJK font (index=0)
fontLatin   C:\Windows\Fonts\arial.ttf              Latin font

Python/Pillow are probed once per mount. A missing interpreter or Pillow makes every tool return
E_PYTHON_ENV - there is no silent fallback.

Tools
-----

uml_lint({spec or specPath})                        validate + lay out, no files written
uml_generate({spec or specPath, out, force?})        write .drawio + <out>.uml.json sidecar
uml_render({path, format:"png", scale?, out?, crop?})  draw.io PNG + Pillow verify/crop

spec and specPath are mutually exclusive. Prefer specPath for a long spec: the file stays the
source of truth and a fix does not re-send the whole object.

Error codes are stable and carry a JSON pointer where it applies: E_SCHEMA_VALIDATION,
E_SPEC_UNREADABLE (specPath missing, outside the workspace, or not JSON), E_ARG_INVALID (both or
neither of spec/specPath, bad scale or crop), E_OUT_PATH, E_PARTICIPANT_UNKNOWN, E_FRAGMENT_BRANCH,
E_UNSUPPORTED_KIND, E_DEPTH_EXCEEDED, E_PAGE_OVERFLOW, E_CONFLICT, E_SIDECAR_CORRUPT,
E_RENDER_FAILED.

After uml_render the skill requires a human-perspective review of the PNG before reporting:
readability, arrow directions (replies must point back to the caller), guard attachment, clipped
labels, unused or missing participants, and method names against the class diagram. Report one
line ("人工视角复核：...") or state "仅通过 lint，未经视觉验证" when images cannot be read.

crop uses page-logical coordinates; on a 2x PNG, measure pixels and divide by 2 before passing.

Standard conformance (UML 2.5.1)
-------------------------------

The output is meant to read as an OMG UML 2.5.1 sequence diagram (formal/17-12-05, 2017-12,
Clause 17 Interactions, https://www.omg.org/spec/UML/2.5.1/PDF), not merely a diagram that
resembles one:

- Guards are InteractionOperand::guard text: the fragment tab, or a dedicated guard strip when an
  operand declares its own guard. Guard text is never emitted as an independent node, so moving
  the diagram cannot detach a guard from its operand.
- Message notation is fixed by emit.py: call = solid + filled arrowhead (ST_CALL), async = solid +
  open arrowhead (ST_ASYNC), reply = dashed + open arrowhead (ST_REPLY), lifeline = dashed
  vertical line (ST_LIFE).
- Notation v1 does not support (par/break/critical, create/delete) is rejected with
  E_UNSUPPORTED_KIND instead of being approximated. Do not hand-edit the generated .drawio to add
  it; change the spec or report the gap.
- The skill body requires the review to state "UML 依据：UML 2.5.1 Clause 17（Interactions）" and
  to list every deliberate simplification.

How it works
------------

- Node is glue: tool registration, workspace-bound paths, sidecar policy, subprocess I/O, errors.
- Python does layout: font metrics (getlength x 1.03), CJK/Latin font choice, three-pass layout,
  fragment bounds, three-level label placement, uncompressed XML, Pillow verification/crop.
- draw.io is invoked directly from Node with --size page (never --size diagram: the default crops
  to the content bounding box and its margin varies by +-2px).
- Tabs and else-guard strips that cross a lifeline get a same-height lifeline repair segment drawn
  on top of the white background (with the keyword/guard text still on top), so the lifeline never
  looks broken. Level-2 label backgrounds deliberately do NOT get a repair segment: they are
  allowed to cover lifelines and always emit W_LABEL_OVER_LIFELINE.
- The first operand's guard normally lives in the fragment tab. If the spec declares one explicitly
  and it differs from the fragment guard, it is drawn as its own guard strip at the top of that
  operand (an identical guard is not duplicated). A declared operand guard is never dropped.

Determinism
-----------

<diagram id> is a hash of the title; element ids are c_ + sha1(content key)[:10] (stableKey wins);
no timestamps, no host data, every geometry value is %.1f. Generating the same spec twice yields
byte-identical .drawio files.

Sidecar
-------

<out>.uml.json = {version, specHash, outputHash, generatedAt}. No output file -> generate; matching
hash -> overwrite; mismatched hash / missing sidecar -> E_CONFLICT; corrupt sidecar ->
E_SIDECAR_CORRUPT. force:true bypasses the conflict branches only.

Calibration (this host)
-----------------------

--size page gives px = logical * scale with origin (0, 0); PNG size is
pageWidth*scale + 2 by pageHeight*scale + 2 (2px right/bottom margin). -b 0 is the default.
Verified by test/test_calibration.py at scale 1 and 2.

v1 limits
---------

- create/delete messages and par/break/critical fragments are rejected (E_UNSUPPORTED_KIND).
- Activation bars are not drawn.
- One page per file; PNG only; no theme options.
- A fragment guard is never wrapped and the tab grows with the text (about 5.7 px per character
  here): a guard longer than the page makes the tab run past the page edge and the PNG clips it.
  No error code is raised, so keep guards short or widen page.width.
- Labels are separate text vertices: moving a message in draw.io does not move its label.
- Repair segments restart draw.io's dash phase; the seam with the main lifeline can be off by half
  a dash. Invisible on a 1px line, potentially visible in high-DPI print.
- Level-2 label backgrounds still cut through lifelines by design (see "How it works"); only tabs
  and else-guard strips are repaired.
- The skill body ships as lib/skill-body.js (this host gates .md writes behind approval).

Development
-----------

python -m unittest discover -s test -p "test_*.py"   Python layout/XML/render tests
node --test test/test_sidecar.mjs test/test_paths.mjs test/test_render_error.mjs
           test/test_spec_source.mjs test/test_skill_body.mjs
                                                     sidecar/path/drawio/spec-source tests

Fixtures: fixtures/prototype.json (7 participants / 50 messages / 5 fragments),
fixtures/cjk-long-label.json (5 participants / width 900 / 65-char CJK label),
fixtures/minimal.json (3 participants / 6 messages).
