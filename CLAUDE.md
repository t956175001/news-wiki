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
- **2026-08-30**：D8 完成。`frontend/` 用 `npm create vite@latest -- --template vue-ts` 起（Vite 8 / Vue 3.5 / TS 6），装齐 ant-design-vue、pinia、vue-router、axios、echarts、dayjs、marked，配好 eslint 9 flat config（`@vue/eslint-config-typescript` + `@vue/eslint-config-prettier`）、prettier、sass、vitest(jsdom)。
  **依赖版本**：`npm install` 默认拉到 Pinia 4 / ECharts 6，手动订正回 CLAUDE.md 锁定的 2.x / 5.x；vue-router 装的是 4.x（不在锁定表里，但 5.x 的 peerOptional 要求 pinia 3/4，与锁定的 Pinia 2.x 冲突，选了摩擦更小的组合）。**已知遗留**：ECharts <6.1.0 有一条 moderate XSS 通报（GHSA-fgmj-fm8m-jvvx），修复要求跳大版本，与锁定版本冲突，暂未处理，记入 BACKLOG，D10 画图谱前评估。
  **`src/api/client.ts`**：`docs/MIGRATION.md` 写的是「原样复制」旧项目版本，但旧版 baseURL 写死、错误处理是弹 `notification` 而不抛错、还带一套这个项目用不上的 CSRF cookie 逻辑（本项目无 session 登录）。改成按 ARCHITECTURE §6 的要求实现：`baseURL` 默认 `/api/v1`、可被 `VITE_API_BASE` 覆盖，响应拦截器统一抛出带 `code` 的 `ApiError`。用 TDD 做的：先写 `client.test.ts`（直接测 `normalizeApiError` 这个纯函数，不 mock 网络），看它因为 `client.ts` 不存在而红，再实现到绿。
  **类型与 API 函数**：`src/types/{ingest,wiki,brief,ops}.ts` 没有照抄 ARCHITECTURE §4 的示例 JSON，是直接读 `backend/apps/*/serializers.py` 逐字段对出来的（后端从 D1 就在了）——顺带发现 `RssSourceViewSet` 是 `pagination_class = None`，返回裸数组不是分页信封，`listRssSources()` 按这个来的。`GraphNode.symbolSize` 保留驼峰不转 snake_case，因为后端注释明确说这是 ECharts 的字段名硬约束。Prompt 只读接口（`/api/v1/prompts/`）和 cron 端点没有包装成前端函数：前者是 D11 的范围，后者需要 `X-Cron-Token` 密钥，浏览器里没有安全的地方放这个密钥，做了就是给自己埋洞。
  **composables**：`useApi.ts` 原样复制。`usePolling.ts` 的终止状态表从旧项目的 `["done","failed","partial"]` 改成 `["done","success","partial","failed"]`——旧项目和本项目的 `ExtractionRun.status` 枚举不一样（本项目没有 `"done"`，是 `"success"`），照抄会导致轮询永远等不到终止态，测试也跟着改了。
  **布局**：没有照抄旧项目的企业蓝配色，`styles/tokens.scss` 定的是「研究笔记本」路线——石墨色侧边栏 + 暖白内容区，`Fraunces` 做展示字体、`IBM Plex Sans/Mono` 做正文/数据字体，一个琥珀色强调色专门留给证据/引用相关的高亮（呼应产品「every claim is sourced」的卖点），另外把 `Entity.ENTITY_TYPES` 的七个分类色也一并定进了 tokens，D9/D10 画徽标和图谱节点时能直接用。
  **验证**（sqlite + `manage.py runserver`，事后清理了进程和临时库文件）：`npm run lint`、`vue-tsc --noEmit`（构建模式下发现 `baseUrl` 在 TS 6 里已弃用，删掉后 `paths` 照常解析）、`npm run test`（4 个测试，含 client 拦截器与 usePolling）、`npm run build` 均通过；`npm run dev` 起在 5174，5 个路由 curl 全部 200，侧边栏按 `route.meta.navKey` 高亮；backend 用 sqlite 起在 8000 后，`curl 127.0.0.1:5174/api/v1/health/` 经 Vite 代理拿到 `{"status":"ok","db":"ok"}`，代理链路端到端验证过。**没做可视化浏览器截图**：本机 Chrome 扩展未连接，视觉细节（字体渲染、颜色观感）没有人眼确认，仅验证了功能可达性。
  下一步执行 `docs/ROADMAP.md` 的 D9（★ 词条页 + 证据溯源）。
- **2026-08-30**：D9 完成。词条列表（`EntityListView.vue`：搜索 + 类型筛选 + 排序 + 分页，卡片网格）与词条详情（`EntityDetailView.vue`）落地，详情页只发一个请求（`GET /api/v1/wiki/entities/{id}/`），不拆多请求。
  **`LinkageGroup.vue`**：拿到的是扁平的 `linkages[]`，组件内部按 `predicate` 分组（`Map` 保序，不重排——后端 `linkage_payload` 已经按谓词+置信度排好，分组时打乱顺序就白排了）。每行是方向图标 + 对方名称 + 置信度 + 展开按钮；`object.kind==='entity'` 才渲染成 `RouterLink`，`concept` 目前没有详情页（路由表里没有），先渲染成纯文本带 namespace，等 D10/图谱页决定概念怎么跳转再回来接上。
  **`EvidenceCard.vue`**：全五项证据信息（原文片段、来源标题+外链+时间+源站、置信度、prompt_key+version、run_id）都在。置信度不是 Evidence 自己的字段（模型里没有），是父级 `Linkage.confidence` 通过 prop 传下来的，一条 linkage 下的多条证据显示同一个值——这是数据模型决定的，不是疏漏。`run_id` 截断显示前 8 位，点击整段跳 `/ops?run_id=<完整id>`；D11 做流水线面板时要读这个 query 参数自动展开对应 run（选了 query 不是 hash，因为 D11 spec 里两者二选一，这里先定下来）。
  **404 处理**：DRF 默认 `NotFound` 的 `code` 是 `not_found`（不是自定义 `AppError`，走的是 `drf_exceptions.py` 里的兜底分支），前端按这个值判断实体不存在 vs. 其他错误，不是猜的，是读 `drf_exceptions.py` 源码确认的。
  **补齐的工程缺口**：`@vue/test-utils` 在 D8 漏装了（vitest 配了 jsdom 但没有装挂载组件的库），这次补上；`listEntities` 加了 `ordering` 参数（对应后端 `EntityViewSet.ordering_fields`，D8 写类型时没预留）。
  全程 TDD：`EvidenceCard.test.ts`（6 例）、`LinkageGroup.test.ts`（6 例，含分组正确性与展开/收起）、`EntityDetailView.test.ts`（5 例，骨架屏/正常态/空关系态/404/其他错误），每个都先跑红确认失败原因对，再实现到绿。`EntityListView.vue` 本身没有专门测试文件——D9 的测试判据只点了这三个组件，没有额外加测试范围。
  全量 21 个前端测试通过，`vue-tsc --noEmit` 和 `npm run build` 干净，`eslint --fix` 只重排了几处换行。
  **视觉验证**：这次 Chrome 扩展仍未连上，改用 Playwright MCP 起了独立浏览器，sqlite + 已有的 demo fixture（360 实体/452 关系/1049 证据）实跑截图验证——词条卡片网格、详情页头部、关系分组展开证据卡（琥珀色底+左侧竖线+等宽字体）、`run_id` 跳转 `/ops?run_id=...`、404 态、空关系态（`Aakriti Shah`，entity id 43）全部过了一遍，控制台零 JS 错误。
  下一步执行 `docs/ROADMAP.md` 的 D10（关系图谱 + 今日简报页）。
- **2026-08-30**：D10 完成。图谱页（`GraphView.vue` + `components/GraphChart.vue`）和简报首页（`BriefView.vue`）落地。
  **发现并修的契约缺口**：今天的任务要求"实体类型多选、概念 namespace 多选"，但 `/api/v1/wiki/graph/` 当时只接受单值精确匹配（D6 写的 `_entity_nodes`/`_concept_nodes` 是 `queryset.filter(entity_type=entity_type)`）。补了后端：`entity_type`/`namespace` 现在接受逗号分隔的多值（`entity_type=org,product`），`.filter()` 换成 `__in`，单值调用方式不受影响。TDD 补了两个用例（`test_the_graph_can_be_filtered_by_multiple_entity_types`/`_namespaces`），backend 全量测试 + ruff 仍全绿。这不算 ARCHITECTURE 4.2 的契约变更（路径、字段名、响应结构都没动，只是同一个 query 参数现在能传多个值），没去改文档。
  **概念节点点击**：`docs/ROADMAP.md` D10 原文明确说"concept 节点跳概念详情或不跳，二选一并保持一致"——沿用 D9 给 `LinkageGroup` 定的规矩（还没有 `/concept/:id` 路由），点实体节点跳 `/wiki/:id`，点概念节点只弹一条 `message.info` 提示，不跳转。
  **namespace 筛选项从哪来**：`Concept.namespace` 是自由字段，不像 `entity_type` 是固定枚举，没法硬编码选项列表；而 `/graph/` 返回的 `categories` 只反映"当前（可能已被筛选/截断的）节点集合里出现过的类别"，不能拿来做筛选下拉的选项源。解法是挂载时额外拉一次 `limit=500`（对齐后端 `MAX_LIMIT`）、不带筛选条件的图，从它的 `categories` 里刨掉已知的 7 个 entity_type，剩下的就是全量 namespace 列表，和实际渲染用的（会跟着筛选器/滑块变化的）请求分开。
  **`GraphChart.vue`**：后端数据结构（`nodes`/`links`/`categories`/`symbolSize`）直接喂给 ECharts `graph` 力导向系列，前端不转换。`nodeClick` 事件只抛裸 id（如 `"e12"`），前缀解析和跳转逻辑留在 `GraphView` 里——`GraphChart` 保持对路由一无所知，纯渲染组件，测试时不用装 vue-router。mock echarts 测试踩了两个坑：`toBe` 断言 props 引用相等失败（Vue 3 会把对象 props 包成 reactive Proxy，改用 `toEqual`）；`window.resize` 断言被前一个测试遗留的监听器污染（mock 的 `echarts.init` 全局共享同一个 `mockChart` 对象，前一个测试没 unmount 就换下一个，两个组件实例的 resize 监听器都还挂着），加了 `afterEach` 统一 unmount 解决。
  **`renderBrief.ts`**：`marked` 装的是 ^18，上游早就把 `sanitize` 选项砍了（官方文档现在直接建议配 DOMPurify），今天任务里给的两个选项已经只剩一个能用，装了 `dompurify`（不在 CLAUDE.md 禁用列表里，不是 UI 框架/状态库）。顺序是 `marked.parse` → `DOMPurify.sanitize` → 再拿正则把 `[n]` 换成 `<a href="#cite-n">`——角标替换必须放 sanitize *之后*，因为这一步会重新长出裸 HTML 字符串，如果顺序反了等于又开了个没消毒的注入口子；这里安全是因为替换内容自己可控（`\d+` 匹配出的纯数字，不可能带出 HTML 特殊字符）。
  **`EntityListView`/`GraphView` 共享 `ENTITY_TYPE_OPTIONS`**：D9 时这张表是 `EntityListView` 本地定义的，今天图谱页也要用同一张，提到了 `src/constants/entityTypes.ts`。
  全量 32 个前端测试通过（新增 11 个：GraphChart 5、renderBrief 6），backend 新增 2 个测试全量仍绿，`vue-tsc --noEmit`、`eslint`、`npm run build`、`check-clean.sh` 全部通过。
  **视觉验证**：sqlite + 已有 demo fixture，Playwright MCP 实跑（Chrome 扩展仍未连接）——图谱能渲染、图例配色随 category 走、实体类型多选筛选后节点集实时收窄（截图验证选中 "Model" 后画布只剩 model 类实体 + 全部概念节点）、截断提示"仅显示关系最多的 150 个节点"正确出现；首页简报正文渲染、角标 `[6][8][9][10]` 点击后滚动到底部对应参考文献、参考文献外链指向真实 arXiv/LWN/Bluesky 原文、日期切换（←更早/更新→ 与下拉三种方式都试了）在 8-30 与 8-29 两期间正确切换且边界按钮正确禁用。全程控制台零 error。
  **没能测的部分**：ECharts 力导向图渲染在单个 `<canvas>` 上，节点不是独立 DOM 元素，这次的浏览器自动化工具没有像素坐标点击能力，没法在真实浏览器里点某个具体节点验证跳转——这条路径靠 `GraphChart.test.ts` 里直接模拟 echarts 的 `click` 回调覆盖（断言 `nodeClick` 事件带正确 id 抛出），`GraphView.handleNodeClick` 的前缀判断逻辑很薄，人工读代码 + 类型检查确认过。
  下一步执行 `docs/ROADMAP.md` 的 D11（流水线面板 + Prompt 只读展示）。
- **2026-08-30**：D11 完成。`OpsView.vue` 落地：顶部四张聚合卡片、抽取记录表格（可展开每行看六步时间线）、Prompt 版本区、`?run_id=` 深链自动展开并滚动定位，running 状态的 run 挂 `usePolling` 每 3 秒刷新。
  **踩了一个 ant-design-vue 的坑**：Table 的展开配置一开始写成 `:expandable="{expandedRowKeys, onExpand}"`（React antd 的嵌套写法），结果点展开图标只把行视觉上翻开、`expandedRowRender` 插槽一直卡在"加载分步详情中"——因为 antd-vue v4 的 `Table.js` 根本没声明 `expandable` 这个 prop（翻了 `node_modules/ant-design-vue/es/table/Table.js` 的 `tableProps()` 确认的），这些配置在 antd-vue 里是摊平的顶层 prop/事件：`:expanded-row-keys` + `@expand`。改成摊平写法后一次过。中途还被一个假象绕了远路：为了排查加了 `console.log` 又改了函数名，Vite 的 HMR 在多次快速编辑后没能正确替换渲染函数，报了一条指向已删除函数名的 `[Vue warn]`——最后发现是本机端口 5173-5176 上还挂着好几个之前 session 没真正杀掉的 `npm run dev` 僵尸进程（Windows 上 `TaskStop` 杀 shell 不一定杀得掉子进程），一直在响应旧代码；清掉僵尸进程、在干净的 5173 上重启才看清是 API 形状的问题，不是 HMR 或时序问题。session 结束前把 5173/5177/8000 上的僵尸进程也清了。
  **测试**：`RunDetail.test.ts`（5 例，覆盖失败步骤的 error_message 和未执行步骤置灰）、`OpsView.test.ts`（2 例，专测轮询——running 状态每 3 秒调 `getRun`，拿到终止态后不再调）。`usePolling` 加了泛型 `<T extends {status:string}>` 让 `getRun` 的返回类型能直接流过去，不用在消费处强制类型转换；已有的 `usePolling.test.ts` 两个用例原样通过。
  **补的工程缺口**：`api/prompts.ts` / `types/prompts.ts` 是 D8 特意没做的（当时说是 D11 的范围），今天按 `listRssSources()` 的先例（`pagination_class=None` 返回裸数组）补上。`tokens.scss` 加了 `--color-warning`（partial，橙）和 `--color-info`（running，蓝）两个新语义色——和证据高亮用的琥珀色分开，避免语义混用。
  测试环境也补了一个洞：`vitest.config.ts` 之前没有 `setupFiles`，第一次挂载 `a-table` 就因为 jsdom 没实现 `window.matchMedia` 直接抛错（antd 的响应式断点观察器要用），加了 `src/test-setup.ts` 做 polyfill。
  全量 39 个前端测试通过，`vue-tsc --noEmit`、`eslint`、`npm run build`、`check-clean.sh` 全部通过。
  **视觉验证**：sqlite + demo fixture 实跑，Playwright MCP——聚合卡片数字（10 run / 90% / 1,196,020 token / ¥2.83）与 fixture 记录的真实数字对得上；展开一条"部分成功"的 run，六步时间线渲染出真实的失败场景（`抽取实体` 步骤红叉 + 错误消息「LLM returned an empty completion」+ 尝试 2 次，`采集`/`生成简报` 两步因为这次 run 没有对应数据而灰显"未执行"）；展开/收起、Prompt 面板展开模板全文、`?run_id=` 深链跳转定位到对应行且自动展开，全部过了一遍，控制台零 error。
  下一步执行 `docs/ROADMAP.md` 的 D12（上线部署）。
- **2026-08-30**：D12 完成，**已上线：https://newswiki.cn**（www 同源别名）。实际资源与 `DEPLOYMENT.md` 原始设定有出入：**阿里云轻量应用服务器，首尔**（不是腾讯云香港），域名 **newswiki.cn**（不是 .app/.dev/.com）。首尔没有 HK 对大陆的线路优势，所以 ADR-006 的"直连优于 CDN"前提这次是真要靠实测验证，不是走过场。
  **仓库从 private 转 public**：VPS 拉取代码、GitHub Actions 的 `deploy.yml`/`cron-daily.yml` 都需要持续访问仓库；给 VPS 配只读 deploy key 也能做但更重，加上这本来就是秋招作品集项目，转 public 更直接。转之前核对过 `.env` 从未被 track、`.forbidden-terms` 从未提交、`check-clean.sh` 每次 commit 都过，历史是干净的。
  **服务器基座**：`adduser --disabled-password` 建的 `deploy` 用户没有 Unix 密码，会导致 `sudo` 永远失败（本地密码认证过不了）——没有给它补密码，而是把仅剩的几个需要 root 的一次性操作（装 Docker、配 ufw）直接以 root 身份做完，再把 `deploy` 加进 `docker` 组即可，长期看 `deploy` 反而不需要任何 sudo 权限，比照抄 runbook 的字面步骤更小权限面。root 密码登录鬼使神差地连续失败 3 次，换用户名/host key 都排除后最终用 Aliyun 控制台的 VNC 直接以 root 登录补上了公钥，原因没深究（大概率是人为输错，同一密码后来再没用上，已经禁用密码登录）。
  **两个真部署 bug**：① 根目录 `.dockerignore` 从 D1 起就排除 `frontend`（那时镜像只打包后端），这次 Dockerfile 改成多阶段构建后，新的 `frontend-builder` 阶段的 `COPY frontend/ ./` 直接找不到目录——`.dockerignore` 现在只排除 `frontend/node_modules` 和 `frontend/dist`。② `docker-compose.prod.yml` 里 `command: >` 用了折叠标量（folded scalar），为了视觉对齐给 gunicorn 参数续行加了额外缩进，YAML 折叠规则里"比首行缩进更深的续行保留字面换行、不折叠成空格"，结果 shell 把 `--bind 0.0.0.0:8000 ...` 解析成了一条独立、永远不会执行到的语句（gunicorn 在前台阻塞，shell 根本走不到下一行）——gunicorn 因此静默回落到默认的 `127.0.0.1:8000` 单进程，`docker exec` 内部健康检查因为走的是同容器 loopback 照样显示 healthy，只有跨容器的 Caddy 反代会 502。排查靠的是 `/proc/net/tcp` 直接看实际监听地址，而不是信 gunicorn 启动日志或 `--bind` 命令行参数。现在改成续行与首行同缩进，YAML 解析结果用本地 venv 的 PyYAML 验证过是单行字符串。
  **CI/CD 端到端验证过，不是只连上就算数**：`ci.yml` 补了一个 `frontend` job（lint + vue-tsc + vitest + build）——`deploy.yml` 靠 `workflow_run` 挂在 `CI` workflow 的结论上（`needs:` 不能跨 workflow 文件），如果 CI 一直没测过前端，这个"绿了才部署"的关卡就是假的。`deploy.yml`、`cron-daily.yml` 都用 `gh workflow run` 手动 `workflow_dispatch` 触发过，两个都拿到了绿灯；`cron-daily` 真实调用了生产的 `/api/v1/ops/cron/daily`，返回了 `run_id`，触发的抽取管线在后台跑完（15 篇文章入库）。
  **Cloudflare Pages 对比没做成**：按 D11 前一晚定的方案，本想只用一个子域名（`cf.newswiki.cn`）单独接 Cloudflare 做 A/B，避免动主域名 DNS。真到 Cloudflare 建站页才发现它现在的入口不收"仅子域名"（明确提示"请提供根域名而非子域名"），要做自定义域名对比就得把整个域名的 NS 迁移过去——对一个演示项目这个成本换不来多少信息量，用户直接跳过了这步。**只做了直连一侧的 ITDOG 实测**：290 个全国监测点，**100% 成功、平均 0.712s**，全部解析到真实服务器 IP、无 DNS 污染。数据没有指向"需要 CDN"的信号，ADR-006（同源直连不用 CDN）予以保留，完整数据与 ADR-006 的验证记录分别写进了 `DEPLOYMENT.md` §8 和 `DECISIONS.md`。
  **本机限制**：Chrome 扩展这次也没连上（和 D8/D9 一样），Cloudflare Pages 的 GUI 步骤没法用浏览器自动化代做，且账号登录类操作本来就不该由我代劳——改成引导用户在自己已登录的浏览器里操作、贴结果回来的方式协作完成。ITDOG 结果是用户存的一张 2194x13099 的长截图，本地装了个 Pillow（只进本机 venv，没进 `requirements.txt`）分块裁剪读数据，原图留在仓库根目录未提交。
  **待办**：手机 4G 打开首页 3 秒出内容——留给用户自己确认，我这边测不了。
  下一步执行 `docs/ROADMAP.md` 的 D13（README + 简历话术）。
- **2026-08-30**：D13 完成。README.md 从占位骨架填成完整门面：顶部一句话定位 + 在线地址 + 演示 GIF、四条核心特性各配一张真实截图、`docs/ARCHITECTURE.md` §2 的 mermaid 数据流图、技术栈表、三行 `docker compose` 快速开始、从 14 条 ADR 里展开写的「设计取舍」（Playwright/三步抽取/Evidence 三可空外键/不用 Celery/成本护栏 各一节）、项目结构树、测试与 CI 说明、License。
  **素材全部来自线上真实站点**，不是本地 sqlite：Chrome 扩展本 session 仍未连接（与 D8/D9/D12 一样），改用 Playwright MCP 直连 `https://newswiki.cn`（已上线的生产环境）截图。四张核心特性图——`pipeline-steps.png`/`evidence-trace.png`/`prompt-panel.png`/`cost-guardrail.png`——分别裁剪/截取自 `/ops` 页某条"部分成功" run 的六步时间线（真实失败重试场景）、`/wiki/410`（OpenAI 词条）展开的一条证据、Prompt 版本面板里 `wiki.extract_linkages` 的真实模板全文、顶部聚合卡片。
  **`demo.gif` 的做法**：本机没有可用的屏幕录制 GUI 工具（ScreenToGif/LICEcap 需要人工操作桌面），改成用 Playwright 截取 6 帧关键状态（首页简报 → 点 [16] 角标滚到参考文献 → 词条库搜索 OpenAI → 词条详情 → 展开"采用→ExploitGym"证据 → 点 `run·ea9b74ec` 跳转 `/ops?run_id=...` 看到同一条证据出自的那次真实 run），用本机 venv 的 Pillow 拼成动图，共 12.1 秒、361KB，远低于 15 秒/5MB 的判据。叙事线是真实数据串起来的：首页当天简报第 [16] 条引用的原文（"The Rise and Fall of Agent Civilizations"）恰好就是 OpenAI 词条那条"采用 ExploitGym"关系的证据来源，两条线在同一篇文章上闭环，不是摆拍。
  **数字全部现查，没有蹚旧账**：backend 488、frontend 39（`pytest -q` / `npm run test` 现跑现数，比 CLAUDE.md 里 D11 记的 486 多 2 个，是 D10 补的多值 `entity_type`/`namespace` 过滤测试）；演示数据集精确数字（95 篇/360 实体/219 概念/452 关系/1049 证据）直接数的 `backend/fixtures/demo.json`，而不是照抄 D7 状态记录里的约数；线上运行统计（11 次/91%/149.2 万 token/¥3.55）是这次直接 `curl https://newswiki.cn/api/v1/ops/stats/` 现查的——比 D7 记录的 10 次多了 D12 验收时触发的那次真实 cron（15 篇文章）。
  **`docs/RESUME.md`** 补完全部 `<X>/<Y>/<Z>/<N>` 占位符：没有编一个"抽取成功率从 X% 提升到 Y%"的虚构对比，改成线上 11 次真实运行的实际分布（10 成功/1 部分成功/0 完全失败）；成本护栏的"日成本控制在 Z 元内"填的是 `LLM_DAILY_BUDGET_CNY` 实际配置值 ¥5，并补充实际日均花费远低于这个阈值；词条详情"压到 <10 条查询"改成精确的"固定 5 次"（ADR-003 的真实断言值）；GitHub/演示链接从占位的 `xxx`/`example.com` 换成真实的 `t956175001/news-wiki` 和 `newswiki.cn`；ADR 计数从"12 条"更正为当前实际的 14 条。
  **GitHub 仓库门面**：`gh repo edit` 设置了 homepage（`https://newswiki.cn`）和 6 个 topics（llm/knowledge-graph/django/vue3/information-extraction/rss），description 保持不动；执行前用 `AskUserQuestion` 征得确认，因为这是修改公开仓库元数据的操作。`.env` 未被跟踪、`.forbidden-terms` 未提交，`scripts/check-clean.sh` 全绿（222 个待提交文件，禁用词/多 provider 残留/明文密钥/垃圾文件全部 PASS）。
  **LICENSE** 的版权署名从占位符 `<YOUR NAME>` 改成真实姓名 Junhe Tang（用户在会话中提供）。
  下一步执行 `docs/ROADMAP.md` 的 D14（打磨 + 演示录制）。
