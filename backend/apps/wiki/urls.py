from django.urls import path

from .views import ExtractView

urlpatterns = [
    path("wiki/extract/", ExtractView.as_view(), name="wiki-extract"),
]
