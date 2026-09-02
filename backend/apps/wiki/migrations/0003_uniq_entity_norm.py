"""Add the new uniqueness constraint, once 0002's rewrites have committed.

Separate from 0002 on purpose. PostgreSQL will not `ALTER TABLE` a table with
pending trigger events, and 0002 leaves plenty of those behind: it deletes
duplicate rows and repoints every foreign key that referenced them. Both
operations in one transaction fails with `ObjectInUse` — on Postgres only, which
is why the local SQLite runs and the migration rehearsal both looked clean.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("wiki", "0002_entity_identity_is_the_name_alone")]

    operations = [
        migrations.AddConstraint(
            model_name="entity",
            constraint=models.UniqueConstraint(fields=["normalized_name"], name="uniq_entity_norm"),
        ),
    ]
