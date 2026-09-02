"""Fold duplicate entity rows into one, carrying their relations and evidence.

Needed because a name's match key can change. When it does — ADR-019 widened
`normalize_name` and dropped `entity_type` from the identity — rows that were
legitimately separate under the old key become the same entry under the new one,
and something has to reconcile them without losing a single citation.

Model classes are passed in rather than imported so a data migration can call
this with its historical models. The rule everywhere below: nothing is deleted
until whatever pointed at it points at the survivor instead.
"""

import logging
from collections.abc import Sequence

logger = logging.getLogger(__name__)

# Ranked worst-to-best. Used only to break a tie between rows with identical
# mention counts and degrees, so that the survivor's type is at least stable
# across reruns instead of depending on primary-key order.
_TYPE_PREFERENCE = ("other", "event", "tech", "product", "model", "org", "person")


def _type_rank(entity_type: str) -> int:
    return _TYPE_PREFERENCE.index(entity_type) if entity_type in _TYPE_PREFERENCE else -1


def choose_primary(entities: Sequence, linkage_model) -> object:
    """The row the others fold into.

    Most-mentioned wins, then best-connected, then the type ranking, then the
    lowest primary key. The last two exist only to make the outcome
    deterministic: re-running the merge on the same data must pick the same
    survivor, or a re-run would shuffle every URL that names an entity id.
    """

    def degree(entity) -> int:
        return linkage_model.objects.filter(subject_entity=entity).count() + (
            linkage_model.objects.filter(object_entity=entity).count()
        )

    return max(
        entities,
        key=lambda entity: (
            entity.mention_count,
            degree(entity),
            _type_rank(entity.entity_type),
            -entity.pk,
        ),
    )


def _repoint_linkages(primary, duplicate, linkage_model, evidence_model) -> None:
    """Move a duplicate's edges onto the primary.

    Two things can go wrong and both are handled by moving the evidence and
    dropping the edge rather than the other way round:

    * the moved edge would duplicate one the primary already has, which the
      `uniq_linkage_triple` constraint forbids;
    * the moved edge would point at the primary from the primary — a self-loop,
      which is what "GitHub the org 属于 GitHub the product" becomes once the
      two are known to be one thing.
    """
    for field in ("subject_entity", "object_entity"):
        for linkage in linkage_model.objects.filter(**{field: duplicate}):
            subject_id = primary.pk if field == "subject_entity" else linkage.subject_entity_id
            object_entity_id = primary.pk if field == "object_entity" else linkage.object_entity_id

            if object_entity_id is not None and subject_id == object_entity_id:
                evidence_model.objects.filter(linkage=linkage).delete()
                linkage.delete()
                continue

            existing = (
                linkage_model.objects.filter(
                    subject_entity_id=subject_id,
                    predicate=linkage.predicate,
                    object_entity_id=object_entity_id,
                    object_concept_id=linkage.object_concept_id,
                )
                .exclude(pk=linkage.pk)
                .first()
            )
            if existing is not None:
                evidence_model.objects.filter(linkage=linkage).update(linkage=existing)
                existing.confidence = max(existing.confidence, linkage.confidence)
                existing.save(update_fields=["confidence"])
                linkage.delete()
                continue

            setattr(linkage, field, primary)
            linkage.save(update_fields=[field])


def merge_entities(primary, duplicates: Sequence, *, entity_model, linkage_model, evidence_model):
    """Fold `duplicates` into `primary` and delete them. Returns `primary`.

    Every duplicate's own name becomes an alias of the survivor, so a search for
    the spelling that lost still finds the entry.
    """
    aliases = set(primary.aliases or [])
    mention_count = primary.mention_count
    confidence = primary.confidence
    summary = primary.summary
    first_seen = primary.first_seen_at
    last_seen = primary.last_seen_at

    for duplicate in duplicates:
        _repoint_linkages(primary, duplicate, linkage_model, evidence_model)
        evidence_model.objects.filter(entity=duplicate).update(entity=primary)

        aliases.update(duplicate.aliases or [])
        if duplicate.name != primary.name:
            aliases.add(duplicate.name)
        mention_count += duplicate.mention_count
        confidence = max(confidence, duplicate.confidence)
        if not summary:
            summary = duplicate.summary
        if duplicate.first_seen_at and (first_seen is None or duplicate.first_seen_at < first_seen):
            first_seen = duplicate.first_seen_at
        if duplicate.last_seen_at and (last_seen is None or duplicate.last_seen_at > last_seen):
            last_seen = duplicate.last_seen_at

        duplicate.delete()

    primary.aliases = sorted(alias for alias in aliases if alias and alias.strip())
    primary.mention_count = mention_count
    primary.confidence = confidence
    primary.summary = summary
    primary.first_seen_at = first_seen
    primary.last_seen_at = last_seen
    primary.save()
    return primary


def merge_duplicate_entities(*, entity_model, linkage_model, evidence_model, normalize) -> int:
    """Re-key every entity and fold together whatever now collides.

    Returns the number of rows removed. Safe to run twice: the second pass finds
    no collisions and rewrites nothing.

    Merging happens before any key is written, and the keys are then written in
    two passes through a temporary value. Both are for the same reason: re-keying
    row by row walks through states where two rows briefly share a key, and while
    the migration runs with `uniq_entity_norm` not yet added, this function lives
    in the service layer and has to hold under the finished schema too.
    """
    groups: dict[str, list] = {}
    for entity in entity_model.objects.all():
        groups.setdefault(normalize(entity.name), []).append(entity)

    removed = 0
    survivors = []
    for key, entities in groups.items():
        primary = entities[0] if len(entities) == 1 else choose_primary(entities, linkage_model)
        if len(entities) > 1:
            duplicates = [entity for entity in entities if entity.pk != primary.pk]
            logger.info("merging %s duplicate rows into entity %s (%s)", len(duplicates), primary.pk, key)
            merge_entities(
                primary,
                duplicates,
                entity_model=entity_model,
                linkage_model=linkage_model,
                evidence_model=evidence_model,
            )
            removed += len(duplicates)
        if primary.normalized_name != key:
            survivors.append((primary.pk, key))

    # `\x00` cannot appear in a name, so the parking space is always free.
    for pk, _key in survivors:
        entity_model.objects.filter(pk=pk).update(normalized_name=f"\x00rekey-{pk}")
    for pk, key in survivors:
        entity_model.objects.filter(pk=pk).update(normalized_name=key)
    return removed
