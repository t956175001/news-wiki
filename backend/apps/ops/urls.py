from django.urls import path

from .views import cron_daily

urlpatterns = [
    # No trailing slash: the path is spelled this way in ARCHITECTURE section 4
    # and in the GitHub Actions workflow that calls it.
    path("ops/cron/daily", cron_daily, name="cron-daily"),
]
