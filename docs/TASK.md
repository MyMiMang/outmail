# 任务进度 (TASK)

> 文档版本：v1.0
> 最后更新：2026-05-08 22:58 UTC+8
> 状态图例：✅ 已完成 · 🟡 进行中 · ⬜ 待办 · ❌ 已取消

## 当前里程碑：**v1.0 上线**（已完成 ✅）

---

## 已完成

### M1. 项目骨架
- ✅ 创建 `webmail/` 目录结构
- ✅ `requirements.txt`（FastAPI 0.115 / httpx 0.27 / Uvicorn 0.32）
- ✅ `.gitignore` / `.dockerignore` / `.env.example`
- ✅ Git 仓库初始化 + 推送到 https://github.com/MyMiMang/outmail

### M2. 后端核心
- ✅ `app/ms_mail.py`：refresh_token 刷新、Graph 拉信、IMAP XOAUTH2 拉信、统一邮件结构
- ✅ `app/code_extract.py`：14 种验证码正则（中英文）
- ✅ `app/main.py`：5 个 API 接口 + 健康检查 + CORS + 可选共享密码鉴权
- ✅ Graph 失败自动回退 IMAP 的 fallback 逻辑
- ✅ asyncio Semaphore=8 并发限流

### M3. 前端
- ✅ `app/static/index.html`：单页布局（顶栏 / 邮箱列表 / 详情面板 / 三个 modal）
- ✅ `app/static/app.js`：localStorage CRUD、API 调用、批量取码、HTML 沙箱渲染、设置持久化
- ✅ `app/static/style.css`：Tailwind CDN + 微调
- ✅ 凭据导入（粘贴 / 文件上传 / 导出）
- ✅ 邮件三视图（HTML/纯文本/原始 JSON）
- ✅ 一键复制验证码

### M4. Docker 部署
- ✅ `Dockerfile`（python 3.11-slim + healthcheck）
- ✅ `docker-compose.yml`（默认：宿主机 nginx 反代模式）
- ✅ `docker-compose.caddy.yml`（备选：自带 Caddy 自动 HTTPS）
- ✅ `Caddyfile`

### M5. 上线
- ✅ 服务器代码部署到 `/opt/webmail/`
- ✅ docker compose 启动验证 `curl /api/health` 通过
- ✅ 写宿主机 nginx 反代 (`/etc/nginx/conf.d/webmail.conf`)
- ✅ 域名解析（用 `mail.dengdengyun.shop`，因 `mail.dengdengshop.com` NS 迁移中）
- ✅ HTTPS（Cloudflare Universal SSL Flexible）
- ✅ 关闭 `ACCESS_PASSWORD`（用户当前选择无密码访问）

### M6. 文档
- ✅ `README.md`：部署模式 A/B 对比 + 一键命令
- ✅ `docs/PRD.md`
- ✅ `docs/ARCH.md`
- ✅ `docs/PROJECT_STATE.md`
- ✅ `docs/TASK.md`（本文档）

---

## 待办（按优先级）

### P0 - 紧急

- ⬜ **真实凭据冒烟测试**：用 1-2 个真实 Outlook 邮箱跑一遍完整流程
  - [ ] 导入 → 拉信 → 取码
  - [ ] 别名过滤 → 取码
  - [ ] 批量取码 5+ 个邮箱
  - [ ] 文件夹切换（垃圾箱）

### P1 - 安全加固

- ⬜ **CF SSL 升级到 Full (strict)**
  - [ ] 临时切灰云 → 跑 `certbot --nginx -d mail.dengdengyun.shop`
  - [ ] 切回橙云 → CF 后台改 Full (strict)
  - [ ] 验证 `curl https://mail.dengdengyun.shop/api/health`
- ⬜ **加 CF Access 零信任**（替代应用层密码，体验更好）
  - [ ] CF Zero Trust → Access → Add Application
  - [ ] 邮件 OTP 登录策略
- ⬜ **服务端日志脱敏**：确认日志中不出现 refresh_token 明文

### P2 - 体验优化

- ✅ **F13 一键复制邮箱**（2026-05-08）
  - 邮箱列表每项加 📋 图标，点击复制
  - 已填别名时复制为 `user+alias@domain`
  - 复用 `copyToClipboard()` 工具函数（验证码复制也接入），含老浏览器降级
- ✅ **F14 静态资源自动刷新**（2026-05-08）
  - HTML 注入 `?v=<hash>` 版本号到 app.js / style.css
  - HTML 响应头 `Cache-Control: no-cache, no-store, must-revalidate`
  - 部署新代码后用户下次打开自动拉新版，无需手动 Ctrl+F5
- ⬜ 批量取码进度条（前端轮询 SSE 或 WebSocket）
- ⬜ 邮箱列表支持拖拽排序、加标签
- ⬜ 失败重试按钮（单条 / 批量）
- ⬜ 移动端响应式优化（当前 lg 断点以下侧栏堆叠 OK，但有微调空间）
- ⬜ 国际化（英文界面）

### P3 - 功能扩展

- ⬜ **定时轮询 + WebHook**：选中邮箱设置每 N 秒自动取码，命中后调 webhook
- ⬜ **localStorage AES 加密**：浏览器主密码派生 key，避免 localStorage 明文
- ⬜ **凭据云端可选同步**（可选）：用户输入 GitHub Gist token 实现跨设备同步
- ⬜ **支持 Gmail / Yahoo OAuth**

### P4 - 工程化

- ⬜ pytest 单元测试（重点：`code_extract.py` / `ms_mail.parse_bundle`）
- ⬜ Playwright E2E（导入 → 取码主路径）
- ⬜ GitHub Actions CI（lint + test + 自动 build docker image）
- ⬜ docker hub / ghcr 自动推镜像，部署改为 `image: ghcr.io/...:tag`，免现场构建
- ⬜ Sentry / 阿里云 SLS 错误上报

### P5 - 运维 & 备份

- ⬜ 配置文件每周自动备份到 GitHub private repo
- ⬜ 加 Watchtower 容器自动拉 image 更新
- ⬜ Uptime Kuma 监控 `/api/health` 心跳

---

## 已取消 / 暂搁

- ❌ Cloudflare Origin 证书方案（用户选择继续 CF 代理 + Flexible，简化部署）
- ❌ Let's Encrypt 直签（DNS 迁移期间不可用，转用 CF Universal SSL）
- ❌ 多用户隔离（PRD 范围外，暂不做）
- ❌ 服务端 SQLite 持久化（与"凭据不上服务端"原则冲突）

---

## 进度可视化

```
v1.0 ████████████████████ 100%   ← 当前已上线
v1.1 ░░░░░░░░░░░░░░░░░░░░   0%   定时轮询 + WebHook + 端到端 HTTPS
v1.2 ░░░░░░░░░░░░░░░░░░░░   0%   localStorage AES + CF Access
v2.0 ░░░░░░░░░░░░░░░░░░░░   0%   多邮箱服务商扩展
```

## 下一步建议（执行顺序）

1. **跑通一次真实取码**（P0）— 最优先，验证业务路径
2. **CF SSL 升 Full (strict)**（P1）— 1 小时内可搞定
3. **加 CF Access**（P1）— 替换无密码裸奔状态
4. **CI + 镜像化**（P4）— 减少现场 docker build 的麻烦
