from django.urls import path

from .views import PromptTemplateDetailView, PromptTemplateListView, PromptVersionListView

urlpatterns = [
    path("prompts/", PromptTemplateListView.as_view(), name="prompt-list"),
    path("prompts/<str:key>/", PromptTemplateDetailView.as_view(), name="prompt-detail"),
    path("prompts/<str:key>/versions/", PromptVersionListView.as_view(), name="prompt-versions"),
]
