from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import ConceptViewSet, EntityViewSet, ExtractView, GraphView

router = DefaultRouter()
router.register("wiki/entities", EntityViewSet, basename="entity")
router.register("wiki/concepts", ConceptViewSet, basename="concept")

urlpatterns = [
    path("wiki/graph/", GraphView.as_view(), name="wiki-graph"),
    path("wiki/extract/", ExtractView.as_view(), name="wiki-extract"),
    *router.urls,
]
