from django.conf import settings
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
import math

from .models import NetworkDefinition, Route, Shop, Warehouse
from .realtime import (
    MANAGER_DASHBOARD_GROUP,
    get_edge_activity_snapshot,
    resolve_reverse_edge_id,
    resolve_route_edge_id,
)
from .simulation import start_simulation_thread
from .user_roles import ROLE_SHOP_WORKER, get_user_role


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


def _active_network_definition():
    network = NetworkDefinition.objects.filter(is_active=True).first()
    if network is None:
        network = NetworkDefinition.objects.first()
    return network


def _definition_route_list(definition):
    if not isinstance(definition, dict):
        return []

    for key in ("routes", "edges", "connections"):
        value = definition.get(key)
        if isinstance(value, list):
            return value

    return []


def _generated_edges_for_snapshot(warehouses, shops):
    edges = []
    if warehouses:
        for index in range(len(warehouses) - 1):
            source = str(warehouses[index].node_id)
            target = str(warehouses[index + 1].node_id)
            edges.append(
                {
                    "id": f"edge-{source}-{target}-{index}",
                    "source": source,
                    "target": target,
                    "type": "moving",
                    "data": {
                        "status": "idle",
                        "targetType": "warehouse",
                        "duration": _edge_duration_from_time(1),
                        "generated": True,
                    },
                }
            )

        if shops:
            for index, shop in enumerate(shops):
                warehouse = warehouses[index % len(warehouses)]
                source = str(warehouse.node_id)
                target = str(shop.node_id)
                edges.append(
                    {
                        "id": f"edge-{source}-{target}-shop-{index}",
                        "source": source,
                        "target": target,
                        "type": "moving",
                        "data": {
                            "status": "idle",
                            "targetType": "shop",
                            "duration": _edge_duration_from_time(1),
                            "generated": True,
                        },
                    }
                )

        return edges

    for index in range(len(shops) - 1):
        source = str(shops[index].node_id)
        target = str(shops[index + 1].node_id)
        edges.append(
            {
                "id": f"edge-{source}-{target}-{index}",
                "source": source,
                "target": target,
                "type": "moving",
                "data": {
                    "status": "idle",
                    "targetType": "shop",
                    "duration": _edge_duration_from_time(1),
                    "generated": True,
                },
            }
        )

    return edges


def _snapshot_payload():
    network = _active_network_definition()
    if network is None:
        return {"nodes": [], "edges": []}

    warehouses = Warehouse.objects.filter(network_definition=network).order_by("name")
    shops = Shop.objects.filter(network_definition=network).order_by("name")
    shop_node_ids = {str(shop.node_id) for shop in shops}

    nodes = []
    for warehouse in warehouses:
        nodes.append(
            {
                "id": warehouse.node_id,
                "data": {
                    "label": warehouse.name,
                    "type": "warehouse",
                    "inventory": warehouse.inventory,
                },
            }
        )

    for shop in shops:
        nodes.append(
            {
                "id": shop.node_id,
                "data": {
                    "label": shop.name,
                    "type": "shop",
                    "inventory": shop.inventory,
                    "target": shop.target,
                    "demandRate": shop.demand_rate,
                },
            }
        )

    route_rows = Route.objects.filter(network_definition=network, is_active=True).order_by(
        "id"
    )
    edge_activity = get_edge_activity_snapshot()
    routes_bidirectional = bool(getattr(settings, "SIMULATION_ROUTES_BIDIRECTIONAL", True))
    edges = []
    for index, route in enumerate(route_rows):
        edge_id = resolve_route_edge_id(route, fallback_index=index)
        route_meta = route.metadata if isinstance(route.metadata, dict) else {}
        route_time = _route_tick_count(route_meta.get("distance"), route.travel_time)
        edges.append(
            {
                "id": edge_id,
                "source": route.source_node_id,
                "target": route.target_node_id,
                "type": "moving",
                "data": {
                    "status": "idle",
                    "cost": route.transport_cost,
                    "time": route_time,
                    "duration": _edge_duration_from_time(route_time),
                    "targetType": "shop"
                    if str(route.target_node_id) in shop_node_ids
                    else "warehouse",
                    **edge_activity.get(str(edge_id), {}),
                },
            }
        )

    if not edges:
        definition = network.definition if isinstance(network.definition, dict) else {}
        node_id_set = {str(node["id"]) for node in nodes}
        for index, route in enumerate(_definition_route_list(definition)):
            if not isinstance(route, dict):
                continue

            source = (
                route.get("source")
                or route.get("from")
                or route.get("fromId")
                or route.get("from_id")
                or route.get("start")
            )
            target = (
                route.get("target")
                or route.get("to")
                or route.get("toId")
                or route.get("to_id")
                or route.get("end")
            )

            if source is None or target is None:
                continue

            source = str(source)
            target = str(target)
            if source not in node_id_set or target not in node_id_set:
                continue

            edge_id = (
                route.get("id")
                or route.get("edgeId")
                or route.get("edge_id")
                or f"edge-{source}-{target}-{index}"
            )
            route_time = _route_tick_count(
                route.get("distance"),
                route.get("time", route.get("travel_time", 1)),
            )

            edges.append(
                {
                    "id": str(edge_id),
                    "source": source,
                    "target": target,
                    "type": "moving",
                    "data": {
                        "status": str(route.get("status", "idle")),
                        "cost": route.get("cost", route.get("transport_cost", 1.0)),
                        "time": route_time,
                        "duration": _edge_duration_from_time(route_time),
                        "targetType": "shop" if target in shop_node_ids else "warehouse",
                        **edge_activity.get(str(edge_id), {}),
                    },
                }
            )

    if not edges:
        edges = _generated_edges_for_snapshot(list(warehouses), list(shops))

    if routes_bidirectional and edges:
        existing_pairs = {(str(edge["source"]), str(edge["target"])) for edge in edges}
        reverse_edges = []
        for edge in edges:
            source = str(edge.get("source"))
            target = str(edge.get("target"))
            if (target, source) in existing_pairs:
                continue

            edge_id = str(edge.get("id"))
            edge_data = edge.get("data") or {}
            route_time = _route_tick_count(
                edge_data.get("distance"),
                edge_data.get("time", edge_data.get("travel_time", 1)),
            )
            reverse_edge_id = resolve_reverse_edge_id(edge_id)

            reverse_edges.append(
                {
                    "id": reverse_edge_id,
                    "source": target,
                    "target": source,
                    "type": "moving",
                    "data": {
                        **edge_data,
                        "status": str(edge_data.get("status", "idle")),
                        "time": route_time,
                        "duration": _edge_duration_from_time(route_time),
                        "targetType": "shop" if source in shop_node_ids else "warehouse",
                        **edge_activity.get(str(reverse_edge_id), {}),
                    },
                }
            )
            existing_pairs.add((target, source))

        edges.extend(reverse_edges)

    for edge in edges:
        edge_state = edge_activity.get(str(edge.get("id")), {})
        if edge_state:
            edge["data"] = {
                **(edge.get("data") or {}),
                **edge_state,
            }

    return {"nodes": nodes, "edges": edges, "layoutName": network.name}


def _edge_duration_from_time(travel_time):
    tick_seconds = float(getattr(settings, "SIMULATION_TICK_SECONDS", 1))
    try:
        seconds = max(0.2, float(travel_time) * tick_seconds)
    except (TypeError, ValueError):
        seconds = max(0.2, tick_seconds)

    return f"{seconds:.2f}s"


class ManagerDashboardConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        # Idempotent start: guarantees tick loop is alive when managers subscribe.
        start_simulation_thread()

        user = self.scope.get("user")
        if (user is None or not user.is_authenticated) and not settings.DEBUG:
            await self.close(code=4401)
            return

        if user is not None and user.is_authenticated:
            role = await database_sync_to_async(get_user_role)(user.id)
            if role == ROLE_SHOP_WORKER and not settings.DEBUG:
                await self.close(code=4403)
                return

        await self.channel_layer.group_add(MANAGER_DASHBOARD_GROUP, self.channel_name)
        await self.accept()

        snapshot = await database_sync_to_async(_snapshot_payload)()
        await self.send_json({"type": "SNAPSHOT", "payload": snapshot})

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(MANAGER_DASHBOARD_GROUP, self.channel_name)

    async def manager_event(self, event):
        await self.send_json(
            {
                "type": event.get("event_type"),
                "payload": event.get("payload", {}),
            }
        )
