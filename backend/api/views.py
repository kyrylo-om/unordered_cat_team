from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.middleware.csrf import get_token
from django.contrib.auth import authenticate, login, logout
from django_ratelimit.decorators import ratelimit
import json
import math

from .models import NetworkDefinition, Warehouse, Shop, Route
from .user_roles import get_user_role, ROLE_WAREHOUSE_WORKER, ROLE_SHOP_WORKER
from .json_parser import parse_network_json
from .realtime import (
    broadcast_node_update,
    get_edge_activity_snapshot,
    resolve_reverse_edge_id,
    resolve_route_edge_id,
)


def _definition_order(definition, key):
    values = definition.get(key, []) if isinstance(definition, dict) else []
    return {
        str(item.get("id")): index
        for index, item in enumerate(values)
        if isinstance(item, dict) and item.get("id") is not None
    }


def _edge_duration_from_time(travel_time):
    tick_seconds = float(getattr(settings, "SIMULATION_TICK_SECONDS", 1))
    try:
        seconds = max(0.2, float(travel_time) * tick_seconds)
    except (TypeError, ValueError):
        seconds = max(0.2, tick_seconds)

    return f"{seconds:.2f}s"


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


def _load_network_definition(network):
    definition = network.definition if isinstance(network.definition, dict) else {}

    if not getattr(network, "json_file", None):
        return definition

    try:
        file_definition = parse_network_json(network.json_file.path)
    except Exception:
        return definition

    return file_definition


def _definition_items_by_id(definition, key):
    values = definition.get(key, []) if isinstance(definition, dict) else []
    return {
        str(item.get("id")): item
        for item in values
        if isinstance(item, dict) and item.get("id") is not None
    }


def _node_position(definition_item):
    if not isinstance(definition_item, dict):
        return {"x": 0, "y": 0}

    position = definition_item.get("position")
    if not isinstance(position, dict):
        return {"x": 0, "y": 0}

    try:
        return {
            "x": float(position.get("x", 0)),
            "y": float(position.get("y", 0)),
        }
    except (TypeError, ValueError):
        return {"x": 0, "y": 0}


def _route_items(definition):
    if not isinstance(definition, dict):
        return []

    for key in ("routes", "edges", "connections"):
        value = definition.get(key)
        if isinstance(value, list):
            return value

    return []


def _edge_payload(source, target, index, route_data=None):
    route_data = route_data or {}
    edge_id = (
        route_data.get("id")
        or route_data.get("edgeId")
        or route_data.get("edge_id")
        or f"edge-{source}-{target}-{index}"
    )
    data = {
        key: value
        for key, value in route_data.items()
        if key
        not in {
            "id",
            "edgeId",
            "edge_id",
            "from",
            "to",
            "source",
            "target",
            "fromId",
            "from_id",
            "toId",
            "to_id",
            "start",
            "end",
        }
    }

    if "status" not in data:
        data["status"] = "idle"

    route_time = _route_tick_count(
        route_data.get("distance"),
        route_data.get("time", route_data.get("travel_time", 1)),
    )
    data["time"] = route_time
    data["duration"] = _edge_duration_from_time(route_time)

    return {
        "id": str(edge_id),
        "source": str(source),
        "target": str(target),
        "type": "moving",
        "data": data,
    }


def _build_definition_edges(definition, valid_node_ids):
    edges = []
    for index, route in enumerate(_route_items(definition)):
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
        if source not in valid_node_ids or target not in valid_node_ids:
            continue

        edges.append(_edge_payload(source, target, index, route))

    return edges


def _split_evenly(items, group_count):
    if group_count <= 0:
        return []

    base_size, remainder = divmod(len(items), group_count)
    groups = []
    start = 0
    for index in range(group_count):
        group_size = base_size + (1 if index < remainder else 0)
        groups.append(items[start:start + group_size])
        start += group_size

    return groups


def _build_generated_edges(warehouses, shops):
    edges = []
    if warehouses:
        for index in range(len(warehouses) - 1):
            source = warehouses[index].node_id
            target = warehouses[index + 1].node_id
            edges.append(
                _edge_payload(
                    source,
                    target,
                    len(edges),
                    {"generated": True},
                )
            )

        for warehouse, assigned_shops in zip(
            warehouses,
            _split_evenly(shops, len(warehouses)),
        ):
            for shop in assigned_shops:
                edges.append(
                    _edge_payload(
                        warehouse.node_id,
                        shop.node_id,
                        len(edges),
                        {"generated": True},
                    )
                )

        return edges

    for index in range(len(shops) - 1):
        edges.append(
            _edge_payload(
                shops[index].node_id,
                shops[index + 1].node_id,
                len(edges),
                {"generated": True},
            )
        )

    return edges


def hello(request):
    """Legacy endpoint for testing backend connectivity."""
    return JsonResponse({"message": "Hello from Django backend"})


@require_http_methods(["GET"])
def map_layout_view(request):
    """Get the active network layout (graph nodes/edges) from JSON definition."""
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Not authenticated"}, status=401)

    # Get the active network definition
    network = NetworkDefinition.objects.filter(is_active=True).first()
    if network is None:
        network = NetworkDefinition.objects.first()

    if network is None:
        return JsonResponse({"nodes": [], "edges": []})

    definition = _load_network_definition(network)
    warehouse_order = _definition_order(definition, "warehouses")
    shop_order = _definition_order(definition, "shops")
    warehouse_positions = _definition_items_by_id(definition, "warehouses")
    shop_positions = _definition_items_by_id(definition, "shops")

    # Build nodes from warehouses and shops
    nodes = []
    warehouses = sorted(
        Warehouse.objects.filter(network_definition=network),
        key=lambda warehouse: (
            warehouse_order.get(str(warehouse.node_id), len(warehouse_order)),
            warehouse.name.casefold(),
            str(warehouse.node_id),
        ),
    )
    for warehouse in warehouses:
        nodes.append({
            "id": warehouse.node_id,
            "data": {
                "label": warehouse.name,
                "type": "warehouse",
                "inventory": warehouse.inventory,
            },
            "position": _node_position(warehouse_positions.get(str(warehouse.node_id))),
        })

    shops = sorted(
        Shop.objects.filter(network_definition=network),
        key=lambda shop: (
            shop_order.get(str(shop.node_id), len(shop_order)),
            shop.name.casefold(),
            str(shop.node_id),
        ),
    )
    shop_node_ids = {str(shop.node_id) for shop in shops}
    for shop in shops:
        nodes.append({
            "id": shop.node_id,
            "data": {
                "label": shop.name,
                "type": "shop",
                "inventory": shop.inventory,
                "target": shop.target,
                "demandRate": shop.demand_rate,
            },
            "position": _node_position(shop_positions.get(str(shop.node_id))),
        })

    node_id_set = {str(node["id"]) for node in nodes}
    edge_activity = get_edge_activity_snapshot()
    routes_bidirectional = bool(getattr(settings, "SIMULATION_ROUTES_BIDIRECTIONAL", True))
    route_rows = Route.objects.filter(network_definition=network, is_active=True).order_by("id")
    if route_rows.exists():
        edges = []
        for index, route in enumerate(route_rows):
            source = str(route.source_node_id)
            target = str(route.target_node_id)
            if source not in node_id_set or target not in node_id_set:
                continue

            edge_id = resolve_route_edge_id(route, fallback_index=index)
            route_meta = route.metadata if isinstance(route.metadata, dict) else {}
            route_time = _route_tick_count(route_meta.get("distance"), route.travel_time)
            base_data = {
                **route_meta,
                "status": route_meta.get("status", "idle"),
                "time": route_time,
                "cost": route.transport_cost,
                "duration": _edge_duration_from_time(route_time),
                "targetType": "shop" if target in shop_node_ids else "warehouse",
            }
            edges.append(
                {
                    "id": edge_id,
                    "source": source,
                    "target": target,
                    "type": "moving",
                    "data": {
                        **base_data,
                        **edge_activity.get(str(edge_id), {}),
                    },
                }
            )
    else:
        edges = _build_definition_edges(definition, node_id_set)
        if not edges:
            edges = _build_generated_edges(warehouses, shops)

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

    return JsonResponse(
        {
            "nodes": nodes,
            "edges": edges,
            "layoutName": network.name,
        }
    )


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
                    "role": get_user_role(user.id),
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
        return JsonResponse({"authenticated": False, "user": None})

    user = request.user
    return JsonResponse(
        {
            "authenticated": True,
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "role": get_user_role(user.id),
            }
        }
    )


@require_http_methods(["POST"])
def logout_view(request):
    """Logout user and clear session."""
    logout(request)
    return JsonResponse({"message": "Logged out successfully"})


@require_http_methods(["GET"])
def store_status_view(request):
    """
    Get the current warehouse/shop status for a worker user.

    Returns name, type, and inventory/demand levels.
    Accessible to both warehouse and shop workers for their own location.
    """
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Not authenticated"}, status=401)

    role = get_user_role(request.user.id)
    if role not in [ROLE_WAREHOUSE_WORKER, ROLE_SHOP_WORKER]:
        return JsonResponse(
            {"error": "Unauthorized - warehouse/shop worker access only"}, status=403
        )

    # Try to find warehouse first
    warehouse = Warehouse.objects.filter(user_id=request.user.id).first()
    if warehouse:
        return JsonResponse(
            {
                "name": warehouse.name,
                "nodeId": warehouse.node_id,
                "type": "warehouse",
                "inventory": warehouse.inventory,
                "target": None,
                "demandRate": 0,
            }
        )

    # Try to find shop
    shop = Shop.objects.filter(user_id=request.user.id).first()
    if shop:
        return JsonResponse(
            {
                "name": shop.name,
                "nodeId": shop.node_id,
                "type": "shop",
                "inventory": shop.inventory,
                "target": shop.target,
                "demandRate": shop.demand_rate,
            }
        )

    return JsonResponse(
        {"error": "Warehouse/shop not found for this user"}, status=404
    )


@require_http_methods(["POST"])
def store_demand_view(request):
    """
    Update store simulation inputs for the authenticated shop worker.

    Accepts JSON: {"target": <number>, "demandRate": <number>}
    Optionally accepts inventory override as {"inventory": <number>}.
    """
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Not authenticated"}, status=401)

    role = get_user_role(request.user.id)
    if role != ROLE_SHOP_WORKER:
        return JsonResponse(
            {"error": "Unauthorized - shop worker access only"}, status=403
        )

    try:
        data = json.loads(request.body)
        target_value = data.get("target")
        demand_rate_value = data.get("demandRate", data.get("demand_rate"))
        inventory_value = data.get("inventory")

        if (
            target_value is None
            and demand_rate_value is None
            and inventory_value is None
        ):
            return JsonResponse(
                {"error": "At least one of target, demandRate, inventory is required"}, status=400
            )

        shop = Shop.objects.filter(user_id=request.user.id).first()
        if shop:
            if target_value is not None:
                shop.target = max(0, int(target_value))

            if demand_rate_value is not None:
                shop.demand_rate = max(0, int(demand_rate_value))

            if inventory_value is not None:
                shop.inventory = max(0, int(inventory_value))

            shop.save()

            broadcast_node_update(
                shop.node_id,
                {
                    "label": shop.name,
                    "type": "shop",
                    "inventory": shop.inventory,
                    "target": shop.target,
                    "demandRate": shop.demand_rate,
                },
            )

            return JsonResponse(
                {
                    "success": True,
                    "name": shop.name,
                    "type": "shop",
                    "inventory": shop.inventory,
                    "target": shop.target,
                    "demandRate": shop.demand_rate,
                    "message": "Store simulation settings updated successfully",
                }
            )

        return JsonResponse(
            {"error": "Warehouse/shop not found for this user"}, status=404
        )

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    except (ValueError, TypeError):
        return JsonResponse(
            {"error": "target, demandRate, and inventory must be numbers"},
            status=400,
        )
    except Exception as e:
        return JsonResponse({"error": f"An error occurred: {str(e)}"}, status=500)


@require_http_methods(["POST"])
def simulation_node_metrics_view(request):
    """
    Update simulation metrics for a selected node from manager Details Panel.

    Accepts JSON:
    {
        "nodeId": "...",
        "inventory": <number>,
        "target": <number>,
        "demandRate": <number>
    }
    """
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Not authenticated"}, status=401)

    role = get_user_role(request.user.id)
    if role == ROLE_SHOP_WORKER:
        return JsonResponse(
            {"error": "Unauthorized - manager/warehouse access only"},
            status=403,
        )

    try:
        data = json.loads(request.body)
        node_id = data.get("nodeId", data.get("id"))
        inventory_value = data.get("inventory")
        target_value = data.get("target")
        demand_rate_value = data.get("demandRate", data.get("demand_rate"))

        if node_id is None:
            return JsonResponse({"error": "nodeId is required"}, status=400)

        if (
            inventory_value is None
            and target_value is None
            and demand_rate_value is None
        ):
            return JsonResponse(
                {"error": "At least one of inventory, target, demandRate is required"},
                status=400,
            )

        network = _active_network_definition()
        if network is None:
            return JsonResponse({"error": "Network is not configured"}, status=404)

        node_id = str(node_id)

        warehouse = Warehouse.objects.filter(
            network_definition=network,
            node_id=node_id,
        ).first()
        if warehouse:
            if inventory_value is not None:
                warehouse.inventory = max(0, int(inventory_value))
                warehouse.save(update_fields=["inventory", "updated_at"])

            payload = {
                "label": warehouse.name,
                "type": "warehouse",
                "inventory": warehouse.inventory,
            }
            broadcast_node_update(warehouse.node_id, payload)
            return JsonResponse(
                {
                    "success": True,
                    "node": {
                        "id": warehouse.node_id,
                        "data": payload,
                    },
                }
            )

        shop = Shop.objects.filter(
            network_definition=network,
            node_id=node_id,
        ).first()
        if shop:
            if inventory_value is not None:
                shop.inventory = max(0, int(inventory_value))

            if target_value is not None:
                shop.target = max(0, int(target_value))

            if demand_rate_value is not None:
                shop.demand_rate = max(0, int(demand_rate_value))

            shop.save(update_fields=["inventory", "target", "demand_rate", "updated_at"])

            payload = {
                "label": shop.name,
                "type": "shop",
                "inventory": shop.inventory,
                "target": shop.target,
                "demandRate": shop.demand_rate,
            }
            broadcast_node_update(shop.node_id, payload)
            return JsonResponse(
                {
                    "success": True,
                    "node": {
                        "id": shop.node_id,
                        "data": payload,
                    },
                }
            )

        return JsonResponse({"error": "Node not found"}, status=404)

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    except (ValueError, TypeError):
        return JsonResponse(
            {"error": "inventory, target, and demandRate must be numbers"},
            status=400,
        )
    except Exception as e:
        return JsonResponse({"error": f"An error occurred: {str(e)}"}, status=500)


@require_http_methods(["POST"])
def change_password_view(request):
    """
    Allow authenticated users to change their password.

    Accepts JSON: {"old_password": "...", "new_password": "..."}
    """
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Not authenticated"}, status=401)

    try:
        data = json.loads(request.body)
        old_password = data.get("old_password")
        new_password = data.get("new_password")

        if not old_password or not new_password:
            return JsonResponse(
                {"error": "old_password and new_password are required"}, status=400
            )

        # Verify old password
        user = authenticate(request, username=request.user.username, password=old_password)
        if user is None:
            return JsonResponse({"error": "Old password is incorrect"}, status=401)

        # Update password
        request.user.set_password(new_password)
        request.user.save()

        return JsonResponse(
            {"success": True, "message": "Password changed successfully"}
        )

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    except Exception as e:
        return JsonResponse({"error": f"An error occurred: {str(e)}"}, status=500)
