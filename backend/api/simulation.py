import logging
import math
import threading
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone

from django.conf import settings

from algo import StorageInventoryEngine

from .models import NetworkDefinition, Route, Shop, Warehouse
from .realtime import (
    broadcast_edge_update,
    broadcast_event_log,
    broadcast_node_update,
    broadcast_tick,
    resolve_reverse_edge_id,
    resolve_route_edge_id,
)

logger = logging.getLogger(__name__)


def _route_tick_count(distance_value=None, time_value=None):
    distance = None
    if distance_value is not None:
        try:
            distance = float(distance_value)
        except (TypeError, ValueError):
            distance = None

    if distance is not None and distance > 0:
        return max(1, int(math.ceil(distance)))

    try:
        route_time = float(time_value)
    except (TypeError, ValueError):
        route_time = 1.0

    if route_time <= 0:
        route_time = 1.0

    return max(1, int(math.ceil(route_time)))


class SimulationRuntime:
    """Tick-based simulation runtime that streams topology deltas over websockets."""

    def __init__(self, vehicle_cap=None, horizon=None):
        self.vehicle_cap = (
            int(vehicle_cap)
            if vehicle_cap is not None
            else int(getattr(settings, "SIMULATION_VEHICLE_CAP", 100))
        )
        self.horizon = (
            int(horizon)
            if horizon is not None
            else int(getattr(settings, "SIMULATION_HORIZON", 5))
        )
        self.max_trucks_per_route_tick = int(
            getattr(settings, "SIMULATION_MAX_TRUCKS_PER_ROUTE_TICK", 3)
        )
        self.routes_bidirectional = bool(
            getattr(settings, "SIMULATION_ROUTES_BIDIRECTIONAL", True)
        )

        self.engine = None
        self.network_id = None
        self.network_updated_at = None
        self.tick_index = 0
        self.route_edge_ids = defaultdict(list)
        self.edge_duration_by_id = {}
        self.pair_default_duration = {}
        self.tick_seconds = float(getattr(settings, "SIMULATION_TICK_SECONDS", 1))

    def _edge_duration_from_time(self, travel_time):
        try:
            seconds = max(0.2, float(travel_time) * self.tick_seconds)
        except (TypeError, ValueError):
            seconds = max(0.2, self.tick_seconds)

        return f"{seconds:.2f}s"

    def _active_network(self):
        network = NetworkDefinition.objects.filter(is_active=True).first()
        if network is None:
            network = NetworkDefinition.objects.first()
        return network

    def _needs_rebuild(self, network):
        if self.engine is None:
            return True

        if self.network_id != network.id:
            return True

        if self.network_updated_at != network.updated_at:
            return True

        return False

    def _route_rows(self, network):
        route_rows = list(
            Route.objects.filter(network_definition=network, is_active=True).order_by("id")
        )
        if route_rows:
            return route_rows

        # Fallback for older data where routes are available only in JSON definition.
        routes_from_definition = []
        definition = network.definition if isinstance(network.definition, dict) else {}
        for index, route in enumerate(definition.get("routes", [])):
            try:
                source = str(route["from"])
                target = str(route["to"])
            except Exception:
                continue

            try:
                travel_time = _route_tick_count(
                    route.get("distance"),
                    route.get("time", route.get("travel_time", 1)),
                )
            except Exception:
                travel_time = 1

            try:
                transport_cost = float(route.get("cost", 1.0))
            except Exception:
                transport_cost = 1.0

            fallback = Route(
                network_definition=network,
                edge_id=str(route.get("id") or f"edge-{source}-{target}-{index}"),
                source_node_id=source,
                target_node_id=target,
                travel_time=travel_time,
                transport_cost=transport_cost,
                metadata={},
                is_active=True,
            )
            routes_from_definition.append(fallback)

        return routes_from_definition

    def _build_engine(self, network, warehouses, shops, route_rows):
        nodes = [warehouse.node_id for warehouse in warehouses] + [shop.node_id for shop in shops]
        route_payload = []
        existing_pairs = set()

        for index, route in enumerate(route_rows):
            source = str(route.source_node_id)
            target = str(route.target_node_id)
            edge_id = resolve_route_edge_id(route, fallback_index=index)
            route_meta = route.metadata if isinstance(route.metadata, dict) else {}
            route_time = _route_tick_count(route_meta.get("distance"), route.travel_time)
            route_info = {
                "edge_id": edge_id,
                "from": source,
                "to": target,
                "time": route_time,
                "cost": float(route.transport_cost),
            }
            route_payload.append(route_info)
            existing_pairs.add((source, target))

        if self.routes_bidirectional:
            synthetic_reverse_routes = []
            for route in route_payload:
                reverse_pair = (route["to"], route["from"])
                if reverse_pair in existing_pairs:
                    continue

                reverse_route = {
                    "edge_id": resolve_reverse_edge_id(route["edge_id"]),
                    "from": route["to"],
                    "to": route["from"],
                    "time": int(route["time"]),
                    "cost": float(route["cost"]),
                }
                synthetic_reverse_routes.append(reverse_route)
                existing_pairs.add(reverse_pair)

            route_payload.extend(synthetic_reverse_routes)

        initial_stocks = {
            warehouse.node_id: int(warehouse.inventory)
            for warehouse in warehouses
        }
        initial_stocks.update(
            {
                shop.node_id: int(shop.inventory)
                for shop in shops
            }
        )

        demand_rates = {warehouse.node_id: 0 for warehouse in warehouses}
        demand_rates.update(
            {
                shop.node_id: int(shop.demand_rate)
                for shop in shops
            }
        )

        engine = StorageInventoryEngine(
            vehicle_cap=self.vehicle_cap,
            horizon=self.horizon,
            max_trucks_per_route_tick=self.max_trucks_per_route_tick,
        )
        engine.initialize(
            {
                "nodes": nodes,
                "routes": [
                    {
                        "from": route["from"],
                        "to": route["to"],
                        "time": route["time"],
                        "cost": route["cost"],
                    }
                    for route in route_payload
                ],
                "initial_stocks": initial_stocks,
                "demand_rates": demand_rates,
            }
        )

        self.route_edge_ids = defaultdict(list)
        self.edge_duration_by_id = {}
        self.pair_default_duration = {}
        for route in route_payload:
            edge_id = str(route["edge_id"])
            pair = (str(route["from"]), str(route["to"]))
            duration = self._edge_duration_from_time(route["time"])
            self.route_edge_ids[pair].append(edge_id)
            self.edge_duration_by_id[edge_id] = duration
            if pair not in self.pair_default_duration:
                self.pair_default_duration[pair] = duration

        self.engine = engine
        self.network_id = network.id
        self.network_updated_at = network.updated_at
        self.tick_index = 0

        logger.info(
            "Simulation engine initialized: network=%s nodes=%s routes=%s",
            network.name,
            len(nodes),
            len(route_payload),
        )

    @staticmethod
    def _active_shipments_counter(shipments):
        return Counter((shipment.from_loc, shipment.to_loc) for shipment in shipments)

    def _node_payload(self, node_id, warehouses_map, shops_map):
        if node_id in warehouses_map:
            warehouse = warehouses_map[node_id]
            return {
                "label": warehouse.name,
                "type": "warehouse",
                "inventory": int(self.engine.stocks.get(node_id, warehouse.inventory)),
            }

        shop = shops_map[node_id]
        return {
            "label": shop.name,
            "type": "shop",
            "inventory": int(self.engine.stocks.get(node_id, shop.inventory)),
            "target": int(shop.target),
            "demandRate": int(shop.demand_rate),
        }

    def _persist_stocks(self, warehouses, shops):
        changed_nodes = set()

        for warehouse in warehouses:
            new_value = max(0, int(self.engine.stocks.get(warehouse.node_id, warehouse.inventory)))
            if warehouse.inventory != new_value:
                warehouse.inventory = new_value
                warehouse.save(update_fields=["inventory", "updated_at"])
                changed_nodes.add(warehouse.node_id)

        for shop in shops:
            new_value = max(0, int(self.engine.stocks.get(shop.node_id, shop.inventory)))
            if shop.inventory != new_value:
                shop.inventory = new_value
                shop.save(update_fields=["inventory", "updated_at"])
                changed_nodes.add(shop.node_id)

        return changed_nodes

    def _sync_engine_stocks_from_db(self, warehouses, shops):
        """
        Keep in-memory simulation stocks aligned with DB values.

        This prevents tick processing from reverting values manually updated
        via manager/store APIs between ticks.
        """
        if self.engine is None:
            return

        for warehouse in warehouses:
            self.engine.stocks[warehouse.node_id] = int(warehouse.inventory)

        for shop in shops:
            self.engine.stocks[shop.node_id] = int(shop.inventory)

    def _broadcast_edge_activity(
        self,
        before_counts,
        after_counts,
        force_pairs=None,
        departures_by_pair=None,
        arrivals_by_pair=None,
    ):
        force_pairs = set(force_pairs or [])
        departures_by_pair = departures_by_pair or {}
        arrivals_by_pair = arrivals_by_pair or {}
        all_pairs = set(before_counts.keys()) | set(after_counts.keys()) | force_pairs
        for pair in all_pairs:
            before_active = before_counts.get(pair, 0)
            after_active = after_counts.get(pair, 0)
            departure_count = int(departures_by_pair.get(pair, 0))
            arrival_count = int(arrivals_by_pair.get(pair, 0))

            if (
                before_active == after_active
                and pair not in force_pairs
                and departure_count == 0
                and arrival_count == 0
            ):
                continue

            edge_ids = self.route_edge_ids.get(pair) or [f"edge-{pair[0]}-{pair[1]}"]
            for edge_id in edge_ids:
                duration = self.edge_duration_by_id.get(
                    edge_id,
                    self.pair_default_duration.get(pair, self._edge_duration_from_time(1)),
                )
                broadcast_edge_update(
                    edge_id,
                    {
                        "status": "moving" if after_active > 0 else "idle",
                        "activeShipments": int(after_active),
                        "departureCount": departure_count,
                        "arrivalCount": arrival_count,
                        "duration": duration,
                        "updatedAt": datetime.now(timezone.utc).isoformat(),
                    },
                )

    @staticmethod
    def _location_label(node_id, warehouses_map, shops_map):
        if node_id in warehouses_map:
            return warehouses_map[node_id].name

        if node_id in shops_map:
            return shops_map[node_id].name

        return str(node_id)

    def _broadcast_departure_events(self, created_shipments, warehouses_map, shops_map):
        if not created_shipments:
            return

        emitted_at = datetime.now(timezone.utc).isoformat()
        for shipment in created_shipments:
            edge_ids = self.route_edge_ids.get((shipment.from_loc, shipment.to_loc)) or []
            edge_id = edge_ids[0] if edge_ids else f"edge-{shipment.from_loc}-{shipment.to_loc}"

            from_label = self._location_label(shipment.from_loc, warehouses_map, shops_map)
            to_label = self._location_label(shipment.to_loc, warehouses_map, shops_map)

            broadcast_event_log(
                {
                    "event": "truck_departure",
                    "tick": int(self.tick_index),
                    "at": emitted_at,
                    "message": (
                        f"Truck departed: {from_label} -> {to_label} "
                        f"({int(shipment.amount)} units)"
                    ),
                    "shipment": {
                        "fromNodeId": str(shipment.from_loc),
                        "fromLabel": from_label,
                        "toNodeId": str(shipment.to_loc),
                        "toLabel": to_label,
                        "amount": int(shipment.amount),
                        "departureTick": int(shipment.departure_t),
                        "arrivalTick": int(shipment.arrival_t),
                        "edgeId": str(edge_id),
                        "totalCost": int(shipment.total_cost),
                    },
                }
            )

    def _log_redistributions(self, created_shipments, arrived_shipments, warehouses_map, shops_map):
        if created_shipments:
            total_departed = sum(int(shipment.amount) for shipment in created_shipments)
            logger.info(
                "Redistribution tick=%s departures=%s departed_units=%s",
                self.tick_index,
                len(created_shipments),
                total_departed,
            )

            for shipment in created_shipments:
                from_label = self._location_label(shipment.from_loc, warehouses_map, shops_map)
                to_label = self._location_label(shipment.to_loc, warehouses_map, shops_map)
                logger.info(
                    "Departure tick=%s from=%s(%s) to=%s(%s) amount=%s depart_t=%s arrive_t=%s total_cost=%s",
                    self.tick_index,
                    from_label,
                    shipment.from_loc,
                    to_label,
                    shipment.to_loc,
                    int(shipment.amount),
                    int(shipment.departure_t),
                    int(shipment.arrival_t),
                    int(shipment.total_cost),
                )

        if arrived_shipments:
            total_arrived = sum(int(shipment.amount) for shipment in arrived_shipments)
            logger.info(
                "Redistribution tick=%s arrivals=%s arrived_units=%s",
                self.tick_index,
                len(arrived_shipments),
                total_arrived,
            )

            for shipment in arrived_shipments:
                from_label = self._location_label(shipment.from_loc, warehouses_map, shops_map)
                to_label = self._location_label(shipment.to_loc, warehouses_map, shops_map)
                logger.info(
                    "Arrival tick=%s from=%s(%s) to=%s(%s) amount=%s arrival_t=%s",
                    self.tick_index,
                    from_label,
                    shipment.from_loc,
                    to_label,
                    shipment.to_loc,
                    int(shipment.amount),
                    int(shipment.arrival_t),
                )

    def tick_once(self):
        network = self._active_network()
        if network is None:
            logger.debug("Simulation tick skipped: no network definition found")
            return False

        warehouses = list(
            Warehouse.objects.filter(network_definition=network).order_by("name", "node_id")
        )
        shops = list(Shop.objects.filter(network_definition=network).order_by("name", "node_id"))
        route_rows = self._route_rows(network)

        if not warehouses and not shops:
            logger.debug("Simulation tick skipped: no warehouses or shops")
            return False

        if not route_rows:
            logger.debug("Simulation tick skipped: no routes configured")
            return False

        if self._needs_rebuild(network):
            self._build_engine(network, warehouses, shops, route_rows)

        self._sync_engine_stocks_from_db(warehouses, shops)

        # Demand and target can be changed from StoreView between ticks.
        targets = {}
        for shop in shops:
            self.engine.demand_rates[shop.node_id] = int(shop.demand_rate)
            targets[shop.node_id] = int(shop.target)

        before_stocks = dict(self.engine.stocks)
        before_shipments = self._active_shipments_counter(self.engine.in_transit)

        step_result = self.engine.step(self.tick_index, targets) or {}
        created_shipments = list(step_result.get("created_shipments") or [])
        arrived_shipments = list(step_result.get("arrived_shipments") or [])

        changed_nodes = {
            node_id
            for node_id, previous_stock in before_stocks.items()
            if int(previous_stock) != int(self.engine.stocks.get(node_id, previous_stock))
        }

        shipment_touch_nodes = {
            str(shipment.from_loc)
            for shipment in created_shipments
        } | {
            str(shipment.to_loc)
            for shipment in arrived_shipments
        }
        changed_nodes |= shipment_touch_nodes

        changed_nodes |= self._persist_stocks(warehouses, shops)

        warehouses_map = {warehouse.node_id: warehouse for warehouse in warehouses}
        shops_map = {shop.node_id: shop for shop in shops}

        self._log_redistributions(
            created_shipments,
            arrived_shipments,
            warehouses_map,
            shops_map,
        )

        for node_id in changed_nodes:
            if node_id not in warehouses_map and node_id not in shops_map:
                continue
            broadcast_node_update(node_id, self._node_payload(node_id, warehouses_map, shops_map))

        self._broadcast_departure_events(created_shipments, warehouses_map, shops_map)

        after_shipments = self._active_shipments_counter(self.engine.in_transit)
        departures_by_pair = self._active_shipments_counter(created_shipments)
        arrivals_by_pair = self._active_shipments_counter(arrived_shipments)
        forced_pairs = {
            (shipment.from_loc, shipment.to_loc)
            for shipment in created_shipments + arrived_shipments
        }
        self._broadcast_edge_activity(
            before_shipments,
            after_shipments,
            force_pairs=forced_pairs,
            departures_by_pair=departures_by_pair,
            arrivals_by_pair=arrivals_by_pair,
        )

        broadcast_tick(self.tick_index)

        self.tick_index += 1
        return True

    def run_forever(self, tick_seconds, stop_event):
        interval = max(0.5, float(tick_seconds))

        while not stop_event.is_set():
            started_at = time.monotonic()
            try:
                self.tick_once()
            except Exception:
                logger.exception("Simulation tick failed")

            elapsed = time.monotonic() - started_at
            wait_time = max(0.0, interval - elapsed)
            stop_event.wait(wait_time)


_runtime_thread = None
_runtime_stop_event = threading.Event()
_runtime_lock = threading.Lock()


def start_simulation_thread(tick_seconds=None, vehicle_cap=None, horizon=None):
    global _runtime_thread

    with _runtime_lock:
        if _runtime_thread is not None and _runtime_thread.is_alive():
            return

        runtime = SimulationRuntime(vehicle_cap=vehicle_cap, horizon=horizon)
        interval = (
            float(tick_seconds)
            if tick_seconds is not None
            else float(getattr(settings, "SIMULATION_TICK_SECONDS", 1))
        )

        _runtime_stop_event.clear()
        _runtime_thread = threading.Thread(
            target=runtime.run_forever,
            args=(interval, _runtime_stop_event),
            name="simulation-runtime",
            daemon=True,
        )
        _runtime_thread.start()

        logger.info(
            "Simulation thread started: interval=%ss horizon=%s vehicle_cap=%s max_trucks_per_route_tick=%s",
            interval,
            runtime.horizon,
            runtime.vehicle_cap,
            runtime.max_trucks_per_route_tick,
        )


def stop_simulation_thread(timeout=3):
    global _runtime_thread

    with _runtime_lock:
        if _runtime_thread is None:
            return

        _runtime_stop_event.set()
        _runtime_thread.join(timeout=timeout)
        _runtime_thread = None
        logger.info("Simulation thread stopped")
