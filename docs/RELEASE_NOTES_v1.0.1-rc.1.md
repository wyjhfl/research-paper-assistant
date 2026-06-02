# Release Notes v1.0.1-rc.1

## 版本信息

- **版本号**: 1.0.1-rc.1
- **类型**: Patch Release Candidate
- **日期**: 2026-05-31

## 变更摘要

v1.0.1 是一个 patch release，聚焦生产化加固和运维能力增强，不包含新功能。

### Phase 0: Python Gate 探测硬化

- 统一 `verify_all.ps1`、`quick_gate.ps1`、`rc_gate.ps1` 的 Python 探测逻辑
- 新增 `Test-PythonCandidate` helper，通过执行 `--version` 验证候选 Python 可用性
- 新增 `Resolve-PythonCommand` 返回结构化对象（Exe + Args），避免 `& "py -3"` 执行失败
- 解决 Windows Store Python alias 误判问题

### Phase 1: OPS_TOKEN 只读 Worker Health 认证

- 新增 `OPS_TOKEN` 配置项，用于 `/jobs/worker/health` 端点认证
- `hmac.compare_digest` 时序安全比较
- 生产模式 `AUTH_ENABLED=true` 时强制 token 验证
- 开发模式 `AUTH_ENABLED=false` 时 token 可选
- `ops_check.ps1` 支持 `-OpsToken` 参数

### Phase 2: Storage Orphan 清理 SOP

- 增强 `cleanup_storage.py`：dry-run 默认、`--confirm` 显式确认、JSON 结构化输出
- 新增 `_referenced_rel_path` helper，正确处理绝对路径、`storage/` 前缀、纯相对路径
- `storage_audit.py` 同步增强：`followlinks=False`、symlink 跳过、forward-slash 归一化
- 路径穿越防护、安全文件名处理

### Phase 3: CI/CD 生产门禁增强

- 新增 `frontend-e2e` job（Playwright E2E，仅 push main + workflow_dispatch）
- 新增 `backend-integration` job（Docker Compose DB 集成测试）
- 新增 `docker-compose.ci.yml` override，防止 CI 读取 `.env`
- 并发控制：同一分支新提交取消旧运行
- CI 不运行 `eval_real_model.py`、不执行 restore、不上传 artifacts/backups

### Phase 4: Backup Freshness 定时化

- 新增 `backup-freshness.yml` GitHub Actions workflow
- `check_backup_freshness.py` 支持 `yyyyMMdd_HHmmssZ`（backup_all.ps1 格式）、ISO Z、ISO aware、naive ISO
- 按 manifest `timestamp` 字段选择最新 manifest（不按文件 mtime）
- `_try_parse_timestamp` 精确区分合法 timestamp vs mtime_fallback
- 损坏 JSON manifest 跳过并 warning；全部损坏 exit 1
- `BACKUP_FRESHNESS_ENABLED` repository variable 控制 schedule 启用

### Phase 5: RC Evidence Pack

- 新增 `scripts/collect_rc_evidence.py`，只读收集仓库状态和门禁结果摘要
- 输出到 `artifacts/rc/`（已 gitignored），JSON + Markdown 摘要
- 证据内容不得包含 secrets、绝对路径、artifacts 内容
- git 不可用时记录 unavailable，不失败
- scanner 失败时 exit 1

## 验证结果

> 以下为各 Phase 本地静态验证结果，非全量 CI/Docker/Playwright 验证。

| Phase | 验证方式 | 结果 |
|-------|---------|------|
| Phase 0 | 本地静态测试 | passed |
| Phase 1 | 本地 pytest + 静态测试 | passed |
| Phase 2 | 本地 pytest + 静态测试 | passed |
| Phase 3 | 本地静态测试（CI workflow 结构） | passed |
| Phase 4 | 本地 pytest + 静态测试 | passed |
| Phase 5 | 本地 pytest + smoke 测试 | passed |

## 未执行项

- Docker build / Docker Compose 集成测试：未在本地环境执行
- Playwright E2E 测试：未在本地环境执行
- GitHub Actions CI 完整运行：未执行
- `verify_all.ps1` 全量验收：未执行
- 真实模型 eval（`eval_real_model.py`）：未执行
- `rc_gate.ps1` 完整门禁：未执行

## 安全约束

- 不包含 .env 内容
- 不包含 API key（sk-/tp- 前缀）
- 不包含 DATABASE_URL 真实值
- 不包含 Authorization header
- 不包含 session token
- 不包含宿主机绝对路径

## 已知限制

- `X-User-Id` 仅开发模式有效，不是生产认证
- local provider 的 hash embedding 和 mock LLM 语义能力有限
- Windows Hyper-V 可能排除端口 7991-8090，当前后端映射为 8091:8000
- backup-freshness schedule 默认不执行，需 `BACKUP_FRESHNESS_ENABLED=true`
