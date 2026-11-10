import assert from 'node:assert/strict'
import { existsSync, mkdirSync, readdirSync, rmSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import test from 'node:test'
import { fileURLToPath } from 'node:url'

import { drawioArgs, runDrawio } from '../lib/drawio.js'
import { runRender } from '../lib/render.js'

const ROOT = fileURLToPath(new URL('../.out/node-test-render/', import.meta.url))
const BOGUS = 'Z:\\definitely-missing\\draw.io.exe'

const CFG = {
  pythonPath: 'C:\\Program Files\\Python314\\python.exe',
  drawioPath: BOGUS,
  fontCjk: 'C:\\Windows\\Fonts\\msyh.ttc',
  fontLatin: 'C:\\Windows\\Fonts\\arial.ttf',
}

const MINIMAL_DRAWIO = `<?xml version="1.0" encoding="UTF-8"?>
<mxfile host="app.diagrams.net" type="device">
  <diagram id="d_test" name="test">
    <mxGraphModel grid="0" page="1" pageWidth="200" pageHeight="120" math="0" shadow="0">
      <root>
        <mxCell id="0"/>
        <mxCell id="1" parent="0"/>
        <mxCell id="box" value="" style="rounded=0;html=0;fillColor=#FF0000;strokeColor=none;" vertex="1" parent="1">
          <mxGeometry x="10" y="10" width="40" height="40" as="geometry"/>
        </mxCell>
      </root>
    </mxGraphModel>
  </diagram>
</mxfile>
`

function reset() {
  rmSync(ROOT, { recursive: true, force: true })
  mkdirSync(ROOT, { recursive: true })
}

test('drawio arguments use page size mode and no border', () => {
  const args = drawioArgs({ input: 'a.drawio', output: 'b.png', scale: 2 })
  assert.equal(args[args.indexOf('--size') + 1], 'page')
  assert.equal(args[args.indexOf('-b') + 1], '0')
  assert.equal(args[args.indexOf('-s') + 1], '2')
  assert.ok(args.includes('-x'))
  assert.ok(args.includes('png'))
})

test('a wrong drawioPath is a readable E_RENDER_FAILED with no output', async () => {
  reset()
  const input = join(ROOT, 'in.drawio')
  writeFileSync(input, MINIMAL_DRAWIO)
  const output = join(ROOT, 'out.png')
  const result = await runDrawio({ drawioPath: BOGUS, input, output, scale: 1 })
  assert.equal(result.ok, false)
  assert.equal(result.code, 'E_RENDER_FAILED')
  assert.match(result.message, /draw\.io/i)
  assert.equal(existsSync(output), false)
})

test('uml_render leaves no output or temp file when draw.io cannot start', async () => {
  reset()
  const input = join(ROOT, 'in.drawio')
  writeFileSync(input, MINIMAL_DRAWIO)
  const output = join(ROOT, 'out.png')
  const result = await runRender({
    path: input,
    scale: 1,
    out: output,
    workspaceRoot: ROOT,
    cfg: CFG,
  })
  assert.equal(result.ok, false)
  assert.equal(result.errors[0].code, 'E_RENDER_FAILED')
  assert.equal(existsSync(output), false)
  const leftovers = readdirSync(ROOT).filter((name) => name.includes('.render-'))
  assert.deepEqual([], leftovers)
})

const ONE_PIXEL_PNG = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==',
  'base64',
)

test('uml_render creates a missing output directory before draw.io runs', async () => {
  reset()
  const input = join(ROOT, 'in.drawio')
  writeFileSync(input, MINIMAL_DRAWIO)
  const output = join(ROOT, 'deep', 'nested', 'out.png')
  let directoryExisted = false
  const drawioImpl = async ({ output: target }) => {
    directoryExisted = existsSync(dirname(target))
    writeFileSync(target, ONE_PIXEL_PNG)
    return { ok: true, elapsedMs: 1 }
  }
  const result = await runRender({
    path: input,
    scale: 1,
    out: output,
    workspaceRoot: ROOT,
    cfg: CFG,
    drawioImpl,
  })
  assert.equal(result.ok, true, JSON.stringify(result.errors))
  assert.equal(directoryExisted, true, 'the output directory must exist before draw.io starts')
  assert.equal(existsSync(output), true)
  assert.equal(result.width, 1)
  assert.equal(result.height, 1)
})

test('uml_render rejects unsupported arguments before spawning', async () => {
  reset()
  const input = join(ROOT, 'in.drawio')
  writeFileSync(input, MINIMAL_DRAWIO)
  const base = { path: input, out: join(ROOT, 'out.png'), workspaceRoot: ROOT, cfg: CFG }
  assert.equal((await runRender({ ...base, format: 'svg' })).errors[0].code, 'E_ARG_INVALID')
  assert.equal((await runRender({ ...base, scale: 0 })).errors[0].code, 'E_ARG_INVALID')
  assert.equal((await runRender({ ...base, crop: { x: 0, y: 0, w: 0, h: 10 } })).errors[0].code, 'E_ARG_INVALID')
})
