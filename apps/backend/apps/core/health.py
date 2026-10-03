from django.db import connection
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView


class LivenessView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(operation_id="getHealthLive", responses={200: dict})
    def get(self, request: Request) -> Response:
        return Response({"status": "ok"})


class ReadinessView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(operation_id="getHealthReady", responses={200: dict, 503: dict})
    def get(self, request: Request) -> Response:
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        except Exception:
            return Response(
                {"status": "unavailable", "dependencies": {"database": "down"}}, status=503
            )
        return Response({"status": "ok", "dependencies": {"database": "ok"}})
