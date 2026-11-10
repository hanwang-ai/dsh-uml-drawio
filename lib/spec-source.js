/** Resolve a spec from an inline object or a workspace-relative JSON file. */
import { readFileSync } from 'node:fs'

import { resolveInsideWorkspace } from './paths.js'

/**
 * Returns { ok: true, spec, source: 'inline'|'file', path } or
 * { ok: false, code, message }.
 *
 * `spec` and `specPath` are mutually exclusive; exactly one is required.
 */
export function resolveSpec({ spec, specPath, workspaceRoot }) {
  if (spec !== undefined && specPath !== undefined) {
    return {
      ok: false,
      code: 'E_ARG_INVALID',
      message: 'Provide either spec or specPath, not both.',
    }
  }

  let payload = spec
  let source = 'inline'
  let path = null

  if (payload === undefined) {
    if (typeof specPath !== 'string' || specPath.trim() === '') {
      return { ok: false, code: 'E_ARG_INVALID', message: 'Provide spec or specPath.' }
    }
    const resolved = resolveInsideWorkspace(workspaceRoot, specPath, { code: 'E_SPEC_UNREADABLE' })
    if (!resolved.ok) return { ok: false, code: resolved.code, message: resolved.message }
    path = resolved.path
    source = 'file'
    let text
    try {
      text = readFileSync(path, 'utf8')
    } catch (error) {
      return { ok: false, code: 'E_SPEC_UNREADABLE', message: `Cannot read ${path}: ${error.message}` }
    }
    try {
      payload = JSON.parse(text)
    } catch (error) {
      return {
        ok: false,
        code: 'E_SCHEMA_VALIDATION',
        message: `specPath is not valid JSON: ${error.message}`,
        path,
      }
    }
  }

  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
    return { ok: false, code: 'E_SCHEMA_VALIDATION', message: 'spec must be a JSON object.' }
  }
  return { ok: true, spec: payload, source, path }
}
