# Release Candidate Checklist

RC 门禁命令，按顺序执行，不要并行。

> 标注：**只读** = 不修改任何数据；**写入 artifacts** = 生成报告/备份文件；**禁止执行** = 不得在门禁中运行

---

## v1.0.1 正式发布流程

v1.0.1 正式发布基于 v1.0.1-rc.1（commit d1d3715）+ 用户人工确认 GitHub Actions 成功。流程如下：

1. 版本从 1.0.1-rc.1 提升为 1.0.1（config.py / .env.example / API_CONTRACT.md）
2. 新增 `docs/RELEASE_NOTES_v1.0.1.md`（正式发布说明）
3. 更新测试覆盖 final 版本一致性
4. 运行本地 pytest + pre_tag_check + secret scan + mojibake scan
5. 提交 `release: finalize v1.0.1` commit
6. 创建 `v1.0.1` tag + push commit + push tag
7. 人工检查 GitHub Actions

> v1.0.1-rc.1 文档和 tag 保留为历史记录，不修改已推送的 rc.1 tag。

---

## v1.0.0 正式发布流程

v1.0.0 正式发布基于 v1.0.0-rc.1 + Phase 44 E2E 证据更新。流程如下：

1. 提交 Phase 44 E2E 证据更新（commit 9b39612）
2. 新增 `docs/RELEASE_NOTES_v1.0.0.md`（正式发布说明）
3. 新增 `docs/RELEASE_EVIDENCE_v1.0.0.md`（正式发布证据）
4. 更新 README.md / RELEASE_CANDIDATE_CHECKLIST.md
5. 运行完整 RC gate（7 步 + backup validate + restore dry-run）
6. 全部通过后：`git tag -a v1.0.0 -m "v1.0.0"` + `git push origin v1.0.0`
7. 在 GitHub 创建 Release，关联 v1.0.0 tag

> v1.0.0-rc.1 文档保留为历史记录，不修改已推送的 rc.1 tag。

---

## 验收分层策略

不要每个小 Phase 都跑完整 E2E / 全量 pytest。根据改动范围选择对应层级：

| Level | 适用场景 | 必须通过 | 预计耗时 |
|-------|----------|----------|----------|
| **Level 1** | 文档/配置小改（README、.env.example、注释） | secret scan + 对应窄测试 | < 1 min |
| **Level 2** | 脚本/后端小改（单个 test file 内的改动） | secret scan + 对应 test file | 1-5 min |
| **Level 3** | API/DB/认证/Job 语义改动 | secret scan + 相关模块测试 + production check | 5-15 min |
| **Level 4** | RC/tag 前 | 完整 `rc_gate.ps1` 一次 | 15-30 min |

### Level 1：文档/配置小改

```powershell
python scripts/check_docs_secrets.py
python scripts/check_frontend_mojibake.py
# 如改了 .env.example，额外跑：
python -m pytest apps/api/tests/test_backup_lifecycle.py -q -k "env_example"
```

### Level 2：脚本/后端小改

```powershell
python scripts/check_docs_secrets.py
# 只跑改动的 test file，例如：
docker compose exec -T backend python -m pytest tests/test_backup_lifecycle.py -q
```

### Level 3：API/DB/认证/Job 语义改动

```powershell
python scripts/check_docs_secrets.py
python scripts/check_frontend_mojibake.py
docker compose exec -T backend python scripts/production_check.py
docker compose exec -T backend python -m alembic current
docker compose exec -T backend python -m pytest tests/test_<相关模块>.py -q
```

### Level 4：RC/tag 前

```powershell
# 只跑一次完整 RC gate
powershell -ExecutionPolicy Bypass -File scripts/rc_gate.ps1
```

> **原则**：小改窄验证，RC 前一次全量。不要反复跑全量 pytest 浪费时间。

---

## Step 1: 文档密钥扫描（只读）

```powershell
python scripts/check_docs_secrets.py
```

## Step 2: 前端乱码扫描（只读）

```powershell
python scripts/check_frontend_mojibake.py
```

## Step 3: Scanner 自身测试（只读）

```powershell
python -m pytest tests/test_check_docs_secrets.py -q
```

## Step 4: Production Check（只读）

```powershell
docker compose exec -T backend python scripts/production_check.py
```

## Step 5: Alembic Migration Check（只读）

```powershell
docker compose exec -T backend python -m alembic current
```

## Step 6: 后端测试（只读）

```powershell
docker compose exec -T backend python -m pytest tests/ -q
```

## Step 7: 前端构建（写入 .next 产物）

```powershell
cd apps/web; npm run build
```

## Step 8: E2E 测试（只读）

```powershell
cd apps/web; npx playwright test
```

## Step 9: Backup Manifest Validate（只读）

```powershell
docker compose exec -T backend python scripts/validate_backup_manifest.py artifacts/backups/backup_manifest_xxx.json
```

## Step 10: Restore Dry-Run（只读，写入 drill record）

```powershell
powershell -ExecutionPolicy Bypass -File scripts/restore_all.ps1 -ManifestPath artifacts/backups/backup_manifest_xxx.json -DryRun
```

> **禁止执行**：`restore_all.ps1 -ConfirmRestore` 不得在 RC 门禁中运行。

---

## 一键执行

```powershell
# 完整 RC 门禁
powershell -ExecutionPolicy Bypass -File scripts/rc_gate.ps1

# 跳过 E2E
powershell -ExecutionPolicy Bypass -File scripts/rc_gate.ps1 -SkipE2E

# 含备份验证
powershell -ExecutionPolicy Bypass -File scripts/rc_gate.ps1 -ManifestPath artifacts/backups/backup_manifest_xxx.json

# 跳过前端构建
powershell -ExecutionPolicy Bypass -File scripts/rc_gate.ps1 -SkipFrontendBuild

# 开发环境（跳过 production check）
powershell -ExecutionPolicy Bypass -File scripts/rc_gate.ps1 -SkipProductionCheck -SkipE2E
```

---

## RC Tag 前安全检查

在创建 v1.0.0-rc.1 tag 前，必须确认以下安全项：

- `.env` 不得被 Git 跟踪：`git ls-files .env` 必须无输出
- `.env` 不得提交到仓库：`git status --short -- .env` 必须无输出
- 真实 API Key / Token 不得出现在文档、commit message、release notes 中
- 如果 Key 曾暴露（提交到 Git / 出现在日志 / 泄露到公开渠道），必须轮换后再 tag
- `.env.example` 仅包含安全占位符和开发默认值，不含真实 key
- `SESSION_COOKIE_SECURE=true` 需要 HTTPS 环境；本地 HTTP 开发可设为 `false`
- 生产环境 `CORS_ALLOWED_ORIGINS` 不得包含 `*`、`localhost`、`127.0.0.1`、`0.0.0.0`；必须使用 HTTPS 域名
- 生产环境 `ENV=production` 启用严格检查
- Release Notes 不含 secrets（sk- / tp- / DATABASE_URL 真实值 / API_KEY 真实值）
- 当前阶段不跑全量 pytest / Playwright / rc_gate，最终 Phase 43 才跑完整 rc_gate

### 验证命令

```powershell
# 确认 .env 未被跟踪
git ls-files .env
# 预期：无输出

# 确认 .gitignore 包含 .env
Select-String -Path .gitignore -Pattern "^\.env$"
# 预期：匹配到 .env 行

# 扫描文档中的密钥
python scripts/check_docs_secrets.py
# 预期：无真实 key

# 检查 .env.example 包含生产配置项
python -m pytest tests/test_backup_lifecycle.py -q -k "env_example"
# 预期：通过
```

---

## 注意事项

- drill 文件读取必须按 mtime 或文件名排序，不依赖 glob 默认顺序
- 不得在门禁脚本里执行真实 restore（`-ConfirmRestore`）
- 不要并行运行多个后端 pytest，避免 DDL deadlock
- **production_check FAIL 会立即导致 RC gate 失败退出**，不允许降级为 WARN
- `-ManifestPath` 只接受项目相对路径（如 `artifacts/backups/backup_manifest_xxx.json`），不接受绝对路径；传入绝对路径会报错 `ManifestPath must be project-relative`
- 所有 gate 脚本（`verify_all.ps1`、`quick_gate.ps1`、`rc_gate.ps1`）会自动探测宿主机 Python：优先 `python`，其次 `py -3`（Windows Python Launcher）；两者都不存在时明确报错退出，不会静默跳过

## CI Job 说明

CI workflow（`.github/workflows/ci.yml`）包含以下 jobs：

| Job | 触发条件 | 说明 |
|-----|----------|------|
| docs-and-security | 所有触发 | 文档密钥扫描 + 前端乱码扫描 |
| backend-unit | 所有触发 | 轻量后端测试（不依赖数据库） |
| frontend-build | 所有触发 | Next.js 构建验证 |
| frontend-e2e | push main / workflow_dispatch | Playwright E2E 测试（不在 PR 默认运行） |
| backend-integration | push main / workflow_dispatch | Docker Compose DB 集成测试（使用 docker-compose.ci.yml，不读取 .env） |

- workflow_dispatch 可手动触发完整 CI，可选 run_e2e / run_backend_integration
- 并发控制：同一分支新提交取消旧运行
- CI 不运行 eval_real_model.py、不执行 restore、不上传 artifacts/backups
- backend-integration 使用显式测试文件列表，不包含 test_backup_lifecycle.py / test_production_health.py

## Backup Freshness Workflow

| 触发 | 说明 |
|------|------|
| schedule | 每日 00:30 UTC（需 `BACKUP_FRESHNESS_ENABLED=true`） |
| workflow_dispatch | 手动触发，不受 `BACKUP_FRESHNESS_ENABLED` 限制 |

- 只读检查，不备份、不 restore、不删除文件
- 权限最小化 `permissions: contents: read`
- 按 manifest `timestamp` 字段选择最新 manifest（不按文件 mtime），timestamp 缺失/非法才 fallback mtime
- 损坏 JSON manifest 跳过并在 warnings 中记录文件名；全部损坏则 `ok=false`、exit 1
- **生产落地前提**：self-hosted runner 或外部监控环境能访问备份 manifest 目录
- **GitHub hosted runner 不具备生产备份可见性**，不能把它的结果当作生产备份状态
- 不上传 backup artifacts

## RC Evidence Pack

v1.0.1 RC 证据包收集步骤：

```powershell
python scripts/collect_rc_evidence.py --output-dir artifacts/rc
```

- 只读收集，不执行 backup、restore、cleanup --confirm、docker compose up、真实模型 eval
- 输出到 `artifacts/rc/`（已 gitignored）
- 输出 JSON + Markdown 摘要
- 证据内容：timestamp、version、git branch/commit/dirty、workflow 文件存在性、scanner 结果、backup freshness 启用说明
- 证据不得包含：.env 内容、API key、Authorization、DATABASE_URL 真实值、session token、artifacts/backups 内容、artifacts/evals 内容、宿主机绝对路径
- git 不可用时记录 unavailable，不失败
- scanner 失败时 exit 1
- 不是 CI 自动上传，是本地/人工 RC 流程

## Pre-Tag Check

v1.0.1-rc.1 打 tag 前检查步骤：

```powershell
python scripts/pre_tag_check.py
```

- 只读检查，不创建 tag、不 push、不执行 restore/backup/cleanup --confirm/docker compose up/eval_real_model
- 检查项：
  - RELEASE_NOTES_v1.0.1-rc.1.md 存在且不含 ALL CHECKS PASSED
  - collect_rc_evidence.py 存在
  - artifacts/rc/ 已 gitignored
  - .env 未被 git 跟踪（git 不可用时记录 warning，不误报通过）
  - docs secret scan 通过
  - frontend mojibake scan 通过
  - backup-freshness.yml 存在且有 BACKUP_FRESHNESS_ENABLED gate
  - ci.yml 不包含 ConfirmRestore/eval_real_model/artifacts/backups upload
  - version metadata 一致（config.py、.env.example、API_CONTRACT.md）
- 输出结构化 JSON：ok、checks[]、warnings[]
- FAIL 项存在时 exit 1；只有 warnings 时 exit 0
- 不输出绝对路径和 secrets
- 不是 CI 自动流程，是本地/人工 RC 流程，不自动创建 tag
- **pre_tag_check 需要 git 可用**：git 不可用时 .env 跟踪检查返回 ok=false，必须人工修复环境或手动执行等价检查（`git ls-files .env`），不能视为通过
