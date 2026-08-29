from rest_framework.routers import DefaultRouter

from .views import RawArticleViewSet, RssSourceViewSet

router = DefaultRouter()
router.register("ingest/sources", RssSourceViewSet, basename="rss-source")
router.register("ingest/articles", RawArticleViewSet, basename="raw-article")

urlpatterns = router.urls
