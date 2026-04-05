from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.middleware.csrf import get_token
from django.contrib.auth import authenticate, login, logout
from django_ratelimit.decorators import ratelimit
import json


def hello(request):
    """Legacy endpoint for testing backend connectivity."""
    return JsonResponse({"message": "Hello from Django backend"})


@require_http_methods(["GET"])
def csrf_token_view(request):
    """Return CSRF token for unprotected requests."""
    token = get_token(request)
    return JsonResponse({"csrfToken": token})


@require_http_methods(["POST"])
@ratelimit(key="ip", rate="5/h", method="POST")
def login_view(request):
    """
    Authenticate user with username and password.
    Returns user data and CSRF token on success.
    """
    try:
        data = json.loads(request.body)
        username = data.get("username")
        password = data.get("password")

        if not username or not password:
            return JsonResponse(
                {"error": "Username and password are required"}, status=400
            )

        user = authenticate(request, username=username, password=password)

        if user is None:
            return JsonResponse({"error": "Invalid username or password"}, status=401)

        login(request, user)
        token = get_token(request)

        return JsonResponse(
            {
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                },
                "csrfToken": token,
            }
        )
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    except Exception as e:
        return JsonResponse({"error": "An error occurred during login"}, status=500)


@require_http_methods(["GET"])
def check_auth_view(request):
    """Check if user is authenticated and return user data."""
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Not authenticated"}, status=401)

    user = request.user
    return JsonResponse(
        {
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email,
            }
        }
    )


@require_http_methods(["POST"])
def logout_view(request):
    """Logout user and clear session."""
    logout(request)
    return JsonResponse({"message": "Logged out successfully"})
