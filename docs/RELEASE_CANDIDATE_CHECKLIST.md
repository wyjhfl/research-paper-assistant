# Release Candidate Checklist

RC 门禁命令，按顺序执行，不要并行。

> 标注：**只读** = 不修改任何数据；**写入 artifacts** = 生成报告/备份文件；**禁止执行** = 不得在门禁中运行

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
