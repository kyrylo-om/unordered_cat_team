from django.apps import AppConfig
import os
import sys

from django.conf import settings


class ApiConfig(AppConfig):
    name = "api"

    def ready(self):
        import api.signals  # noqa

        if not getattr(settings, "SIMULATION_AUTOSTART", False):
            return

        command = sys.argv[1] if len(sys.argv) > 1 else ""
        if command not in {"runserver", "daphne", "uvicorn"}:
            return

        # Prevent duplicate runtime threads when Django's autoreloader forks.
        if command == "runserver" and os.environ.get("RUN_MAIN") != "true":
            return

        from .simulation import start_simulation_thread

        start_simulation_thread()
