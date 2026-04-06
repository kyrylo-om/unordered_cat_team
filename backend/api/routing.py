from django.urls import path

from .consumers import ManagerDashboardConsumer

websocket_urlpatterns = [
    path("ws/manager-dashboard/", ManagerDashboardConsumer.as_asgi()),
]
