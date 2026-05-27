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
6. **worker health 认证场景**：当 AUTH_ENABLED=true 且 worker health 端点需要认证时，ops_check 只记录 WARN（`worker health requires authenticated session; skipped in read-only ops_check`），不自动登录。如需认证态 worker health 数据，应由人工在受控环境手动检查，或未来设计只读 ops token（不在本阶段实现）
