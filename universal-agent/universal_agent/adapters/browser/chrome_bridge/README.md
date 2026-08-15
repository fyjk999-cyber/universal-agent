# Universal Agent 官方会话桥（Chrome 扩展）

让 Universal Agent 在**你本人的 Chrome 个人资料**中打开白名单航司官方页面，
航司登录态由 Chrome 自己保持（可用 Chrome 密码管理器自动填充）。

> 由 `scripts/gen_chrome_bridge.py` 从航司名录生成；白名单变更后重新运行该脚本。

## 安装（只需一次，需你本人操作）

1. Chrome 打开 `chrome://extensions`，开启右上角“开发者模式”。
2. 点击“加载已解压的扩展程序”，选择本目录 `chrome_bridge` 文件夹。
3. 复制 Chrome 显示的扩展程序 ID（可选，供本地应用校验）。
4. 在浏览器打开本地看板（默认 `http://127.0.0.1:8632`），使用“官方会话”功能，
   每次打开官方页面都会先请求你批准（默认拒绝，RULE-007）。

## 严格边界（不可移除）

- **不申请 `cookies` 权限**，不读取、导出或同步 Cookie。
- 不读取 Chrome 密码管理器、保存的密码、网页表单或网页内容。
- 只接受来自本地应用源（`externally_connectable`）的消息，且只可打开
  预先批准的 HTTPS 官方域名（见 `bridge-policy.mjs`）。
- 不处理支付字段，不点击确认付款，不提交购买（SPAC §33 非目标）。
