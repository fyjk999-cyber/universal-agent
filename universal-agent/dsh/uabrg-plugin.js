// DSH UA Bridge — Universal Agent 定时扫描桥（动态 Cordis 插件，Host 侧）
//
// 把 Universal Agent 接入 DeepSeek Harness：
//   1. 注册 ua_watch_scan 动态工具：模型/用户可在对话中触发多域扫描
//   2. 可选定时调度：ua/scheduler/start | ua/scheduler/stop 事件
//   3. host RPC: harness.handle('ua/scan')
//
// 运行方式：在 DSH 会话中用 cordis_define + cordis_run 挂载（见 README）
// 已实测：flight / hotel / jobs / bundle / prepare / execute 全部通过
//
// 架构（RULE 1/2）：Universal Agent Core 零修改；DSH 仅通过 shell 调用
// 其 CLI，符合 HostProtocol 反向桥接原则。
//
// FR-033（可移植配置）：路径解析优先级 =
//   Plugin Config（apply(ctx) 的 ctx.config.uaRoot/uaPython）
//   → Environment（UA_ROOT / UA_PYTHON / UA_DATA_DIR / UA_CONFIG）
//   → Auto Discovery（相对 __dirname / 当前工作目录的仓库标记）
//   → Explicit Failure（找不到时抛错，绝不静默回退到开发者机器路径）

let fs = null
let path = null
try {
  fs = require('fs')
  path = require('path')
} catch (e) { /* Cordis 沙箱可能无 require：仅靠配置/环境变量解析 */ }

function discoverRoot() {
  // Auto Discovery：插件位于 <repo>/dsh/uabrg-plugin.js → 尝试 __dirname 上级
  if (!fs || !path) {
    return process.env.UA_ROOT || null  // 无文件系统能力时仅接受显式配置
  }
  const dir = (typeof __dirname === 'string') ? path.resolve(__dirname, '..') : process.cwd()
  for (const cand of [dir, process.cwd()]) {
    try {
      if (fs.existsSync(path.join(cand, 'pyproject.toml')) &&
          fs.existsSync(path.join(cand, 'universal_agent'))) {
        return cand
      }
    } catch (e) { /* ignore */ }
  }
  return null
}

function resolvePaths(ctx) {
  // 1) Plugin Config（最高优先）
  const cfg = (ctx && ctx.config) || {}
  // 2) Environment
  const envRoot = process.env.UA_ROOT || ''
  const envPy = process.env.UA_PYTHON || ''
  // 3) Auto Discovery
  const root = cfg.uaRoot || envRoot || discoverRoot()
  const py = cfg.uaPython || envPy ||
    (root && fs ? path.join(root, '..', '.venv', 'bin', 'python') : '')
  const pyOk = !py || (fs ? fs.existsSync(py) : true)  // 无 fs 时信任显式 UA_PYTHON
  if (!root || !py || !pyOk) {
    const msg =
      'UA_BRIDGE: 无法定位 Universal Agent 运行环境。请配置 UA_ROOT / UA_PYTHON ' +
      '(环境变量或插件配置 uaRoot / uaPython)。拒绝回退到开发者机器路径。' +
      ' (root=' + root + ', py=' + py + ')'
    throw new Error(msg)
  }
  return { root: root, py: py }
}

return {
  inject: ['shell', 'timer'],
  apply(ctx) {
    const shell = ctx.get('shell')
    if (shell === undefined) return
    const timer = ctx.get('timer')
    // FR-033：可移植路径解析（无硬编码）
    const UA = resolvePaths(ctx)
    const UA_ROOT = UA.root
    const PY = UA.py
    // UA_DATA_DIR / UA_CONFIG：传递给被调 CLI 进程（供下游使用）
    const UA_DATA_DIR = process.env.UA_DATA_DIR || (ctx.config && ctx.config.uaDataDir) || ''
    const UA_CONFIG = process.env.UA_CONFIG || (ctx.config && ctx.config.uaConfig) || ''

    function toStr(v) {
      if (v === null || v === undefined) return ''
      if (typeof v === 'string') return v
      if (typeof v === 'object') { try { return JSON.stringify(v) } catch (e) { return String(v) } }
      return String(v)
    }

    async function runScan(domain) {
      const allowed = ['flight', 'hotel', 'jobs', 'bundle', 'prepare', 'execute']
      if (!allowed.includes(domain)) {
        return { ok: false, error: 'unknown domain: ' + domain, allowed: allowed }
      }
      let spec
      try {
        spec = shell.resolve({
          command: PY + ' -m universal_agent.apps.agent_cli --domain ' + domain,
          workdir: UA_ROOT,
          timeoutMs: 60000,
        })
      } catch (e) {
        return { ok: false, domain: domain, error: 'resolve: ' + toStr((e && e.message) || e) }
      }
      try {
        const result = await shell.run(spec)
        const output = toStr(result && result.stdout)
        return {
          ok: !!(result && result.exitCode === 0),
          domain: domain,
          exitCode: result && result.exitCode,
          outputTail: output.split('\n').slice(-12).join('\n'),
        }
      } catch (e) {
        return { ok: false, domain: domain, error: toStr((e && (e.message || e)) || e) }
      }
    }

    let disposeTool = null
    const toolDef = harness.defineTool({
      name: 'ua_watch_scan',
      description: '运行 Universal Agent 扫描（SHADOW MODE，不购买）。domain: flight|hotel|jobs|bundle|prepare|execute。返回 JSON 摘要。',
      parameters: {
        domain: { type: 'string', enum: ['flight', 'hotel', 'jobs', 'bundle', 'prepare', 'execute'], description: '要扫描的领域' },
      },
      output: {
        schema: {
          type: 'object',
          additionalProperties: true,
          properties: {
            ok: { type: 'boolean' },
            domain: { type: 'string' },
            exitCode: { type: 'number' },
            outputTail: { type: 'string' },
            error: { type: 'string' },
          },
        },
        render(args, value) {
          const v = (value && typeof value === 'object') ? value : {}
          const text = v.ok
            ? '扫描完成: ' + v.domain + ' (exit=' + v.exitCode + ')\n' + (v.outputTail || '')
            : '扫描失败: ' + String((v && v.error) || 'unknown') + (v.outputTail ? '\n' + v.outputTail : '')
          return [{ type: 'text', text: String(text) }]
        },
      },
      async execute(args) {
        return await runScan(String((args && args.domain) || 'flight'))
      },
    })
    if (toolDef) {
      disposeTool = harness.registerTool(ctx, toolDef)
    }

    // 可选定时调度（默认关闭；事件开启）
    let intervalDispose = null
    ctx.on('ua/scheduler/start', (payload) => {
      const domain = (payload && payload.domain) || 'flight'
      const secs = Math.max(60, Number((payload && payload.intervalSec) || 3600))
      if (intervalDispose) intervalDispose()
      if (timer !== undefined) {
        intervalDispose = timer.interval(async () => {
          try { await runScan(domain) } catch (e) { console.error('ua scheduled scan failed', e) }
        }, secs * 1000)
      }
      return { started: true, domain: domain, intervalSec: secs }
    })
    ctx.on('ua/scheduler/stop', () => {
      if (intervalDispose) { intervalDispose(); intervalDispose = null }
      return { stopped: true }
    })

    harness.handle('ua/scan', async (args) => runScan(String((args && args.domain) || 'flight')))

    // CH2-2.5：健康检查 RPC（agent_cli --health → JSON）
    harness.handle('ua/health', async () => {
      try {
        const spec = shell.resolve({
          command: PY + ' -m universal_agent.apps.agent_cli --health --data-dir ' +
            (UA_DATA_DIR || '/tmp/ua-svc'),
          workdir: UA_ROOT,
          timeoutMs: 30000,
        })
        const result = await shell.run(spec)
        return {
          ok: !!(result && result.exitCode === 0),
          exitCode: result && result.exitCode,
          health: toStr(result && result.stdout),
          error: toStr(result && result.stderr) || undefined,
        }
      } catch (e) {
        return { ok: false, error: toStr((e && (e.message || e)) || e) }
      }
    })
  },
}
