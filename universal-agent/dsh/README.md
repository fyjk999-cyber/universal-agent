# DSH 接入 — Universal Agent ↔ DeepSeek Harness 调度桥

## 状态：✅ 已接入（uabrg-15/pkg-15 运行中，已实测）

把 Universal Agent 接入 DeepSeek Harness（当前宿主），提供：
1. **`ua_watch_scan` 动态工具**：模型/用户在 DSH 对话中直接触发多域扫描
2. **可选定时调度**：`ua/scheduler/start` / `ua/scheduler/stop` 事件（`timer.interval`）
3. **host RPC**：`harness.handle('ua/scan')`

## 已实测输出（2026-08-14）

```
ua_watch_scan(domain=bundle)
→ 扫描完成: bundle (exit=0) 组合 9 个; 最优 total=¥9930

ua_watch_scan(domain=flight)
→ Top5: SHA ¥3980 / PVG ¥4260 / HGH ¥4380 / PVG ¥4520 / HGH ¥5080, 机会分 75.4

ua_watch_scan(domain=jobs)
→ Top3: AI Engineer@DeepMind / ML@Alibaba / Backend@ByteDance

ua_watch_scan(domain=hotel)
→ 候选 3 个; 最佳: Heritage Queenstown ¥850/晚
```

## 架构（RULE 1/2 遵守）

```text
DeepSeek Harness (当前 Host)
   ↓  shell 调用 CLI（HostProtocol 反向桥）
Universal Agent (独立产品，零修改)
```

- **Universal Agent Core 零修改**：DSH 只通过 `shell` 调用 `agent_cli.py`
- 符合 RULE 1/2：换 Jarvis 时只需新的宿主桥，Core 不动

## 重新挂载（重启 DSH 后）

插件源码：`dsh/uabrg-plugin.js`。在 DSH 会话中：

1. `cordis_define` 创建 Plugin（code.host = 文件内容）
2. `cordis_run` 激活
3. 用 `ua_watch_scan` 工具触发扫描

或：通过 `harness.handle` 事件/宿主预设挂载（进阶）。

## 可移植配置（FR-033，2026-08-15 起无硬编码路径）

插件路径解析优先级（拒绝静默回退到开发者机器路径）：

1. **Plugin Config**：`cordis_run` 时传 `{ uaRoot, uaPython, uaDataDir, uaConfig }`
2. **Environment**：`UA_ROOT` / `UA_PYTHON` / `UA_DATA_DIR` / `UA_CONFIG`
3. **Auto Discovery**：相对插件位置 `<repo>/dsh/uabrg-plugin.js` 向上找仓库标记
   （`pyproject.toml` + `universal_agent/`），venv 取 `<repo>/.venv/bin/python`
4. **Explicit Failure**：找不到时抛错，绝不静默使用开发者路径

示例（环境变量方式）：

```bash
export UA_ROOT=/path/to/universal-agent
export UA_PYTHON=/path/to/venv/bin/python
```

## 定时调度用法

- 开始：触发 `ua/scheduler/start` 事件，payload `{ domain, intervalSec }`（间隔 ≥60s）
- 停止：触发 `ua/scheduler/stop`
- 注意：动态插件进程内存在，重启后需重新挂载；持久定时建议用
  `apps/scheduler.py`（WatchDaemon，§15/§60）

## 安全

- SHADOW MODE：工具只触发只读扫描，不购买不执行（§56）
- 遵守 Universal Agent 的 Policy/Kill Switch 边界
