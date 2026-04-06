from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from threading import Lock
from datetime import datetime, timezone

MANAGER_DASHBOARD_GROUP = "manager-dashboard"

_EDGE_ACTIVITY_LOCK = Lock()
_EDGE_ACTIVITY_STATE = {}


def resolve_route_edge_id(route, fallback_index=0):
    """Return a stable edge ID for websocket updates and React Flow mapping."""
    edge_id = getattr(route, "edge_id", "")
    if edge_id:
        return str(edge_id)

    source_id = getattr(route, "source_node_id", "")
    target_id = getattr(route, "target_node_id", "")
    route_pk = getattr(route, "pk", None) or getattr(route, "id", None)

    if route_pk is not None:
        return f"edge-{source_id}-{target_id}-{route_pk}"

    return f"edge-{source_id}-{target_id}-{fallback_index}"


def resolve_reverse_edge_id(edge_id):
    return f"{str(edge_id)}__reverse"


def send_manager_event(event_type, payload):
    """Send a typed websocket event to all manager dashboard subscribers."""
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return

    async_to_sync(channel_layer.group_send)(
        MANAGER_DASHBOARD_GROUP,
        {
            "type": "manager.event",
            "event_type": event_type,
            "payload": payload,
        },
    )


def get_edge_activity_snapshot():
    with _EDGE_ACTIVITY_LOCK:
        return {
            edge_id: dict(data)
            for edge_id, data in _EDGE_ACTIVITY_STATE.items()
        }


def _store_edge_activity(edge_id, data):
    with _EDGE_ACTIVITY_LOCK:
        merged = {
            **_EDGE_ACTIVITY_STATE.get(edge_id, {}),
            **(data or {}),
        }
        _EDGE_ACTIVITY_STATE[edge_id] = merged
        return dict(merged)


def broadcast_node_update(node_id, data):
    payload = {
        "id": str(node_id),
        "data": data or {},
    }
    send_manager_event("NODE_UPDATE", payload)


def broadcast_edge_update(edge_id, data):
    edge_id = str(edge_id)
    merged_data = _store_edge_activity(edge_id, data)
    payload = {
        "id": edge_id,
        "data": merged_data,
    }
    send_manager_event("EDGE_UPDATE", payload)


def broadcast_event_log(event_entry):
    send_manager_event("EVENT_LOG", event_entry or {})


def broadcast_tick(tick_index):
    send_manager_event(
        "TICK",
        {
            "tick": int(tick_index),
            "at": datetime.now(timezone.utc).isoformat(),
        },
    )
