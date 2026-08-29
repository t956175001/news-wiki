# CLAUDE.md — news-wiki 项目宪法

> 这份文件是本仓库的最高约束。每个 session 开始时先读它，再读 `docs/ROADMAP.md` 里当天的任务。

## 项目一句话

**news-wiki**：每天自动采集 AI 资讯，用 LLM 三阶段结构化抽取（实体 → 概念 → 关系）生成可溯源的资讯维基。每条论断都挂着原文证据片段 + 来源链接 + 置信度。

这是一个**秋招作品集项目**。评判标准不是功能多，而是：工程判断是否清晰、AI 输出是否被有效约束、代码是否经得起面试官逐行问。

---

## 禁止清单（HARD NO）

违反任何一条都要立即停下来问，不要自作主张。

1. **不得出现任何前雇主标识或内网地址。** 具体的禁用词列表见仓库根目录的 `.forbidden-terms`（本地文件，不提交）。commit message、代码注释、文档、变量名一律适用。本项目是全新仓库，与任何公司代码无继承关系。
   **每次 commit 前跑 `bash scripts/check-clean.sh`，必须全部 PASS。**
2. **不得提交任何真实密钥。** `.env` 永远在 `.gitignore` 里。`.env.example` 中所有敏感值一律写 `replace-me`，**绝不贴真实值或"看起来像真的"的随机串**。
3. **不得引入以下依赖**：Celery、Redis、RabbitMQ、任何向量数据库（pgvector/Chroma/Milvus/Qdrant）、任何新的前端 UI 框架或组件库（已定 Ant Design Vue）、任何新的状态管理库（已定 Pinia）。理由见 `docs/DECISIONS.md`。确有必要时先提出并等确认。
4. **不得在未告知的情况下修改 `docs/` 下的规格文档**（`PRD.md` / `ARCHITECTURE.md` / `PROMPTS.md` / `DECISIONS.md`）。这些是契约。若实现中发现规格有误，先说明问题再改，改完要在 `DECISIONS.md` 追加一条记录。
5. **不得扩大范围。** `docs/PRD.md` 有明确的「不做清单」。看到"顺手加个 xx 会更好"的念头时，写进 `docs/BACKLOG.md`，不要实现。项目只有 14 天。
6. **不得跳过测试。** 见下方测试要求。

---

## 技术栈（已锁定）

| 层 | 选型 | 版本 |
|---|---|---|
| 后端 | Django + Django REST Framework | Django 5.0.x |
| API 文档 | drf-spectacular | 最新稳定版 |
| 数据库 | PostgreSQL（生产）/ PostgreSQL 容器（本地） | 16 |
| LLM | 智谱 GLM，走 OpenAI 兼容 SDK | `openai>=1.0` |
| 采集 | `feedparser` + `httpx` + `trafilatura` | — |
| 重试 | `tenacity` | — |
| 前端 | Vue 3 (`<script setup>`) + TypeScript + Vite | Vue 3.4+ |
| 组件库 | Ant Design Vue | 4.x |
| 状态 | Pinia | 2.x |
| 图表 | ECharts（`graph` 力导向系列） | 5.x |
| 测试 | pytest + pytest-django；vitest | — |
| 部署 | Docker Compose：Caddy + Gunicorn + Postgres | — |

---

## 目录约定

```
news-wiki/
├── backend/
│   ├── apps/
│   │   ├── common/      # 跨模块共享：LLM 客户端、prompts、异常、分页、限流
│   │   ├── ingest/      # RSS 采集与正文抽取
│   │   ├── wiki/        # 实体/概念/关系/证据 + 三步抽取管线（核心）
│   │   ├── brief/       # 每日简报
│   │   └── ops/         # ExtractionRun 观测 + cron 端点
│   ├── config/settings/ # base.py / dev.py / prod.py
│   └── tests/           # 按 app 分子目录，与 apps/ 结构镜像
├── frontend/src/
│   ├── api/             # axios 客户端 + 各模块请求函数
│   ├── components/      # 跨页面复用组件
│   ├── composables/     # useApi / usePolling 等
│   ├── stores/          # Pinia
│   ├── types/           # TS 类型，与后端 serializer 一一对应
│   └── views/           # 页面，按路由分目录
├── deploy/              # Caddyfile + docker-compose.prod.yml
└── docs/                # 规格文档（契约，勿擅改）
```

**分层规则（后端）**：`views.py` 只做参数校验和序列化，业务逻辑一律放 `services/`。**任何 LLM 调用只能出现在 `services/` 里**，不得出现在 view、serializer、model 中。

**分层规则（前端）**：组件不直接调 `axios`，一律经 `src/api/`。跨页面共享状态才进 Pinia，页面内状态用 `ref`/`reactive`。

---

## 编码规范

**Python**
- 全部函数带类型注解，`from __future__ import annotations` 不需要（Python 3.11+）
- 私有函数 `_` 前缀；模块级常量全大写
- 异常：业务错误抛 `apps/common/exceptions.py` 里的自定义异常，由 `drf_exceptions.py` 统一转成带错误码的 JSON 响应。**不要裸抛 `Exception`，不要吞异常**
- 日志：`logger = logging.getLogger(__name__)`。所有 LLM 相关日志必须带 `run_id`
- 格式化：`ruff format`；检查：`ruff check`

**TypeScript / Vue**
- 一律 `<script setup lang="ts">`
- Props / Emits 用类型声明，不用运行时声明
- 后端返回的类型定义放 `src/types/`，字段名与 serializer 严格一致（snake_case，不在前端转 camelCase）
- 格式化：`prettier`；检查：`eslint`

**注释**：只写"为什么"，不写"是什么"。代码能自解释的不加注释。中文注释可以，但公开 API 的 docstring 用英文。

---

## 测试要求

- **新增 service 层函数必须有单测。** view 层有接口测试即可。
- LLM 调用在测试里**一律 mock**，禁止在测试中发真实网络请求。mock 的 fixture 放 `tests/conftest.py`。
- 抽取管线的测试必须覆盖：正常路径、LLM 返回非法 JSON、LLM 返回缺字段、重试后仍失败。
- 目标 60-80 个测试。**不追求覆盖率数字，追求覆盖关键分支。**
- 每次改完代码，跑对应模块的测试；提 commit 前跑全量。

```bash
# 后端
cd backend && pytest -q                    # 全量
cd backend && pytest tests/wiki/ -q        # 单模块
cd backend && ruff check . && ruff format --check .

# 前端
cd frontend && npm run test
cd frontend && npm run lint && npx vue-tsc --noEmit
```

---

## Git 规范

- **Conventional Commits**，message 全英文：`feat:` `fix:` `refactor:` `test:` `docs:` `chore:`
- 一个 commit 一件事，不要把 10 个文件的无关改动塞一起
- commit message 里**不得出现任何公司名**
- 不要自动 commit。改完告诉用户改了什么，由用户决定何时提交

---

## 每天开工流程

1. 读 `CLAUDE.md`（本文件）
2. 读 `docs/ROADMAP.md` 中当天条目，按「前置阅读」列表读那几个文件
3. 执行任务
4. 跑当天的「完成判据」命令，**贴出真实输出**
5. 判据不通过就不算完成，不要嘴上说"应该没问题"

**关于验证**：不要在没跑过命令的情况下声称功能可用。测试失败就如实说失败并贴输出。

---

## 当前状态

- **2026-08-28**：仓库初始化，文档就绪，尚无业务代码。下一步执行 `docs/ROADMAP.md` 的 D1。
- **2026-08-29**：D1–D3 完成。工程基座、数据模型、RSS 采集管线、LLM 调用层（`apps/common/llm/`：GLMClient + 令牌桶 + 计价 + factory）、Prompt 服务、三个抽取校验器（`apps/wiki/services/validators.py`）均已落地，`tests/conftest.py` 提供 `mock_llm` fixture。全量 170 个测试通过，`ruff check` / `ruff format --check` / `scripts/check-clean.sh` 全绿。
  下一步执行 `docs/ROADMAP.md` 的 D4（三步抽取管线）。
  **本机限制**：没装 Docker/Postgres，本地跑测试时用 `DATABASE_URL=sqlite:///...` 覆盖；CI 用的是 Postgres 16 service container，涉及 DB 行为的改动以 CI 结果为准。
