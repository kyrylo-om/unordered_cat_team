from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.middleware.csrf import get_token
from django.contrib.auth import authenticate, login, logout
from django_ratelimit.decorators import ratelimit
import json

from .models import NetworkDefinition, Warehouse, Shop
from .user_roles import get_user_role, ROLE_WAREHOUSE_WORKER, ROLE_SHOP_WORKER
from .json_parser import parse_network_json


def _definition_order(definition, key):
    values = definition.get(key, []) if isinstance(definition, dict) else []
    return {
        str(item.get("id")): index
        for index, item in enumerate(values)
        if isinstance(item, dict) and item.get("id") is not None
    }


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
                "type": "warehouse"
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
    for shop in shops:
        nodes.append({
            "id": shop.node_id,
            "data": {
                "label": shop.name,
                "type": "shop",
                "inventory": shop.inventory
            },
            "position": _node_position(shop_positions.get(str(shop.node_id))),
        })

    node_id_set = {str(node["id"]) for node in nodes}
    edges = _build_definition_edges(definition, node_id_set)
    if not edges:
        edges = _build_generated_edges(warehouses, shops)

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
        return JsonResponse({"error": "Not authenticated"}, status=401)

    user = request.user
    return JsonResponse(
        {
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
                "inventory": None,  # Warehouses don't have inventory field
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
            }
        )

    return JsonResponse(
        {"error": "Warehouse/shop not found for this user"}, status=404
    )


@require_http_methods(["POST"])
def store_demand_view(request):
    """
    Update inventory or demand level for a shop/warehouse.

    Accepts JSON: {"inventory": <number>} for shops
    Accessible to both warehouse and shop workers for their own location.
    """
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Not authenticated"}, status=401)

    role = get_user_role(request.user.id)
    if role not in [ROLE_WAREHOUSE_WORKER, ROLE_SHOP_WORKER]:
        return JsonResponse(
            {"error": "Unauthorized - warehouse/shop worker access only"}, status=403
        )

    try:
        data = json.loads(request.body)
        inventory_level = data.get("inventory")

        if inventory_level is None:
            return JsonResponse(
                {"error": "inventory field is required"}, status=400
            )

        # Try to update warehouse first (warehouses can have inventory too)
        warehouse = Warehouse.objects.filter(user_id=request.user.id).first()
        if warehouse:
            # For now, warehouses don't persist inventory
            return JsonResponse(
                {
                    "success": True,
                    "name": warehouse.name,
                    "type": "warehouse",
                    "message": "Update received (not persisted yet)",
                }
            )

        # Try to update shop
        shop = Shop.objects.filter(user_id=request.user.id).first()
        if shop:
            shop.inventory = max(0, int(inventory_level))
            shop.save()
            return JsonResponse(
                {
                    "success": True,
                    "name": shop.name,
                    "type": "shop",
                    "inventory": shop.inventory,
                    "message": "Inventory updated successfully",
                }
            )

        return JsonResponse(
            {"error": "Warehouse/shop not found for this user"}, status=404
        )

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    except (ValueError, TypeError):
        return JsonResponse({"error": "inventory must be a number"}, status=400)
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
