"""Load the v1 prompt texts.

This imports `PROMPT_SEEDS` from application code rather than inlining a copy.
A data migration normally freezes its payload, but two copies of a 2 KB prompt
drift apart silently — which is exactly what happened in the previous codebase.
The insert is `get_or_create`, so re-running is a no-op and an already-migrated
database is never rewritten. Adding a *new* prompt later means a new migration.
"""

from django.db import migrations

from apps.common.prompts.seeds import PROMPT_SEEDS


def seed_prompts(apps, schema_editor):
    PromptTemplate = apps.get_model("prompts", "PromptTemplate")
    PromptVersion = apps.get_model("prompts", "PromptVersion")

    for seed in PROMPT_SEEDS:
        template, created = PromptTemplate.objects.get_or_create(
            key=seed["key"],
            defaults={
                "name": seed["name"],
                "description": seed["description"],
                "default_text": seed["text"],
            },
        )
        if not created:
            continue

        version = PromptVersion.objects.create(
            template=template,
            version_no=1,
            text=seed["text"],
            note="初版",
            is_default=True,
        )
        template.current_version = version
        template.save(update_fields=["current_version"])


def unseed_prompts(apps, schema_editor):
    PromptTemplate = apps.get_model("prompts", "PromptTemplate")
    PromptTemplate.objects.filter(key__in=[seed["key"] for seed in PROMPT_SEEDS]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("prompts", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_prompts, unseed_prompts),
    ]
