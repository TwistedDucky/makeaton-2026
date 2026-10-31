import re

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError

from rest_framework import serializers

from .models import User


class RegisterSerializer(serializers.ModelSerializer):
    """
    Used for customer self-registration via POST /api/auth/register/.
    The role is always forced to CUSTOMER — clients cannot choose it.
    """

    password = serializers.CharField(write_only=True, min_length=9)

    class Meta:
        model = User
        fields = ["email", "first_name", "last_name", "phone_number", "password"]

    def validate_password(self, value):
        # Hackathon rules: >8 chars, 1 upper, 1 lower, 1 special
        errors = []

        if len(value) <= 8:
            errors.append("Must be more than 8 characters.")

        if not re.search(r"[A-Z]", value):
            errors.append("Must contain at least one uppercase letter.")

        if not re.search(r"[a-z]", value):
            errors.append("Must contain at least one lowercase letter.")

        if not re.search(r"[^a-zA-Z0-9]", value):
            errors.append("Must contain at least one special character.")

        if errors:
            raise serializers.ValidationError(errors)

        # Also run Django's built-in validators (common passwords, etc.)
        try:
            validate_password(value)
        except DjangoValidationError as e:
            raise serializers.ValidationError(list(e.messages))

        return value

    def create(self, validated_data):
        # Force role to CUSTOMER regardless of any payload manipulation
        validated_data["role"] = User.Role.CUSTOMER
        validated_data["is_active"] = True

        return User.objects.create_user(**validated_data)


class UserSerializer(serializers.ModelSerializer):
    """
    Used by admin for user management: GET /api/users/, POST /api/users/, etc.
    Admins can set role (STAFF / ADMIN). Password is write-only on create.
    """

    password = serializers.CharField(write_only=True, required=False, min_length=9)

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "phone_number",
            "role",
            "is_active",
            "date_joined",
            "password",
        ]
        read_only_fields = ["id", "date_joined"]

    def validate_password(self, value):
        errors = []

        if len(value) <= 8:
            errors.append("Must be more than 8 characters.")

        if not re.search(r"[A-Z]", value):
            errors.append("Must contain at least one uppercase letter.")

        if not re.search(r"[a-z]", value):
            errors.append("Must contain at least one lowercase letter.")

        if not re.search(r"[^a-zA-Z0-9]", value):
            errors.append("Must contain at least one special character.")

        if errors:
            raise serializers.ValidationError(errors)

        try:
            validate_password(value)
        except DjangoValidationError as e:
            raise serializers.ValidationError(list(e.messages))

        return value

    def create(self, validated_data):
        password = validated_data.pop("password", None)

        if not password:
            raise serializers.ValidationError({"password": "Password is required."})

        return User.objects.create_user(password=password, **validated_data)

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        if password:
            instance.set_password(password)

        instance.save()
        return instance


class CurrentUserSerializer(serializers.ModelSerializer):
    """
    Read-only. Returned by GET /api/auth/me/ — safe to expose to any role.
    """

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "phone_number",
            "role",
            "is_active",
            "date_joined",
        ]
        read_only_fields = fields
