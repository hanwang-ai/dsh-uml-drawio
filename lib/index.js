/** dsh-uml-drawio: Host plugin entry. */
import { Config, resolveConfig } from './config.js'
import { SKILL_BODY } from './skill-body.js'
import { probePython } from './python.js'
import { createTools } from './tools.js'

export const name = 'dsh-uml-drawio'
export const inject = ['tools']
export { Config }

const SKILL_META = {
  name: 'uml-sequence-drawio',
  description: 'Generate and verify professional UML sequence diagrams (.drawio) from a JSON spec.',
  whenToUse:
    '当用户要求画 UML 时序图 / sequence diagram / 交互图，或要把一段流程描述落成可编辑的 .drawio 时使用。',
}

export function apply(ctx, config) {
  const cfg = resolveConfig(config)
  // Verified once per mount; every tool awaits this promise and fails hard with
  // E_PYTHON_ENV when the interpreter or Pillow is unavailable.
  const probe = probePython({ pythonPath: cfg.pythonPath })

  for (const tool of createTools({ cfg, probe })) {
    ctx.effect(() => ctx.tools.register(tool))
  }

  // `skills` is optional: deployments without a skill registry still work.
  const skills = typeof ctx.get === 'function' ? ctx.get('skills') : undefined
  if (skills && typeof skills.register === 'function') {
    if (SKILL_BODY.trim() !== '') {
      ctx.effect(() => skills.register({
        ...SKILL_META,
        // Required by the registry's validateDefinition when the body is loaded.
        source: 'runtime',
        content: SKILL_BODY,
      }))
    }
  }
}
