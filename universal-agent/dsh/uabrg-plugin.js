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

return {
  inject: ['shell', 'timer'],
  apply(ctx) {
    const shell = ctx.get('shell')
    if (shell === undefined) return
    const timer = ctx.get('timer')
    const UA_ROOT = '/Users/huhongjie/Desktop/扫描决策类agent/universal-agent'
    const PY = '/Users/huhongjie/Desktop/扫描决策类agent/.venv/bin/python'

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
  },
}
