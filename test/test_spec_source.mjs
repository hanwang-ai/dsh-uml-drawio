import assert from 'node:assert/strict'
import { mkdirSync, rmSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import test from 'node:test'
import { fileURLToPath } from 'node:url'

import { resolveSpec } from '../lib/spec-source.js'

const ROOT = fileURLToPath(new URL('../.out/node-test-spec-source/', import.meta.url))

function reset() {
  rmSync(ROOT, { recursive: true, force: true })
  mkdirSync(ROOT, { recursive: true })
}

const MINIMAL = { version: 1, participants: [{ id: 'a', name: 'A' }], events: [] }

test('inline spec is passed through', () => {
  reset()
  const resolved = resolveSpec({ spec: MINIMAL, workspaceRoot: ROOT })
  assert.equal(resolved.ok, true)
  assert.equal(resolved.source, 'inline')
  assert.deepEqual(resolved.spec, MINIMAL)
})

test('specPath loads a workspace JSON file', () => {
  reset()
  const file = join(ROOT, 'diagram.spec.json')
  writeFileSync(file, JSON.stringify(MINIMAL), 'utf8')
  const resolved = resolveSpec({ specPath: 'diagram.spec.json', workspaceRoot: ROOT })
  assert.equal(resolved.ok, true)
  assert.equal(resolved.source, 'file')
  assert.equal(resolved.path.toLowerCase(), file.toLowerCase())
  assert.deepEqual(resolved.spec, MINIMAL)
})

test('spec and specPath are mutually exclusive', () => {
  reset()
  const resolved = resolveSpec({ spec: MINIMAL, specPath: 'x.json', workspaceRoot: ROOT })
  assert.equal(resolved.ok, false)
  assert.equal(resolved.code, 'E_ARG_INVALID')
})

test('neither spec nor specPath is E_ARG_INVALID', () => {
  reset()
  const resolved = resolveSpec({ workspaceRoot: ROOT })
  assert.equal(resolved.ok, false)
  assert.equal(resolved.code, 'E_ARG_INVALID')
})

test('missing spec file is E_SPEC_UNREADABLE', () => {
  reset()
  const resolved = resolveSpec({ specPath: 'missing.json', workspaceRoot: ROOT })
  assert.equal(resolved.ok, false)
  assert.equal(resolved.code, 'E_SPEC_UNREADABLE')
})

test('escaping the workspace is E_SPEC_UNREADABLE', () => {
  reset()
  const resolved = resolveSpec({ specPath: '../escape.json', workspaceRoot: ROOT })
  assert.equal(resolved.ok, false)
  assert.equal(resolved.code, 'E_SPEC_UNREADABLE')
})

test('invalid JSON is E_SCHEMA_VALIDATION with the file path', () => {
  reset()
  const file = join(ROOT, 'broken.json')
  writeFileSync(file, '{ nope', 'utf8')
  const resolved = resolveSpec({ specPath: 'broken.json', workspaceRoot: ROOT })
  assert.equal(resolved.ok, false)
  assert.equal(resolved.code, 'E_SCHEMA_VALIDATION')
  assert.ok(String(resolved.message).includes('broken.json') || resolved.path)
})

test('non-object payload is E_SCHEMA_VALIDATION', () => {
  reset()
  const file = join(ROOT, 'array.json')
  writeFileSync(file, '[1,2,3]', 'utf8')
  const inline = resolveSpec({ spec: [1, 2, 3], workspaceRoot: ROOT })
  const fromFile = resolveSpec({ specPath: 'array.json', workspaceRoot: ROOT })
  assert.equal(inline.ok, false)
  assert.equal(inline.code, 'E_SCHEMA_VALIDATION')
  assert.equal(fromFile.ok, false)
  assert.equal(fromFile.code, 'E_SCHEMA_VALIDATION')
})
