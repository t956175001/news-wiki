"""Decide whether a feed item is about AI before we spend a page fetch on it.

Most usable Chinese feeds are general tech publications, not AI desks: 量子位 is
pure AI, but IT 之家 and 钛媒体 publish everything from phone launches to
earnings. Feeding all of that to the extraction pipeline would fill the wiki
with entries nobody came here for, and would burn tokens doing it.

Deliberately a keyword list, not a classifier. The judgement being made is
"was this article filed under AI", which the headline almost always answers
outright; a model here would be a second LLM call per item, on the cheapest
decision in the pipeline, in exchange for failure modes that are harder to
explain than a missing word.
"""

import logging
from urllib.parse import urlparse

from django.conf import settings

logger = logging.getLogger(__name__)

# Sites whose entire output is AI coverage. Checked before the keyword list so
# a piece like 「OpenClaw 拿下 20 亿融资」— unmistakably on-topic to a reader,
# with no keyword in the headline — is not thrown away.
ALWAYS_RELEVANT_HOSTS = frozenset(
    {
        "qbitai.com",
        "jiqizhixin.com",
        "syncedreview.com",
    }
)

# Matched case-insensitively as substrings against title + summary. Chinese has
# no word boundaries, and the Latin terms here (GPT, LLM, RAG…) appear inside
# product names often enough that whole-word matching would lose more than it
# saves. False positives cost one page fetch; false negatives lose an article.
AI_KEYWORDS: tuple[str, ...] = (
    # 中文 · 领域
    "人工智能",
    "机器学习",
    "深度学习",
    "神经网络",
    "自然语言",
    "计算机视觉",
    "语音识别",
    "知识图谱",
    "强化学习",
    "具身智能",
    "通用人工智能",
    # 中文 · 模型与产品
    "大模型",
    "语言模型",
    "多模态",
    "生成式",
    "智能体",
    "开源模型",
    "推理模型",
    "文生图",
    "文生视频",
    "自动驾驶",
    "机器人",
    "算力",
    # Qualified rather than bare "芯片": a memory-chip IPO is not AI news, and
    # on a general feed that is most of what bare 芯片 brings in. The AI angle
    # is covered by these plus 算力 / 英伟达 / gpu.
    "ai 芯片",
    "ai芯片",
    "算力芯片",
    "训练",
    "微调",
    "提示词",
    "幻觉",
    # English
    "artificial intelligence",
    " ai ",
    "ai:",
    "agi",
    "llm",
    "gpt",
    "transformer",
    "diffusion",
    "multimodal",
    "embedding",
    "fine-tun",
    "inference",
    "neural",
    "machine learning",
    "deep learning",
    "generative",
    "chatbot",
    "copilot",
    "agent",
    # Padded: unpadded "rag" is a substring of "fragment", "fragrance", …
    " rag ",
    "gpu",
    "cuda",
    "tensor",
    # 主要厂商与模型家族
    "openai",
    "anthropic",
    "claude",
    "chatgpt",
    "gemini",
    "deepseek",
    "qwen",
    "通义",
    "文心",
    "豆包",
    "kimi",
    "智谱",
    # 月之暗面 is deliberately absent: it is also an ordinary Chinese phrase
    # ("dark side of the moon"), and a real sweep pulled in a pair of headphones
    # named after it. "kimi" is how the company's product is actually referred
    # to in coverage.
    "英伟达",
    "nvidia",
    "huggingface",
    "hugging face",
    "midjourney",
    "stable diffusion",
    "llama",
    "mistral",
)


def _host(url: str) -> str:
    """Registrable-ish host: `www.qbitai.com` → `qbitai.com`."""
    netloc = urlparse(url).netloc.lower()
    host = netloc.split("@")[-1].split(":")[0]
    return host[4:] if host.startswith("www.") else host


def is_ai_related(title: str, summary: str = "", url: str = "") -> bool:
    """True when this item should be ingested.

    `url` is optional and only consulted for the always-relevant host check, so
    callers that only have a headline can still use this.
    """
    if not settings.INGEST_TOPIC_FILTER:
        return True

    if url and _host(url) in ALWAYS_RELEVANT_HOSTS:
        return True

    # Padded so the ` ai ` keyword can match a title that starts or ends with
    # it, without also matching the "ai" inside "said" or "chain".
    haystack = f" {title} {summary} ".lower()
    return any(keyword in haystack for keyword in AI_KEYWORDS)
