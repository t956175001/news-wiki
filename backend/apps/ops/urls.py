from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import ExtractionRunViewSet, StatsView, cron_daily

router = DefaultRouter()
router.register("ops/runs", ExtractionRunViewSet, basename="extraction-run")

urlpatterns = [
    path("ops/stats/", StatsView.as_view(), name="ops-stats"),
    # No trailing slash: the path is spelled this way in ARCHITECTURE section 4
    # and in the GitHub Actions workflow that calls it.
    path("ops/cron/daily", cron_daily, name="cron-daily"),
    *router.urls,
]
