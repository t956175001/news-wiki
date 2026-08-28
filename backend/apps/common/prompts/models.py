from django.db import models


class PromptTemplate(models.Model):
    key = models.CharField(max_length=100, unique=True)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    default_text = models.TextField()
    current_version = models.ForeignKey(
        "PromptVersion",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["key"]

    def __str__(self):
        return self.key


class PromptVersion(models.Model):
    template = models.ForeignKey(PromptTemplate, on_delete=models.CASCADE, related_name="versions")
    version_no = models.PositiveIntegerField()
    text = models.TextField()
    note = models.CharField(max_length=500, blank=True)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("template", "version_no")]
        ordering = ["template", "version_no"]

    def __str__(self):
        return f"{self.template.key} v{self.version_no}"
