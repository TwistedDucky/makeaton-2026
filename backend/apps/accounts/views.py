import json

from django.contrib.auth import authenticate, login, logout, get_user_model
from django.contrib.auth.forms import PasswordResetForm, SetPasswordForm
from django.contrib.auth.tokens import default_token_generator
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from common.permissions import IsAdmin
from .models import User
from .serializers import RegisterSerializer, UserSerializer, CurrentUserSerializer

# ---------------------------------------------------------------------------
# Auth views
# ---------------------------------------------------------------------------

@require_GET
@ensure_csrf_cookie
def csrf_token(request):
    return JsonResponse({
        "success": True,
        "csrfToken": get_token(request),
    })


@require_POST
@csrf_protect
def login_view(request):
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({
            "success": False,
            "message": "Invalid JSON",
            "errors": None,
        }, status=400)

    email = data.get("email", "").strip().lower()
    password = data.get("password", "")

    if not email or not password:
        return JsonResponse({
            "success": False,
            "message": "Email and password are required",
            "errors": {
                "email": ["This field is required."] if not email else [],
                "password": ["This field is required."] if not password else [],
            },
        }, status=400)

    user = authenticate(request, username=email, password=password)

    if user is None:
        return JsonResponse({
            "success": False,
            "message": "Invalid email or password",
            "errors": None,
        }, status=401)

    if not user.is_active:
        return JsonResponse({
            "success": False,
            "message": "This account is inactive",
            "errors": None,
        }, status=403)

    login(request, user)

    return JsonResponse({
        "success": True,
        "message": "Login successful",
        "data": {
            "id": str(user.id),
            "email": user.email,
            "role": user.role,
        },
    })


@require_POST
@csrf_protect
def logout_view(request):
    logout(request)
    return JsonResponse({
        "success": True,
        "message": "Logout successful",
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def current_user(request):
    serializer = CurrentUserSerializer(request.user)
    return Response({
        "success": True,
        "data": serializer.data,
    })


@api_view(["POST"])
@permission_classes([AllowAny])
def register_view(request):
    serializer = RegisterSerializer(data=request.data)

    if not serializer.is_valid():
        return Response({
            "success": False,
            "message": "Registration failed",
            "errors": serializer.errors,
        }, status=status.HTTP_400_BAD_REQUEST)

    user = serializer.save()

    # Auto-login after successful registration
    login(request, user)

    return Response({
        "success": True,
        "message": "Account created successfully",
        "data": {
            "id": str(user.id),
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "role": user.role,
        },
    }, status=status.HTTP_201_CREATED)


# ---------------------------------------------------------------------------
# Password reset views
# ---------------------------------------------------------------------------

@api_view(["POST"])
@permission_classes([AllowAny])
def password_reset_request(request):
    """
    POST /api/auth/password-reset/
    Accepts { "email": "..." } and sends a reset link to the console
    (EMAIL_BACKEND = console in dev). Always returns 200 to avoid
    leaking whether an email exists.
    """
    email = request.data.get("email", "").strip().lower()

    if not email:
        return Response({
            "success": False,
            "message": "Email is required",
            "errors": {"email": ["This field is required."]},
        }, status=status.HTTP_400_BAD_REQUEST)

    # Use Django's built-in PasswordResetForm — handles token generation
    # and email sending via the configured EMAIL_BACKEND.
    form = PasswordResetForm(data={"email": email})

    if form.is_valid():
        form.save(
            request=request,
            use_https=False,
            email_template_name="registration/password_reset_email.txt",
            subject_template_name="registration/password_reset_subject.txt",
        )

    # Always 200 — don't reveal whether the email exists
    return Response({
        "success": True,
        "message": "If that email is registered, a reset link has been sent.",
    })


@api_view(["POST"])
@permission_classes([AllowAny])
def password_reset_confirm(request):
    """
    POST /api/auth/password-reset/confirm/
    Accepts { "uid": "...", "token": "...", "new_password": "..." }
    """
    uid = request.data.get("uid", "")
    token = request.data.get("token", "")
    new_password = request.data.get("new_password", "")

    if not uid or not token or not new_password:
        return Response({
            "success": False,
            "message": "uid, token, and new_password are required",
            "errors": None,
        }, status=status.HTTP_400_BAD_REQUEST)

    # Decode the uid to get the user
    try:
        user_pk = force_str(urlsafe_base64_decode(uid))
        user = User.objects.get(pk=user_pk)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        return Response({
            "success": False,
            "message": "Invalid or expired reset link",
            "errors": None,
        }, status=status.HTTP_400_BAD_REQUEST)

    # Validate the token
    if not default_token_generator.check_token(user, token):
        return Response({
            "success": False,
            "message": "Invalid or expired reset link",
            "errors": None,
        }, status=status.HTTP_400_BAD_REQUEST)

    # Validate + set the new password using Django's SetPasswordForm
    form = SetPasswordForm(user=user, data={
        "new_password1": new_password,
        "new_password2": new_password,
    })

    if not form.is_valid():
        return Response({
            "success": False,
            "message": "Password validation failed",
            "errors": form.errors,
        }, status=status.HTTP_400_BAD_REQUEST)

    form.save()

    return Response({
        "success": True,
        "message": "Password has been reset successfully. Please log in.",
    })


# ---------------------------------------------------------------------------
# User management views (Admin only)
# ---------------------------------------------------------------------------

@api_view(["GET", "POST"])
@permission_classes([IsAdmin])
def user_list_create(request):
    """
    GET  /api/users/  — list all users with optional filters
    POST /api/users/  — create a new STAFF or ADMIN user
    """
    if request.method == "GET":
        queryset = User.objects.all().order_by("-date_joined")

        # Optional query filters: ?role=STAFF&is_active=true
        role = request.query_params.get("role")
        is_active = request.query_params.get("is_active")

        if role:
            queryset = queryset.filter(role=role.upper())

        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == "true")

        serializer = UserSerializer(queryset, many=True)
        return Response({
            "success": True,
            "count": queryset.count(),
            "data": serializer.data,
        })

    # POST — create new user (admin creates staff/admin accounts)
    serializer = UserSerializer(data=request.data)

    if not serializer.is_valid():
        return Response({
            "success": False,
            "message": "User creation failed",
            "errors": serializer.errors,
        }, status=status.HTTP_400_BAD_REQUEST)

    user = serializer.save()

    return Response({
        "success": True,
        "message": "User created successfully",
        "data": serializer.data,
    }, status=status.HTTP_201_CREATED)


@api_view(["GET", "PATCH", "DELETE"])
@permission_classes([IsAdmin])
def user_detail(request, pk):
    """
    GET    /api/users/<pk>/  — retrieve a single user
    PATCH  /api/users/<pk>/  — update role, name, active status, password
    DELETE /api/users/<pk>/  — soft-deactivate (never hard delete)
    """
    try:
        user = User.objects.get(pk=pk)
    except User.DoesNotExist:
        return Response({
            "success": False,
            "message": "User not found",
            "errors": None,
        }, status=status.HTTP_404_NOT_FOUND)

    if request.method == "GET":
        serializer = UserSerializer(user)
        return Response({
            "success": True,
            "data": serializer.data,
        })

    if request.method == "PATCH":
        # Prevent admin from deactivating their own account
        if user == request.user and request.data.get("is_active") is False:
            return Response({
                "success": False,
                "message": "You cannot deactivate your own account",
                "errors": None,
            }, status=status.HTTP_400_BAD_REQUEST)

        serializer = UserSerializer(user, data=request.data, partial=True)

        if not serializer.is_valid():
            return Response({
                "success": False,
                "message": "Update failed",
                "errors": serializer.errors,
            }, status=status.HTTP_400_BAD_REQUEST)

        serializer.save()
        return Response({
            "success": True,
            "message": "User updated successfully",
            "data": serializer.data,
        })

    if request.method == "DELETE":
        # Prevent admin from deactivating themselves
        if user == request.user:
            return Response({
                "success": False,
                "message": "You cannot deactivate your own account",
                "errors": None,
            }, status=status.HTTP_400_BAD_REQUEST)

        # Soft delete — just mark inactive
        user.is_active = False
        user.save(update_fields=["is_active"])

        return Response({
            "success": True,
            "message": f"User {user.email} has been deactivated",
        })
