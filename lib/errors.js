/** Error envelope helpers shared by the three tools. */

export const ERROR_HINTS = {
  E_SCHEMA_VALIDATION: 'fix the spec shape; every error carries a JSON pointer path',
  E_SPEC_VERSION: 'only spec version 1 is supported',
  E_PARTICIPANT_UNKNOWN: 'use a participant id declared in participants[]',
  E_PARTICIPANT_DUPLICATE: 'participant ids must be unique',
  E_FRAGMENT_BRANCH: 'alt needs >= 2 branches, opt/loop exactly 1; non-first branches need a guard',
  E_UNSUPPORTED_KIND: 'v1 supports call/async/reply and alt/opt/loop only',
  E_PAGE_OVERFLOW: 'widen page.width or reduce participants/content',
  E_CONFLICT: 'pass force:true after confirming there are no manual edits worth keeping',
  E_SIDECAR_CORRUPT: 'delete the sidecar or pass force:true',
  E_PYTHON_ENV: 'check pythonPath (Pillow is required) in the plugin configuration',
  E_RENDER_TIMEOUT: 'draw.io took longer than 60s; retry or render at scale 1',
  E_RENDER_FAILED: 'check drawioPath, and make sure the output directory is writable; inspect the reported stderr tail',
  E_ID_DUPLICATE: 'stableKey values must be unique',
  E_DEPTH_EXCEEDED: 'fragment nesting is limited to 6 levels',
  E_FONT_MISSING: 'check fontCjk/fontLatin in the plugin configuration',
  E_SPEC_UNREADABLE: 'specPath must point to a readable JSON file inside the workspace',
  E_ARG_INVALID: 'check the tool arguments',
  E_WRITE_FAILED: 'the previous output may be stale; retry and pass force:true if needed',
  E_OUT_PATH: 'outputs must stay inside the session workspace and use .drawio/.png',
  E_LABEL_IMPOSSIBLE: 'shorten the label, add labelWidth, or move the message out of the fragment',
}

export function makeError(code, message, extra = {}) {
  return { code, message, ...extra }
}

export function failure(tool, code, message, extra = {}) {
  return { ok: false, tool, errors: [makeError(code, message, extra)] }
}

export function failureFrom(tool, workerResult) {
  const errors = Array.isArray(workerResult?.errors) && workerResult.errors.length
    ? workerResult.errors
    : [makeError('E_WRITE_FAILED', 'Worker failed without an error list.')]
  return { ok: false, tool, errors }
}

/** Model-facing text for a failed result. */
export function errorText(value) {
  const lines = []
  for (const error of value.errors ?? []) {
    lines.push(`ERROR [${error.code}] ${error.message}`)
    if (error.path) lines.push(`  path: ${error.path}`)
    if (error.details) lines.push(`  details: ${JSON.stringify(error.details)}`)
    const hint = ERROR_HINTS[error.code]
    if (hint) lines.push(`  hint: ${hint}`)
  }
  return [{ type: 'text', text: lines.join('\n') }]
}

/** Model-facing text for a successful lint/generate/render result. */
export function successText(lines) {
  return [{ type: 'text', text: lines.join('\n') }]
}
