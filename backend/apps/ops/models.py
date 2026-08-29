"""Ops models: one row per extraction run, used for the pipeline dashboard.

Field contract: `docs/ARCHITECTURE.md` section 3.3.
"""

from django.db import models


class ExtractionRun(models.Model):
    STATUS = [
        ("running", "Running"),
        ("success", "Success"),
        ("partial", "Partial"),
        ("failed", "Failed"),
    ]
    TRIGGERS = [("cron", "Cron"), ("manual", "Manual"), ("seed", "Seed")]

    run_id = models.CharField(max_length=32, unique=True)
    status = models.CharField(max_length=20, choices=STATUS, default="running")
    trigger = models.CharField(max_length=20, choices=TRIGGERS, default="cron")
    step_metrics = models.JSONField(default=dict)
    prompt_versions = models.JSONField(default=dict)
    articles_in = models.PositiveIntegerField(default=0)
    entities_saved = models.PositiveIntegerField(default=0)
    concepts_saved = models.PositiveIntegerField(default=0)
    linkages_saved = models.PositiveIntegerField(default=0)
    prompt_tokens = models.PositiveIntegerField(default=0)
    completion_tokens = models.PositiveIntegerField(default=0)
    total_tokens = models.PositiveIntegerField(default=0)
    cost_cny = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    elapsed_ms = models.PositiveIntegerField(default=0)
    error_message = models.TextField(blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-started_at"]

    def __str__(self) -> str:
        return f"{self.run_id} ({self.status})"
