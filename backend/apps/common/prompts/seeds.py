"""Initial prompt texts, loaded into the DB as version 1 by migration 0002.

The full text of every prompt lives here and in `docs/PROMPTS.md` — nowhere
else. Application code only ever looks prompts up by key.

Placeholders are `str.format` style: `{raw_text}` is a variable, `{{` and `}}`
are literal braces (the JSON skeletons in the prompt bodies rely on this).

Editing a text below does **not** change an already-migrated database. Tuning a
prompt means adding a new `PromptVersion`, never rewriting v1 in place —
otherwise "this entry was extracted by v1" stops being true.
"""

PROMPT_SEEDS: list[dict[str, str]] = [
    {
        "key": "wiki.extract_entities",
        "name": "实体抽取",
        "description": "三步抽取第一步：从语料中抽出具体实体。",
        "text": """你是一个信息抽取引擎。从下面的资讯语料中抽取出所有**具体实体**。

## 什么算实体
实体是客观存在的具体对象，必须是文中明确提到的专有名词。类型限定为：
- person：人物，如 "Sam Altman"
- org：组织机构、公司，如 "OpenAI"、"清华大学"
- product：产品、服务，如 "ChatGPT"、"Copilot"
- model：具体的模型，如 "GPT-5"、"Claude Opus 5"、"DeepSeek-V4"
- tech：具体的技术方案或框架，如 "Transformer"、"vLLM"
- event：具名事件，如 "NeurIPS 2026"
- other：以上都不属于但确为专有名词

## 不算实体（不要抽）
- 抽象概念、趋势、方法论（如"多模态"、"AI 监管"）——这些留给下一步
- 泛指的普通名词（如"大模型"、"这家公司"）
- 文中未出现、需要你补充背景知识才知道的东西

## 输出要求
严格输出如下 JSON，不要任何额外文字或 Markdown 代码块：

{{
  "entities": [
    {{
      "name": "实体的规范名称",
      "type": "person|org|product|model|tech|event|other",
      "aliases": ["文中出现的其他叫法"],
      "summary": "基于本语料的一句话说明，不超过 50 字",
      "confidence": 0.95,
      "evidence": "原文中提到该实体的连续片段，原样复制，不超过 200 字",
      "raw_article_id": 42
    }}
  ]
}}

## 硬性约束
1. `evidence` 必须是原文的**连续片段**，逐字复制。不得改写、不得拼接不相邻的句子。
2. `raw_article_id` 必须是该 evidence 所在文章的 ARTICLE_ID，不得编造。
3. 同一实体在多篇文章出现时，只输出一次，evidence 取最具代表性的一处。
4. 宁缺勿滥。不确定的实体不要抽，或给低 confidence。
5. 如果语料中没有任何实体，输出 {{"entities": []}}。

## 语料
{raw_text}
""",
    },
    {
        "key": "wiki.extract_concepts",
        "name": "概念抽取",
        "description": "三步抽取第二步：抽取抽象概念，入参带上第一步结果以避免重复。",
        "text": """你是一个信息抽取引擎。从下面的资讯语料中抽取出**抽象概念**。

## 什么算概念
概念是抽象的主题、技术路线、趋势或议题，不是具体的专有名词。用 namespace 分类：
- technique：技术方法与路线，如 "混合专家模型"、"推理时扩展"、"强化学习微调"
- trend：行业趋势，如 "模型小型化"、"AI 应用商业化"
- policy：政策与监管议题，如 "AI 安全监管"、"数据合规"
- market：市场与商业议题，如 "算力供给紧张"、"融资热潮"
- other：以上都不属于

## 已抽取的实体（不要重复抽成概念）
{entities_json}

## 输出要求
严格输出如下 JSON，不要任何额外文字或 Markdown 代码块：

{{
  "concepts": [
    {{
      "name": "概念名称，用中文，简洁准确",
      "namespace": "technique|trend|policy|market|other",
      "definition": "基于本语料的一句话定义，不超过 60 字",
      "signals": ["文中指向该概念的关键词"],
      "confidence": 0.9,
      "evidence": "原文中体现该概念的连续片段，原样复制，不超过 200 字",
      "raw_article_id": 42
    }}
  ]
}}

## 硬性约束
1. `evidence` 必须是原文的连续片段，逐字复制。
2. `raw_article_id` 必须是该 evidence 所在文章的 ARTICLE_ID，不得编造。
3. 不要把上面已列出的实体重复抽成概念。
4. 概念要有实质内容。不要抽"人工智能"、"技术"这类过于宽泛的词。
5. 每篇文章的概念控制在 3 个以内，全部语料不超过 15 个。
6. 如果没有值得抽取的概念，输出 {{"concepts": []}}。

## 语料
{raw_text}
""",
    },
    {
        "key": "wiki.extract_linkages",
        "name": "关系抽取",
        "description": "三步抽取第三步：抽取实体之间、实体与概念之间的关系三元组。",
        "text": """你是一个信息抽取引擎。从下面的资讯语料中抽取**关系三元组**。

## 可用的实体
{entities_json}

## 可用的概念
{concepts_json}

## 关系格式
每条关系是 (subject, predicate, object)：
- `subject` 必须是上面「可用的实体」中的某个 name，逐字一致
- `object` 必须是上面「可用的实体」或「可用的概念」中的某个 name，逐字一致
- `object_type` 标明 object 来自实体还是概念

## 谓词用词规范
用简洁的中文动词，优先使用以下词表；表中没有合适的再自拟（2-4 个字）：
发布 / 收购 / 投资 / 合作 / 竞争 / 采用 / 支持 / 基于 / 属于 / 隶属 /
任职 / 离职 / 开源 / 集成 / 超越 / 替代 / 依赖 / 涉及 / 应用于 / 反对

## 输出要求
严格输出如下 JSON，不要任何额外文字或 Markdown 代码块：

{{
  "linkages": [
    {{
      "subject": "OpenAI",
      "predicate": "发布",
      "object_type": "entity",
      "object": "GPT-5",
      "confidence": 0.95,
      "evidence": "原文中体现该关系的连续片段，原样复制，不超过 200 字",
      "raw_article_id": 42
    }}
  ]
}}

## 硬性约束
1. `subject` 和 `object` 必须**逐字**来自上面给出的实体/概念列表。不在列表里的一律不要输出。
2. `object_type` 只能是 "entity" 或 "concept"，必须与 object 的实际来源一致。
3. `evidence` 必须是原文的连续片段，且该片段必须**同时**提到 subject 和 object（或明确指代）。做不到就不要输出这条关系。
4. `raw_article_id` 必须是该 evidence 所在文章的 ARTICLE_ID，不得编造。
5. 不要输出自反关系（subject 和 object 相同）。
6. 不要编造语料中没有明说的关系。推测出来的关系一律不要。
7. 如果没有可靠的关系，输出 {{"linkages": []}}。

## 语料
{raw_text}
""",
    },
    {
        "key": "brief.daily",
        "name": "每日简报",
        "description": "把当日抽取结果写成带引用角标的简报。",
        "text": """你是一名 AI 领域的资讯编辑。根据下面的素材，写一份当日 AI 资讯简报。

## 日期
{date}

## 素材文章
{articles_json}

## 当日抽取到的重点实体
{entities_json}

## 当日抽取到的重点关系
{linkages_json}

## 写作要求
1. 开头一段（80-120 字）概括当日最值得关注的动向。
2. 之后分 3-5 个小节，每节一个主题，用 `## 小标题` 分隔。
3. 每个小节 100-200 字，聚焦事实，不要空泛评论。
4. **每一个来自素材的事实性陈述，句尾必须标注引用角标**，格式为 `[n]`，n 是素材文章的序号。一句话涉及多篇就写 `[1][3]`。
5. 不要编造素材中没有的信息。宁可少写，不要凑字数。
6. 全文用中文，语气客观克制，不用"令人震撼""颠覆性"这类营销词。

## 输出要求
严格输出如下 JSON，不要任何额外文字或 Markdown 代码块：

{{
  "title": "简报标题，不超过 30 字",
  "content_md": "Markdown 正文，含 [n] 角标",
  "used_indexes": [1, 2, 3]
}}

`used_indexes` 列出正文中实际引用过的素材序号。
""",
    },
]
