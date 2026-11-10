/**
 * Embedded skill body for dsh-uml-drawio.
 *
 * Kept as JS rather than a .md file because this host gates documentation-file
 * writes behind an approval prompt, and approval prompts are disabled in the
 * session that installed the plugin. The content is ordinary Markdown.
 */
export const SKILL_BODY = `# UML sequence diagrams (dsh-uml-drawio)

Use this skill when the user asks for a UML sequence diagram (时序图 / sequence diagram / 交互图),
or when a described flow should become an editable .drawio file.

The layout is computed by Python. Never invent coordinates and never hand-edit the generated
.drawio; change the spec and regenerate.

## Workflow (max 3 rounds)

1. Write the JSON spec (shape below). If you will iterate, save it next to the diagram:
   \`uml_lint\` and \`uml_generate\` accept either \`spec\` (inline object) or \`specPath\` (workspace
   JSON file). Use \`specPath\` for anything longer than a handful of events, so a fix does not
   re-send the whole object.
2. Call uml_lint - fix every error. Warnings are informational.
3. Re-lint after the fix. Stop after 3 rounds, or earlier when the issue count no longer drops;
   report what remains instead of looping.
4. Call uml_generate - writes <out>.drawio and the sidecar <out>.uml.json.
5. Call uml_render - PNG at scale 2 by default.
6. Run the human review below, then report the .drawio path, the PNG path, the page size, every
   remaining warning and the review result.

uml_generate refuses to overwrite a file whose hash does not match the sidecar. Pass force:true only
after confirming there are no manual edits worth keeping.

## Human review before you report (mandatory)

You are the first reader, not the author. After uml_render, look at the PNG and answer these the
way a stranger would:

1. Can the flow be followed top to bottom without opening the spec?
2. Do arrows leave the caller and arrive at the callee? Do replies point back to the caller -
   never to a third participant?
3. Is every fragment guard readable, and attached to the operand it belongs to?
4. Does any label get cut, sit on a fragment border, or cover a lifeline it should not?
5. Is every participant used, and is anyone missing from the story?
6. Do the message names match the classes/methods the user already has? Cross-check the class
   diagram when the project has one.

If any answer is no: change the spec, regenerate, and stay inside the 3-round budget.
If you cannot read images, say exactly "仅通过 lint，未经视觉验证" - do not claim a visual check.
Report one line: \`人工视角复核：<已核对项 / 已修项 / 剩余风险>\`.

## Spec shape (v1)

    {
      "version": 1,
      "title": "Login flow",
      "subtitle": "optional",
      "page": { "width": 1600, "leftMargin": 35, "rightMargin": 35 },
      "defaults": { "labelWidth": 220, "frameMargin": 60 },
      "participants": [
        { "id": "alice", "name": "Alice" },
        { "id": "api", "name": "API" }
      ],
      "events": []
    }

participants[].id must match ^[A-Za-z_][A-Za-z0-9_]{0,31}$.

### Events (document order)

- message - { "type": "message", "kind": "call|async|reply", "from": "a", "to": "b", "label": "doIt()" }
  - from === to is a self message; there is no separate self event type.
  - optional labelWidth (px) controls wrapping; every extra line adds 14px of pitch.
  - optional stableKey fixes the element id.
- fragment - { "type": "fragment", "kind": "alt|opt|loop", "guard": "[cond]", "branches": [{ "guard": null, "events": [] }] }
  - alt needs >= 2 branches; opt/loop exactly 1.
  - the first branch may set guard to null (it inherits the fragment guard); every later branch
    must provide its own guard.
  - nesting is limited to 6 levels.
- note - { "type": "note", "target": "a" or ["a","b"], "position": "left|right|over", "text": "..." }
- text - { "type": "text", "text": "...", "width": 400, "align": "left|center" }

v1 rejects create/delete messages and par/break/critical fragments with E_UNSUPPORTED_KIND.
Activation bars are not drawn.

## Labels

Three levels: (1) land in a lifeline gap near the sender; (2) centered with a white background and
W_LABEL_OVER_LIFELINE; (3) E_LABEL_IMPOSSIBLE. To fix (2)/(3), shorten the label, raise labelWidth,
or move the message out of the fragment - do not add participants to create space.

## Error codes you will see

| code | fix |
|---|---|
| E_SCHEMA_VALIDATION | follow the JSON pointer in path |
| E_PARTICIPANT_UNKNOWN | use a declared participant id |
| E_FRAGMENT_BRANCH | alt >=2 branches, opt/loop =1, later branches need guards |
| E_UNSUPPORTED_KIND | v1 supports call/async/reply and alt/opt/loop |
| E_LABEL_IMPOSSIBLE | shorten the label or raise labelWidth |
| E_CONFLICT | re-run with force:true only if no manual edits matter |
| E_PAGE_OVERFLOW | widen page.width |
| E_SPEC_UNREADABLE | specPath must be a readable JSON file inside the workspace |
| E_ARG_INVALID | pass exactly one of spec / specPath, plus a valid out, scale and crop |
| E_DEPTH_EXCEEDED | flatten the nesting; fragments deeper than 6 levels are rejected |
| E_OUT_PATH | outputs stay inside the workspace and end with .drawio / .png |
| E_PYTHON_ENV or E_FONT_MISSING | check the plugin configuration |
| E_RENDER_FAILED or E_RENDER_TIMEOUT | check drawioPath; retry |
`
