"""Re-key entities on the name alone and fold what collides (ADR-019).

Two changes land together because they produce the same collisions and one
sweep has to resolve both:

* `normalize_name` now drops separators instead of collapsing them, so
  `小米 18 Fold` and `小米18 Fold` become one key;
* `entity_type` leaves the uniqueness key, so `GitHub` the org and `GitHub` the
  product become one row.

Order matters. The old constraint has to go *first*: re-keying rows one at a
time walks through states that `uniq_entity_norm_type` would reject.

Adding the new constraint is a separate migration, and that split is not
cosmetic. PostgreSQL refuses `ALTER TABLE` on a table that has pending trigger
events, which is exactly what the deletes and foreign-key rewrites below leave
behind inside the same transaction. Doing both here passed on SQLite and failed
in production with `cannot ALTER TABLE "wiki_entity" because it has pending
trigger events`.
"""

from django.db import migrations

from apps.wiki.services.merge import merge_duplicate_entities
from apps.wiki.services.normalize import normalize_name


def fold_duplicates(apps, schema_editor):
    removed = merge_duplicate_entities(
        entity_model=apps.get_model("wiki", "Entity"),
        linkage_model=apps.get_model("wiki", "Linkage"),
        evidence_model=apps.get_model("wiki", "Evidence"),
        normalize=normalize_name,
    )
    if removed:
        print(f"  merged {removed} duplicate entity rows")


def unfold(apps, schema_editor):
    """Nothing to undo.

    Reversing the schema is fine; the merged rows are not coming back, because
    the information needed to split them again (which of two typings each
    citation belonged to) was the thing being discarded. Left as a no-op rather
    than raising so the schema can still be rolled back.
    """


class Migration(migrations.Migration):
    dependencies = [("wiki", "0001_initial")]

    operations = [
        migrations.RemoveConstraint(model_name="entity", name="uniq_entity_norm_type"),
        migrations.RunPython(fold_duplicates, unfold),
    ]
