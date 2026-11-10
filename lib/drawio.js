/**
 * draw.io desktop CLI bridge.
 *
 * The CLI is always invoked with `--size page`: the default `diagram` mode
 * crops to the content bounding box, whose stroke/AA margin varies by ±2px and
 * cannot be used for absolute crop coordinates. Page mode gives
 * `px = logical * scale` with origin (0, 0) plus a fixed 2px right/bottom
 * margin (calibrated by test_calibration.py).
 */
import { spawn } from 'node:child_process'

export const DRAWIO_TIMEOUT_MS = 60000

export function drawioArgs({ input, output, scale }) {
  return [
    '-x',
    '-f', 'png',
    '-s', String(scale),
    '--size', 'page',
    '-b', '0',
    '-o', output,
    input,
  ]
}

function tail(text, limit = 800) {
  const value = String(text ?? '').trim()
  return value.length > limit ? '…' + value.slice(-limit) : value
}

/**
 * Run one draw.io export.
 * @returns {Promise<{ok: true, elapsedMs: number} | {ok: false, code: string, message: string, details?: object}>}
 */
export function runDrawio({
  drawioPath,
  input,
  output,
  scale,
  timeoutMs = DRAWIO_TIMEOUT_MS,
  signal,
  spawnImpl = spawn,
}) {
  return new Promise((resolve) => {
    const started = Date.now()
    let child
    try {
      child = spawnImpl(drawioPath, drawioArgs({ input, output, scale }), {
        windowsHide: true,
        stdio: ['ignore', 'pipe', 'pipe'],
        signal,
      })
    } catch (error) {
      resolve({
        ok: false,
        code: 'E_RENDER_FAILED',
        message: `Cannot start draw.io at ${drawioPath}: ${error.message}`,
        details: { drawioPath },
      })
      return
    }
    let stderr = ''
    let settled = false
    const finish = (value) => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      resolve(value)
    }
    const timer = setTimeout(() => {
      try {
        child.kill('SIGKILL')
      } catch {
        // already gone
      }
      if (process.platform === 'win32' && child.pid) {
        try {
          spawnImpl('taskkill', ['/PID', String(child.pid), '/T', '/F'], {
            windowsHide: true,
            stdio: 'ignore',
          })
        } catch {
          // best effort
        }
      }
      finish({
        ok: false,
        code: 'E_RENDER_TIMEOUT',
        message: `draw.io did not finish within ${timeoutMs} ms.`,
        details: { drawioPath, timeoutMs },
      })
    }, timeoutMs)
    child.stderr.on('data', (chunk) => {
      if (stderr.length < 65536) stderr += chunk
    })
    child.on('error', (error) => {
      finish({
        ok: false,
        code: 'E_RENDER_FAILED',
        message: `Failed to start draw.io at ${drawioPath}: ${error.message}`,
        details: { drawioPath, code: error.code },
      })
    })
    child.on('close', (code) => {
      if (code !== 0) {
        finish({
          ok: false,
          code: 'E_RENDER_FAILED',
          message: `draw.io failed (exit ${code}): ${tail(stderr)}`,
          details: { drawioPath, exitCode: code },
        })
        return
      }
      finish({ ok: true, elapsedMs: Date.now() - started })
    })
  })
}
