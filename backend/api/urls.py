from django.urls import path

from .views import hello, csrf_token_view, login_view, check_auth_view, logout_view

urlpatterns = [
    path("hello/", hello),
    path("auth/csrf-token/", csrf_token_view),
    path("auth/login/", login_view),
    path("auth/check/", check_auth_view),
    path("auth/logout/", logout_view),
]
