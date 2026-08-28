from rest_framework import serializers

from .models import PromptTemplate, PromptVersion


class PromptVersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = PromptVersion
        fields = ["id", "version_no", "text", "note", "is_default", "created_at"]
        read_only_fields = fields


class PromptTemplateSerializer(serializers.ModelSerializer):
    current_version = PromptVersionSerializer(read_only=True)

    class Meta:
        model = PromptTemplate
        fields = ["key", "name", "description", "default_text", "current_version", "created_at"]
        read_only_fields = fields
