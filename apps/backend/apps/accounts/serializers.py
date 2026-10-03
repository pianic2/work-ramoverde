from typing import Any

from rest_framework import serializers

from .models import User


class UserSerializer(serializers.ModelSerializer[User]):
    class Meta:
        model = User
        fields = ["id", "email", "first_name", "last_name"]
        read_only_fields = fields


class SessionLoginSerializer(serializers.Serializer[dict[str, Any]]):
    email = serializers.EmailField()
    password = serializers.CharField(trim_whitespace=False, write_only=True)


class CsrfTokenSerializer(serializers.Serializer[dict[str, Any]]):
    csrfToken = serializers.CharField()


class MobileCredentialsSerializer(serializers.Serializer[dict[str, Any]]):
    email = serializers.EmailField()
    password = serializers.CharField(trim_whitespace=False, write_only=True)


class MobileTokenResponseSerializer(serializers.Serializer[dict[str, Any]]):
    access = serializers.CharField()
    refresh = serializers.CharField()


class MobileRefreshSerializer(serializers.Serializer[dict[str, Any]]):
    refresh = serializers.CharField()


class MobileLogoutSerializer(serializers.Serializer[dict[str, Any]]):
    refresh = serializers.CharField(write_only=True)
