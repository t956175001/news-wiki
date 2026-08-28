<!--
⚠️ 这是 D13 才补完的占位骨架。
标了 TODO 的地方在 D13 用真实内容替换，替换后删除本注释。
写作要求见 docs/ROADMAP.md 的 D13 章节。
-->

# news-wiki

> 自动生成、可溯源的 AI 资讯维基 —— 让大模型的每条结论都能回溯到原文出处。

<!-- TODO(D13): 徽章 -->
<!-- ![CI](https://github.com/xxx/news-wiki/actions/workflows/ci.yml/badge.svg) -->
<!-- ![License](https://img.shields.io/badge/license-MIT-blue) -->

**在线演示**：<!-- TODO(D13) --> `https://news-wiki.example.com`

<!-- TODO(D13): 演示 GIF，15 秒内，5MB 以内
     路径：docs/images/demo.gif
     内容：首页简报 → 点引用角标 → 进词条页 → 展开证据 → 跳流水线面板 -->

---

*English summary: news-wiki automatically ingests AI news via RSS, runs a three-stage LLM extraction pipeline (entities → concepts → relations), and builds a traceable knowledge wiki where every extracted claim links back to its source snippet, URL, confidence score, and the exact prompt version used. Includes a daily AI brief with inline citations, an interactive relation graph, and a pipeline observability dashboard tracking per-step latency, tokens, and cost.*

---

## 这个项目在解决什么问题

大多数「AI 摘要」工具的问题是：输出读起来很流畅，但你没法验证它对不对，只能选择信或不信。

news-wiki 换了个思路——**不直接生成文本，而是先做结构化抽取，再把每条结论钉死在原文上**。

<!-- TODO(D13): 词条页展开证据的截图，这是最有说服力的一张 -->

## 核心特性

<!-- TODO(D13): 每条配一张截图 -->

### 1. 三阶段串行抽取，用工程手段约束 LLM

实体 → 概念 → 关系，后一步的候选集被约束为前一步的输出。抽关系时主语宾语必须逐字来自已抽出的实体清单，不在清单里的一律丢弃——这挡住了「同一实体被模型拆成多个别名节点」的典型问题。

配合 JSON Schema 校验 + 指数退避重试，并区分两类失败：格式错误重试，个别条目非法则跳过并计数。

### 2. 证据溯源

每条抽取结论落库时绑定：**原文片段 + 来源 URL + 发布时间 + 置信度 + 所用 Prompt 版本 + 运行 ID**。

数据库层用 `CheckConstraint` 强制「一条证据有且仅有一个目标」，保证溯源链路不被脏数据污染。

### 3. Prompt 版本管理 + 流水线可观测

Prompt 以版本记录存储，抽取时快照版本号写入每条证据——所以词条页上「本条由 v2 抽出」是真的。

`ExtractionRun` 记录分步耗时、token、成本，面板可下钻到单次运行的每一个步骤。

### 4. 演示成本护栏

预置语料 + IP 维度限流 + 日预算熔断，公开演示环境的成本可控。

---

## 架构

<!-- TODO(D13): 从 docs/ARCHITECTURE.md 第 2 节搬 mermaid 数据流图过来 -->

## 技术栈

| 层 | 选型 |
|---|---|
| 后端 | Django 5 · Django REST Framework · drf-spectacular |
| 数据库 | PostgreSQL 16 |
| LLM | 智谱 GLM（OpenAI 兼容 SDK）· tenacity |
| 采集 | feedparser · httpx · trafilatura |
| 前端 | Vue 3 · TypeScript · Vite · Ant Design Vue · Pinia · ECharts |
| 部署 | Docker Compose · Caddy（自动 HTTPS）· GitHub Actions |

## 快速开始

```bash
git clone https://github.com/xxx/news-wiki.git
cd news-wiki
cp .env.example .env        # 填入 SECRET_KEY 和 GLM_API_KEY
docker compose up -d
docker compose exec web python manage.py seed_demo
```

打开 http://localhost:8000 ，API 文档在 http://localhost:8000/api/v1/docs/

## 设计取舍

<!-- TODO(D13): 从 docs/DECISIONS.md 挑 5 条展开写。建议：
     - 为什么云端不跑 Playwright（ADR-001）
     - 为什么拆成三步抽取而不是一次抽全（ADR-002）
     - 证据表为什么用三个可空外键而不是 GenericForeignKey（ADR-003）
     - 为什么不用 Celery（ADR-004）
     - 演示环境的成本控制怎么做的（ADR-012）
     这一章是简历项目和玩具项目的分水岭，认真写。 -->

## 项目结构

<!-- TODO(D13): 从 docs/ARCHITECTURE.md 第 1 节精简后搬过来 -->

## 测试

```bash
cd backend && pytest -q          # 后端
cd frontend && npm run test      # 前端
```

LLM 调用在测试中全部 mock，重点覆盖失败路径（非法 JSON、字段缺失、引用越界、重试耗尽）。

## 后续规划

见 [docs/BACKLOG.md](docs/BACKLOG.md)。

## 文档

| 文档 | 内容 |
|---|---|
| [docs/PRD.md](docs/PRD.md) | 产品定位与验收标准 |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | 数据模型、API 契约、数据流 |
| [docs/DECISIONS.md](docs/DECISIONS.md) | 架构决策记录（ADR） |
| [docs/PROMPTS.md](docs/PROMPTS.md) | Prompt 全文与校验规则 |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | 部署 Runbook |

## License

MIT
