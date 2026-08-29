"""Schema validation for the three extraction steps.

Authoritative rules: the 「校验规则」 table in `docs/PROMPTS.md`. Two failure
modes, and keeping them apart is the whole point of this module:

* **`SchemaError`** — the payload's *shape* is wrong (missing root key, missing
  required field, a field of the wrong type). The model is not following the
  contract, so the pipeline retries the call. Cheap to retry, likely to help.
* **skip** — one item is individually unusable (it cites an article that was not
  in this batch, or names an entity that was never extracted) while the rest are
  fine. Retrying would produce the same garbage, so the item is dropped, counted
  in the returned stats, and the run carries on.

Rule of thumb behind the split: a *type* error raises, a *value* error skips.
`confidence: "abc"` means the model misunderstood the schema; `raw_article_id:
999` means it hallucinated one number in an otherwise valid item.

Each validator returns `(items, stats)`. `stats` keys are always present, even at
zero, so the pipeline can sum them into `ExtractionRun.step_metrics` without
guarding every lookup.
"""

import math
from collections.abc import Collection, Mapping

# ARCHITECTURE 3.2: `Entity.entity_type` has `choices`, and Django does not
# enforce them on save. Anything outside this set would reach the DB and break
# the graph's category axis, so it is folded into "other" here instead.
ENTITY_TYPES = frozenset({"person", "org", "product", "model", "tech", "event", "other"})

# `Concept.namespace` is a plain CharField, but the graph legend and the
# namespace filter both assume a closed set. Same treatment.
CONCEPT_NAMESPACES = frozenset({"technique", "trend", "policy", "market", "other"})

FALLBACK_TYPE = "other"

DEFAULT_CONFIDENCE = 1.0

# Unverifiable quotes are kept but marked down rather than dropped: the model is
# usually right about the fact and wrong about the whitespace, and a missing
# entity costs more than an over-confident one.
EVIDENCE_PENALTY = 0.8


class SchemaError(ValueError):
    """LLM output does not match the contract; the caller should retry the call.

    Deliberately a `ValueError` and not an `AppError`: it never reaches a view.
    It is an internal signal to `extract_pipeline`'s tenacity policy, which
    retries on it alongside `json.JSONDecodeError`.
    """


# --- primitives ---------------------------------------------------------


def _strip_ws(text: str) -> str:
    """Drop every whitespace character.

    Evidence is compared in this form because models reflow quotes, swap
    full-width spaces for half-width ones and drop newlines, none of which mean
    the quote is invented.
    """
    return "".join(text.split())


def _norm(name: str) -> str:
    """Match key for entity and concept names. Same formula as `Entity.normalized_name`."""
    return " ".join(name.lower().split())


def _root_list(payload: object, root_key: str) -> list:
    if not isinstance(payload, Mapping):
        raise SchemaError(f"Expected a JSON object at the top level, got {type(payload).__name__}")
    if root_key not in payload:
        raise SchemaError(f"Missing root key '{root_key}'")
    items = payload[root_key]
    if not isinstance(items, list):
        raise SchemaError(f"Root key '{root_key}' must be an array, got {type(items).__name__}")
    return items


def _mapping(item: object, root_key: str, index: int) -> Mapping:
    if not isinstance(item, Mapping):
        raise SchemaError(f"{root_key}[{index}] must be an object, got {type(item).__name__}")
    return item


def _required_text(item: Mapping, field: str, root_key: str, index: int) -> str:
    value = item.get(field)
    if value is None:
        raise SchemaError(f"{root_key}[{index}] is missing required field '{field}'")
    if not isinstance(value, str):
        raise SchemaError(f"{root_key}[{index}].{field} must be a string, got {type(value).__name__}")
    text = value.strip()
    if not text:
        raise SchemaError(f"{root_key}[{index}].{field} must not be empty")
    return text


def _optional_text(item: Mapping, field: str) -> str:
    value = item.get(field)
    return value.strip() if isinstance(value, str) else ""


def _str_list(item: Mapping, field: str, root_key: str, index: int) -> list[str]:
    value = item.get(field)
    if value is None:
        return []
    if not isinstance(value, list):
        raise SchemaError(f"{root_key}[{index}].{field} must be an array of strings")
    out = []
    for element in value:
        if not isinstance(element, str):
            raise SchemaError(
                f"{root_key}[{index}].{field} must contain only strings, found {type(element).__name__}"
            )
        text = element.strip()
        if text:
            out.append(text)
    return out


def _confidence(item: Mapping, root_key: str, index: int) -> float:
    value = item.get("confidence")
    if value is None:
        return DEFAULT_CONFIDENCE

    # `isinstance(True, int)` is True in Python, and a boolean confidence is a
    # schema misunderstanding rather than a number worth clamping.
    if isinstance(value, bool):
        raise SchemaError(f"{root_key}[{index}].confidence must be a number, got bool")

    if isinstance(value, int | float):
        number = float(value)
    elif isinstance(value, str):
        try:
            number = float(value.strip())
        except ValueError:
            raise SchemaError(f"{root_key}[{index}].confidence is not a number: {value!r}") from None
    else:
        raise SchemaError(f"{root_key}[{index}].confidence must be a number, got {type(value).__name__}")

    if math.isnan(number) or math.isinf(number):
        raise SchemaError(f"{root_key}[{index}].confidence is not a finite number: {value!r}")

    return min(1.0, max(0.0, number))


def _article_id(item: Mapping, root_key: str, index: int) -> int | None:
    """Return the cited article id, or None when the value is not a whole number.

    A missing key raises — it is a required field. A present-but-unparseable
    value returns None so the caller can skip the item: whatever it is, it is not
    one of this batch's ids.
    """
    if item.get("raw_article_id") is None:
        raise SchemaError(f"{root_key}[{index}] is missing required field 'raw_article_id'")

    value = item["raw_article_id"]
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if value.is_integer() else None
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return None
    return None


def _enum(value: str, allowed: Collection[str]) -> tuple[str, bool]:
    """Return `(value, was_coerced)`, folding anything unknown into "other"."""
    lowered = value.strip().lower()
    if lowered in allowed:
        return lowered, False
    return FALLBACK_TYPE, True


def _base_stats() -> dict:
    return {
        "skipped_invalid_article_ids": 0,
        "evidence_empty": 0,
        "evidence_not_in_source": 0,
    }


def _evidence(
    item: Mapping,
    article_id: int,
    article_texts: Mapping[int, str] | None,
    confidence: float,
    stats: dict,
) -> tuple[str, float]:
    """Return `(snippet, confidence)`, discounting quotes that are not in the source.

    A non-string or absent `evidence` is treated as empty rather than as a schema
    error: the item still describes a real entity, it just cannot be sourced, and
    `docs/PROMPTS.md` says to keep it without creating an `Evidence` row.
    """
    raw = item.get("evidence")
    snippet = raw.strip() if isinstance(raw, str) else ""
    if not snippet:
        stats["evidence_empty"] += 1
        return "", confidence

    if article_texts is None:
        return snippet, confidence

    source = article_texts.get(article_id)
    if source is None:
        # The batch text for this article was not supplied; unverifiable is not
        # the same as wrong, so leave the confidence alone.
        return snippet, confidence

    if _strip_ws(snippet) in _strip_ws(source):
        return snippet, confidence

    stats["evidence_not_in_source"] += 1
    return snippet, round(confidence * EVIDENCE_PENALTY, 4)


# --- validators ---------------------------------------------------------


def validate_entities(
    payload: object,
    allowed_article_ids: Collection[int],
    *,
    article_texts: Mapping[int, str] | None = None,
) -> tuple[list[dict], dict]:
    """Validate a `wiki.extract_entities` payload.

    `article_texts` maps article id to the body text that went into the corpus.
    Omit it to skip the evidence substring check entirely; the pipeline passes it
    so unsourceable quotes get marked down.
    """
    root_key = "entities"
    items = _root_list(payload, root_key)
    allowed = set(allowed_article_ids)
    stats = _base_stats() | {"coerced_types": 0}
    validated: list[dict] = []

    for index, raw_item in enumerate(items):
        item = _mapping(raw_item, root_key, index)

        name = _required_text(item, "name", root_key, index)
        raw_type = _required_text(item, "type", root_key, index)
        aliases = _str_list(item, "aliases", root_key, index)
        confidence = _confidence(item, root_key, index)
        article_id = _article_id(item, root_key, index)

        if article_id is None or article_id not in allowed:
            stats["skipped_invalid_article_ids"] += 1
            continue

        entity_type, coerced = _enum(raw_type, ENTITY_TYPES)
        stats["coerced_types"] += int(coerced)

        snippet, confidence = _evidence(item, article_id, article_texts, confidence, stats)

        validated.append(
            {
                "name": name,
                "type": entity_type,
                "aliases": aliases,
                "summary": _optional_text(item, "summary"),
                "confidence": confidence,
                "evidence": snippet,
                "raw_article_id": article_id,
            }
        )

    return validated, stats


def validate_concepts(
    payload: object,
    allowed_article_ids: Collection[int],
    *,
    article_texts: Mapping[int, str] | None = None,
) -> tuple[list[dict], dict]:
    """Validate a `wiki.extract_concepts` payload. Same contract as `validate_entities`."""
    root_key = "concepts"
    items = _root_list(payload, root_key)
    allowed = set(allowed_article_ids)
    stats = _base_stats() | {"coerced_types": 0}
    validated: list[dict] = []

    for index, raw_item in enumerate(items):
        item = _mapping(raw_item, root_key, index)

        name = _required_text(item, "name", root_key, index)
        raw_namespace = _required_text(item, "namespace", root_key, index)
        signals = _str_list(item, "signals", root_key, index)
        confidence = _confidence(item, root_key, index)
        article_id = _article_id(item, root_key, index)

        if article_id is None or article_id not in allowed:
            stats["skipped_invalid_article_ids"] += 1
            continue

        namespace, coerced = _enum(raw_namespace, CONCEPT_NAMESPACES)
        stats["coerced_types"] += int(coerced)

        snippet, confidence = _evidence(item, article_id, article_texts, confidence, stats)

        validated.append(
            {
                "name": name,
                "namespace": namespace,
                "definition": _optional_text(item, "definition"),
                "signals": signals,
                "confidence": confidence,
                "evidence": snippet,
                "raw_article_id": article_id,
            }
        )

    return validated, stats


def validate_linkages(
    payload: object,
    allowed_article_ids: Collection[int],
    known_entities: Collection[str],
    known_concepts: Collection[str],
    *,
    article_texts: Mapping[int, str] | None = None,
) -> tuple[list[dict], dict]:
    """Validate a `wiki.extract_linkages` payload.

    `subject` and `object` are resolved back to the exact names in
    `known_entities` / `known_concepts` so the persistence step can look them up
    directly. Matching is on the normalized name, not byte equality: the prompt
    asks for verbatim names and mostly gets them, but casing and spacing drift.
    """
    root_key = "linkages"
    items = _root_list(payload, root_key)
    allowed = set(allowed_article_ids)
    entity_by_norm = {_norm(name): name for name in known_entities}
    concept_by_norm = {_norm(name): name for name in known_concepts}

    stats = _base_stats() | {
        "skipped_unknown_refs": 0,
        "skipped_self_references": 0,
        "corrected_object_types": 0,
    }
    validated: list[dict] = []

    for index, raw_item in enumerate(items):
        item = _mapping(raw_item, root_key, index)

        subject = _required_text(item, "subject", root_key, index)
        predicate = _required_text(item, "predicate", root_key, index)
        object_name = _required_text(item, "object", root_key, index)
        declared_type = _required_text(item, "object_type", root_key, index).lower()
        confidence = _confidence(item, root_key, index)
        article_id = _article_id(item, root_key, index)

        if article_id is None or article_id not in allowed:
            stats["skipped_invalid_article_ids"] += 1
            continue

        # Only entities can be the subject of a relation (ARCHITECTURE 3.2:
        # `Linkage.subject_entity` is a non-null FK to Entity).
        subject_norm = _norm(subject)
        resolved_subject = entity_by_norm.get(subject_norm)
        if resolved_subject is None:
            stats["skipped_unknown_refs"] += 1
            continue

        resolved = _resolve_object(object_name, declared_type, entity_by_norm, concept_by_norm)
        if resolved is None:
            stats["skipped_unknown_refs"] += 1
            continue
        object_type, resolved_object = resolved
        if object_type != declared_type:
            stats["corrected_object_types"] += 1

        # Hard constraint 5 of the linkage prompt. A self-loop adds no edge to the
        # graph and survives the DB's uniqueness constraint, so it is caught here.
        if object_type == "entity" and _norm(resolved_object) == subject_norm:
            stats["skipped_self_references"] += 1
            continue

        snippet, confidence = _evidence(item, article_id, article_texts, confidence, stats)

        validated.append(
            {
                "subject": resolved_subject,
                "predicate": predicate,
                "object": resolved_object,
                "object_type": object_type,
                "confidence": confidence,
                "evidence": snippet,
                "raw_article_id": article_id,
            }
        )

    return validated, stats


def _resolve_object(
    object_name: str,
    declared_type: str,
    entity_by_norm: Mapping[str, str],
    concept_by_norm: Mapping[str, str],
) -> tuple[str, str] | None:
    """Resolve `object` to `(object_type, canonical_name)`, or None if unknown.

    The declared `object_type` is a hint, not gospel — models routinely label a
    concept as an entity. If the name resolves in the other collection, the name
    wins and the caller counts the correction; only a name in neither is dropped.
    """
    normalized = _norm(object_name)
    as_entity = entity_by_norm.get(normalized)
    as_concept = concept_by_norm.get(normalized)

    if declared_type == "entity" and as_entity is not None:
        return "entity", as_entity
    if declared_type == "concept" and as_concept is not None:
        return "concept", as_concept
    if as_entity is not None:
        return "entity", as_entity
    if as_concept is not None:
        return "concept", as_concept
    return None
