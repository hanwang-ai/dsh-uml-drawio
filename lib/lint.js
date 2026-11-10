/** uml_lint orchestration: validate + lay out without writing files. */
import { failure } from './errors.js'
import { runPythonJson } from './python.js'
import { WORKER_SCRIPT } from './paths.js'
import { resolveSpec } from './spec-source.js'

export async function runLint({
  spec,
  specPath,
  workspaceRoot,
  cfg,
  signal,
  spawnImpl,
}) {
  const resolved = resolveSpec({ spec, specPath, workspaceRoot })
  if (!resolved.ok) return failure('uml_lint', resolved.code, resolved.message)
  const payload = resolved.spec

  const response = await runPythonJson({
    pythonPath: cfg.pythonPath,
    script: WORKER_SCRIPT,
    request: {
      mode: 'lint',
      spec: payload,
      fonts: { cjk: cfg.fontCjk, latin: cfg.fontLatin },
    },
    signal,
    spawnImpl,
  })
  if (!response.ok) return failure('uml_lint', response.code, response.message)
  return { ...response.result, tool: 'uml_lint' }
}
