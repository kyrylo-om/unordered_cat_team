import logging
import math
import secrets
import string

from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction

logger = logging.getLogger(__name__)


def _route_tick_count(route_data):
    distance_value = route_data.get("distance")
    if distance_value is not None:
        try:
            distance = float(distance_value)
            if distance > 0:
                return max(1, int(math.ceil(distance)))
        except (TypeError, ValueError):
            pass

    for key in ("time", "travel_time"):
        value = route_data.get(key)
        if value is None:
            continue
        try:
            route_time = float(value)
        except (TypeError, ValueError):
            continue

        if route_time > 0:
            return max(1, int(math.ceil(route_time)))

    return 1


class StoreAccountService:
    """Service for managing automatic warehouse/shop account creation from network definitions."""

    @staticmethod
    def generate_secure_password(length=16):
        """
        Generate a secure random password that passes Django validation.

        Args:
                length: Password length (default 16 characters)

        Returns:
                str: A secure random password

        Raises:
                ValidationError: If generated password fails Django validation
        """
        # Character sets for password generation
        characters = string.ascii_letters + string.digits + "!@#$%^&*"

        # Generate password ensuring it has mixed character types
        password = (
            secrets.choice(string.ascii_uppercase)
            + secrets.choice(string.ascii_lowercase)
            + secrets.choice(string.digits)
            + secrets.choice("!@#$%^&*")
            + "".join(secrets.choice(characters) for _ in range(length - 4))
        )

        # Shuffle the password to avoid predictable patterns
        password_list = list(password)
        for i in reversed(range(1, len(password_list))):
            j = secrets.randbelow(i + 1)
            password_list[i], password_list[j] = password_list[j], password_list[i]

        final_password = "".join(password_list)

        # Validate the password meets Django requirements
        try:
            validate_password(final_password)
        except ValidationError as e:
            logger.warning(f"Generated password failed validation: {e}, retrying...")
            return StoreAccountService.generate_secure_password(length)

        return final_password

    @staticmethod
    def _sanitize_username(text):
        """
        Sanitize a string to be a valid Django username.
        Removes special characters and spaces.

        Args:
                text: Original text

        Returns:
                str: Sanitized username
        """
        import re
        # Remove anything that's not alphanumeric or underscore
        sanitized = re.sub(r'[^a-zA-Z0-9_]', '', str(text))
        # Limit to 150 characters (Django username max)
        return sanitized[:150]

    @staticmethod
    def create_accounts_from_json(network_definition, parsed_definition):
        """
        Create warehouse and shop accounts from JSON network definition.
        All users share the same password from the network definition.

        Args:
                network_definition: NetworkDefinition instance
                parsed_definition: Dict with 'warehouses' and 'shops' lists from parse_network_json()

        Returns:
                List[Dict]: List of created credentials with 'name', 'username', 'type'

        Raises:
                Exception: Database or account creation errors
        """
        from .models import (
            Warehouse,
            Shop,
            WarehouseCredential,
            ShopCredential,
            Route,
        )

        created_credentials = []
        shared_password = network_definition.shared_password

        try:
            with transaction.atomic():
                # Delete existing accounts for this network
                existing_warehouses = Warehouse.objects.filter(
                    network_definition=network_definition
                ).select_related("user")
                warehouse_user_ids = []

                for warehouse in existing_warehouses:
                    if warehouse.user:
                        warehouse_user_ids.append(warehouse.user.id)

                existing_warehouses.delete()

                # Delete existing shops
                existing_shops = Shop.objects.filter(
                    network_definition=network_definition
                ).select_related("user")
                shop_user_ids = []

                for shop in existing_shops:
                    if shop.user:
                        shop_user_ids.append(shop.user.id)

                existing_shops.delete()

                # Delete existing topology routes for this network
                Route.objects.filter(network_definition=network_definition).delete()

                # Delete associated users
                all_user_ids = warehouse_user_ids + shop_user_ids
                if all_user_ids:
                    User.objects.filter(id__in=all_user_ids).delete()

                # Create warehouse accounts
                for warehouse_data in parsed_definition.get("warehouses", []):
                    warehouse_id = warehouse_data["id"]
                    warehouse_name = warehouse_data["name"]
                    warehouse_inventory = max(0, int(warehouse_data.get("inventory", 500)))
                    username = StoreAccountService._sanitize_username(warehouse_id)

                    # Ensure username uniqueness
                    base_username = username
                    counter = 1
                    while User.objects.filter(username=username).exists():
                        username = f"{base_username}_{counter}"
                        counter += 1

                    # Create User with shared password
                    user = User.objects.create_user(
                        username=username,
                        password=shared_password,
                        is_staff=False,
                        is_active=True,
                    )

                    # Create Warehouse record
                    warehouse = Warehouse.objects.create(
                        name=warehouse_name,
                        node_id=warehouse_id,
                        network_definition=network_definition,
                        user=user,
                        inventory=warehouse_inventory,
                    )

                    # Set role
                    from .user_roles import set_user_role, ROLE_WAREHOUSE_WORKER
                    set_user_role(user.id, ROLE_WAREHOUSE_WORKER)

                    # Create credential record (stores username for reference)
                    WarehouseCredential.objects.create(
                        warehouse=warehouse,
                        username=username,
                        password=shared_password,
                        expires_at=None,  # No expiry for shared password
                    )

                    created_credentials.append({
                        "name": warehouse_name,
                        "username": username,
                        "type": "warehouse",
                    })

                    logger.info(
                        f"Created warehouse account: username={username}, "
                        f"warehouse={warehouse_name}"
                    )

                # Create shop accounts
                for shop_data in parsed_definition.get("shops", []):
                    shop_id = shop_data["id"]
                    shop_name = shop_data["name"]
                    shop_inventory = shop_data.get("inventory", 0)
                    # Planning inputs are initialized to zero and later updated by shop workers.
                    shop_target = 0
                    shop_demand_rate = 0
                    username = StoreAccountService._sanitize_username(shop_id)

                    # Ensure username uniqueness
                    base_username = username
                    counter = 1
                    while User.objects.filter(username=username).exists():
                        username = f"{base_username}_{counter}"
                        counter += 1

                    # Create User with shared password
                    user = User.objects.create_user(
                        username=username,
                        password=shared_password,
                        is_staff=False,
                        is_active=True,
                    )

                    # Create Shop record
                    shop = Shop.objects.create(
                        name=shop_name,
                        node_id=shop_id,
                        network_definition=network_definition,
                        user=user,
                        inventory=max(0, int(shop_inventory)),
                        target=max(0, int(shop_target)),
                        demand_rate=max(0, int(shop_demand_rate)),
                    )

                    # Set role
                    from .user_roles import set_user_role, ROLE_SHOP_WORKER
                    set_user_role(user.id, ROLE_SHOP_WORKER)

                    # Create credential record (stores username for reference)
                    ShopCredential.objects.create(
                        shop=shop,
                        username=username,
                        password=shared_password,
                        expires_at=None,  # No expiry for shared password
                    )

                    created_credentials.append({
                        "name": shop_name,
                        "username": username,
                        "type": "shop",
                    })

                    logger.info(
                        f"Created shop account: username={username}, shop={shop_name}"
                    )

                # Persist route topology for simulation and websocket updates
                for route_index, route_data in enumerate(parsed_definition.get("routes", [])):
                    source_id = str(route_data["from"])
                    target_id = str(route_data["to"])
                    travel_time = _route_tick_count(route_data)
                    transport_cost = float(route_data.get("cost", 1.0))

                    metadata = {
                        key: value
                        for key, value in route_data.items()
                        if key
                        not in {
                            "id",
                            "from",
                            "to",
                            "source",
                            "target",
                            "time",
                            "cost",
                        }
                    }

                    edge_id = str(
                        route_data.get("id")
                        or route_data.get("edgeId")
                        or route_data.get("edge_id")
                        or f"edge-{source_id}-{target_id}-{route_index}"
                    )

                    Route.objects.create(
                        network_definition=network_definition,
                        edge_id=edge_id,
                        source_node_id=source_id,
                        target_node_id=target_id,
                        travel_time=travel_time,
                        transport_cost=transport_cost,
                        metadata=metadata,
                        is_active=True,
                    )

                logger.info(
                    "Persisted %s routes for network=%s",
                    len(parsed_definition.get("routes", [])),
                    network_definition.name,
                )

        except Exception as e:
            logger.error(f"Error creating accounts from JSON: {e}")
            raise

        return created_credentials
