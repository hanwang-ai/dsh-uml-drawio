/** uml_render orchestration: draw.io CLI -> Pillow verify/crop -> final PNG. */
import { randomUUID } from 'node:crypto'
import { existsSync, mkdirSync, rmSync, statSync } from 'node:fs'
import { dirname } from 'node:path'

import { DRAWIO_TIMEOUT_MS, runDrawio } from './drawio.js'
import { failure } from './errors.js'
import { runPythonJson } from './python.js'
import { RENDER_CHECK_SCRIPT, resolveInsideWorkspace } from './paths.js'

function validCrop(crop) {
  if (crop === null || crop === undefined) return { ok: true, value: null }
  if (typeof crop !== 'object' || Array.isArray(crop)) return { ok: false }
  const values = [crop.x, crop.y, crop.w, crop.h]
  if (!values.every((value) => typeof value === 'number' && Number.isFinite(value))) return { ok: false }
  if (crop.w <= 0 || crop.h <= 0) return { ok: false }
  return { ok: true, value: { x: crop.x, y: crop.y, w: crop.w, h: crop.h } }
}

export async function runRender({
  path,
  format = 'png',
  scale = 2,
  out,
  crop = null,
  workspaceRoot,
  cfg,
  signal,
  spawnImpl,
  drawioImpl = runDrawio,
}) {
  if (format !== 'png') {
    return failure('uml_render', 'E_ARG_INVALID', 'v1 supports format "png" only.')
  }
  if (!Number.isInteger(scale) || scale < 1 || scale > 4) {
    return failure('uml_render', 'E_ARG_INVALID', 'scale must be an integer between 1 and 4.')
  }
  const cropCheck = validCrop(crop)
  if (!cropCheck.ok) {
    return failure('uml_render', 'E_ARG_INVALID', 'crop needs positive numeric x, y, w, h.')
  }

  const resolvedInput = resolveInsideWorkspace(workspaceRoot, path, { mustExist: true })
  if (!resolvedInput.ok) return failure('uml_render', resolvedInput.code, resolvedInput.message)
  const input = resolvedInput.path
  if (!input.toLowerCase().endsWith('.drawio')) {
    return failure('uml_render', 'E_OUT_PATH', 'path must end with .drawio.', { path: input })
  }

  const defaultOut = input.replace(/\.drawio$/i, '.png')
  const resolvedOut = resolveInsideWorkspace(workspaceRoot, out ?? defaultOut)
  if (!resolvedOut.ok) return failure('uml_render', resolvedOut.code, resolvedOut.message)
  const target = resolvedOut.path
  if (!target.toLowerCase().endsWith('.png')) {
    return failure('uml_render', 'E_OUT_PATH', 'out must end with .png.', { path: target })
  }

  const temp = `${target}.render-${randomUUID()}.png`
  const started = Date.now()
  try {
    // P1: draw.io writes straight to `temp`, so its directory must exist before
    // the spawn; a fresh nested `out` used to fail inside draw.io.
    mkdirSync(dirname(target), { recursive: true })
    const drawio = await drawioImpl({
      drawioPath: cfg.drawioPath,
      input,
      output: temp,
      scale,
      timeoutMs: DRAWIO_TIMEOUT_MS,
      signal,
      spawnImpl,
    })
    if (!drawio.ok) {
      return failure('uml_render', drawio.code, drawio.message, {
        path: target,
        details: drawio.details ?? { drawioPath: cfg.drawioPath },
      })
    }

    let size = 0
    try {
      size = statSync(temp).size
    } catch (error) {
      return failure('uml_render', 'E_RENDER_FAILED', `draw.io left no output file: ${error.message}`, {
        path: target,
      })
    }
    if (size <= 0) {
      return failure('uml_render', 'E_RENDER_FAILED', 'draw.io produced an empty file.', { path: target })
    }

    const check = await runPythonJson({
      pythonPath: cfg.pythonPath,
      script: RENDER_CHECK_SCRIPT,
      request: { image: temp, out: target, scale, crop: cropCheck.value },
      timeoutMs: 60000,
      signal,
      spawnImpl,
    })
    if (!check.ok) return failure('uml_render', check.code, check.message, { path: target })
    if (!check.result.ok) return { ...check.result, tool: 'uml_render' }

    return {
      ok: true,
      tool: 'uml_render',
      path: check.result.path,
      width: check.result.width,
      height: check.result.height,
      bytes: check.result.bytes,
      scale,
      effectiveScale: scale,
      crop: check.result.crop,
      renderMs: Date.now() - started,
    }
  } finally {
    try {
      if (existsSync(temp)) rmSync(temp)
    } catch {
      // best effort
    }
  }
}
