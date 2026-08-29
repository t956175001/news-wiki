from django.urls import path, re_path

from .views import DailyBriefByDateView, DailyBriefLatestView, DailyBriefListView

urlpatterns = [
    path("brief/", DailyBriefListView.as_view(), name="brief-list"),
    path("brief/latest/", DailyBriefLatestView.as_view(), name="brief-latest"),
    # Constrained to a date shape so it can never swallow `latest/` — order
    # dependence between two routes is the kind of thing that survives review and
    # then breaks when someone sorts the list.
    re_path(
        r"^brief/(?P<date>\d{4}-\d{2}-\d{2})/$",
        DailyBriefByDateView.as_view(),
        name="brief-by-date",
    ),
]
