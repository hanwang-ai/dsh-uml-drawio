import assert from 'node:assert/strict'
import test from 'node:test'

import { SKILL_BODY } from '../lib/skill-body.js'

test('skill documents specPath as an alternative to inline spec', () => {
  assert.ok(SKILL_BODY.includes('specPath'))
  assert.ok(SKILL_BODY.includes('either `spec` (inline object) or `specPath`'))
})

test('skill requires a human-perspective review after rendering', () => {
  assert.ok(SKILL_BODY.includes('Human review before you report (mandatory)'))
  for (const item of [
    'Do arrows leave the caller and arrive at the callee',
    'attached to the operand it belongs to',
    'missing from the story',
    'match the classes/methods',
  ]) {
    assert.ok(SKILL_BODY.includes(item), `missing review item: ${item}`)
  }
  assert.ok(SKILL_BODY.includes('人工视角复核'))
  assert.ok(SKILL_BODY.includes('仅通过 lint，未经视觉验证'))
})

test('skill keeps the 3-round budget and conflict rule', () => {
  assert.ok(SKILL_BODY.includes('max 3 rounds'))
  assert.ok(SKILL_BODY.includes('force:true'))
})

test('skill error table documents every reachable failure the tools raise', () => {
  for (const code of ['E_SPEC_UNREADABLE', 'E_ARG_INVALID', 'E_DEPTH_EXCEEDED', 'E_OUT_PATH']) {
    assert.ok(SKILL_BODY.includes(`| ${code} |`), `missing error row: ${code}`)
  }
})
