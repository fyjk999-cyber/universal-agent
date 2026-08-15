# legacy/ — 早期原型归档（DO NOT EXTEND）

> 依据 SPAC §32（Legacy Cleanup）· Reality Audit 结论：早期原型，已归档，不再演进。

## 审计结论（2026-08-14，CHAPTER 0）

| 目录 | 内容 | 判定 | 处理 |
|---|---|---|---|
| `legacy/scanner/` | 早期 ScanTask 框架（任务抽象/注册/调度、fx、history、report、run） | 早期原型 | 归档，不扩展 |
| `legacy/tasks/flights_zqn/` | 首个实例任务：杭州/上海 → Queenstown(ZQN) 往返机票扫描（日期组合、评分、Top5、价格提醒、报告） | 早期原型 | 归档，不扩展 |

## 归档理由

- 该框架与业务逻辑已被 `universal-agent/`（Universal Agent Core）完整取代：
  - `scanner.core.ScanTask` → `universal_agent/coordinator/task_registry/` + `domains/flight/`
  - `tasks/flights_zqn` 的搜索/评分/Top5/价格提醒 → `domains/flight/` + `adapters/skyscanner/` + `core/scoring/` + `core/opportunity/` + `notifications/`
- `universal-agent/` 无任何代码 import 本目录（已 grep 验证）。
- 按 SPAC §32：不得同时存在两套持续演进的主框架。此处仅保留作历史参考。

## 规则

1. **DO NOT EXTEND**：禁止在此目录新增或修改业务逻辑。
2. 若未来需要复用其中的思路（如 ZQN 日期组合生成），先提取到 `universal-agent/domains/flight/` 的对应模块并写测试，不在本目录演进。
3. 如需删除整个 `legacy/`，git 历史仍保留全部内容。
