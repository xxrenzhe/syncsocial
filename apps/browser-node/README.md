# Browser Node（远程浏览器节点）

职责：
- 为 `LoginSession` 提供可交互的浏览器会话（配合 noVNC）
- 提供内部 API：检查登录态、导出 `storage_state`、关闭会话

说明：
- 该服务只应部署在内网，通过 `BROWSER_NODE_INTERNAL_TOKEN` 与 API Server 通信。
- 不要在日志/接口返回中输出任何 Cookie/Storage 值（除 `/storage-state` 内部接口，且仅供 API Server 调用）。

