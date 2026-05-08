# Outlook 邮箱取件 Web 工具

基于 Microsoft `refresh_token` 的 Outlook / Hotmail 邮箱批量取件工具。

- **后端**：FastAPI（无状态纯转发，不落盘任何凭据）
- **前端**：单页 HTML + Tailwind，凭据全部存浏览器 `localStorage`
- **取件通道**：
  - 优先 Microsoft Graph API（`/me/messages`）
  - 自动回退 IMAP XOAUTH2（`outlook.office365.com:993`）
- **部署**：Docker Compose + Caddy 自动 HTTPS

## 凭据格式

每行一条：

```
email----password----client_id----refresh_token
```

支持 `user+suffix@domain` 裂变别名（仍用主邮箱登录）。

## 功能

- 批量导入 / 文件导入 / 导出
- 单个邮箱：拉取邮件列表、查看 HTML/纯文本/原始 JSON、一键提取验证码
- 批量取码：所有邮箱并发取最新验证码（含发件人、主题过滤）
- 文件夹切换：全部 / 收件箱 / 垃圾箱 / 收件箱+垃圾箱
- token 测试：诊断 `client_id` + `refresh_token` 是否有效

## 快速部署（Debian 12）

```bash
# 1. 安装 Docker（如未安装）
curl -fsSL https://get.docker.com | sh

# 2. 拉代码到服务器
git clone <你的仓库> /opt/webmail && cd /opt/webmail
# 或者直接 scp 整个 webmail/ 目录上去

# 3. 配置环境
cp .env.example .env
nano .env
#   ACCESS_PASSWORD=随便起一个强密码
#   DOMAIN=mail.yourdomain.com    # 已解析到本服务器
#   EMAIL=you@example.com

# 4. 启动
docker compose up -d --build

# 5. 查看日志
docker compose logs -f
```

域名解析到服务器后 Caddy 会自动申请 Let's Encrypt 证书，访问 `https://mail.yourdomain.com` 即可。

### 仅内网 / IP 部署（无 HTTPS）

`.env` 留 `DOMAIN=:80` 即可，访问 `http://服务器IP/`。**这种情况下务必设置 `ACCESS_PASSWORD`**。

## 接口（外部脚本也可用）

所有接口需带 `X-Access-Password` 头（如启用了密码）。

### `POST /api/parse_bundle`
```json
{ "text": "a@b.com----p----cid----rt\n..." }
```
返回结构化邮箱列表。

### `POST /api/refresh`
```json
{ "email": "a@b.com", "client_id": "...", "refresh_token": "..." }
```
返回 `{ token_type, scope, expires_in }`。

### `POST /api/messages`
```json
{
  "email": "a@b.com",
  "client_id": "...",
  "refresh_token": "...",
  "master_email": "a@b.com",
  "alias": "",
  "folder": "all",
  "top": 20,
  "sender_contains": "",
  "subject_contains": ""
}
```

### `POST /api/code`
同上 + `only_latest: false`，返回 `{ code, channel, matched_subject }`。

### `POST /api/batch_code`
```json
{
  "mailboxes": [ { "email": "...", "client_id": "...", "refresh_token": "...", "alias": "" } ],
  "folder": "all",
  "top": 10,
  "sender_contains": "",
  "subject_contains": ""
}
```

## 开发

```bash
# Windows / 任意系统
python -m venv .venv
.venv\Scripts\activate     # Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8765
# 浏览器打开 http://127.0.0.1:8765
```

## 安全注意

- ✅ 凭据**只**存浏览器 localStorage，服务端不落盘
- ✅ 公网部署务必启用 `ACCESS_PASSWORD` + HTTPS（Caddy 自动）
- ✅ 邮件正文用 `<iframe sandbox>` 隔离渲染，防止恶意脚本
- ⚠️ localStorage 数据未加密，使用后请在公共电脑上"清空所有本地凭据"
- ⚠️ 服务端日志默认不记录凭据；如需更严格审计可自行加 IP 白名单 / mTLS

## 文件结构

```
webmail/
├── app/
│   ├── main.py            # FastAPI 入口
│   ├── ms_mail.py         # Graph + IMAP 双通道核心
│   ├── code_extract.py    # 验证码正则
│   └── static/            # 前端 (index.html / app.js / style.css)
├── Dockerfile
├── docker-compose.yml
├── Caddyfile
├── requirements.txt
├── .env.example
└── README.md
```
