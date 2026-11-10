/** uml_generate orchestration: conflict policy -> Python worker -> sidecar. */
import { existsSync, readFileSync } from 'node:fs'

import { failure } from './errors.js'
import { runPythonJson } from './python.js'
import { resolveInsideWorkspace, WORKER_SCRIPT } from './paths.js'
import { resolveSpec } from './spec-source.js'
import {
  buildSidecar,
  decideOverwrite,
  md5Hex,
  readSidecar,
  sha256Hex,
  sidecarPath,
  writeSidecar,
} from './sidecar.js'

export async function runGenerate({
  spec,
  specPath,
  out,
  force = false,
  workspaceRoot,
  cfg,
  signal,
  spawnImpl,
  now = () => new Date(),
}) {
  const resolvedSpec = resolveSpec({ spec, specPath, workspaceRoot })
  if (!resolvedSpec.ok) {
    return failure('uml_generate', resolvedSpec.code, resolvedSpec.message)
  }
  if (typeof out !== 'string' || out.trim() === '') {
    return failure('uml_generate', 'E_ARG_INVALID', 'out is required.')
  }

  const resolvedOut = resolveInsideWorkspace(workspaceRoot, out)
  if (!resolvedOut.ok) return failure('uml_generate', resolvedOut.code, resolvedOut.message)
  const target = resolvedOut.path
  if (!target.toLowerCase().endsWith('.drawio')) {
    return failure('uml_generate', 'E_OUT_PATH', 'out must end with .drawio.', { path: target })
  }

  // Conflict policy runs before the worker: it prevents both wasted work and
  // accidental overwrites. force only bypasses branches 2-5.
  const outExists = existsSync(target)
  const actualOutputHash = outExists ? sha256Hex(readFileSync(target)) : null
  const decision = decideOverwrite({
    outExists,
    actualOutputHash,
    sidecarRead: readSidecar(sidecarPath(target)),
    force: Boolean(force),
  })
  if (decision.action === 'conflict') {
    return failure('uml_generate', decision.code, decision.message, {
      path: target,
      details: {
        branch: decision.branch,
        actualOutputHash,
        sidecar: sidecarPath(target),
        forceHint: 're-run with force:true after confirming there are no manual edits worth keeping',
      },
    })
  }

  const started = Date.now()
  const response = await runPythonJson({
    pythonPath: cfg.pythonPath,
    script: WORKER_SCRIPT,
    request: {
      mode: 'generate',
      spec: resolvedSpec.spec,
      out: target,
      fonts: { cjk: cfg.fontCjk, latin: cfg.fontLatin },
    },
    signal,
    spawnImpl,
  })
  if (!response.ok) return failure('uml_generate', response.code, response.message)
  const result = response.result
  if (!result.ok) return { ...result, tool: 'uml_generate' }

  let data
  try {
    data = readFileSync(target)
  } catch (error) {
    return failure('uml_generate', 'E_WRITE_FAILED', `Generated file is missing: ${error.message}`, {
      path: target,
    })
  }
  const md5 = md5Hex(data)
  if (md5 !== result.md5) {
    return failure('uml_generate', 'E_WRITE_FAILED', 'Generated file hash does not match the worker report.', {
      path: target,
      details: { worker: result.md5, actual: md5 },
    })
  }

  const sidecar = buildSidecar({
    specHash: result.specHash,
    outputHash: sha256Hex(data),
    generatedAt: now().toISOString(),
  })
  try {
    writeSidecar(sidecarPath(target), sidecar)
  } catch (error) {
    return failure('uml_generate', 'E_WRITE_FAILED', `Output was written but the sidecar failed: ${error.message}`, {
      path: target,
      details: {
        sidecar: sidecarPath(target),
        forceHint: 'the next run will report E_CONFLICT; pass force:true',
      },
    })
  }

  return {
    ok: true,
    tool: 'uml_generate',
    path: target,
    specSource: resolvedSpec.source === 'file' ? resolvedSpec.path : 'inline',
    sidecar: sidecarPath(target),
    bytes: data.length,
    md5,
    sha256: sidecar.outputHash,
    specHash: sidecar.specHash,
    page: result.page,
    cells: result.cells,
    stats: result.stats,
    warnings: result.warnings,
    elapsedMs: Date.now() - started,
  }
}
