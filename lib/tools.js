/** Model-facing tool declarations and result rendering. */
import { defineTool } from '@deepseek-ai/dsh-tools'

import { errorText, failure, successText } from './errors.js'
import { runGenerate } from './generate.js'
import { runLint } from './lint.js'
import { runRender } from './render.js'

const RESULT_SCHEMA = {
  type: 'object',
  additionalProperties: true,
  properties: {
    ok: { type: 'boolean', required: true },
  },
}

const TIMEOUT_MS = 180000

function workspaceRootOf(exec) {
  return exec?.agent?.session?.header?.cwd ?? process.cwd()
}

function statsLine(stats) {
  if (!stats) return 'stats: (unavailable)'
  const levels = stats.labelLevels ?? {}
  return [
    `${stats.participants} participants, ${stats.messages} messages, ${stats.fragments} fragments`,
    `(${stats.topLevelFragments} top-level, depth ${stats.maxDepth})`,
    `labels L1=${levels['1'] ?? 0} L2=${levels['2'] ?? 0} self=${levels.self ?? 0}`,
  ].join(' ')
}

function warningsBlock(warnings) {
  if (!Array.isArray(warnings) || warnings.length === 0) return 'warnings: none'
  const lines = ['warnings:']
  for (const warning of warnings) {
    lines.push(`- [${warning.code}] ${warning.message}${warning.path ? ` (${warning.path})` : ''}`)
  }
  return lines.join('\n')
}

function pageLine(page) {
  if (!page) return 'page: (unavailable)'
  return `page: ${Math.round(page.width)}x${Math.round(page.height)}`
}

function renderLint(value) {
  return successText([
    'uml_lint OK',
    pageLine(value.page),
    statsLine(value.stats),
    warningsBlock(value.warnings),
  ])
}

function renderGenerate(value) {
  const lines = [
    'uml_generate OK',
    `path: ${value.path}`,
    `sidecar: ${value.sidecar}`,
    `bytes: ${value.bytes}; md5: ${value.md5}`,
    `${pageLine(value.page)}; cells: ${value.cells}`,
    statsLine(value.stats),
    warningsBlock(value.warnings),
  ]
  if (value.specSource && value.specSource !== 'inline') {
    lines.push(`spec: ${value.specSource}`)
  }
  return successText(lines)
}

function renderRender(value) {
  const lines = [
    'uml_render OK',
    `path: ${value.path}`,
    `size: ${value.width}x${value.height} px; bytes: ${value.bytes}; scale: ${value.scale}; effectiveScale: ${value.effectiveScale}`,
    `renderMs: ${value.renderMs}`,
  ]
  if (value.crop) {
    lines.push(`crop: x=${value.crop.x} y=${value.crop.y} w=${value.crop.w} h=${value.crop.h} (pixels)`)
  }
  lines.push('next: run the human-perspective review checklist from the skill before reporting')
  return successText(lines)
}

function renderFailure(value) {
  return errorText(value)
}

export function createTools({ cfg, probe }) {
  const guard = async (toolName, run) => {
    const probeResult = await probe
    if (!probeResult.ok) {
      return failure(toolName, 'E_PYTHON_ENV', probeResult.message)
    }
    try {
      return await run()
    } catch (error) {
      return failure(toolName, 'E_WRITE_FAILED', `Internal error: ${error?.message ?? error}`)
    }
  }

  const lintTool = defineTool({
    name: 'uml_lint',
    description:
      'Validate a UML sequence diagram spec and report layout warnings without writing files. '
      + 'Uses the same layout engine as uml_generate, so lint results match the generated diagram. '
      + 'Call it before uml_generate and after each fix (max 3 rounds).',
    parameters: {
      spec: {
        type: 'object',
        additionalProperties: true,
        description: 'The sequence diagram spec (JSON object).',
      },
      specPath: { type: 'string', description: 'Workspace-relative path to a spec JSON file; use instead of spec.' },
    },
    output: { schema: RESULT_SCHEMA, render: (_args, value) => (value.ok ? renderLint(value) : renderFailure(value)) },
    timeoutMs: TIMEOUT_MS,
    isConcurrencySafe: () => true,
    execute: async (args, exec) => guard('uml_lint', () => runLint({
      spec: args.spec,
      specPath: args.specPath,
      workspaceRoot: workspaceRootOf(exec),
      cfg,
      signal: exec?.signal,
    })),
  })

  const generateTool = defineTool({
    name: 'uml_generate',
    description:
      'Generate a professional UML sequence diagram as uncompressed .drawio XML from a JSON spec '
      + '(inline `spec`, or `specPath` to a workspace JSON file). '
      + 'Validates the spec, refuses to overwrite a hand-edited file unless force:true, writes a '
      + '<out>.uml.json sidecar, and returns the page size, md5, stats and warnings.',
    parameters: {
      spec: {
        type: 'object',
        additionalProperties: true,
        description: 'The sequence diagram spec (JSON object). Use either spec or specPath.',
      },
      specPath: {
        type: 'string',
        description: 'Workspace-relative path to a spec JSON file; use instead of spec.',
      },
      out: { type: 'string', required: true, description: 'Output path inside the workspace; must end with .drawio.' },
      force: { type: 'boolean', description: 'Overwrite even when the sidecar is missing/corrupt or the hashes differ.' },
    },
    output: { schema: RESULT_SCHEMA, render: (_args, value) => (value.ok ? renderGenerate(value) : renderFailure(value)) },
    timeoutMs: TIMEOUT_MS,
    isConcurrencySafe: () => false,
    execute: async (args, exec) => guard('uml_generate', () => runGenerate({
      spec: args.spec,
      specPath: args.specPath,
      out: args.out,
      force: args.force === true,
      workspaceRoot: workspaceRootOf(exec),
      cfg,
      signal: exec?.signal,
    })),
  })

  const renderTool = defineTool({
    name: 'uml_render',
    description:
      'Render a generated .drawio sequence diagram to PNG with the draw.io desktop CLI '
      + '(full page, 60s timeout), verify it with Pillow, and optionally crop using page-logical '
      + 'coordinates. Returns the final path, width, height and byte size. '
      + 'After a successful render, inspect the PNG and run the human-perspective review checklist '
      + 'from the uml-sequence-drawio skill before reporting the result.',
    parameters: {
      path: { type: 'string', required: true, description: 'Workspace .drawio file to render.' },
      format: { type: 'string', enum: ['png'], description: 'v1 supports png only (default png).' },
      scale: { type: 'integer', description: 'Raster scale 1-4 (default 2).' },
      out: { type: 'string', description: 'Output .png path inside the workspace (default: same name as the .drawio).' },
      crop: {
        type: 'object',
        additionalProperties: false,
        description: 'Crop box in page-logical coordinates (divide 2x-PNG measurements by scale first).',
        properties: {
          x: { type: 'number', required: true },
          y: { type: 'number', required: true },
          w: { type: 'number', required: true },
          h: { type: 'number', required: true },
        },
      },
    },
    output: { schema: RESULT_SCHEMA, render: (_args, value) => (value.ok ? renderRender(value) : renderFailure(value)) },
    timeoutMs: TIMEOUT_MS,
    isConcurrencySafe: () => false,
    execute: async (args, exec) => guard('uml_render', () => runRender({
      path: args.path,
      format: args.format ?? 'png',
      scale: args.scale ?? 2,
      out: args.out,
      crop: args.crop ?? null,
      workspaceRoot: workspaceRootOf(exec),
      cfg,
      signal: exec?.signal,
    })),
  })

  return [lintTool, generateTool, renderTool]
}
