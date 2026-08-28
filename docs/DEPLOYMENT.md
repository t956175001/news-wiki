# DEPLOYMENT — 上线 Runbook

> 目标：`https://news-wiki.<你的域名>` 在国内可稳定访问，HTTPS 自动续期，每日定时更新。
> 主方案：**腾讯云香港轻量 + Docker Compose（Caddy + Gunicorn + Postgres）+ 前后端同源**。

---

## 0. 前置清单

| 项 | 说明 |
|---|---|
| 服务器 | 腾讯云**香港**轻量应用服务器，2C2G / 20M 起，Ubuntu 22.04 或 24.04。**必须选香港或其他境外地域**——境内地域需 ICP 备案 |
| 域名 | 任意注册商买 `.app` / `.dev` / `.com`（~$12/年）。境外注册商的域名无法备案，但**境外服务器不需要备案** |
| DNS | 域名 NS 指向 Cloudflare（免费），用 Cloudflare 管理解析 |
| GLM Key | https://open.bigmodel.cn 申请 |
| GitHub 仓库 | 已推送代码 |

**成本**：服务器 ~¥288/年 + 域名 ~¥85/年 ≈ **¥373/年**。

---

## 1. 服务器初始化

> 以下命令在 VPS 上执行。**逐步执行并确认输出**，不要一次性粘贴一大段。

```bash
# --- 以 root 登录后 ---
apt update && apt upgrade -y

# 创建非 root 用户
adduser deploy
usermod -aG sudo deploy

# 配置 SSH 密钥（在本地执行 ssh-keygen 后，把公钥贴进去）
mkdir -p /home/deploy/.ssh
vim /home/deploy/.ssh/authorized_keys      # 粘贴本地 ~/.ssh/id_ed25519.pub
chmod 700 /home/deploy/.ssh
chmod 600 /home/deploy/.ssh/authorized_keys
chown -R deploy:deploy /home/deploy/.ssh

# 关闭密码登录和 root 登录
vim /etc/ssh/sshd_config
#   PasswordAuthentication no
#   PermitRootLogin no
systemctl restart sshd
```

**⚠️ 重新开一个终端验证 `ssh deploy@<IP>` 能登录后，再关闭当前 root 会话。** 否则可能把自己锁在外面。

```bash
# --- 以 deploy 登录 ---
# Docker
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker deploy
newgrp docker
docker --version && docker compose version

# 防火墙
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp      # ★ ACME HTTP-01 挑战必需，不能只开 443
sudo ufw allow 443/tcp
sudo ufw --force enable
sudo ufw status
```

**同时在腾讯云控制台的「防火墙/安全组」放行 22 / 80 / 443。** 轻量服务器有两层防火墙，ufw 通了控制台没放行照样不通——这是最常见的踩坑点。

---

## 2. DNS 配置

在 Cloudflare 添加两条 A 记录：

| 类型 | 名称 | 内容 | 代理状态 |
|---|---|---|---|
| A | `news-wiki` | `<VPS 公网 IP>` | **DNS only（灰云）** |
| A | `@` 或其他 | `<VPS 公网 IP>` | DNS only（灰云） |

> ★ **必须是灰云**。开橙云代理会让国内流量绕行 Cloudflare 边缘节点，比直连香港更慢，白白浪费腾讯云香港的线路优势。详见 `DECISIONS.md` ADR-007。
> 灰云模式下 Cloudflare 不签发证书，HTTPS 由 Caddy 自动申请 Let's Encrypt。

验证解析生效：
```bash
dig +short news-wiki.<你的域名>     # 应返回 VPS 的 IP，不是 Cloudflare 的
```

---

## 3. 部署文件

### `deploy/Caddyfile`

```caddyfile
{$SITE_DOMAIN} {
    encode gzip zstd

    # API 反代到 gunicorn
    handle /api/* {
        reverse_proxy web:8000
    }
    handle /admin/* {
        reverse_proxy web:8000
    }
    handle /static/* {
        reverse_proxy web:8000
    }

    # 其余交给前端 SPA
    handle {
        root * /srv/frontend
        try_files {path} /index.html
        file_server
    }

    header {
        X-Content-Type-Options nosniff
        X-Frame-Options DENY
        Referrer-Policy strict-origin-when-cross-origin
        -Server
    }

    log {
        output file /var/log/caddy/access.log
    }
}
```

### `deploy/docker-compose.prod.yml`

```yaml
services:
  db:
    image: postgres:16-alpine
    restart: unless-stopped
    environment:
      POSTGRES_DB: ${POSTGRES_DB}
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER}"]
      interval: 10s
      retries: 5

  web:
    build:
      context: ..
      dockerfile: Dockerfile
    restart: unless-stopped
    env_file: ../.env
    depends_on:
      db:
        condition: service_healthy
    volumes:
      - static:/app/staticfiles
      - frontend_dist:/app/frontend_dist
    command: >
      sh -c "python manage.py migrate --noinput &&
             python manage.py collectstatic --noinput &&
             gunicorn config.wsgi:application
             --bind 0.0.0.0:8000 --workers 3 --threads 2 --timeout 120
             --access-logfile - --error-logfile -"

  caddy:
    image: caddy:2-alpine
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    environment:
      SITE_DOMAIN: ${SITE_DOMAIN}
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - frontend_dist:/srv/frontend:ro
      - caddy_data:/data
      - caddy_config:/config
      - caddy_logs:/var/log/caddy
    depends_on:
      - web

volumes:
  pgdata:
  static:
  frontend_dist:
  caddy_data:
  caddy_config:
  caddy_logs:
```

> `frontend_dist` 卷由 `web` 镜像在构建阶段填充（Dockerfile 多阶段构建里 `COPY --from=frontend-builder /app/dist /app/frontend_dist`），Caddy 只读挂载。

### `Dockerfile`（多阶段）

```dockerfile
# --- 前端构建 ---
FROM node:20-alpine AS frontend-builder
WORKDIR /app
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# --- 后端运行 ---
FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ .
COPY --from=frontend-builder /app/dist /app/frontend_dist

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD curl -fsS http://localhost:8000/api/v1/health/ || exit 1
```

---

## 4. 首次部署

```bash
ssh deploy@<VPS_IP>
git clone https://github.com/<你的账号>/news-wiki.git
cd news-wiki

# 写生产 .env（不要提交到仓库）
cp .env.example .env
vim .env
```

`.env` 必填项：
```bash
DJANGO_ENV=prod
SECRET_KEY=<python -c "import secrets;print(secrets.token_urlsafe(50))" 生成>
ALLOWED_HOSTS=news-wiki.<你的域名>
SITE_DOMAIN=news-wiki.<你的域名>

POSTGRES_DB=newswiki
POSTGRES_USER=newswiki
POSTGRES_PASSWORD=<强密码>
DATABASE_URL=postgres://newswiki:<强密码>@db:5432/newswiki

GLM_API_KEY=<你的 key>
CRON_TOKEN=<python -c "import secrets;print(secrets.token_urlsafe(32))" 生成>

DEMO_MODE=true
DEMO_WRITE_RATE=3/day
LLM_DAILY_BUDGET_CNY=5.0
CORS_ALLOWED_ORIGINS=
```

启动：
```bash
cd deploy
docker compose -f docker-compose.prod.yml --env-file ../.env up -d --build
docker compose -f docker-compose.prod.yml logs -f caddy    # 看证书是否签发成功
```

灌演示数据 + 创建管理员：
```bash
docker compose -f docker-compose.prod.yml exec web python manage.py seed_demo
docker compose -f docker-compose.prod.yml exec web python manage.py createsuperuser
```

---

## 5. 验收

```bash
DOMAIN=news-wiki.<你的域名>

curl -sI https://$DOMAIN | head -3                          # 200 + HTTPS
curl -s https://$DOMAIN/api/v1/health/ | jq .               # {"status":"ok","db":"ok"}
curl -s https://$DOMAIN/api/v1/wiki/entities/ | jq .count   # > 0
curl -s https://$DOMAIN/api/v1/brief/latest/ | jq .title
curl -s -o /dev/null -w "%{http_code}\n" https://$DOMAIN/api/v1/docs/    # 200

# 证书有效期
echo | openssl s_client -connect $DOMAIN:443 2>/dev/null | openssl x509 -noout -dates

# cron 端点
curl -s -o /dev/null -w "%{http_code}\n" -X POST https://$DOMAIN/api/v1/ops/cron/daily   # 403
curl -s -X POST -H "X-Cron-Token: $CRON_TOKEN" https://$DOMAIN/api/v1/ops/cron/daily | jq .run_id
```

浏览器：五个页面都能打开，词条页能展开证据，图谱能渲染。
**手机 4G 网络**打开首页，3 秒内出内容。

---

## 6. CI/CD

### `.github/workflows/ci.yml`

push / PR 触发：ruff check + ruff format --check + pytest（带 postgres service）+ 前端 lint/vue-tsc/test/build。

### `.github/workflows/deploy.yml`

```yaml
name: deploy
on:
  push:
    branches: [main]
  workflow_dispatch:

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: appleboy/ssh-action@v1
        with:
          host: ${{ secrets.VPS_HOST }}
          username: ${{ secrets.VPS_USER }}
          key: ${{ secrets.VPS_SSH_KEY }}
          script: |
            cd ~/news-wiki
            git pull --ff-only
            cd deploy
            docker compose -f docker-compose.prod.yml --env-file ../.env up -d --build
            docker compose -f docker-compose.prod.yml exec -T web python manage.py migrate --noinput
            docker image prune -f
```

> 建议给 `deploy.yml` 加 `needs: [ci]` 或用 `workflow_run`，确保 CI 绿了才部署。

### `.github/workflows/cron-daily.yml`

```yaml
name: cron-daily
on:
  schedule:
    - cron: "0 0 * * *"     # UTC 00:00 = 北京 08:00
  workflow_dispatch:

jobs:
  trigger:
    runs-on: ubuntu-latest
    steps:
      - name: Trigger daily pipeline
        run: |
          RESP=$(curl -sS -X POST \
            -H "X-Cron-Token: ${{ secrets.CRON_TOKEN }}" \
            https://${{ secrets.SITE_DOMAIN }}/api/v1/ops/cron/daily)
          echo "$RESP"
          echo "$RESP" | jq -e .run_id > /dev/null
```

**需要的 repo secrets**：`VPS_HOST` `VPS_USER` `VPS_SSH_KEY` `CRON_TOKEN` `SITE_DOMAIN`。

> GitHub 的定时任务在高峰期可能延迟几分钟到半小时，对本项目无影响。
> 仓库连续 60 天无提交时 GitHub 会自动停用 schedule，需手动重新启用——留意这一点。

---

## 7. 运维

```bash
cd ~/news-wiki/deploy
C="docker compose -f docker-compose.prod.yml"

$C ps                                    # 状态
$C logs -f web                           # 应用日志
$C logs -f caddy                         # 证书/访问日志
$C restart web                           # 重启后端
$C exec web python manage.py shell       # Django shell

# 数据库备份（建议加进 crontab 每日执行）
$C exec -T db pg_dump -U newswiki newswiki | gzip > ~/backup/db-$(date +%F).sql.gz

# 恢复
gunzip -c ~/backup/db-2026-09-11.sql.gz | $C exec -T db psql -U newswiki newswiki
```

**磁盘监控**：轻量服务器盘小，日志和镜像容易吃满。
```bash
df -h && docker system df
docker system prune -af --volumes    # ⚠️ 会删除未使用的卷，执行前确认 pgdata 正在使用中
```

---

## 8. 备选方案 A：前端放 Cloudflare Pages

若 D12 实测发现同源方案国内速度不理想，可把前端分离。

1. Cloudflare Dashboard → Workers & Pages → 连接 GitHub 仓库
2. 构建配置：
   - 构建命令 `cd frontend && npm ci && npm run build`
   - 输出目录 `frontend/dist`
   - 环境变量 `VITE_API_BASE=https://api.<你的域名>/api/v1`
3. 绑定自定义域名 `news-wiki.<你的域名>`（**不要用 `*.pages.dev`，国内有 DNS 污染**）
4. 后端另绑 `api.<你的域名>`，`.env` 里设
   `CORS_ALLOWED_ORIGINS=https://news-wiki.<你的域名>`
5. Caddyfile 里删掉静态文件 handle，只保留反代

**D12 必做**：用 [ITDOG](https://www.itdog.cn/http/) 对两套方案各测一次全国 HTTP 访问，记录平均耗时和成功率，**用数据决定**最终方案，结论写回 `DECISIONS.md` ADR-006。

---

## 9. 备选方案 B：纯静态降级（VPS 故障时的保底）

保证简历链接永远能打开。

思路：GitHub Actions 定时跑一个 Python 脚本（直接用 Django 的 management command，连本地 SQLite），把抽取结果导出成静态 JSON 提交回仓库的 `frontend/public/data/`，前端检测到 `VITE_STATIC_MODE=true` 时改读静态 JSON，部署到 Cloudflare Pages。

代价：失去实时抽取和所有写操作，`/ops` 面板变成历史快照。**仅作为应急，不作为主方案。**

---

## 10. 故障排查

| 症状 | 排查 |
|---|---|
| 证书签发失败 | 80 端口是否对公网开放（ufw **和**腾讯云控制台两处）；DNS 是否已生效且是灰云；`docker compose logs caddy` 看 ACME 错误 |
| 502 Bad Gateway | `docker compose ps` 看 web 是否健康；`logs web` 看 gunicorn 报错；确认 Caddyfile 里是 `web:8000` 不是 `localhost:8000` |
| 国内打不开但国外正常 | 确认 DNS 是灰云；`dig` 返回的是否为 VPS IP；用 ITDOG 测各省解析 |
| cron 没跑 | GitHub Actions 页面看 workflow 是否被自动停用（60 天无提交会停）；手动 `workflow_dispatch` 试一次 |
| 抽取一直 running | 后台线程随进程重启丢失。查 `ExtractionRun` 里 `started_at` 超过 30 分钟仍 running 的记录，手动置 failed |
| 磁盘满 | `docker system prune -af`；清 Caddy 日志；检查 pgdata 大小 |
| LLM 调用失败 | 确认 `GLM_API_KEY` 有效、账户有余额；香港 VPS 访问 `open.bigmodel.cn` 应该直连可达，无需代理 |
