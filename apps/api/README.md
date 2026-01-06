# SyncSocial API（FastAPI）

本目录为 SaaS 后端服务（Phase 0：鉴权 + 管理员用户管理）。

本地运行（示例）：
- 启动依赖：`docker compose up -d`
- 安装依赖：`python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`
- 安装浏览器（Playwright）：`python -m playwright install chromium`
- 初始化数据库：`alembic upgrade head`
- 初始化管理员：`python -m app.seed`（需先配置环境变量，参考 `.env.example`）
- 启动服务：`uvicorn app.main:app --reload --port 8000`
