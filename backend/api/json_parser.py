"""Parse JSON network definitions and create warehouse/shop accounts."""

import json
from pathlib import Path


def _normalize_position(raw_position, field_name):
    if raw_position is None:
        return None

    if isinstance(raw_position, dict):
        x_value = raw_position.get("x")
        y_value = raw_position.get("y")
    elif isinstance(raw_position, (list, tuple)) and len(raw_position) >= 2:
        x_value, y_value = raw_position[0], raw_position[1]
    else:
        raise ValueError(
            f"'{field_name}' must be an object with x/y or a 2-item list"
        )

    try:
        x_position = float(x_value)
        y_position = float(y_value)
    except (ValueError, TypeError):
        raise ValueError(f"'{field_name}' coordinates must be numeric")

    return {
        "x": x_position,
        "y": y_position,
    }


def parse_network_json(json_file_path):
    """
    Parse JSON network definition file.

    Expected JSON format:
    {
        "name": "Distribution Network",
        "warehouses": [
            {"id": "warehouse1", "name": "Main Warehouse", "position": {"x": 200, "y": 0}},
            {"id": "warehouse2", "name": "Secondary Warehouse", "position": {"x": 420, "y": 0}}
        ],
        "shops": [
            {"id": "shop1", "name": "Downtown Store", "inventory": 100, "position": {"x": 200, "y": 220}},
            {"id": "shop2", "name": "Uptown Store", "inventory": 50, "position": {"x": 420, "y": 220}}
        ],
        "routes": [
            {"from": "warehouse1", "to": "shop1", "time": 1, "cost": 10.5}
        ]
    }

    Args:
        json_file_path: Path to JSON file

    Returns:
        dict: Parsed definition with 'warehouses', 'shops', and 'routes' lists

    Raises:
        ValueError: If JSON is invalid or malformed
    """
    path = Path(json_file_path)
    if not path.exists():
        raise ValueError(f"JSON file does not exist: {json_file_path}")

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON format: {str(e)}")
    except Exception as e:
        raise ValueError(f"Error reading JSON file: {str(e)}")

    if not isinstance(data, dict):
        raise ValueError("JSON root must be an object")

    # Extract and validate warehouses
    warehouses = data.get("warehouses", [])
    if not isinstance(warehouses, list):
        raise ValueError("'warehouses' must be a list")

    validated_warehouses = []
    for idx, warehouse in enumerate(warehouses):
        if not isinstance(warehouse, dict):
            raise ValueError(f"Warehouse at index {idx} must be an object")

        warehouse_id = warehouse.get("id")
        warehouse_name = warehouse.get("name", str(warehouse_id))
        warehouse_inventory = warehouse.get("inventory", warehouse.get("initial_stock", 500))
        warehouse_position = _normalize_position(
            warehouse.get("position", warehouse.get("location")),
            f"warehouses[{idx}].position",
        )

        if not warehouse_id:
            raise ValueError(f"Warehouse at index {idx} missing 'id' field")

        try:
            inventory = int(warehouse_inventory)
        except (ValueError, TypeError):
            raise ValueError(
                f"Warehouse '{warehouse_id}' inventory must be a number, got {warehouse_inventory}"
            )

        warehouse_item = {
            "id": str(warehouse_id),
            "name": str(warehouse_name),
            "inventory": max(0, inventory),
        }
        if warehouse_position is not None:
            warehouse_item["position"] = warehouse_position

        validated_warehouses.append(warehouse_item)

    # Extract and validate shops
    shops = data.get("shops", [])
    if not isinstance(shops, list):
        raise ValueError("'shops' must be a list")

    validated_shops = []
    for idx, shop in enumerate(shops):
        if not isinstance(shop, dict):
            raise ValueError(f"Shop at index {idx} must be an object")

        shop_id = shop.get("id")
        shop_name = shop.get("name", str(shop_id))
        shop_inventory = shop.get("inventory", 0)
        # Shops start from zero planning inputs and workers set them later via StoreView.
        shop_target = 0
        shop_demand_rate = 0
        shop_position = _normalize_position(
            shop.get("position", shop.get("location")),
            f"shops[{idx}].position",
        )

        if not shop_id:
            raise ValueError(f"Shop at index {idx} missing 'id' field")

        try:
            inventory = int(shop_inventory)
        except (ValueError, TypeError):
            raise ValueError(
                f"Shop '{shop_id}' inventory must be a number, got {shop_inventory}"
            )

        target = int(shop_target)
        demand_rate = int(shop_demand_rate)

        shop_item = {
            "id": str(shop_id),
            "name": str(shop_name),
            "inventory": max(0, inventory),
            "target": max(0, target),
            "demand_rate": max(0, demand_rate),
        }
        if shop_position is not None:
            shop_item["position"] = shop_position

        validated_shops.append(shop_item)

    node_ids = {
        item["id"] for item in validated_warehouses
    } | {
        item["id"] for item in validated_shops
    }

    # Extract and validate routes
    raw_routes = data.get("routes")
    if raw_routes is None:
        raw_routes = data.get("edges")
    if raw_routes is None:
        raw_routes = data.get("connections", [])

    if not isinstance(raw_routes, list):
        raise ValueError("'routes' must be a list")

    validated_routes = []
    for idx, route in enumerate(raw_routes):
        if not isinstance(route, dict):
            raise ValueError(f"Route at index {idx} must be an object")

        route_from = (
            route.get("from")
            or route.get("source")
            or route.get("fromId")
            or route.get("from_id")
            or route.get("start")
        )
        route_to = (
            route.get("to")
            or route.get("target")
            or route.get("toId")
            or route.get("to_id")
            or route.get("end")
        )

        if not route_from or not route_to:
            raise ValueError(
                f"Route at index {idx} must include both source and target nodes"
            )

        route_from = str(route_from)
        route_to = str(route_to)

        if route_from not in node_ids:
            raise ValueError(
                f"Route at index {idx} references unknown source node '{route_from}'"
            )

        if route_to not in node_ids:
            raise ValueError(
                f"Route at index {idx} references unknown target node '{route_to}'"
            )

        normalized_route = {
            "from": route_from,
            "to": route_to,
        }

        if route.get("id") is not None:
            normalized_route["id"] = str(route.get("id"))

        for numeric_field in ("time", "cost", "distance"):
            if route.get(numeric_field) is None:
                continue
            try:
                normalized_route[numeric_field] = float(route[numeric_field])
            except (ValueError, TypeError):
                raise ValueError(
                    f"Route '{route_from}' -> '{route_to}' field "
                    f"'{numeric_field}' must be numeric"
                )

        for key, value in route.items():
            if key in {
                "id",
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
                "time",
                "cost",
                "distance",
            }:
                continue
            normalized_route[key] = value

        validated_routes.append(normalized_route)

    return {
        "warehouses": validated_warehouses,
        "shops": validated_shops,
        "routes": validated_routes,
    }
