import json

from django.contrib.auth import authenticate, login, logout
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated


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

    user = authenticate(
        request,
        username=email,
        password=password,
    )

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
    user = request.user

    return JsonResponse({
        "success": True,
        "data": {
            "id": str(user.id),
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "role": user.role,
        },
    })