from django.db import connection

ROLE_WAREHOUSE_WORKER = "warehouse_worker"
ROLE_SHOP_WORKER = "shop_worker"

ROLE_CHOICES = (
    (ROLE_WAREHOUSE_WORKER, "Warehouse Worker"),
    (ROLE_SHOP_WORKER, "Shop Worker"),
)

DEFAULT_ROLE = ROLE_SHOP_WORKER


def normalize_role(value):
    role = str(value or "").strip().lower()

    if role in {"warehouse", "warehouse_worker", "warehouseworker"}:
        return ROLE_WAREHOUSE_WORKER

    if role in {"shop", "shop_worker", "shopworker", "worker", "store", "store_worker"}:
        return ROLE_SHOP_WORKER

    return DEFAULT_ROLE


def get_user_role(user_id):
    with connection.cursor() as cursor:
        cursor.execute("SELECT role FROM auth_user WHERE id = %s", [user_id])
        row = cursor.fetchone()

    if not row:
        return DEFAULT_ROLE

    return normalize_role(row[0])


def set_user_role(user_id, role):
    normalized = normalize_role(role)

    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE auth_user SET role = %s WHERE id = %s",
            [normalized, user_id],
        )

    return normalized
