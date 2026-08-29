"""Ingest models: RSS sources and the raw articles pulled from them.

Field contract: `docs/ARCHITECTURE.md` section 3.1.
"""

from django.db import models


class RssSource(models.Model):
    name = models.CharField(max_length=200)
    url = models.URLField(unique=True)
    site_url = models.URLField(blank=True)
    enabled = models.BooleanField(default=True)
    last_fetched_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class RawArticle(models.Model):
    EXTRACT_STATUS = [
        ("pending", "Pending"),
        ("extracted", "Extracted"),
        ("failed", "Failed"),
        ("skipped", "Skipped"),
    ]

    source = models.ForeignKey(
        RssSource,
        on_delete=models.CASCADE,
        related_name="articles",
        null=True,
        blank=True,
    )
    title = models.CharField(max_length=500)
    url = models.URLField(max_length=1000)
    content = models.TextField()
    summary = models.TextField(blank=True)
    author = models.CharField(max_length=200, blank=True)
    publish_time = models.DateTimeField(null=True, blank=True)
    content_hash = models.CharField(max_length=64, unique=True)
    lang = models.CharField(max_length=10, blank=True)
    extract_status = models.CharField(max_length=20, choices=EXTRACT_STATUS, default="pending")
    fetched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-publish_time", "-fetched_at"]
        indexes = [
            models.Index(fields=["extract_status"]),
            models.Index(fields=["-publish_time"]),
        ]

    def __str__(self) -> str:
        return self.title
