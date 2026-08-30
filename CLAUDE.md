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
  **本机限制**：没装 Docker/Postgres，本地跑测试时用 `DATABASE_URL=sqlite:///...` 覆盖；CI 用的是 Postgres 16 service container，涉及 DB 行为的改动以 CI 结果为准。
- **2026-08-29**：D4 完成。三步抽取管线（`apps/wiki/services/extract_pipeline.py`）+ 归一化（`normalize.py`）落地，三步全跑通并落库。全量 227 个测试通过（`tests/wiki/` 122 个，其中管线 39 个），ruff 与 `check-clean.sh` 全绿。
  **端到端实跑已验证**：118 篇真实文章入库，3 篇跑完整管线 → 14 实体 / 3 概念 / **12 关系** / 29 条 Evidence，每条都能回链到原文。
  **GLM key 余额为 0**（`code 1113`，付费模型全部 429），实跑是用免费的 `glm-4-flash` 完成的；充值后把 `GLM_MODEL` 改回 `glm-4.7` 即可，代码无需改动。
- **2026-08-29**：D5 完成。每日简报（`apps/brief/services/generate.py`，citations 一律由后端按 `used_indexes` 反查构造，不信 LLM 的引用元数据）、编排入口（`apps/ops/services/pipeline.py::run_daily`，ingest→extract→brief 三段写进同一个 run）、成本护栏（`apps/common/budget.py` + `throttling.py`）、cron 端点（`POST /api/v1/ops/cron/daily`）、手动抽取端点（`POST /api/v1/wiki/extract/`）全部落地。
  **重构**：LLM 调用循环从 `extract_pipeline._invoke_json` 提到 `apps/common/llm/invoke.py::invoke_json`，抽取与简报共用，日预算熔断挂在这一个点上（见 ADR-013）。`SchemaError` 随之移到 `apps/common/exceptions.py`，validators 重新导出，调用方 import 不变。
  全量 296 个测试通过（新增 69 个），ruff 与 `check-clean.sh` 全绿。cron 端点与限流的完成判据用 sqlite + runserver 实跑通过：无 token/错 token 均 403，对 token 返回 32 位 hex run_id（202），`/api/v1/wiki/extract/` 前 3 次 202、第 4 次 429 且返回中文文案。
  下一步执行 `docs/ROADMAP.md` 的 D6（API 层 + OpenAPI）。
- **2026-08-29**：D6 完成。契约表里 20 条路径全部实现，OpenAPI 21 个 operation 每个都有 summary + description，`spectacular` 零 warning。
  **词条详情**（`/api/v1/wiki/entities/{id}/`）严格按 ARCHITECTURE 4.1 输出，出边入边合并进一个 `linkages` 数组用 `direction` 区分，每条关系挂着 `evidences[]{snippet, prompt_key, prompt_version, run_id, article{...}}`；**固定 5 次查询**（实体 + 出边 + 出边证据 + 入边 + 入边证据），有 `django_assert_num_queries(5)` 卡着，加到 23 条关系仍是 5 次。
  **图谱**按 4.2 输出，`symbolSize = min(60, 12 + value*2)` 后端算好，超 limit 按 Top-N 截断并置 `truncated`，categories 用模型 choices 顺序保证 ECharts 配色稳定。
  全量 362 个测试通过（新增 66 个），ruff 与 `check-clean.sh` 全绿。所有端点用 sqlite + runserver 实跑验证过，证据结构无 null 字段。
  下一步执行 `docs/ROADMAP.md` 的 D7（机动：补测试 + seed_demo）。
- **2026-08-30**：切到 `glm-5.3-flash`（推理模型，`thinking` 关不掉），为此改了三处 LLM 层：
  1. **流式**：`GLMClient` 默认 `stream=True` + `stream_options.include_usage`。非流式下长请求会在 ~145s 被上游掐断（`APIConnectionError`，不是超时），关系抽取因此从没成功过；流式后 221.8s 的调用一次就过。
  2. **重试分类**：`invoke_json` 不再外层重试 `LLMError`——客户端已经用掉自己的 3 次，外层再来 3 次只会把确定性拒绝重复三遍。失败从 10 分钟缩到 30 秒-2 分钟。
  3. **内容审查降级**：`ContentFilteredError`（HTTP 400 / code 1301）单独成类，简报被拒时记 `skipped` 而非 failed。
  另：超时 120s→300s 且改成 `LLM_TIMEOUT_SECONDS` 可配（已补进 ARCHITECTURE §7）；价目表加 `glm-5.3-flash`。
  **端到端实跑通过**：3 篇 arXiv → 13 实体 / 8 概念 / **16 关系** / 37 条 Evidence，37,003 token，0.0868 CNY；简报 3 条引用全部回链真实 URL。全量 377 个测试通过。
  **实测记录**：语料大小不影响延迟（1 篇 102s / 3 篇 96s），思考链长度主导耗时，所以调小 `EXTRACT_BATCH_SIZE` 不提速，保持 5。本机代理（`127.0.0.1:7897`）对国内 API 是负作用，跑真实调用时要 `unset HTTP_PROXY HTTPS_PROXY`。
- **2026-08-30**：D7 完成。全量 **486 个测试**通过（新增 109 个），`apps/` 覆盖率 99%，**所有 service 模块 100%**；ruff 与 `check-clean.sh` 全绿。
  **补测试**：按 `--cov` 报告逐个补失败路径——后台线程（`background.py` 43%→100%）、采集去重竞态与 `source_ids` 收窄、编排的非 `NO_ARTICLES` 异常分支、简报校验的空标题/数字字符串序号、persist 里「过了校验但落库后找不到」的悬空引用、`_article_id` 的 bool/float 强制转换、坏模板渲染、trafilatura 解析崩溃、retry-after 为负数。
  **顺带修了两个真 bug**：① `prompts/service.py::render` 里 `Formatter().parse()` 在 try 之外，模板括号不配对时漏出**裸 `ValueError`**（违反「不裸抛」规范，且会变成 500 而非带错误码的响应）；② `conftest.py` 的 `mock_llm` 只 patch 了 factory，而 `generate.py` / `extract_pipeline.py` 是 `from ... import get_llm_client` **在自己命名空间绑定**的，自己解析 client 的代码路径（`seed_demo`）会真发网络请求——写 `seed_demo` 测试时真打到了线上。现在 patch 三处绑定，另加一条 autouse 保险丝：谁构造真的 OpenAI client 就断言失败（`test_llm_factory.py` 用 `allow_openai_client` marker 豁免）。
  **`seed_demo`**：`--from-fixture`（默认，1.2s loaddata，零 LLM 调用）/ `--live`（真跑，重建 fixture）。`--live` 里两个顺序上的坑：**先剪枝再写简报**（简报按日期取素材，会取到没抽取的文章，剪枝在后就会留下指向已删行的 citation），以及 **dumpdata 必须自己按 UTF-8 落盘**（`--output` 用系统 locale，中文 Windows 上会写出 GBK，CI 和服务器都读不了）。
  **演示数据实跑**：332 篇入库 → 100 篇跑完整管线（10 个 run，每天 10 篇）→ **360 实体 / 219 概念 / 452 关系 / 1049 条 Evidence / 10 天简报**，1,196,020 token，**2.83 CNY**，约 2.5 小时。fixture 1.45 MB 已提交。
  **质量核查**：Evidence 逐字回链原文 **1038/1049 = 99.0%**；实体名在所引文章中逐字出现 **351/360 = 97.5%**，9 个例外全部核过，是 LaTeX 归一化（`G$^2$D`→`G2D`、`X$^2$Localizer`）、枚举展开（`Qwen3-8B/14B/32B`→`Qwen3-14B`）、只出现在标题里（`MTE`）、姓氏补全（`Wittgenstein`→`Ludwig Wittgenstein`），**无编造**。23 条 fixture 质量断言写进 `tests/test_demo_fixture.py`，直接校验 JSON 产物本身（计数、引用完整性、逐字率、密钥扫描），CI 每次都跑。
  **改了安全网**：`check-clean.sh` 的禁用词改为「拉丁词整词匹配 + 中文子串匹配」。某个 4 字母禁用词是 `capacity` 等普通英文的子串，在演示数据里误报 36 次、整词 0 次，fixture 提不进去。改完用临时探针验证过 5 个词的整词与点分形式仍会 FAIL。
  **已知短板（未改，记进 BACKLOG）**：图谱默认 `limit=50` 只出 5 条边、41 个孤立点——不是抽取问题，是 ARCHITECTURE 4.2 规定按 `mention_count` 截断，而 360 个实体里 349 个 `mention_count=1`，度数最高的节点反被切掉（实测 limit=50/100/200/400 → 边 5/20/94/307）。改排序键要动 4.2 契约和 D6 的测试，留给 D10。
  **演示数据的日期是回填的**：真实 feed 只有一天的量（317 篇里 309 篇同一天），`--spread-days 10` 把 100 篇重新摊到 10 天，所以**入库的 publish_time 与源站页面不一致**；URL/标题/正文/证据片段全是原样，溯源不受影响。这条在 D13 写 README 时要交代。
  下一步执行 `docs/ROADMAP.md` 的 D8（前端脚手架 + 布局 + API 层）。
