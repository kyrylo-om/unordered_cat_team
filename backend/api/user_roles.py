from django.db import connection

ROLE_MANAGER = "manager"
ROLE_WAREHOUSE_WORKER = "warehouse_worker"
ROLE_SHOP_WORKER = "shop_worker"

ROLE_CHOICES = (
    (ROLE_MANAGER, "Manager"),
    (ROLE_WAREHOUSE_WORKER, "Warehouse Worker"),
    (ROLE_SHOP_WORKER, "Shop Worker"),
)

DEFAULT_ROLE = ROLE_MANAGER


def _fallback_role_from_location(user_id):
    from .models import Warehouse, Shop

    if Warehouse.objects.filter(user_id=user_id).exists():
        return ROLE_WAREHOUSE_WORKER

    if Shop.objects.filter(user_id=user_id).exists():
        return ROLE_SHOP_WORKER

    return DEFAULT_ROLE


def normalize_role(value):
    role = str(value or "").strip().lower()

    if role in {"manager", "admin", "owner"}:
        return ROLE_MANAGER

    if role in {"warehouse", "warehouse_worker", "warehouseworker"}:
        return ROLE_WAREHOUSE_WORKER

    if role in {"shop", "shop_worker", "shopworker", "worker", "store", "store_worker"}:
        return ROLE_SHOP_WORKER

    return DEFAULT_ROLE


def get_user_role(user_id):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT role FROM auth_user WHERE id = %s", [user_id])
            row = cursor.fetchone()
    except Exception:
        return _fallback_role_from_location(user_id)

    if not row:
        return _fallback_role_from_location(user_id)

    return normalize_role(row[0])


def set_user_role(user_id, role):
    normalized = normalize_role(role)

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE auth_user SET role = %s WHERE id = %s",
                [normalized, user_id],
            )
    except Exception:
        return normalized

    return normalized
