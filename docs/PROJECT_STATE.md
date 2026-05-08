# 项目当前状态 (PROJECT STATE)

> 文档版本：v1.0
> 最后更新：2026-05-08 22:58 UTC+8
> 维护方式：每次重大变更后更新此文档

## 1. 一句话状态

**v1.0 已部署上线**，运行在 `https://mail.dengdengyun.shop` 上，CF 代理 + Universal SSL，可正常使用。

## 2. 线上环境

| 项 | 当前值 |
|---|---|
| 域名 | `mail.dengdengyun.shop` |
| 入口 | `https://mail.dengdengyun.shop`（CF 代理） |
| 服务器 IP | `186.244.244.89`（海外，无需备案） |
| OS | Debian 12 |
| 容器名 | `webmail` |
| 容器端口 | `127.0.0.1:8765`（loopback only） |
| 反代 | 宿主机 nginx 1.22.1 |
| HTTPS | Cloudflare Universal SSL，模式 **Flexible** |
| 访问控制 | **当前未启用**密码（`ACCESS_PASSWORD` 留空） |
| 部署目录 | `/opt/webmail/` |
| 服务管理 | `cd /opt/webmail && docker compose up -d` |

## 3. 代码仓库

- GitHub: https://github.com/MyMiMang/outmail
- 默认分支：`main`
- 最近 commit：`feat: split deploy into nginx-reverse-proxy (default) and caddy modes`

## 4. 与服务器其他项目的隔离

| 容器 | 端口 | 用途 | 与 webmail 冲突？ |
|---|---|---|---|
| `flova2api` | `127.0.0.1:3001` | 已有 API | ❌ |
| `dengdeng-canvas-web` | `127.0.0.1:18088` | 前端 | ❌ |
| `dengdeng-canvas-backend` | `8787` (内网) | 后端 | ❌ |
| `webmail` | `127.0.0.1:8765` | 本项目 | ✅ 隔离 |
| 宿主机 nginx | `0.0.0.0:80,443` | 反代总入口 | ✅ 共用 |

## 5. nginx 反代配置

文件：`/etc/nginx/conf.d/webmail.conf`
- HTTP only（端口 80），server_name = `mail.dengdengyun.shop`
- 转发到 `http://127.0.0.1:8765`
- 未启用源站 HTTPS（依赖 CF 终端 SSL）

> 待优化：申请 Let's Encrypt 源站证书，CF SSL 升级为 Full (strict)

## 6. 当前已知问题

| ID | 描述 | 影响 | 优先级 |
|---|---|---|---|
| ISSUE-1 | `dengdengshop.com` NS 迁移中，相关子域无法解析 | 备用域名暂不可用 | 低（已有可用域名） |
| ISSUE-2 | CF 模式为 Flexible，CF↔origin 走 HTTP | 中间链路无加密 | 中 |
| ISSUE-3 | 服务无认证，公开可访问 | 任何人能调 API | 中 |
| ISSUE-4 | 大批量取码无前端进度条 | 体验一般 | 低 |

## 7. 未发布功能（已编写未上线）

无。所有已实现功能均在 v1.0 部署中。

## 8. 测试覆盖情况

- ❌ 无单元测试
- ❌ 无 E2E 测试
- ✅ 已经过冒烟手测：
  - 接口 `/api/health` 返回正常
  - 前端页面可正常打开
  - （凭据导入流程 / 取码流程待用户实测后补记录）

## 9. 监控 / 日志

- **容器日志**：`docker compose logs -f` 查看 uvicorn stdout
- **nginx 访问日志**：`/var/log/nginx/access.log`
- **错误日志**：`/var/log/nginx/error.log`
- **告警**：无（v1 不做监控）

## 10. 备份策略

- **代码**：GitHub
- **配置**：`/opt/webmail/.env`、`/etc/nginx/conf.d/webmail.conf` —— 当前**未做自动备份**
- **数据**：无（服务端零持久化）
- **用户凭据**：在用户浏览器 localStorage 中，提示用户使用「导出」按钮自行备份

## 11. 常用运维命令速查

```bash
# 查看后端日志
docker compose -f /opt/webmail/docker-compose.yml logs -f --tail=100

# 重启后端
cd /opt/webmail && docker compose restart

# 重新构建并启动
cd /opt/webmail && docker compose up -d --build

# 测试接口
curl -s https://mail.dengdengyun.shop/api/health

# 拉最新代码并重启
cd /opt/webmail && git pull && docker compose up -d --build

# 查看 nginx 配置
sudo nginx -T 2>/dev/null | grep -A20 mail.dengdengyun.shop

# 检查端口监听
sudo ss -tlnp | grep -E '(8765|443|80)'
```
