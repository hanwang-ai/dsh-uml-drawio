/**
 * Workspace-bound path helpers for dsh-uml-drawio.
 *
 * Rules:
 *  - Every path argument is resolved against the session workspace root.
 *  - The resolved path must stay inside that root (realpath of the nearest
 *    existing ancestor is checked, so `..` and symlinks cannot escape).
 *  - Writes are atomic: temp file in the same directory, then rename.
 */
import { existsSync, mkdirSync, realpathSync, renameSync, writeFileSync } from 'node:fs'
import { basename, dirname, isAbsolute, join, relative, resolve, sep } from 'node:path'
import { fileURLToPath } from 'node:url'

export const LIB_DIR = dirname(fileURLToPath(import.meta.url))
export const PACKAGE_DIR = dirname(LIB_DIR)
export const PYTHON_DIR = join(PACKAGE_DIR, 'python')
export const WORKER_SCRIPT = join(PYTHON_DIR, 'uml_seq.py')
export const RENDER_CHECK_SCRIPT = join(PYTHON_DIR, 'render_check.py')
export const SCHEMA_PATH = join(PACKAGE_DIR, 'schema', 'uml-seq.spec.schema.json')

function absolute(path) {
  return resolve(path)
}

function compareKey(path) {
  return process.platform === 'win32' ? path.toLowerCase() : path
}

/** True when `target` is the root itself or a descendant of `root`. */
export function isInside(root, target) {
  const rel = relative(compareKey(absolute(root)), compareKey(absolute(target)))
  return rel === '' || (rel !== '..' && !rel.startsWith('..' + sep) && !isAbsolute(rel))
}

function realpathNearest(target) {
  let current = absolute(target)
  const missing = []
  while (!existsSync(current)) {
    missing.unshift(basename(current))
    const parent = dirname(current)
    if (parent === current) break
    current = parent
  }
  let base
  try {
    base = realpathSync(current)
  } catch {
    base = current
  }
  return missing.length ? join(base, ...missing) : base
}

/**
 * Resolve one caller-supplied path against the session workspace.
 * @returns {{ok: true, path: string} | {ok: false, code: string, message: string}}
 */
export function resolveInsideWorkspace(root, input, { mustExist = false, code = 'E_OUT_PATH' } = {}) {
  if (typeof input !== 'string' || input.trim() === '') {
    return { ok: false, code, message: 'Path is empty.' }
  }
  const absoluteTarget = isAbsolute(input) ? absolute(input) : resolve(root, input)
  if (!isInside(root, absoluteTarget)) {
    return {
      ok: false,
      code,
      message: `Path escapes the session workspace: ${absoluteTarget}`,
      details: { workspace: absolute(root) },
    }
  }
  const realTarget = realpathNearest(absoluteTarget)
  if (!isInside(realpathNearest(root), realTarget)) {
    return {
      ok: false,
      code,
      message: `Path resolves outside the session workspace: ${realTarget}`,
      details: { workspace: realpathNearest(root) },
    }
  }
  if (mustExist && !existsSync(realTarget)) {
    return { ok: false, code, message: `Path does not exist: ${realTarget}` }
  }
  return { ok: true, path: realTarget }
}

/** Write a file atomically (temp + rename in the destination directory). */
export function writeFileAtomic(file, data) {
  mkdirSync(dirname(file), { recursive: true })
  const temp = `${file}.tmp-${process.pid}-${Date.now()}`
  writeFileSync(temp, data)
  renameSync(temp, file)
}
