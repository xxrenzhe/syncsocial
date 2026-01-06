# SyncSocial（SaaS 重构版）

本仓库用于从旧版自动化系统演进到多用户 SaaS 版本。

注意事项（对齐 `docs/BasicPrinciples/MustKnowV1.md`）：
- `docs/`、`oldcode/`、`secrets/` 不纳入代码提交与镜像构建；仅用于本地资料与参考。
- 不要把任何 Cookie/代理/API Key 等敏感信息写入代码库或提交记录。

代码目录（逐步落地）：
- `apps/api/`：FastAPI 后端（鉴权、用户管理、后续接入队列与浏览器集群）
- `apps/web/`：Next.js 控制台（左侧导航：用户功能 / 管理员功能）

