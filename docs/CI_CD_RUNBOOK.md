# CI/CD Runbook — v1.0.0

本文件说明项目 CI 做什么、不做什么，以及后续扩展方向。

## CI Workflow

位置：`.github/workflows/ci.yml`

触发条件：push / pull_request 到 `main` 分支。

### Jobs

| Job | 运行环境 | 内容 |
|-----|----------|------|
| docs-and-security | ubuntu-latest | `check_docs_secrets.py` + `check_frontend_mojibake.py` |
| backend-unit | ubuntu-latest | `test_check_docs_secrets.py` + 轻量 gate 测试（release_notes / rc_evidence / deployment / secret_hygiene） |
| frontend-build | ubuntu-latest | `npm ci` + `npm run build` |

### CI 做什么

- 文档 secret 扫描：确保 docs/ 不含 sk-/tp-/DATABASE_URL 真实值
- 前端乱码扫描：确保前端代码不含 mojibake
- 轻量后端测试：不依赖真实数据库的文档/配置守卫测试
- 前端构建验证：确保 Next.js 可成功编译

### CI 明确不做

| 不做 | 原因 |
|------|------|
| 真实 restore（`-ConfirmRestore`） | 危险操作，仅手动运维 |
| 使用真实 `.env` | CI 不持有生产密钥 |
| 跑真实 provider eval | 需要真实 API Key，成本高 |
| Docker Compose 全栈测试 | 需要数据库，CI 资源有限 |
| Playwright E2E | 需要运行 dev server + 浏览器，后续可加 dedicated job |
| 全量 pytest（453+ tests） | 依赖数据库，CI 中只跑轻量测试 |
| backup / restore drill | 需要运行时环境，属于运维操作 |

### 后续扩展方向

见 [OPERATIONS_BACKLOG.md](./OPERATIONS_BACKLOG.md)。

## 本地验证

CI 命令均可在本地复现：

```bash
python scripts/check_docs_secrets.py
python scripts/check_frontend_mojibake.py
python -m pytest tests/test_check_docs_secrets.py -q
python -m pytest apps/api/tests/test_backup_lifecycle.py -k "release_notes or rc_evidence or deployment or secret_hygiene" -q
cd apps/web && npm ci && npm run build
```

## 故障排查

### CI 失败：secret scan

检查最近提交的文档是否包含 sk-/tp-/DATABASE_URL 真实值。占位符（`<YOUR_...>`、`<REPLACE_ME>`）在白名单中。

### CI 失败：mojibake scan

检查前端代码是否引入乱码中文字符。

### CI 失败：frontend build

检查 TypeScript 类型错误或依赖缺失。本地 `cd apps/web && npm ci && npm run build` 复现。

### CI 失败：backend unit

检查测试是否依赖数据库或 Docker 环境。轻量测试不应依赖运行时服务。
