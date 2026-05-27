# Deployment Runbook — v1.0.0

本文件是多 Agent 科研论文助手 v1.0.0 的生产部署操作手册。

## 1. 从 GitHub 获取代码

```bash
git clone https://github.com/wyjhfl/research-paper-assistant.git
cd research-paper-assistant
git checkout v1.0.0
```

或更新已有仓库：

```bash
cd research-paper-assistant
git fetch origin
git checkout v1.0.0
```

## 2. 配置 .env

```bash
cp .env.example .env
```

编辑 `.env`，按需修改以下关键配置：

| 变量 | 生产环境必须设置 | 说明 |
|------|-----------------|------|
| AUTH_ENABLED | `true` | 启用真实认证 |
| ALLOW_DEV_USER_HEADER | `false` | 禁止 X-User-Id 伪造 |
| SESSION_COOKIE_SECURE | `true`（需 HTTPS） | Session Cookie Secure 属性 |
| CORS_ALLOWED_ORIGINS | HTTPS 域名 | 允许的跨域来源 |
| DATABASE_URL | 按实际配置 | 数据库连接 |
| LLM_PROVIDER / EMBEDDING_PROVIDER | `openai_compatible` | 真实模型 provider |
| LLM_API_KEY / EMBEDDING_API_KEY | 真实 key（不提交） | API Key |

> **安全要求**：
> - 不要使用 `.env.example` 中的占位符作为真实 key
> - `.env` 不提交到 Git（已在 `.gitignore` 中）
> - 如果 key 曾暴露，必须轮换后再部署

## 3. Docker Compose 启动

```bash
docker compose up -d --build
```

验证服务状态：

```bash
docker compose ps
```

预期 3 个服务运行：`backend`、`frontend`、`db`。

## 4. Alembic 数据库迁移

```bash
docker compose exec backend python -m alembic upgrade head
```

确认当前版本：

```bash
docker compose exec backend python -m alembic current
```

预期：`003_job_runs (head)`

> 旧开发环境需先 stamp baseline：
> ```bash
> docker compose exec backend python -m alembic stamp 001_baseline
> docker compose exec backend python -m alembic upgrade head
> ```

## 5. Production Check

```bash
docker compose exec backend python scripts/production_check.py
```

预期：`19/19 ALL CHECKS PASSED`

检查项包括：Database / pgvector / Core tables / Storage / Eval / CORS / Real model / Alembic / Backup dir / Backup manifest / Auth config / Job worker / Job poll interval / Job max attempts / Job stale running / Maintenance scripts / Validate manifest script / ENV / Embedding dimension

> **FAIL 会立即退出（exit 1），不允许降级为 WARN。**

## 6. 前端访问检查

| URL | 预期 |
|-----|------|
| http://localhost:3000 | 首页，显示"多 Agent 科研论文助手" |
| http://localhost:8091/health | `{"status": "ok", ...}` |

## 7. 登录/注册检查

如 AUTH_ENABLED=true：

1. 访问 `/register`，注册新用户
2. 注册成功后跳转 `/login`
3. 登录成功后跳转首页
4. 导航栏显示用户名和登出按钮

如 AUTH_ENABLED=false（开发模式）：

- 导航栏显示 UserSwitcher，默认用户 "default"

## 8. PDF 上传 Smoke

```bash
# 写入 demo 数据
docker compose exec backend python scripts/seed_demo.py
```

访问 `/papers`，确认显示 3 篇 demo 论文。

## 9. Job Worker Health 检查

```bash
curl http://localhost:8091/jobs/worker/health
```

预期：返回 worker 健康状态 JSON。

## 10. 备份

```powershell
powershell -ExecutionPolicy Bypass -File scripts/backup_all.ps1
```

产物输出到 `artifacts/backups/`：
- `db/db_backup_<timestamp>.sql`
- `storage/storage_backup_<timestamp>.zip`
- `evals/eval_backup_<timestamp>.zip`（可选）
- `backup_manifest_<timestamp>.json`

## 11. 校验 Backup Manifest

```bash
docker compose exec backend python scripts/validate_backup_manifest.py artifacts/backups/backup_manifest_<timestamp>.json
```

预期：`{"ok": true, "errors": [], "warnings": []}`

## 12. Restore Dry-Run

```powershell
powershell -ExecutionPolicy Bypass -File scripts/restore_all.ps1 -ManifestPath artifacts/backups/backup_manifest_<timestamp>.json -DryRun
```

预期：DB + Storage + Eval 均找到，Validation passed，无数据修改。

> **禁止在部署门禁中执行真实 restore**：`restore_all.ps1 -ConfirmRestore` 仅在运维手动操作时使用。

## 13. Storage Audit

```bash
docker compose exec backend python scripts/storage_audit.py
```

输出：total_files / orphan_files / missing_files 统计。

## 14. 常见故障与恢复

### Docker 服务未启动

```bash
docker compose up -d --build
docker compose ps
```

### 数据库连接失败

1. 检查 `db` 服务是否运行：`docker compose ps db`
2. 检查 DATABASE_URL 配置
3. 重启：`docker compose restart db backend`

### 前端无法访问后端

1. 检查 `NEXT_PUBLIC_API_URL` 和 `INTERNAL_API_URL`
2. Docker 内部通信使用 `http://backend:8000`
3. 浏览器端使用 `http://localhost:8091`

### Alembic 版本不一致

```bash
docker compose exec backend python -m alembic current
docker compose exec backend python -m alembic upgrade head
```

### pytest 在 Docker 中卡死

并行 pytest 导致 TRUNCATE/DDL 锁。恢复流程见 OPERATIONS_RUNBOOK §12：
1. 停止所有 pytest 进程
2. 等待 30 秒
3. 顺序重跑

### 端口冲突

Windows Hyper-V 可能保留端口范围。检查：
```bash
netsh interface ipv4 show excludedportrange protocol=tcp
```

修改 `docker-compose.yml` 中的端口映射。

## 15. Rollback / 回滚步骤

### 回滚到上一版本

1. 停止当前服务：
   ```bash
   docker compose down
   ```

2. 切换到上一版本 tag：
   ```bash
   git fetch origin
   git checkout v1.0.0-rc.1
   ```

3. 重建并启动：
   ```bash
   docker compose up -d --build
   ```

4. 如需恢复数据（使用最近的备份）：
   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts/restore_all.ps1 -ManifestPath artifacts/backups/backup_manifest_<timestamp>.json -ConfirmRestore
   ```

### 数据库回滚

```bash
docker compose exec backend python -m alembic downgrade <target_revision>
```

> **注意**： downgrade 可能不可逆，执行前确保有有效备份。

### 完全重建

```bash
docker compose down -v
docker compose up -d --build
docker compose exec backend python -m alembic upgrade head
```

> **警告**：`-v` 会删除所有 Docker volume（数据库数据、上传文件等）。仅在确认无需保留数据时使用。
