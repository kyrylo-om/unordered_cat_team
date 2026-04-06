from django.urls import path

from .views import (
    hello,
    csrf_token_view,
    login_view,
    check_auth_view,
    logout_view,
    map_layout_view,
    store_status_view,
    store_demand_view,
    simulation_node_metrics_view,
    change_password_view,
)

urlpatterns = [
    path("hello/", hello),
    path("map-layout", map_layout_view),
    path("auth/csrf-token/", csrf_token_view),
    path("auth/login/", login_view),
    path("auth/check/", check_auth_view),
    path("auth/logout/", logout_view),
    path("auth/change-password/", change_password_view),
    path("store/status", store_status_view),
    path("store/demand", store_demand_view),
    path("simulation/node-metrics", simulation_node_metrics_view),
]
