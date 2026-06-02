# Operations Monitoring — v1.0.0

本文件定义生产运行后的最小监控闭环：巡检频率、告警条件、操作约束。

## 每日检查

### 执行命令

```powershell
powershell -ExecutionPolicy Bypass -File scripts/ops_check.ps1
python scripts/check_backup_freshness.py --max-age-hours 24
```

### 检查项

| 检查项 | 来源 | 告警条件 |
|--------|------|----------|
| Docker 服务状态 | `docker compose ps` | 任何服务非 running |
| /health | ops_check | status ≠ ok |
| /health/ready | ops_check | ready ≠ true |
| Job worker health | ops_check | stale_running_count > 0 |
| Production check | ops_check | 任何项 FAIL |
| Alembic 版本 | ops_check | 不在 head |
| Storage audit | ops_check | missing_count > 0 |
| Backup freshness | check_backup_freshness.py | 最新备份超过 24h |

> **Backup freshness 定时检查**：GitHub Actions workflow `backup-freshness.yml` 每日 00:30 UTC 自动运行。默认 schedule 不执行（避免 hosted runner 默认红灯），需在 GitHub 仓库设置 `BACKUP_FRESHNESS_ENABLED=true` repository variable 后才启用。生产落地需要 self-hosted runner 或外部监控环境能访问备份 manifest 目录。GitHub hosted runner 不具备生产备份可见性，不能把它的结果当作生产备份状态。stale/missing manifest 只告警/失败，不自动 backup、不 restore、不删除文件。`check_backup_freshness.py` 按 manifest `timestamp` 字段选择最新 manifest（不按文件 mtime），timestamp 缺失/非法才 fallback mtime 并在 warnings 中说明。损坏 JSON manifest 会跳过；全部损坏则失败。

## 每周检查

### 执行命令

```powershell
powershell -ExecutionPolicy Bypass -File scripts/backup_all.ps1
docker compose exec -T backend python scripts/validate_backup_manifest.py artifacts/backups/<latest_manifest>.json
powershell -ExecutionPolicy Bypass -File scripts/restore_all.ps1 -ManifestPath artifacts/backups/<latest_manifest>.json -DryRun
docker compose exec -T backend python scripts/storage_audit.py
```

### 检查项

| 检查项 | 告警条件 |
|--------|----------|
| Backup manifest validate | ok ≠ true |
| Restore dry-run | 验证失败 |
| Storage orphan 增长 | orphan_count 异常增长 |
| Storage missing | missing_count > 0 |

> **所有 restore 只能 dry-run，真实 restore 需人工审批。**

## 每月检查

| 检查项 | 说明 |
|--------|------|
| 依赖更新 | 检查 npm/pip 是否有安全更新 |
| Release evidence 归档 | 确认当月 release 有完整 evidence |
| 灾备演练 | 执行完整 restore dry-run drill，确认恢复路径可用 |
| CI 有效性 | 确认 GitHub Actions CI 正常运行 |
| Ops 脚本有效性 | 确认 ops_check / backup_freshness 正常执行 |

## 告警条件汇总

| 告警 | 条件 | 严重性 |
|------|------|--------|
| Backup 过期 | 最新备份超过 24h | 高 |
| Job stale running | stale_running_count > 0 | 高 |
| Production check FAIL | 任何项 FAIL | 高 |
| Health/ready false | ready ≠ true | 高 |
| Storage missing | missing_count > 0 | 高 |
| Docker 服务异常 | 任何服务非 running | 高 |
| Alembic 版本落后 | 不在 head | 中 |
| Storage orphan 增长 | orphan_count 异常 | 低 |

> **orphan_count 异常增长只告警，不自动修复。** 需人工按 OPERATIONS_RUNBOOK.md 中 Storage Orphan 清理 SOP 执行 dry-run → 审核 → --confirm。禁止自动化 --confirm。

## 告警建议

- 邮件 / Slack / 企业微信通知
- 高严重性告警需 15 分钟内响应
- 低严重性告警可在下次巡检时处理
- 告警必须可操作，避免告警疲劳

## 操作约束

1. **ops_check 只读**：不执行任何写入、恢复、备份操作；不注册用户、不登录、不创建 session、不发送 POST 请求
2. **backup freshness 不输出绝对路径**：只输出文件名
3. **stale job 告警不自动删除/重置任务**：需人工判断后操作
4. **所有 restore 只能 dry-run**：`-ConfirmRestore` 需人工审批
5. **不读取 .env**：监控脚本不依赖 .env 内容
6. **worker health 认证场景**：当 AUTH_ENABLED=true 时，可配置 OPS_TOKEN 环境变量让 ops_check 通过 X-Ops-Token header 访问 /jobs/worker/health。OPS_TOKEN 只允许访问 worker health 端点（全局统计），不允许访问 /jobs 等业务接口。OPS_TOKEN 为空时，ops_check 仍 WARN 跳过。token 比较使用 hmac.compare_digest 防止 timing leak。不要在日志或 API 响应中输出 OPS_TOKEN 值
