/**
 * Sidecar state machine for dsh-uml-drawio.
 *
 * `<out>.uml.json` records {version, specHash, outputHash, generatedAt}.
 * Five branches (plus the empty-file case, which falls into the hash mismatch):
 *   1. no output file                  -> generate (sidecar is replaced)
 *   2. output hash matches sidecar     -> overwrite (idempotent)
 *   3. output hash differs             -> E_CONFLICT unless force
 *   4. output exists, sidecar missing  -> E_CONFLICT unless force
 *   5. sidecar corrupt / wrong version -> E_SIDECAR_CORRUPT unless force
 * force bypasses branches 2-5 but never the schema/path checks.
 */
import { createHash } from 'node:crypto'
import { readFileSync } from 'node:fs'

import { writeFileAtomic } from './paths.js'

export const SIDECAR_VERSION = 1

export function sidecarPath(out) {
  return `${out}.uml.json`
}

export function hashHex(algorithm, data) {
  return createHash(algorithm).update(data).digest('hex')
}

export function sha256Hex(data) {
  return hashHex('sha256', data)
}

export function md5Hex(data) {
  return hashHex('md5', data)
}

/** @returns {{ok: true, value: object} | {ok: false, reason: 'missing'|'corrupt', detail?: string}} */
export function readSidecar(file) {
  let text
  try {
    text = readFileSync(file, 'utf8')
  } catch (error) {
    if (error?.code === 'ENOENT') return { ok: false, reason: 'missing' }
    return { ok: false, reason: 'corrupt', detail: String(error?.message ?? error) }
  }
  let data
  try {
    data = JSON.parse(text)
  } catch (error) {
    return { ok: false, reason: 'corrupt', detail: `invalid JSON: ${error.message}` }
  }
  const valid = data
    && typeof data === 'object'
    && data.version === SIDECAR_VERSION
    && typeof data.specHash === 'string'
    && typeof data.outputHash === 'string'
    && typeof data.generatedAt === 'string'
  if (!valid) return { ok: false, reason: 'corrupt', detail: 'missing or invalid fields' }
  return { ok: true, value: data }
}

/** Decide whether the target may be overwritten. */
export function decideOverwrite({ outExists, actualOutputHash, sidecarRead, force }) {
  if (!outExists) return { action: 'generate', branch: 'no-output' }
  if (force) return { action: 'generate', branch: 'force' }
  if (!sidecarRead.ok) {
    if (sidecarRead.reason === 'missing') {
      return {
        action: 'conflict',
        branch: 'no-sidecar',
        code: 'E_CONFLICT',
        message: 'Output exists without a sidecar; refusing to overwrite.',
      }
    }
    return {
      action: 'conflict',
      branch: 'corrupt-sidecar',
      code: 'E_SIDECAR_CORRUPT',
      message: `Sidecar is unreadable: ${sidecarRead.detail}`,
    }
  }
  if (sidecarRead.value.outputHash === actualOutputHash) {
    return { action: 'generate', branch: 'hash-match' }
  }
  return {
    action: 'conflict',
    branch: 'hash-mismatch',
    code: 'E_CONFLICT',
    message: 'Output was modified after the last generation; refusing to overwrite.',
  }
}

export function buildSidecar({ specHash, outputHash, generatedAt }) {
  return { version: SIDECAR_VERSION, specHash, outputHash, generatedAt }
}

export function writeSidecar(file, data) {
  writeFileAtomic(file, JSON.stringify(data, null, 2) + '\n')
}
