import assert from 'node:assert/strict'
import { mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import test from 'node:test'
import { fileURLToPath } from 'node:url'

import {
  buildSidecar,
  decideOverwrite,
  readSidecar,
  sha256Hex,
  sidecarPath,
  writeSidecar,
} from '../lib/sidecar.js'

const TMP = fileURLToPath(new URL('../.out/node-test/', import.meta.url))

function reset() {
  rmSync(TMP, { recursive: true, force: true })
  mkdirSync(TMP, { recursive: true })
}

function makeOutput(content = 'drawio-bytes') {
  const file = join(TMP, 'diagram.drawio')
  writeFileSync(file, content)
  return { file, hash: sha256Hex(readFileSync(file)), sidecar: sidecarPath(file) }
}

test('branch 1: no output file generates', () => {
  reset()
  const decision = decideOverwrite({
    outExists: false,
    actualOutputHash: null,
    sidecarRead: { ok: false, reason: 'missing' },
    force: false,
  })
  assert.equal(decision.action, 'generate')
  assert.equal(decision.branch, 'no-output')
})

test('branch 2: matching output hash overwrites', () => {
  reset()
  const { file, hash, sidecar } = makeOutput()
  writeSidecar(sidecar, buildSidecar({ specHash: 's', outputHash: hash, generatedAt: '2026-01-01T00:00:00.000Z' }))
  const decision = decideOverwrite({
    outExists: true,
    actualOutputHash: hash,
    sidecarRead: readSidecar(sidecar),
    force: false,
  })
  assert.equal(decision.action, 'generate')
  assert.equal(decision.branch, 'hash-match')
  assert.equal(sidecarPath(file), sidecar)
})

test('branch 3: hash mismatch conflicts', () => {
  reset()
  const { hash, sidecar } = makeOutput()
  writeSidecar(sidecar, buildSidecar({ specHash: 's', outputHash: hash, generatedAt: '2026-01-01T00:00:00.000Z' }))
  const decision = decideOverwrite({
    outExists: true,
    actualOutputHash: sha256Hex('hand-edited'),
    sidecarRead: readSidecar(sidecar),
    force: false,
  })
  assert.equal(decision.action, 'conflict')
  assert.equal(decision.code, 'E_CONFLICT')
  assert.equal(decision.branch, 'hash-mismatch')
})

test('branch 4: missing sidecar conflicts', () => {
  reset()
  const { hash } = makeOutput()
  const decision = decideOverwrite({
    outExists: true,
    actualOutputHash: hash,
    sidecarRead: { ok: false, reason: 'missing' },
    force: false,
  })
  assert.equal(decision.action, 'conflict')
  assert.equal(decision.code, 'E_CONFLICT')
  assert.equal(decision.branch, 'no-sidecar')
})

test('branch 5: corrupt sidecar is E_SIDECAR_CORRUPT', () => {
  reset()
  const { file, hash } = makeOutput()
  const sidecar = sidecarPath(file)
  writeFileSync(sidecar, '{ this is not json')
  const decision = decideOverwrite({
    outExists: true,
    actualOutputHash: hash,
    sidecarRead: readSidecar(sidecar),
    force: false,
  })
  assert.equal(decision.action, 'conflict')
  assert.equal(decision.code, 'E_SIDECAR_CORRUPT')
  assert.equal(decision.branch, 'corrupt-sidecar')
})

test('force bypasses branches 3-5', () => {
  reset()
  const { file, hash } = makeOutput()
  const sidecar = sidecarPath(file)
  writeFileSync(sidecar, 'not json')
  for (const sidecarRead of [readSidecar(sidecar), { ok: false, reason: 'missing' }]) {
    const decision = decideOverwrite({
      outExists: true,
      actualOutputHash: hash,
      sidecarRead,
      force: true,
    })
    assert.equal(decision.action, 'generate')
    assert.equal(decision.branch, 'force')
  }
})

test('readSidecar round-trips and rejects bad fields', () => {
  reset()
  const file = join(TMP, 'x.drawio')
  const sidecar = sidecarPath(file)
  writeSidecar(sidecar, buildSidecar({ specHash: 's', outputHash: 'o', generatedAt: '2026-01-01T00:00:00.000Z' }))
  const read = readSidecar(sidecar)
  assert.equal(read.ok, true)
  assert.equal(read.value.outputHash, 'o')

  writeFileSync(sidecar, JSON.stringify({ version: 2 }))
  assert.equal(readSidecar(sidecar).reason, 'corrupt')
  writeFileSync(sidecar, JSON.stringify({ version: 1, specHash: 's', outputHash: 'o' }))
  assert.equal(readSidecar(sidecar).reason, 'corrupt')
})
