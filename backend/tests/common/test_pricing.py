"""Pricing tests.

These pin the arithmetic and the override mechanism, not the price list itself —
the numbers in `DEFAULT_PRICES` are expected to drift with the provider's
pricing page, and a test that asserted them would just have to be edited too.
"""

from decimal import Decimal

import pytest

from apps.common.llm import pricing
from apps.common.llm.pricing import estimate_cost, get_prices


@pytest.fixture(autouse=True)
def _forget_warned_models():
    pricing._warned_models.clear()
    yield
    pricing._warned_models.clear()


def test_cost_is_input_and_output_priced_separately(monkeypatch):
    monkeypatch.setitem(pricing.DEFAULT_PRICES, "test-model", ("0.002", "0.008"))

    # 10k prompt at 0.002/1k = 0.02; 2k completion at 0.008/1k = 0.016
    assert estimate_cost("test-model", 10_000, 2_000) == Decimal("0.0360")


def test_cost_of_the_configured_default_model():
    input_price, output_price = get_prices("glm-4.7")
    expected = (Decimal(10_000) * input_price + Decimal(2_000) * output_price) / 1000

    assert estimate_cost("glm-4.7", 10_000, 2_000) == expected.quantize(Decimal("0.0001"))


def test_zero_tokens_cost_nothing():
    assert estimate_cost("glm-4.7", 0, 0) == Decimal("0.0000")


def test_result_is_quantized_to_four_places(monkeypatch):
    monkeypatch.setitem(pricing.DEFAULT_PRICES, "test-model", ("0.000123456", "0"))

    cost = estimate_cost("test-model", 1000, 0)

    # 0.000123456 rounds half-up to 0.0001, and the exponent matches
    # ExtractionRun.cost_cny's decimal_places=4.
    assert cost == Decimal("0.0001")
    assert cost.as_tuple().exponent == -4


def test_rounding_is_half_up(monkeypatch):
    monkeypatch.setitem(pricing.DEFAULT_PRICES, "test-model", ("0.00015", "0"))

    assert estimate_cost("test-model", 1000, 0) == Decimal("0.0002")


def test_model_lookup_is_case_insensitive():
    assert get_prices("GLM-4.7") == get_prices("glm-4.7")


def test_an_unpriced_model_costs_zero_instead_of_raising(caplog):
    # A stale price table is a reporting gap; it must not fail an extraction.
    cost = estimate_cost("some-unlisted-model", 5_000, 1_000)

    assert cost == Decimal("0.0000")
    assert "No price for model" in caplog.text


def test_the_unpriced_warning_is_logged_once_per_model(caplog):
    estimate_cost("some-unlisted-model", 1, 1)
    estimate_cost("some-unlisted-model", 1, 1)

    assert caplog.text.count("No price for model") == 1


def test_an_env_override_replaces_the_table(monkeypatch):
    monkeypatch.setenv("LLM_PRICE_GLM_4_7", "1,2")

    assert get_prices("glm-4.7") == (Decimal("1"), Decimal("2"))
    assert estimate_cost("glm-4.7", 1000, 1000) == Decimal("3.0000")


def test_an_env_override_can_price_a_model_the_table_never_heard_of(monkeypatch):
    monkeypatch.setenv("LLM_PRICE_BRAND_NEW_MODEL", "0.01,0.02")

    assert estimate_cost("brand.new-model", 1000, 1000) == Decimal("0.0300")


@pytest.mark.parametrize("raw", ["", "0.01", "0.01,0.02,0.03", "cheap,free", "-1,2"])
def test_a_malformed_override_is_ignored(monkeypatch, raw):
    monkeypatch.setenv("LLM_PRICE_GLM_4_7", raw)

    assert get_prices("glm-4.7") == (
        Decimal(pricing.DEFAULT_PRICES["glm-4.7"][0]),
        Decimal(pricing.DEFAULT_PRICES["glm-4.7"][1]),
    )


def test_negative_token_counts_do_not_produce_a_credit():
    assert estimate_cost("glm-4.7", -100, -100) == Decimal("0.0000")
