"""通用定时扫描 Agent 框架 (Generic Scheduled Scanner Framework)

设计目标：
  - 任务无关的通用骨架：任务注册、历史记录、报告渲染、汇率换算、调度安装。
  - 具体任务通过 tasks/<task_name>/task.py 注册，只需实现 ScanTask 接口。
  - 一次构建，可承载任意“定时扫描类”任务（机票、价格、库存、监控等）。

包结构：
  scanner/core.py    任务抽象与注册表
  scanner/history.py 历史记录存储与趋势对比
  scanner/fx.py      汇率换算
  scanner/report.py  Markdown 报告通用组件
  scanner/run.py     CLI 入口（扫描 / 历史 / 安装 cron / 测试）
  tasks/<name>/      具体任务实现
"""

__version__ = "1.0.0"
