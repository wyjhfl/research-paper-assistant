# Post-Release Issue Template

发布后问题报告模板。复制此模板创建新问题。

## 问题类型

- [ ] bug — 功能缺陷或异常行为
- [ ] ops — 运维/部署/监控问题
- [ ] security — 安全漏洞或配置风险
- [ ] docs — 文档错误或缺失
- [ ] enhancement — 体验改进或功能建议

## 影响范围

- 影响的功能模块：
- 影响的用户群体：
- 是否影响数据完整性：

## 复现步骤

1.
2.
3.

## 预期行为

## 实际行为

## 日志摘要

> **注意**：日志中不得包含 .env 内容、API Key（sk-/tp- 前缀）、DATABASE_URL 真实值、Authorization header、session token。如有必要，用 `<REDACTED>` 替换敏感值。

```
在此粘贴日志摘要（脱敏后）
```

## 环境信息

- 应用版本：
- 部署方式：Docker Compose / 本地开发
- AUTH_ENABLED：true / false
- Provider：local / openai_compatible
- 浏览器（如前端问题）：
- 操作系统：

## 严重级别

- [ ] P0 — 生产阻塞：服务不可用或数据丢失
- [ ] P1 — 高优先级：影响安全或核心功能
- [ ] P2 — 中优先级：体验问题或运维不便
- [ ] P3 — 低优先级：小问题或改进建议

## 建议处理版本

- [ ] v1.0.1（紧急修复）
- [ ] v1.1.0（常规修复）
- [ ] v2.0.0（大版本）

## 补充信息

## 安全提醒

- 不要在此报告中粘贴 `.env` 文件内容
- 不要粘贴真实 API Key、Token、密码
- 不要粘贴包含 `Authorization` header 的完整请求
- 不要粘贴数据库连接串真实值
- 日志中的敏感信息必须用 `<REDACTED>` 替换
