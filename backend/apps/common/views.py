from django.db import connection
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response


@extend_schema(
    summary="健康检查",
    description="容器编排和部署脚本用它判断实例是否可用。会真的打一次数据库。",
    responses={200: dict, 503: dict},
)
@api_view(["GET"])
@permission_classes([AllowAny])
def health(request: Request) -> Response:
    try:
        # `ensure_connection` can be satisfied by a stale pooled handle, so issue
        # a real round trip instead.
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except Exception:
        return Response(
            {"status": "error", "db": "error"},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    return Response({"status": "ok", "db": "ok"})
