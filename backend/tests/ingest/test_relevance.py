"""The AI-topic filter that runs between the feed and the article fetch."""

import pytest

from apps.ingest.services.relevance import ALWAYS_RELEVANT_HOSTS, is_ai_related


@pytest.fixture(autouse=True)
def filter_on(settings):
    settings.INGEST_TOPIC_FILTER = True


@pytest.mark.parametrize(
    "title",
    [
        "智谱发布新一代大模型，推理成本降低 40%",
        "英伟达最新显卡在深度学习训练上的实测",
        "国内首个具身智能机器人量产下线",
        "多模态生成式模型在文生视频上的进展",
    ],
)
def test_chinese_ai_headlines_pass(title):
    assert is_ai_related(title) is True


@pytest.mark.parametrize(
    "title",
    [
        "OpenAI ships a new reasoning model",
        "Benchmarking LLM inference on consumer GPUs",
        "Hugging Face releases a multimodal dataset",
    ],
)
def test_english_ai_headlines_pass(title):
    assert is_ai_related(title) is True


@pytest.mark.parametrize(
    "title",
    [
        "某新能源车企公布第三季度交付量",
        "国庆档票房破纪录，观影人次同比增长",
        "本周股市收评：三大指数集体收涨",
    ],
)
def test_off_topic_headlines_are_rejected(title):
    assert is_ai_related(title) is False


def test_the_summary_counts_when_the_title_alone_is_vague():
    assert is_ai_related("一次值得记录的发布会", "会上公布了新的大模型定价") is True


def test_matching_ignores_case():
    assert is_ai_related("OPENAI announces GPT-6") is True
    assert is_ai_related("openai announces gpt-6") is True


def test_a_pure_ai_site_bypasses_the_keyword_list():
    """量子位 files nothing but AI; a keyword-free headline there is still AI."""
    off_topic_looking = "这家公司刚刚拿下 20 亿融资"

    assert is_ai_related(off_topic_looking) is False
    assert is_ai_related(off_topic_looking, url="https://www.qbitai.com/2026/08/1.html") is True


def test_the_www_prefix_does_not_defeat_the_host_check():
    assert "qbitai.com" in ALWAYS_RELEVANT_HOSTS
    bare = is_ai_related("随便一条标题", url="https://qbitai.com/x")
    prefixed = is_ai_related("随便一条标题", url="https://www.qbitai.com/x")

    assert bare is True
    assert prefixed is True


def test_a_lookalike_domain_does_not_inherit_the_bypass():
    """`notqbitai.com` must not match `qbitai.com` by suffix."""
    assert is_ai_related("随便一条标题", url="https://notqbitai.com/x") is False


def test_the_bare_ai_token_does_not_match_ordinary_words():
    """` ai ` is padded precisely so 'said'/'chain'/'maintain' do not trigger."""
    assert is_ai_related("He said the chain will maintain its prices") is False
    assert is_ai_related("AI is eating the world") is True


@pytest.mark.parametrize(
    "title",
    [
        # All four were pulled in by a real sweep on 2026-08-31 and are the
        # reason the keyword list no longer carries bare 芯片/显卡/月之暗面.
        "存储芯片厂商江波龙拟香港上市，融资不超过 62.8 亿港元",
        "消息称长鑫存储开始试产 HBM3E 内存，有望数周内大规模量产",
        "水月雨「月之暗面」平面磁式头戴式耳机 9 月 2 日发售",
        "vivo OriginOS 7 系统重构渲染管线和编译框架",
    ],
)
def test_headlines_that_only_look_like_ai_are_rejected(title):
    assert is_ai_related(title) is False


def test_chips_still_count_when_the_headline_says_they_are_ai_chips():
    assert is_ai_related("华为发布新一代 AI 芯片，算力提升三倍") is True
    assert is_ai_related("英伟达下一代数据中心平台曝光") is True


def test_rag_does_not_match_words_that_merely_contain_it():
    assert is_ai_related("A fragment of a fragrance brand's storage strategy") is False
    assert is_ai_related("Building a RAG pipeline over internal docs") is True


def test_turning_the_filter_off_lets_everything_through(settings):
    settings.INGEST_TOPIC_FILTER = False

    assert is_ai_related("国庆档票房破纪录") is True
