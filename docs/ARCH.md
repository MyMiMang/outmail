# 架构决策文档 (ADR / ARCH)

> 文档版本：v1.0
> 最后更新：2026-05-08

## 1. 总体架构

```
┌──────────────────────────────────────────────────────────────────┐
│                          浏览器 (Browser)                        │
│  - localStorage：邮箱凭据列表                                    │
│  - 单页应用：index.html + app.js + style.css (Tailwind CDN)      │
└─────────────────┬───────────────────────▲────────────────────────┘
                  │ HTTPS                  │ HTML/JSON
                  ▼                        │
┌──────────────────────────────────────────┴────────────────────────┐
│              Cloudflare (Universal SSL, Flexible 模式)            │
│              （或 Let's Encrypt 直连，二选一）                    │
└─────────────────┬─────────────────────────────────────────────────┘
                  │ HTTP/HTTPS
                  ▼
┌──────────────────────────────────────────────────────────────────┐
│                  宿主机 nginx (Debian 12)                        │
│   server_name mail.xxx → proxy_pass 127.0.0.1:8765               │
└─────────────────┬────────────────────────────────────────────────┘
                  │ HTTP loopback
                  ▼
┌──────────────────────────────────────────────────────────────────┐
│        Docker 容器: webmail (FastAPI + Uvicorn, 无状态)          │
│   /api/parse_bundle  /api/refresh                                │
│   /api/messages      /api/code     /api/batch_code               │
└─────┬───────────────────────────────────────────────┬────────────┘
      │ HTTPS                                         │ IMAP+TLS
      ▼                                               ▼
┌─────────────────────────┐               ┌────────────────────────┐
│ Microsoft Graph API     │               │ outlook.office365.com  │
│ (graph.microsoft.com)   │               │ :993 (XOAUTH2)         │
└─────────────────────────┘               └────────────────────────┘
```

## 2. 关键技术决策（ADR）

### ADR-1：服务端**不**持久化凭据
- **决定**：refresh_token / 密码不落任何数据库、文件、缓存
- **理由**：(1) 用户痛点是"不放心交出去"；(2) 服务端被攻破时无敏感数据外泄；(3) 简化部署，无需备份
- **代价**：换设备/清缓存后凭据丢失，需重导
- **替代**：localStorage AES 主密码加密（v1.2 计划）

### ADR-2：取件双通道（Graph 优先 + IMAP 回退）
- **决定**：先尝试 Microsoft Graph（`Mail.Read` scope），失败再用 IMAP XOAUTH2
- **理由**：
  - Graph 速度快、JSON 友好、支持 `$top/$filter/$orderby`
  - 部分老号 / 撤权号 Graph 不可用，但 IMAP 仍可用
  - 应用注册时 scope 不一致也能兼容
- **实现**：`@app/ms_mail.py:fetch_messages()` 自动选择
- **替代**：仅 IMAP（兼容更好但慢、解析麻烦）；仅 Graph（不兼容老号）

### ADR-3：FastAPI + Uvicorn，**不**用 Gunicorn
- **决定**：单进程 Uvicorn 即可
- **理由**：(1) 取件本身是 IO bound，asyncio 单进程足够；(2) 简化容器；(3) 反代由宿主 nginx 处理
- **代价**：单核瓶颈；CPU 密集时撑不住，但本场景无 CPU 密集任务

### ADR-4：前端**不**做构建（无 npm / webpack）
- **决定**：Tailwind 用 CDN，原生 JS 直接写，零编译产物
- **理由**：(1) 部署只需 docker build；(2) 调试方便；(3) 业务复杂度还撑不起 SPA 框架
- **代价**：app.js 单文件 ~400 行后会难维护
- **未来**：业务复杂到需 Vue/React 时再迁移（v2 之后）

### ADR-5：部署模式**复用宿主机 nginx**（默认）
- **决定**：webmail 容器只 `127.0.0.1:8765`，由宿主机已有 nginx 反代
- **理由**：(1) 与服务器其他容器项目共存（如 dengdeng-canvas, flova2api）；(2) 宿主 nginx 已有完整证书 / 限流 / 监控；(3) 不抢 80/443
- **备选**：仓库附 `@e:\AI\outmail\webmail\docker-compose.caddy.yml`，需要时一键切换为容器自带 Caddy 自动 HTTPS

### ADR-6：HTTPS 由 **Cloudflare** 处理（当前线上配置）
- **决定**：DNS + 代理 + Universal SSL 都走 CF
- **理由**：(1) 免证书运维（无续签）；(2) 自带 CDN/DDoS；(3) 当前 `dengdengshop.com` NS 在迁移中，`dengdengyun.shop` 走 CF 已稳定
- **当前 SSL 模式**：Flexible（CF↔origin 走 HTTP）
- **后续优化**：升级到 Full (strict) + Let's Encrypt 源站证书，端到端加密

### ADR-7：批量并发用 **asyncio.Semaphore=8**
- **决定**：批量取码时最多 8 个邮箱并发请求
- **理由**：避免触发 Graph 限流（1000 req/10min/app）和 IMAP 连接数限制
- **代价**：1000 个邮箱顺序约 2 分钟
- **可调**：`@e:\AI\outmail\webmail\app\main.py` 里 `Semaphore(8)`

### ADR-8：邮件正文 `<iframe sandbox>` 渲染
- **决定**：HTML 邮件用 sandbox iframe，**不允许 scripts/forms**
- **理由**：钓鱼邮件 / XSS 邮件不在我们控制内，必须沙箱化
- **代码**：`@e:\AI\outmail\webmail\app\static\index.html` 中 `sandbox="allow-same-origin"`

### ADR-9：Token 刷新策略 — **每次请求都重新刷**
- **决定**：每个 API 调用独立刷一次 access_token，不缓存
- **理由**：(1) 服务端无状态；(2) Graph access_token 有效期 1h，缓存收益小；(3) 无并发安全问题
- **代价**：多一次 token endpoint 往返（~200ms）
- **未来**：浏览器端短期缓存 access_token（5min）减少往返

## 3. 目录结构

```
webmail/
├── app/
│   ├── main.py            # FastAPI 路由 / 鉴权 / 过滤
│   ├── ms_mail.py         # Graph + IMAP 双通道核心
│   ├── code_extract.py    # 验证码正则集
│   └── static/            # 前端三件套
│       ├── index.html
│       ├── app.js
│       └── style.css
├── deploy/
│   └── nginx-webmail.conf # 宿主机 nginx 反代示例
├── docs/                  # 本目录（PRD / ARCH / PROJECT_STATE / TASK）
├── Dockerfile
├── docker-compose.yml         # 默认：仅 webmail 容器，绑 127.0.0.1:8765
├── docker-compose.caddy.yml   # 备选：webmail + Caddy 自带 HTTPS
├── Caddyfile
├── requirements.txt
├── .env.example
├── .gitignore
├── .dockerignore
└── README.md
```

## 4. 数据流（取验证码场景）

```
1. 浏览器: 用户点"取验证码" 按钮
2. app.js: POST /api/code  (含 client_id, refresh_token, email, alias, folder, top)
3. nginx: 反代到 127.0.0.1:8765
4. main.py: api_code() 校验 X-Access-Password
5. ms_mail.py: refresh_access_token()
   ├─ POST login.microsoftonline.com/.../oauth2/v2.0/token (Graph scope)
   └─ 失败 → POST 同上 (IMAP scope)
6. ms_mail.py: fetch_via_graph(...)  或  fetch_via_imap(...)
7. main.py: _match() 按 alias / sender / subject 过滤
8. code_extract.py: extract_code() 跑 14 种正则
9. main.py: 返回 {code, channel, matched_subject}
10. app.js: 渲染 + 复制按钮
```

## 5. 关键依赖版本

| 库 | 版本 | 作用 |
|---|---|---|
| fastapi | 0.115.4 | Web 框架 |
| uvicorn[standard] | 0.32.0 | ASGI 服务器 |
| httpx | 0.27.2 | 异步 HTTP 客户端（Graph） |
| pydantic | 2.9.2 | 请求体校验 |
| python-multipart | 0.0.12 | form-data 解析 |
| imaplib | 标准库 | IMAP 客户端 |

## 6. 风险与对策

| 风险 | 等级 | 对策 |
|---|---|---|
| Microsoft 限流 | 中 | 批量 Semaphore=8；前端可显式间隔 |
| refresh_token 大批失效 | 中 | F9 token 测试按钮辅助批量 ping |
| 浏览器 localStorage 被清 | 低 | 提示用户导出备份；v1.2 加云端可选同步 |
| HTML 邮件 XSS | 低 | iframe sandbox 已隔离 |
| 服务被滥用 | 中 | `ACCESS_PASSWORD` + CF Rate Limit + （可选）CF Access |
| 单点 VPS 故障 | 低 | 凭据在浏览器 localStorage，重新部署即恢复 |
