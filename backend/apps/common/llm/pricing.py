"""Token counts to CNY. Feeds `ExtractionRun.cost_cny` and the budget guard.

PRICES ARE A DEFAULT, NOT A SOURCE OF TRUTH — 以官网为准
(https://open.bigmodel.cn/pricing). The provider changes them, and GLM's
flagship models are billed in tiers keyed on prompt length, which a flat
per-1k table cannot express. The numbers below are the base tier; when they
drift, override without touching code:

    LLM_PRICE_GLM_4_7=0.005,0.005     # <input per 1k>,<output per 1k>, CNY

Decimal, not float, all the way through: `ExtractionRun.cost_cny` is a
`DecimalField(max_digits=10, decimal_places=4)` and money that rounds twice is
money that stops reconciling.
"""

import logging
import os
import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

logger = logging.getLogger(__name__)

# CNY per 1000 tokens, as (input, output). Strings, so no float ever gets near
# the Decimal constructor.
DEFAULT_PRICES: dict[str, tuple[str, str]] = {
    # GLM-4.7 is tier-priced by prompt *and* completion length; this is the
    # previous generation's flat rate used as a stand-in. Confirm on the pricing
    # page and override via env before quoting real costs to anyone.
    "glm-4.7": ("0.005", "0.005"),
    "glm-4.6": ("0.005", "0.005"),
}

QUANTUM = Decimal("0.0001")  # matches decimal_places=4 on ExtractionRun.cost_cny

_ENV_PREFIX = "LLM_PRICE_"
_NON_ALNUM = re.compile(r"[^A-Z0-9]+")

# Warn once per unpriced model instead of once per call.
_warned_models: set[str] = set()


def _env_name(model: str) -> str:
    """`glm-4.7` -> `LLM_PRICE_GLM_4_7`."""
    return _ENV_PREFIX + _NON_ALNUM.sub("_", model.upper()).strip("_")


def _parse_override(raw: str, model: str) -> tuple[Decimal, Decimal] | None:
    parts = [part.strip() for part in raw.split(",")]
    if len(parts) != 2:
        logger.warning("Ignoring %s=%r: expected '<input>,<output>'", _env_name(model), raw)
        return None
    try:
        prices = (Decimal(parts[0]), Decimal(parts[1]))
    except InvalidOperation:
        logger.warning("Ignoring %s=%r: not two decimal numbers", _env_name(model), raw)
        return None
    if prices[0] < 0 or prices[1] < 0:
        logger.warning("Ignoring %s=%r: prices cannot be negative", _env_name(model), raw)
        return None
    return prices


def get_prices(model: str) -> tuple[Decimal, Decimal] | None:
    """CNY per 1k tokens as `(input, output)`, or None if the model is unpriced.

    An environment override wins over the built-in table, including for models
    the table has never heard of.
    """
    key = model.strip().lower()

    raw = os.environ.get(_env_name(key), "").strip()
    if raw:
        override = _parse_override(raw, key)
        if override is not None:
            return override

    listed = DEFAULT_PRICES.get(key)
    if listed is None:
        return None
    return Decimal(listed[0]), Decimal(listed[1])


def estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> Decimal:
    """Cost of one call in CNY, rounded to 4 decimal places.

    An unpriced model yields 0 rather than raising: a stale price table is a
    reporting gap, and failing the whole extraction over it would turn a cosmetic
    problem into a data-loss one. The warning is the signal to update the table.
    """
    prices = get_prices(model)
    if prices is None:
        if model not in _warned_models:
            _warned_models.add(model)
            logger.warning(
                "No price for model %r; reporting its cost as 0. Add it to DEFAULT_PRICES or set %s.",
                model,
                _env_name(model),
            )
        return Decimal("0").quantize(QUANTUM)

    input_price, output_price = prices
    billed = Decimal(max(prompt_tokens, 0)) * input_price + Decimal(max(completion_tokens, 0)) * output_price
    return (billed / 1000).quantize(QUANTUM, rounding=ROUND_HALF_UP)
