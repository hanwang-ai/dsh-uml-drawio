/** Plugin configuration (schemastery) and the runtime value reader. */
import z from '@deepseek-ai/schemastery'

const DEFAULT_PYTHON = 'C:\\Program Files\\Python314\\python.exe'
const DEFAULT_DRAWIO = 'D:\\drawio\\draw.io\\draw.io.exe'
const DEFAULT_CJK = 'C:\\Windows\\Fonts\\msyh.ttc'
const DEFAULT_LATIN = 'C:\\Windows\\Fonts\\arial.ttf'

export const Config = z.object({
  pythonPath: z.string().default(DEFAULT_PYTHON).description(
    'Python interpreter with Pillow installed (Pillow 12.x tested).',
  ).volatile(),
  drawioPath: z.string().default(DEFAULT_DRAWIO).description(
    'draw.io desktop executable used for PNG rendering.',
  ).volatile(),
  fontCjk: z.string().default(DEFAULT_CJK).description(
    'CJK font file; msyh.ttc uses index 0.',
  ).volatile(),
  fontLatin: z.string().default(DEFAULT_LATIN).description(
    'Latin font file (arial.ttf).',
  ).volatile(),
})

function read(value, fallback) {
  if (value === undefined || value === null) return fallback
  if (typeof value === 'object' && typeof value.get === 'function') return value.get()
  return value
}

/** Unwrap volatile settings handles into plain strings. */
export function resolveConfig(config = {}) {
  return {
    pythonPath: read(config.pythonPath, DEFAULT_PYTHON),
    drawioPath: read(config.drawioPath, DEFAULT_DRAWIO),
    fontCjk: read(config.fontCjk, DEFAULT_CJK),
    fontLatin: read(config.fontLatin, DEFAULT_LATIN),
  }
}

export function fontsOf(cfg) {
  return { cjk: cfg.fontCjk, latin: cfg.fontLatin }
}
