"""Brief models: the generated daily digest.

Field contract: `docs/ARCHITECTURE.md` section 3.4.
"""

from django.db import models


class DailyBrief(models.Model):
    date = models.DateField(unique=True)
    title = models.CharField(max_length=300)
    content_md = models.TextField()
    citations = models.JSONField(default=list)
    model_name = models.CharField(max_length=80)
    extraction_run = models.ForeignKey(
        "ops.ExtractionRun",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="briefs",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date"]

    def __str__(self) -> str:
        return f"{self.date} {self.title}"
