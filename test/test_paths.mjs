import assert from 'node:assert/strict'
import { existsSync, mkdirSync, readFileSync, rmSync } from 'node:fs'
import { join } from 'node:path'
import test from 'node:test'
import { fileURLToPath } from 'node:url'

import { isInside, resolveInsideWorkspace, writeFileAtomic } from '../lib/paths.js'

const ROOT = fileURLToPath(new URL('../.out/node-test-paths/', import.meta.url))

function reset() {
  rmSync(ROOT, { recursive: true, force: true })
  mkdirSync(ROOT, { recursive: true })
}

test('isInside accepts the root and descendants, rejects escapes', () => {
  reset()
  assert.equal(isInside(ROOT, ROOT), true)
  assert.equal(isInside(ROOT, join(ROOT, 'a', 'b.drawio')), true)
  assert.equal(isInside(ROOT, join(ROOT, '..', 'escape.drawio')), false)
  assert.equal(isInside(ROOT, 'C:\\Windows\\win.ini'), false)
})

test('relative paths resolve against the workspace', () => {
  reset()
  const resolved = resolveInsideWorkspace(ROOT, 'sub/out.drawio')
  assert.equal(resolved.ok, true)
  assert.ok(resolved.path.startsWith(ROOT))
})

test('absolute paths inside the workspace are accepted', () => {
  reset()
  const target = join(ROOT, 'nested', 'diagram.drawio')
  const resolved = resolveInsideWorkspace(ROOT, target)
  assert.equal(resolved.ok, true)
  assert.equal(resolved.path.toLowerCase(), target.toLowerCase())
})

test('escapes and empty values are E_OUT_PATH', () => {
  reset()
  const escape = resolveInsideWorkspace(ROOT, '..\\escape.drawio')
  assert.equal(escape.ok, false)
  assert.equal(escape.code, 'E_OUT_PATH')
  const empty = resolveInsideWorkspace(ROOT, '   ')
  assert.equal(empty.ok, false)
  assert.equal(empty.code, 'E_OUT_PATH')
})

test('missing paths only fail when mustExist is set', () => {
  reset()
  const lazy = resolveInsideWorkspace(ROOT, 'not-there/diagram.drawio')
  assert.equal(lazy.ok, true)
  const strict = resolveInsideWorkspace(ROOT, 'not-there/diagram.drawio', { mustExist: true })
  assert.equal(strict.ok, false)
})

test('writeFileAtomic writes the file and leaves no temp sibling', () => {
  reset()
  const target = join(ROOT, 'deep', 'file.drawio')
  writeFileAtomic(target, 'hello')
  assert.equal(readFileSync(target, 'utf8'), 'hello')
  assert.equal(existsSync(`${target}.tmp-${process.pid}`), false)
})
