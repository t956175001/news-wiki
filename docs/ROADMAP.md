# ROADMAP — news-wiki 14 天实施计划

> 每天一个 session。**用法**：新开 Claude Code session，把当天的「Session Prompt」整段粘进去即可。
> 完成判据是**可执行命令**，必须真跑并贴出输出。判据不过 = 当天没完成。

**起始日**：2026-08-28
**目标上线日**：2026-09-11

---

## 进度总览

- [ ] D1 仓库脚手架与工程基座
- [ ] D2 数据模型 + RSS 采集
- [ ] D3 LLM 客户端 + Prompt 服务 + 校验器
- [ ] D4 ★ 三步抽取管线
- [ ] D5 每日简报 + cron 端点 + 限流熔断
- [ ] D6 API 层 + OpenAPI
- [ ] D7 机动：补测试 + seed_demo
- [ ] D8 前端脚手架 + 布局 + API 层
- [ ] D9 ★ 词条页 + 证据溯源
- [ ] D10 关系图谱 + 今日简报页
- [ ] D11 流水线面板 + Prompt 只读展示
- [ ] D12 上线部署
- [ ] D13 README + 简历话术
- [ ] D14 打磨 + 演示录制

---

# Week 1 — 后端与 AI 管线

## D1 — 仓库脚手架与工程基座

**前置阅读**：`CLAUDE.md`、`docs/ARCHITECTURE.md` 第 1、7 节

### Session Prompt

```
读 CLAUDE.md 和 docs/ARCHITECTURE.md 的第 1 节（目录树）与第 7 节（配置项）。

今天做 D1：搭起工程基座，不写任何业务逻辑。

1. 后端骨架
   - backend/ 下建 Django 5 项目，模块名 config
   - config/settings/ 拆成 base.py / dev.py / prod.py，通过 DJANGO_ENV 切换
   - base.py 从 .env 读配置（python-dotenv），DATABASE_URL 用 dj-database-url 解析
   - 建五个空 app：apps/common、apps/ingest、apps/wiki、apps/brief、apps/ops
     （apps/common/prompts 作为 common 下的独立 app）
   - 装好 DRF、django-filter、drf-spectacular、django-cors-headers、whitenoise
   - config/urls.py 挂 /api/v1/ 前缀和 /api/v1/docs/（drf-spectacular SwaggerUI）
   - 实现 /api/v1/health/ 返回 {"status":"ok","db":"ok"}（真去 ping 一下数据库）
   - requirements.txt / requirements-dev.txt
   - pyproject.toml 配 ruff（line-length 110）
   - pytest.ini 配 pytest-django，DJANGO_SETTINGS_MODULE=config.settings.dev

2. 从旧仓库移植 common 四件套
   按 docs/MIGRATION.md 的清单，从旧仓库复制并改造：
   - apps/common/exceptions.py
   - apps/common/drf_exceptions.py
   - apps/common/pagination.py
   - apps/common/prompts/ 整个 app
   注意 MIGRATION.md 里逐条列出的删除项，特别是任何非 GLM 的 provider 配置。

3. 容器化
   - Dockerfile：python:3.11-slim，装依赖，collectstatic，gunicorn 启动
   - docker-compose.yml（本地开发）：db(postgres:16) + web，web 挂载源码热重载
   - .env.example 按 ARCHITECTURE.md 第 7 节的表逐项写全，敏感值一律 replace-me

4. CI
   - .github/workflows/ci.yml：push 和 PR 触发，跑 ruff check + ruff format --check + pytest
   - 用 postgres service container

5. 仓库卫生
   - .gitignore（Python + Node + .env + logs + data）
   - LICENSE（MIT，作者留占位 <YOUR NAME>）
   - 写一个 tests/test_smoke.py，测 /api/v1/health/ 返回 200

不要写任何业务模型或业务逻辑，那是 D2 的事。
```

### 完成判据

```bash
cd D:/Claude/demo/news-wiki
docker compose up -d db
cd backend && pytest -q                          # 至少 1 个测试通过
cd backend && ruff check . && ruff format --check .
cd backend && python manage.py migrate           # 无报错
cd backend && python manage.py runserver 8000    # 另开终端：
curl -s localhost:8000/api/v1/health/            # 期望 {"status":"ok","db":"ok"}
curl -s -o /dev/null -w "%{http_code}" localhost:8000/api/v1/docs/   # 期望 200
bash scripts/check-clean.sh                       # 期望全部 PASS
```

---

## D2 — 数据模型 + RSS 采集

**前置阅读**：`docs/ARCHITECTURE.md` 第 3 节（模型字段级契约）、第 8 节第 1-2 条

### Session Prompt

```
读 docs/ARCHITECTURE.md 第 3 节和第 8 节。

今天做 D2：建全部数据模型，实现 RSS 采集。

1. 模型（严格按 ARCHITECTURE.md 第 3 节的字段定义，不要增删字段）
   - apps/ingest/models.py: RssSource, RawArticle
   - apps/wiki/models.py: Entity, Concept, Linkage, Evidence
   - apps/ops/models.py: ExtractionRun
   - apps/brief/models.py: DailyBrief
   注意三个约束一个都不能少：uniq_entity_norm_type、linkage_object_required、
   evidence_single_target。
   生成迁移并 migrate。

2. Django Admin
   每个模型注册 admin，配好 list_display / list_filter / search_fields。
   Evidence 的 admin 要能按 raw_article 和 extraction_run 过滤。

3. 采集实现
   - apps/ingest/fetchers/base.py: 定义 ArticleFetcher Protocol
     （fetch(url) -> FetchedArticle，FetchedArticle 是 dataclass）
   - apps/ingest/fetchers/rss.py: feedparser 解析 feed，返回条目列表
   - apps/ingest/fetchers/article.py: httpx 拉页面 + trafilatura 抽正文
     超时 20s，UA 伪装成常见浏览器，失败抛 FetchError
   - apps/ingest/services/ingest.py:
     * compute_hash(url, title) -> str  按 ARCHITECTURE 第 3.1 节的规则
     * fetch_source(source) -> dict  拉一个源，去重后入库，返回统计
     * fetch_all_enabled() -> dict  遍历所有 enabled 的源
     去重：content_hash 已存在则跳过，计入 deduped 计数
     失败：单篇失败不影响其他，记进 RssSource.last_error

4. 种子源
   apps/common/management/commands/seed_sources.py，灌入这些 AI 资讯 RSS：
   - 机器之心、量子位（若无官方 RSS 用 RSSHub 格式的占位 URL，注释说明）
   - Hacker News front page: https://hnrss.org/frontpage
   - arXiv cs.AI: http://export.arxiv.org/rss/cs.AI
   至少 4 个源，enabled=True。

5. 测试 tests/ingest/
   - test_ingest.py: compute_hash 稳定性、去重逻辑、单篇失败不中断
   - test_fetchers.py: mock httpx 响应，测 trafilatura 抽取；测 FetchError
   网络请求全部 mock，禁止真实外网调用。
```

### 完成判据

```bash
cd backend
pytest tests/ingest/ -q                          # 全绿
python manage.py migrate                          # 无 pending 迁移
python manage.py makemigrations --check --dry-run # 期望 "No changes detected"
python manage.py seed_sources
python manage.py shell -c "from apps.ingest.models import RssSource; print(RssSource.objects.count())"  # >= 4
# 真实拉一次（需外网）：
python manage.py shell -c "
from apps.ingest.services.ingest import fetch_all_enabled
print(fetch_all_enabled())"
python manage.py shell -c "from apps.ingest.models import RawArticle; a=RawArticle.objects.first(); print(a.title, len(a.content))"
```

> 最后两条需要外网。若当前网络不通，跳过并注明，改用 mock 数据验证入库路径。

---

## D3 — LLM 客户端 + Prompt 服务 + 校验器

**前置阅读**：`docs/ARCHITECTURE.md` 第 5 节、`docs/PROMPTS.md` 全文

### Session Prompt

```
读 docs/ARCHITECTURE.md 第 5 节和 docs/PROMPTS.md 全文。

今天做 D3：LLM 调用层与输出校验，为 D4 的管线铺路。

1. LLM 客户端 apps/common/llm/
   - client.py: LLMResult (TypedDict) 和 LLMClient (Protocol)
   - glm.py: GLMClient，用 openai SDK 指向 GLM_BASE_URL
     ★ chat() 必须返回 LLMResult，从 response.usage 读 token 数。
       旧项目返回裸 str 丢了 usage，这次不能重蹈覆辙。usage 缺失时填 0。
     内置 tenacity 重试（APIStatusError/APIConnectionError，3 次指数退避）
     429 时读 retry-after header 后 sleep
   - ratelimit.py: 令牌桶，进程内共享，LLM_RATE_LIMIT_RPM 控制
   - pricing.py: estimate_cost(model, prompt_tokens, completion_tokens) -> Decimal
     价格表硬编码 GLM-4.7 官网价，环境变量可覆盖，注释写明价格以官网为准
   - factory.py: get_llm_client() 读 settings 构造，带 lru_cache

2. Prompt 服务
   - apps/common/prompts/seeds.py: 把 docs/PROMPTS.md 里四个 prompt 的全文
     作为 v1 灌进去，key 分别是 wiki.extract_entities / wiki.extract_concepts /
     wiki.extract_linkages / brief.daily
   - 用 data migration 落库，保证 migrate 后即可用
   - service.py: render(key, ctx) -> str，取 current_version 的 text 做 format
     get_version(key) -> int，返回当前版本号（管线要记录）
     key 不存在抛 AppError

3. 校验器 apps/wiki/services/validators.py
   严格按 docs/PROMPTS.md「校验规则」表实现：
   - SchemaError(ValueError) 异常类
   - validate_entities(payload, allowed_article_ids) -> tuple[list[dict], dict]
   - validate_concepts(...) 同上
   - validate_linkages(payload, allowed_article_ids, known_entities, known_concepts) -> ...
   返回值第二项是 skipped 统计 dict。
   注意区分「抛错重试」和「跳过该项」两类处理，表里写得很清楚。
   evidence 子串检查前先去除所有空白再比对。

4. 测试 tests/common/ 和 tests/wiki/test_validators.py
   - LLM 客户端：mock openai SDK，测正常返回带 usage、测 usage 缺失填 0、
     测 429 重试、测重试耗尽抛 LLMError
   - pricing: 已知 token 数算出预期金额
   - render: 变量替换正确、缺 key 抛错
   - validators: 每一条校验规则一个用例，特别是
     * 根键缺失 → SchemaError
     * raw_article_id 不在集合 → 跳过且计数
     * evidence 非原文子串 → confidence 打折但不抛错
     * linkage 引用未知实体 → 跳过且计数

5. tests/conftest.py 加一个 mock_llm fixture，后续所有 LLM 测试复用。
```

### 完成判据

```bash
cd backend
pytest tests/common/ tests/wiki/test_validators.py -q   # 全绿，至少 20 个用例
python manage.py migrate
python manage.py shell -c "
from apps.common.prompts.service import render, get_version
print(get_version('wiki.extract_entities'))
print(render('wiki.extract_entities', {'raw_text':'TEST'})[:200])"
# 期望：打印 1，以及渲染后含 TEST 的 prompt 开头
python manage.py shell -c "
from apps.common.llm.pricing import estimate_cost
print(estimate_cost('glm-4.7', 10000, 2000))"   # 期望一个合理的 Decimal 金额
```

---

## D4 — ★ 三步抽取管线（本周最难）

**前置阅读**：`docs/ARCHITECTURE.md` 第 3.2/3.3 节、第 8 节；`docs/PROMPTS.md` 全文；`docs/DECISIONS.md` ADR-002

### Session Prompt

```
读 docs/ARCHITECTURE.md 第 3.2、3.3、8 节，以及 docs/PROMPTS.md 全文。

今天做 D4：三步抽取管线。这是整个项目的核心，慢一点没关系，做扎实。

背景：旧项目的 extract_pipeline.py 只跑了第一步，
extract_concepts 和 extract_linkages 写了但从未被调用，log["mode"] 硬编码
"entities_only"，所以图谱根本没有边。这次必须三步全跑通并落库。

1. apps/wiki/services/normalize.py
   - normalize_name(name) -> str  = " ".join(name.lower().split())
   - PREDICATE_ALIASES: dict[str,str]，把同义谓词映射到规范词
     （如 推出/发行/上线 → 发布；并购/收购 → 收购）
     至少覆盖 docs/PROMPTS.md 里 extract_linkages 谓词表的常见同义词
   - normalize_predicate(p) -> str，映射不到就原样返回
   - merge_aliases(old, new) -> list[str]  并集去重排序

2. apps/wiki/services/extract_pipeline.py
   - build_corpus(articles) -> str   按 docs/PROMPTS.md「语料格式」
     正文截断到 settings.EXTRACT_CONTENT_LIMIT（默认 4000）
   - _invoke_json(prompt_key, ctx, **llm_opts) -> tuple[dict, StepMeta]
     调 LLM，json.loads，失败抛 SchemaError（带 response 前 1000 字预览）
     tenacity 重试 3 次，指数退避，retry 条件含 LLMError/SchemaError/JSONDecodeError
     StepMeta 记录 elapsed_ms / prompt_tokens / completion_tokens / attempts
   - extract_entities(corpus, allowed_ids)
   - extract_concepts(corpus, entities, allowed_ids)
   - extract_linkages(corpus, entities, concepts, allowed_ids)
   - persist(run, articles, entities, concepts, linkages) -> dict
     * Entity: update_or_create(normalized_name, entity_type)，别名并集，
       mention_count += 1，first/last_seen_at 维护
     * Concept: update_or_create(namespace, name)
     * Linkage: subject/object 按 name 反查刚落库的对象；
       predicate 过 normalize_predicate；用 get_or_create 靠
       uniq_linkage_triple 去重
     * Evidence: 每个抽取项若有 evidence 就建一条，写入
       prompt_key + prompt_version + extraction_run
     整个 persist 包在一个 transaction.atomic() 里
   - run_extraction(articles, trigger="manual") -> ExtractionRun
     * 建 ExtractionRun，run_id=uuid4().hex，status=running
     * 开头快照四个 prompt 的 version 写进 prompt_versions
     * 分批：每批 settings.EXTRACT_BATCH_SIZE（默认 5）篇
     * 逐步执行，每步结束把 StepMeta 写进 run.step_metrics 并 save()
       （要能在执行过程中被前端轮询看到进度）
     * 任一步失败：记 error_message，status 置 partial（若前面有成功的步骤）
       或 failed（第一步就挂），已成功的结果保留，不整体回滚
     * 结束时汇总 token、算 cost_cny、写 elapsed_ms、finished_at
     * 把处理过的 RawArticle.extract_status 置 extracted / failed

3. 测试 tests/wiki/test_extract_pipeline.py（重点，至少 12 个用例）
   全部 mock LLM，禁止真实调用。必须覆盖：
   - 正常路径：三步都返回合法 JSON → Entity/Concept/Linkage/Evidence 都落库，
     数量正确，run.status == "success"
   - Evidence 的 prompt_key / prompt_version 写对了
   - Linkage 的 subject/object 正确指向落库的对象
   - 谓词归一化生效（喂 "推出" 得到 "发布"）
   - 重复运行同一批数据：Entity 不重复创建，mention_count 递增，
     Linkage 因 uniq_linkage_triple 不重复
   - step1 返回非法 JSON → 重试 3 次后 run.status == "failed"，
     step_metrics["extract_entities"]["attempts"] == 3
   - step2 失败但 step1 成功 → status == "partial"，实体已落库
   - LLM 返回的 raw_article_id 不在批次内 → 跳过，计入 skipped
   - linkage 引用了未抽出的实体 → 跳过，计入 skipped
   - 空结果（entities: []）→ 不重试，正常结束
   - token 汇总和 cost_cny 计算正确
   - 分批：喂 12 篇 + batch_size=5 → LLM 被调用的次数符合预期
```

### 完成判据

```bash
cd backend
pytest tests/wiki/ -q -v        # 全绿，test_extract_pipeline 至少 12 个用例
# 端到端真跑一次（需 GLM_API_KEY 和已采集的文章）：
python manage.py shell -c "
from apps.ingest.models import RawArticle
from apps.wiki.services.extract_pipeline import run_extraction
arts = list(RawArticle.objects.filter(extract_status='pending')[:3])
run = run_extraction(arts, trigger='manual')
print('status:', run.status)
print('entities:', run.entities_saved, 'concepts:', run.concepts_saved, 'linkages:', run.linkages_saved)
print('tokens:', run.total_tokens, 'cost:', run.cost_cny)
print('steps:', list(run.step_metrics.keys()))"
# ★ linkages 必须 > 0，否则图谱没有边，D4 不算完成
python manage.py shell -c "
from apps.wiki.models import Evidence
e = Evidence.objects.filter(linkage__isnull=False).first()
print(e.snippet[:80]); print(e.prompt_key, 'v', e.prompt_version)"
```

> **D4 是最可能延期的一天。** 若 `linkages` 始终为 0，先检查 prompt 里 subject/object
> 必须逐字来自列表这条约束是否太严；可放宽为模糊匹配（去空白后小写比对）。
> 仍不行则按 PRD 优先级降级：只做 entity + concept，图谱变二部图，词条页不受影响。

---

## D5 — 每日简报 + cron 端点 + 限流熔断

**前置阅读**：`docs/ARCHITECTURE.md` 第 3.4 节、第 4 节；`docs/PRD.md` 第 4 节；`docs/PROMPTS.md` 的 `brief.daily`

### Session Prompt

```
读 docs/ARCHITECTURE.md 第 3.4、4 节，docs/PRD.md 第 4 节，
docs/PROMPTS.md 的 brief.daily 章节。

今天做 D5：简报生成、编排入口、成本护栏。

1. apps/brief/services/generate.py
   - generate_daily_brief(date, run=None) -> DailyBrief
     * 取当日（按 publish_time 或 fetched_at）的 RawArticle，最多 20 篇
     * 取当日 run 产出的 Entity / Linkage 作为素材
     * articles_json 里给每篇编 index（1 起）
     * 调 brief.daily prompt
     * ★ 不信任 LLM 输出的引用元数据：按返回的 used_indexes 反查
       RawArticle 自己构造 citations
     * used_indexes 里有越界的序号 → 忽略该序号并记 warning
     * upsert 到 DailyBrief（date 唯一）
   - 当日无文章时抛 AppError("NO_ARTICLES")，不调 LLM

2. apps/ops/services/pipeline.py
   - run_daily(source_ids=None, trigger="cron") -> ExtractionRun
     编排：ingest → extract → brief，三步各自写进同一个 ExtractionRun 的
     step_metrics。任一步失败不阻断后续可执行的步骤，最终 status 取
     success / partial / failed。

3. 成本护栏
   - apps/common/budget.py
     * today_cost() -> Decimal  汇总当日所有 ExtractionRun 的 cost_cny
     * check_budget()  超过 LLM_DAILY_BUDGET_CNY 抛 BudgetExceededError
     * 在 _invoke_json 调用前检查；cron 触发时跳过检查（trigger == "cron"）
   - apps/common/throttling.py
     * DemoWriteThrottle(ScopedRateThrottle)，scope="demo_write"
     * 速率读 settings.DEMO_WRITE_RATE（默认 "3/day"）
     * DEMO_MODE=false 时不限流
   - drf_exceptions.py 里把 429 转成
     {"code":"RATE_LIMITED","detail":"演示模式下每个 IP 每天可触发 3 次实时抽取，明天再来试试～"}

4. cron 端点
   - POST /api/v1/ops/cron/daily
     校验 X-Cron-Token header 与 settings.CRON_TOKEN 相等（用 secrets.compare_digest）
     不等返回 403 {"code":"FORBIDDEN"}
     校验通过后在后台线程跑 run_daily，立即返回 {"run_id": "...", "status": "running"}
     免限流、免预算检查

5. 测试
   - tests/brief/test_generate.py: mock LLM，测 citations 是后端反查构造的
     （故意让 LLM 返回错误的 url，断言最终 citations 里是数据库里的真 url）；
     测 used_indexes 越界被忽略；测无文章抛 AppError
   - tests/ops/test_pipeline.py: 测三步编排、测中间步骤失败时 status 为 partial
   - tests/ops/test_cron.py: 测无 token 403、错 token 403、对 token 200 返回 run_id
   - tests/common/test_budget.py: 测超预算抛错、测 cron 触发跳过检查
   - tests/common/test_throttle.py: 测第 4 次请求返回 429 和中文文案
```

### 完成判据

```bash
cd backend
pytest tests/brief/ tests/ops/ tests/common/test_budget.py tests/common/test_throttle.py -q
# cron 端点
export CRON_TOKEN=testtoken
python manage.py runserver 8000 &
curl -s -o /dev/null -w "%{http_code}\n" -X POST localhost:8000/api/v1/ops/cron/daily          # 期望 403
curl -s -X POST -H "X-Cron-Token: testtoken" localhost:8000/api/v1/ops/cron/daily | jq .run_id # 期望一个 hex 串
# 限流
for i in 1 2 3 4; do
  curl -s -o /dev/null -w "$i: %{http_code}\n" -X POST localhost:8000/api/v1/wiki/extract/ \
    -H "Content-Type: application/json" -d '{"article_ids":[1]}'
done   # 期望前 3 次 2xx，第 4 次 429
```

---

## D6 — API 层 + OpenAPI

**前置阅读**：`docs/ARCHITECTURE.md` 第 4 节全文（尤其 4.1、4.2 的响应结构）

### Session Prompt

```
读 docs/ARCHITECTURE.md 第 4 节全文。

今天做 D6：把所有接口按契约表实现出来。响应结构必须和 4.1、4.2 节
给的 JSON 逐字段一致，前端就是照着这个写类型的。

1. serializers + filters + viewsets，逐个 app 实现契约表里的端点
   - ingest: RssSourceViewSet(list/create), RawArticleViewSet(list/retrieve)
     filters: source, extract_status, search(title)
   - wiki: EntityViewSet, ConceptViewSet, graph 端点, extract 端点
     ★ EntityDetailSerializer 必须产出 4.1 节那个嵌套结构：
       linkages[].direction / predicate / object{kind,id,name,...} /
       evidences[]{snippet,prompt_key,prompt_version,run_id,article{...}}
       出边入边合并到一个 linkages 数组，用 direction 区分
     ★ 必须 select_related/prefetch_related，用 assertNumQueries 卡住查询数 < 10
     graph 端点：按 ARCHITECTURE 4.2 输出，symbolSize 后端算好
       (min(60, 12 + value*2))，超 limit 时按 mention_count 取 Top-N 并置
       truncated=true
     extract 端点：走 DemoWriteThrottle，后台线程跑，返回 run_id
   - brief: list / latest / by-date
   - ops: runs list/retrieve(用 run_id 作 lookup_field)、stats
   - prompts: 只读 list，含当前版本全文

2. drf-spectacular
   给所有 viewset 加 @extend_schema，写清 summary 和 response
   /api/v1/docs/ 打开每个端点都要有描述，不能一片空白

3. 测试 tests/*/test_views.py
   每个端点至少一个用例。重点：
   - 词条详情的嵌套结构完整（断言 evidences[0] 里 prompt_version 和
     article.url 都在）
   - 词条详情的查询数 < 10（assertNumQueries）
   - graph 端点 truncated 逻辑
   - 筛选和搜索参数生效
   - 分页格式正确
   - 错误响应格式是 {"code":..., "detail":...}
```

### 完成判据

```bash
cd backend
pytest tests/ -q                                  # 全量全绿
python manage.py spectacular --file /tmp/schema.yml && echo "schema ok"
python manage.py runserver 8000 &
curl -s localhost:8000/api/v1/wiki/entities/ | jq '.count, .results[0].name'
ENTITY_ID=$(curl -s localhost:8000/api/v1/wiki/entities/ | jq -r '.results[0].id')
curl -s localhost:8000/api/v1/wiki/entities/$ENTITY_ID/ | jq '.linkages[0].evidences[0] | {snippet, prompt_key, prompt_version, run_id, article}'
# ★ 上面必须打印出完整的证据结构，任一字段为 null 都不算完成
curl -s "localhost:8000/api/v1/wiki/graph/?limit=50" | jq '.nodes | length, .links | length, .truncated'
curl -s localhost:8000/api/v1/ops/stats/ | jq .
```

---

## D7 — 机动日：补测试 + seed_demo

### Session Prompt

```
今天做 D7：补齐测试短板，并做出演示数据。

1. 跑 pytest --cov，找出覆盖薄弱的 service 函数，补测试。
   目标 60-80 个测试。不追覆盖率数字，追关键分支：
   每个 service 层函数的失败路径都要有用例。

2. apps/common/management/commands/seed_demo.py
   - 用真实 GLM 调用，跑通完整链路，产出 80-100 篇文章的抽取结果
     和至少 7 天的简报（按日期回填）
   - 把结果 dumpdata 成 fixture：backend/fixtures/demo.json
   - seed_demo 命令支持两种模式：
     --from-fixture（默认）：loaddata，不调 LLM，秒级完成
     --live：真跑 LLM 重新生成 fixture（本地用，线上不用）
   - fixture 提交进仓库（这是访客零成本浏览的基础）
   - fixture 里不能有任何密钥或个人信息

3. 检查 fixture 质量：
   - 实体数 >= 60，关系数 >= 80，简报 >= 7 天
   - 随机抽 5 条 Evidence，snippet 确实能在对应文章正文里找到
   - 没有明显的 LLM 幻觉（编造的公司名、不存在的产品）
   质量不行就调 prompt 重跑，这是访客第一眼看到的东西。

4. 补 tests/integration/test_e2e.py：
   全 mock LLM，从 RssSource 到 DailyBrief 跑通一遍编排，
   断言各模型都有数据、ExtractionRun 状态为 success。
```

### 完成判据

```bash
cd backend
pytest -q                                        # 60-80 个用例全绿
pytest --cov=apps --cov-report=term-missing | tail -30
python manage.py flush --noinput
python manage.py seed_demo                       # 秒级完成，不调 LLM
python manage.py shell -c "
from apps.wiki.models import Entity, Linkage, Evidence
from apps.brief.models import DailyBrief
print('entities:', Entity.objects.count())       # >= 60
print('linkages:', Linkage.objects.count())      # >= 80
print('evidences:', Evidence.objects.count())
print('briefs:', DailyBrief.objects.count())"    # >= 7
```

---

# Week 2 — 前端与上线

## D8 — 前端脚手架 + 布局 + API 层

**前置阅读**：`docs/ARCHITECTURE.md` 第 4、6 节；`CLAUDE.md` 的前端规范

### Session Prompt

```
读 docs/ARCHITECTURE.md 第 4 节（API 契约）和第 6 节（路由），
以及 CLAUDE.md 的前端编码规范。

今天做 D8：前端工程基座，不做具体页面内容。

1. Vite + Vue 3 + TS 脚手架，装 ant-design-vue、pinia、vue-router、
   axios、echarts、dayjs、marked
   配 vitest、eslint、prettier、sass

2. src/api/client.ts
   从旧项目的 frontend/src/api/client.ts 移植：
   axios 实例，baseURL 默认 '/api/v1'（可被 VITE_API_BASE 覆盖），
   响应拦截器把后端 {code, detail} 错误统一抛成带 code 的 Error

3. src/types/ 按 ARCHITECTURE 第 4 节的响应结构写全 TS 类型
   ★ 字段名保持 snake_case，与后端一致，不要转 camelCase
   重点写好 EntityDetail / LinkageWithEvidence / Evidence / GraphData

4. src/api/{ingest,wiki,brief,ops}.ts 每个端点一个函数，返回类型明确

5. src/composables/ 从旧项目移植 useApi.ts 和 usePolling.ts

6. 布局
   - components/AppHeader.vue + AppSider.vue（自己设计，不要照抄旧项目的
     企业风格；配色用一套中性的 tokens，深色侧边栏 + 浅色内容区）
   - layouts/DefaultLayout.vue
   - components/{EmptyState,ErrorState,LoadingPanel,DataTable}.vue
   - styles/tokens.scss 定义颜色/间距/圆角变量

7. router/index.ts 按 ARCHITECTURE 第 6 节配 5 条路由，
   每个页面先放占位组件，能点通导航即可

8. vite.config.ts 配 dev proxy：/api → http://localhost:8000

9. 一个 vitest 用例：测 client.ts 的错误拦截器能正确抛出带 code 的 Error
```

### 完成判据

```bash
cd frontend
npm install
npm run lint && npx vue-tsc --noEmit    # 零错误
npm run test                            # 通过
npm run build                           # 构建成功
npm run dev                             # 浏览器打开 localhost:5173
# 五个路由都能点通，侧边栏高亮正确，后端起着时 /api 代理通
```

---

## D9 — ★ 词条页 + 证据溯源（本项目的核心卖点）

**前置阅读**：`docs/PRD.md` 第 3.2 节、`docs/ARCHITECTURE.md` 第 4.1 节

### Session Prompt

```
读 docs/PRD.md 第 3.2 节（词条页验收标准）和 docs/ARCHITECTURE.md 第 4.1 节
（词条详情响应结构）。

今天做 D9：词条页。这是整个项目最重要的页面，是简历截图和演示视频的主角，
把设计做到位，不要糊。

1. views/wiki/EntityListView.vue（/wiki）
   - 实体卡片网格或列表，显示 name、类型 badge、mention_count、summary 截断
   - 顶部：搜索框 + 实体类型筛选 + 排序
   - 分页
   - 点击进详情

2. views/wiki/EntityDetailView.vue（/wiki/:id）★
   一次请求拿全数据（GET /api/v1/wiki/entities/{id}/），不要拆多个请求。
   - 头部区：实体名（大字号）、类型 badge、别名 tag 列表、AI 摘要、
     置信度、mention_count、首次/最近出现时间
   - 关系区：按 predicate 分组（components/LinkageGroup.vue）
     每组标题是谓词，下面列出该谓词下的所有关系
     每条关系一行：方向图标 + 对方名称（可点击跳转）+ 置信度
     ★ 每条关系可展开，展开后渲染 EvidenceCard
   - components/EvidenceCard.vue ★ 核心组件，必须显示全五项：
     * 原文片段（用引用块样式，左侧竖线，浅色底）
     * 来源：文章标题（外链，target=_blank）+ 发布时间 + 源站名
     * 置信度：进度条 + 数值
     * 抽取来源：prompt_key + v{version} 的 tag
     * run_id：截断显示前 8 位，可点击跳 /ops 并定位到该 run
   - 空状态：无关系时用 EmptyState，文案说明"该实体暂未抽取到关联关系"
   - 加载态：骨架屏，不要白屏
   - 错误态：404 时提示实体不存在并给返回列表的按钮

3. 设计要求
   证据卡片是这个项目的门面。要让人一眼看出"这条 AI 结论是有出处的"。
   建议：证据区用明显区别于正文的背景色，原文片段用等宽或衬线字体，
   来源链接带外链图标。整体克制，不要花哨。

4. 测试 vitest
   - EvidenceCard 渲染：给定 props 断言五项信息都出现在 DOM 里
   - LinkageGroup 分组逻辑正确
   - EntityDetailView：mock API，断言空状态和正常态渲染
```

### 完成判据

```bash
cd frontend && npm run test && npx vue-tsc --noEmit
# 手动验收（后端需已 seed_demo）：
# 1. 打开 /wiki，能看到实体列表，搜索和筛选生效
# 2. 点进任一实体，能看到关系按谓词分组
# 3. 展开任一关系，五项信息全部可见：
#    原文片段 / 来源标题+链接+时间 / 置信度 / prompt key+版本 / run_id
# 4. 点来源链接能打开原文
# 5. 点 run_id 能跳到 /ops
# 6. 找一个没有关系的实体，确认空状态正常
```

> 这一天做完请截图存档，D13 写 README 和 D14 录演示时要用。

---

## D10 — 关系图谱 + 今日简报页

**前置阅读**：`docs/PRD.md` 第 3.1、3.3 节；`docs/ARCHITECTURE.md` 第 4.2 节

### Session Prompt

```
读 docs/PRD.md 第 3.1、3.3 节和 docs/ARCHITECTURE.md 第 4.2 节。

今天做 D10：图谱页和简报首页。

1. views/wiki/GraphView.vue（/graph）
   - components/GraphChart.vue 封装 ECharts graph 力导向图
     后端返回的数据结构已经对齐 ECharts 格式，直接喂，不要在前端转换
     配置：roam 缩放拖拽、label 显示节点名、力导向参数调到不乱飞
     categories 决定节点颜色，图例可点击筛选
   - 顶部筛选：实体类型多选、概念 namespace 多选、节点数上限滑块
   - 边 hover 显示 predicate（tooltip formatter）
   - 点击节点 → router.push(`/wiki/${id}`)（注意剥掉 id 的 e/c 前缀，
     concept 节点跳概念详情或不跳，二选一并保持一致）
   - truncated 为 true 时在右上角提示"仅显示关系最多的 N 个节点"
   - 组件销毁时 dispose ECharts 实例，避免内存泄漏
   - 窗口 resize 时 chart.resize()

2. views/brief/BriefView.vue（/，首页）
   - GET /api/v1/brief/latest/
   - marked 渲染 content_md
   - ★ 把正文里的 [n] 角标替换成可点击的锚点，点击滚动到底部对应引用
     实现：渲染后用正则替换 [n] 为 <a href="#cite-n" class="cite">[n]</a>
     ★ 必须对 marked 输出做 XSS 处理（用 DOMPurify 或 marked 的 sanitize 选项）
   - 底部参考文献列表：编号 + 标题（外链）+ 源站 + 发布时间，id="cite-n"
   - 顶部元信息："由 {model_name} 于 {created_at} 自动生成"
   - 日期切换：能查看历史简报（简单的日期下拉或前后翻页）
   - 无数据时 EmptyState

3. 测试
   - 角标替换逻辑单测（输入含 [1][3] 的 md，断言输出含对应锚点）
   - XSS：喂一段含 <script> 的 content_md，断言被清理
   - GraphChart：mock echarts，断言 setOption 被调用且数据结构正确
```

### 完成判据

```bash
cd frontend && npm run test && npx vue-tsc --noEmit
# 手动验收：
# 1. /graph 图能渲染，节点不重叠成一团，能缩放拖拽
# 2. 筛选实体类型，图实时更新
# 3. 点节点跳词条页
# 4. 首页简报正文渲染正常，点 [1] 滚动到底部第 1 条引用
# 5. 点引用条目能打开原文
# 6. 切换到历史日期能看到往期简报
```

---

## D11 — 流水线面板 + Prompt 只读展示

**前置阅读**：`docs/PRD.md` 第 3.4 节；`docs/ARCHITECTURE.md` 第 3.3 节的 `step_metrics` 结构

### Session Prompt

```
读 docs/PRD.md 第 3.4 节和 docs/ARCHITECTURE.md 第 3.3 节。

今天做 D11：流水线可观测面板。这一页是给面试官看"我懂 AI 工程"的。

1. views/ops/OpsView.vue（/ops）
   - 顶部四张聚合卡片（GET /api/v1/ops/stats/）：
     近 7 天 run 数 / 成功率 / 总 token / 总成本（人民币）
   - run 列表表格：run_id(前 8 位) / 开始时间 / 触发方式 / 状态 badge /
     耗时 / token / 成本 / 产出数量（实体+概念+关系）
   - 行可展开 → components/RunDetail.vue
     按 step_metrics 的六个固定步骤渲染一条时间线：
     ingest → extract_entities → extract_concepts → extract_linkages
     → persist → brief
     每步显示：状态图标、耗时、token（有的话）、产出数量、重试次数
     失败的步骤展开 error_message（等宽字体，可复制）
     未执行的步骤置灰
   - 状态 badge 配色：success 绿 / partial 橙 / failed 红 / running 蓝+转圈
   - running 状态的 run 用 usePolling 每 3 秒刷新，结束后停止轮询

2. Prompt 版本区（同页下方或独立 tab）
   - GET /api/v1/prompts/
   - 列出四个 prompt：key / name / 当前版本号 / 更新时间
   - 点击展开显示模板全文（只读，等宽字体，可折叠）
   - 明确标注"只读展示"，不提供编辑入口

3. 从词条页跳过来时（带 run_id 的 query 或 hash），自动展开对应 run

4. 测试
   - RunDetail：给一个含失败步骤的 step_metrics，断言渲染出 error_message
     且未执行的步骤置灰
   - 轮询：running 状态启动轮询，success 后停止
```

### 完成判据

```bash
cd frontend && npm run test && npx vue-tsc --noEmit
# 手动验收：
# 1. /ops 打开能看到聚合卡片有真实数字
# 2. 至少一条 run 记录，展开后六个步骤的耗时和 token 都有值
# 3. 从词条页点 run_id 跳过来，对应 run 自动展开
# 4. Prompt 区能看到四个 prompt 的全文和版本号
# 5. 触发一次实时抽取，run 状态从 running 轮询变到 success
```

---

## D12 — 上线部署

**前置阅读**：`docs/DEPLOYMENT.md` 全文

### Session Prompt

```
读 docs/DEPLOYMENT.md 全文，按 runbook 逐步执行。

今天做 D12：上线到腾讯云香港 VPS。

1. 准备部署产物
   - deploy/Caddyfile
   - deploy/docker-compose.prod.yml（caddy + web + db）
   - Dockerfile 多阶段构建：前端 build 产物拷进后端镜像的 static 目录，
     或独立挂载给 Caddy（二选一，DEPLOYMENT.md 里选定的方案）
   - .github/workflows/deploy.yml：CI 通过后 SSH 到 VPS 拉取并重启
   - .github/workflows/cron-daily.yml：每天 00:00 UTC（北京 08:00）
     curl 打 cron 端点，token 从 secrets 读

2. 按 DEPLOYMENT.md 的清单在 VPS 上执行（这部分需要用户配合提供
   服务器 IP、SSH 凭据、域名）。逐步骤确认，不要一次性跑一大堆命令。

3. 上线后逐条验收（见下方判据）

4. ★ 国内访问实测
   用 ITDOG 或类似工具测各省访问速度，记录结果。
   同时按 DEPLOYMENT.md 的备选方案把前端也发一份到 Cloudflare Pages，
   对比两者国内速度，用数据决定最终方案，把结论写进 DEPLOYMENT.md。

注意：涉及服务器的操作先说明要做什么再执行，不要自作主张改防火墙规则
或删除文件。
```

### 完成判据

```bash
# 域名替换成实际的
DOMAIN=news-wiki.example.com
curl -sI https://$DOMAIN | head -3                      # 200 + HTTPS
curl -s https://$DOMAIN/api/v1/health/ | jq .           # {"status":"ok","db":"ok"}
curl -s https://$DOMAIN/api/v1/brief/latest/ | jq .title
curl -s https://$DOMAIN/api/v1/wiki/entities/ | jq .count   # > 0
curl -s -o /dev/null -w "%{http_code}\n" https://$DOMAIN/api/v1/docs/   # 200
curl -s -X POST -H "X-Cron-Token: $CRON_TOKEN" https://$DOMAIN/api/v1/ops/cron/daily | jq .run_id
# 证书自动签发验证
echo | openssl s_client -connect $DOMAIN:443 2>/dev/null | openssl x509 -noout -dates
# GitHub Actions：手动触发一次 cron-daily workflow，确认绿灯
# 手机 4G 打开 https://$DOMAIN，首屏 3 秒内出内容
```

---

## D13 — README + 简历话术

**前置阅读**：`docs/DECISIONS.md`、`docs/RESUME.md`

### Session Prompt

```
读 docs/DECISIONS.md 和 docs/RESUME.md。

今天做 D13：把仓库门面做出来。README 是面试官看的第一眼，
质量直接决定他会不会点进代码。

1. README.md 结构（中文为主，顶部加英文摘要段）
   - 一句话定位 + 在线地址 + 演示 GIF（放最上面）
   - 核心特性：4 条，每条配一张截图
     ★ 证据溯源那条放词条页展开证据的截图，这是最有说服力的
   - 架构图（mermaid，GitHub 原生渲染）：数据流那张
   - 技术栈表格
   - 快速开始：docker compose up 三行命令跑起来
   - ★「设计取舍」章节：从 DECISIONS.md 挑 5 条最有料的展开写
     （为什么砍 Playwright、为什么不用 Celery、怎么约束 LLM 输出、
       怎么做证据溯源、怎么控制演示成本）
     这一章是简历项目和玩具项目的分水岭，好好写
   - 项目结构树
   - 测试与 CI 说明
   - LICENSE

2. 演示素材
   - 录 GIF：首页简报 → 点角标 → 进词条页 → 展开证据 → 跳 /ops 看 run
     用 ScreenToGif 或 LICEcap，控制在 15 秒内、5MB 以内
   - 关键页面截图放 docs/images/

3. 补完 docs/RESUME.md：
   按实际做出来的东西修订简历条目和面试问答稿，把真实数字填进去
   （实体数、关系数、测试数、抽取耗时、单次成本等）

4. GitHub 仓库设置
   - About 填一句话描述 + 在线地址
   - Topics: llm, knowledge-graph, django, vue3, information-extraction, rss
   - 确认 .env 不在仓库里
```

### 完成判据

```bash
cd D:/Claude/demo/news-wiki
bash scripts/check-clean.sh           # ★ 必须全部 PASS
ls docs/images/                       # 至少 4 张截图 + 1 个 gif
# README 在 GitHub 上预览：mermaid 图能渲染、GIF 能播、所有链接可点
```

---

## D14 — 打磨 + 演示录制

### Session Prompt

```
今天做 D14：收尾。

1. 全站走查，修 bug
   - 每个页面的加载态 / 空态 / 错误态都试一遍
   - 移动端响应式：手机上打开各页面不横向滚动、图谱页可用
   - 控制台零 error、零 warning
   - 慢网络下（DevTools 限速 Slow 3G）页面不白屏

2. 性能
   - Lighthouse 跑一遍，性能分 > 80
   - 前端产物体积检查，ECharts 用按需引入，别整包打进去

3. 最终验收：把 D1-D13 所有完成判据重跑一遍，全绿

4. 录 30 秒演示视频（简历/求职信里可以放链接）：
   讲清三件事——它做什么、证据溯源怎么体现、AI 工程怎么做的

5. 在 docs/BACKLOG.md 里记下所有"想做但没做"的东西
   （面试被问"还能怎么改进"时直接答）
```

### 完成判据

```bash
cd backend && pytest -q
cd frontend && npm run test && npm run build && npx vue-tsc --noEmit
# 线上全站点一遍，控制台无 error
# Lighthouse 性能分 > 80
# D1-D13 的判据命令全部重跑通过
```

---

## 延期应对

时间不够时按此顺序砍，**从下往上**：

| 优先级 | 内容 | 可否砍 |
|---|---|---|
| 1 | 词条页 + 证据溯源（D9） | **绝不能砍**，砍了项目就没卖点 |
| 2 | 三步抽取管线（D4） | 可降级为 entity + concept 两步 |
| 3 | 今日简报（D5/D10） | 可降级为不带引用角标的纯摘要 |
| 4 | 流水线面板（D11） | 可降级为只有聚合卡片、无分步详情 |
| 5 | 关系图谱可视化（D10） | 可降级为实体列表 + 关系表格 |

**D12 上线不可延期。** 一个能打开的 80 分项目，远胜一个跑在本地的 100 分项目。
