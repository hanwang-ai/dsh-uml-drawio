/**
 * Python bridge: one process per tool call, JSON over stdin/stdout, logs over
 * stderr. The Python worker always answers with one JSON object; a crash or an
 * unparsable answer is mapped to E_PYTHON_ENV by the caller.
 */
import { spawn } from 'node:child_process'

const PROBE_CODE = [
  'import json, sys',
  'import PIL',
  'print(json.dumps({"pillow": PIL.__version__, "python": "%d.%d.%d" % tuple(sys.version_info[:3])}))',
].join('\n')

function tail(text, limit = 800) {
  const value = String(text ?? '').trim()
  return value.length > limit ? '…' + value.slice(-limit) : value
}

function killQuietly(child) {
  try {
    child.kill('SIGKILL')
  } catch {
    // already gone
  }
}

/** Verify the interpreter and Pillow once per plugin mount. */
export function probePython({ pythonPath, timeoutMs = 15000, spawnImpl = spawn }) {
  return new Promise((resolve) => {
    let child
    try {
      child = spawnImpl(pythonPath, ['-c', PROBE_CODE], {
        windowsHide: true,
        stdio: ['ignore', 'pipe', 'pipe'],
      })
    } catch (error) {
      resolve({ ok: false, message: `Cannot start Python at ${pythonPath}: ${error.message}` })
      return
    }
    let stdout = ''
    let stderr = ''
    let settled = false
    const timer = setTimeout(() => {
      if (settled) return
      settled = true
      killQuietly(child)
      resolve({ ok: false, message: `Python probe timed out after ${timeoutMs} ms.` })
    }, timeoutMs)
    child.stdout.on('data', (chunk) => {
      if (stdout.length < 65536) stdout += chunk
    })
    child.stderr.on('data', (chunk) => {
      if (stderr.length < 65536) stderr += chunk
    })
    child.on('error', (error) => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      resolve({ ok: false, message: `Python is not available at ${pythonPath}: ${error.message}` })
    })
    child.on('close', (code) => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      if (code !== 0) {
        resolve({ ok: false, message: `Python probe failed (exit ${code}): ${tail(stderr)}` })
        return
      }
      try {
        const info = JSON.parse(stdout.trim())
        resolve({ ok: true, python: info.python, pillow: info.pillow })
      } catch {
        resolve({ ok: false, message: `Python probe returned unparsable output: ${tail(stdout)}` })
      }
    })
  })
}

/**
 * Run one Python JSON worker call.
 * @returns {Promise<{ok: true, result: object} | {ok: false, code: string, message: string}>}
 */
export function runPythonJson({
  pythonPath,
  script,
  request,
  timeoutMs = 120000,
  signal,
  spawnImpl = spawn,
}) {
  return new Promise((resolve) => {
    let child
    try {
      child = spawnImpl(pythonPath, [script], {
        windowsHide: true,
        stdio: ['pipe', 'pipe', 'pipe'],
        signal,
      })
    } catch (error) {
      resolve({ ok: false, code: 'E_PYTHON_ENV', message: `Cannot start Python: ${error.message}` })
      return
    }
    let stdout = ''
    let stderr = ''
    let settled = false
    const finish = (value) => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      resolve(value)
    }
    const timer = setTimeout(() => {
      killQuietly(child)
      finish({ ok: false, code: 'E_PYTHON_ENV', message: `Python worker timed out after ${timeoutMs} ms.` })
    }, timeoutMs)
    child.stdout.on('data', (chunk) => {
      if (stdout.length < 8_000_000) stdout += chunk
    })
    child.stderr.on('data', (chunk) => {
      if (stderr.length < 65536) stderr += chunk
    })
    child.on('error', (error) => {
      finish({ ok: false, code: 'E_PYTHON_ENV', message: `Python worker failed: ${error.message}` })
    })
    child.on('close', (code) => {
      if (code !== 0) {
        finish({
          ok: false,
          code: 'E_PYTHON_ENV',
          message: `Python worker exited with ${code}: ${tail(stderr)}`,
        })
        return
      }
      const lines = String(stdout).trim().split(/\r?\n/).filter(Boolean)
      if (lines.length === 0) {
        finish({ ok: false, code: 'E_PYTHON_ENV', message: 'Python worker produced no output.' })
        return
      }
      try {
        const result = JSON.parse(lines[lines.length - 1])
        if (!result || typeof result.ok !== 'boolean') {
          finish({ ok: false, code: 'E_PYTHON_ENV', message: 'Python worker result has no ok flag.' })
          return
        }
        finish({ ok: true, result })
      } catch (error) {
        finish({
          ok: false,
          code: 'E_PYTHON_ENV',
          message: `Python worker returned unparsable output: ${tail(lines[lines.length - 1])}`,
        })
      }
    })
    child.stdin.on('error', () => {
      // The child may have exited before reading stdin; the close handler reports it.
    })
    try {
      child.stdin.end(JSON.stringify(request))
    } catch (error) {
      finish({ ok: false, code: 'E_PYTHON_ENV', message: `Cannot write to Python stdin: ${error.message}` })
    }
  })
}
