from django.db import connection

ROLE_MANAGER = "manager"
ROLE_STORE_WORKER = "store_worker"

ROLE_CHOICES = (
    (ROLE_MANAGER, "Manager"),
    (ROLE_STORE_WORKER, "Store Worker"),
)

DEFAULT_ROLE = ROLE_MANAGER


def normalize_role(value):
    role = str(value or "").strip().lower()

    if role in {"manager", "dispatcher"}:
        return ROLE_MANAGER

    if role in {"store", "worker", "store_worker", "storeworker"}:
        return ROLE_STORE_WORKER

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
