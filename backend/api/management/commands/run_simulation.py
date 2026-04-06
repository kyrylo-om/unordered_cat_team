import time

from django.conf import settings
from django.core.management.base import BaseCommand

from api.simulation import SimulationRuntime


class Command(BaseCommand):
    help = "Run tick-based logistics simulation and publish deltas to websocket clients"

    def add_arguments(self, parser):
        parser.add_argument(
            "--tick-seconds",
            type=float,
            default=float(getattr(settings, "SIMULATION_TICK_SECONDS", 3)),
            help="Seconds per simulation tick",
        )
        parser.add_argument(
            "--horizon",
            type=int,
            default=int(getattr(settings, "SIMULATION_HORIZON", 5)),
            help="Time-expanded graph horizon",
        )
        parser.add_argument(
            "--vehicle-cap",
            type=int,
            default=int(getattr(settings, "SIMULATION_VEHICLE_CAP", 100)),
            help="Max shipment capacity per route edge",
        )
        parser.add_argument(
            "--once",
            action="store_true",
            help="Run only one simulation tick",
        )

    def handle(self, *args, **options):
        runtime = SimulationRuntime(
            vehicle_cap=options["vehicle_cap"],
            horizon=options["horizon"],
        )

        channel_backend = (
            settings.CHANNEL_LAYERS.get("default", {}).get("BACKEND", "")
            if hasattr(settings, "CHANNEL_LAYERS")
            else ""
        )
        if channel_backend == "channels.layers.InMemoryChannelLayer":
            self.stdout.write(
                self.style.WARNING(
                    "InMemoryChannelLayer is process-local. "
                    "Use SIMULATION_AUTOSTART=1 with runserver for realtime websocket updates "
                    "or configure Redis channel layer for multi-process mode."
                )
            )

        tick_seconds = max(0.5, float(options["tick_seconds"]))

        self.stdout.write(
            self.style.SUCCESS(
                f"Simulation started (tick={tick_seconds}s, horizon={runtime.horizon}, vehicle_cap={runtime.vehicle_cap})"
            )
        )

        if options["once"]:
            updated = runtime.tick_once()
            if updated:
                self.stdout.write(self.style.SUCCESS("Tick completed"))
            else:
                self.stdout.write("Tick skipped (network not ready)")
            return

        try:
            while True:
                started = time.monotonic()
                runtime.tick_once()
                elapsed = time.monotonic() - started
                sleep_for = max(0.0, tick_seconds - elapsed)
                time.sleep(sleep_for)
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("Simulation stopped"))
