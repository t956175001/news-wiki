from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.common.views import health

API = "api/v1/"

urlpatterns = [
    path("admin/", admin.site.urls),
    path(f"{API}health/", health, name="health"),
    path(f"{API}schema/", SpectacularAPIView.as_view(), name="schema"),
    path(f"{API}docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path(API, include("apps.common.prompts.urls")),
    path(API, include("apps.ingest.urls")),
    path(API, include("apps.wiki.urls")),
    path(API, include("apps.brief.urls")),
    path(API, include("apps.ops.urls")),
]
