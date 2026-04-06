import { useEffect, useState } from "react";
import { GraphMap } from "../components/GraphMap";
import "../styles/Dashboard.css";

const MAP_LAYOUT_URL = import.meta.env.VITE_MAP_LAYOUT_URL || "/api/map-layout";
const MANAGER_WS_URL = import.meta.env.VITE_MANAGER_WS_URL;

function getAuthToken() {
  return localStorage.getItem("accessToken") || localStorage.getItem("token") || "";
}

function getAuthHeaders() {
  const token = getAuthToken();
  if (!token) {
    return {};
  }
  return { Authorization: `Bearer ${token}` };
}

function withToken(url, token) {
  if (!token) {
    return url;
  }

  const separator = url.includes("?") ? "&" : "?";
  return `${url}${separator}token=${encodeURIComponent(token)}`;
}

function getSocketUrls(token) {
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  const urls = [];

  if (MANAGER_WS_URL) {
    urls.push(withToken(MANAGER_WS_URL, token));
  }

  urls.push(withToken(`${protocol}://${window.location.host}/ws/manager-dashboard/`, token));

  if (import.meta.env.DEV) {
    urls.push(
      withToken(`${protocol}://127.0.0.1:8000/ws/manager-dashboard/`, token),
    );
    urls.push(
      withToken(
        `${protocol}://${window.location.hostname}:8000/ws/manager-dashboard/`,
        token,
      ),
    );
  }

  return Array.from(new Set(urls));
}

function parseLayoutPayload(payload) {
  const directNodes = Array.isArray(payload?.nodes) ? payload.nodes : [];
  const directEdges = Array.isArray(payload?.edges) ? payload.edges : [];

  if (directNodes.length || directEdges.length) {
    return { nodes: directNodes, edges: directEdges };
  }

  const definition =
    payload?.definition && typeof payload.definition === "object"
      ? payload.definition
      : payload;
  const warehouses = Array.isArray(definition?.warehouses)
    ? definition.warehouses
    : [];
  const shops = Array.isArray(definition?.shops) ? definition.shops : [];
  const routes = Array.isArray(definition?.edges)
    ? definition.edges
    : Array.isArray(definition?.routes)
      ? definition.routes
      : Array.isArray(definition?.connections)
        ? definition.connections
        : [];

  const nodes = [
    ...warehouses.map((warehouse) => ({
      id: warehouse.id ?? warehouse.nodeId ?? warehouse.node_id,
      position: warehouse.position,
      data: {
        ...warehouse.data,
        label: warehouse.name ?? warehouse.label ?? warehouse.data?.label,
        type: warehouse.type ?? warehouse.data?.type ?? "warehouse",
      },
    })),
    ...shops.map((shop) => ({
      id: shop.id ?? shop.nodeId ?? shop.node_id,
      position: shop.position,
      data: {
        ...shop.data,
        label: shop.name ?? shop.label ?? shop.data?.label,
        type: shop.type ?? shop.data?.type ?? "shop",
        inventory: shop.inventory ?? shop.data?.inventory,
      },
    })),
  ].filter((node) => node.id !== undefined && node.id !== null);

  const edges = routes
    .map((route, index) => {
      const source =
        route.source ??
        route.from ??
        route.fromId ??
        route.from_id ??
        route.start;
      const target =
        route.target ?? route.to ?? route.toId ?? route.to_id ?? route.end;

      if (source === undefined || source === null || target === undefined || target === null) {
        return null;
      }

      return {
        ...route,
        id: route.id ?? route.edgeId ?? route.edge_id ?? `edge-${index}`,
        source,
        target,
      };
    })
    .filter(Boolean);

  return { nodes, edges };
}

function normalizeNodeUpdate(payload) {
  if (!payload || typeof payload !== "object") {
    return null;
  }

  const id = payload.id ?? payload.nodeId ?? payload.node_id;
  if (id === undefined || id === null) {
    return null;
  }

  const data =
    payload.data && typeof payload.data === "object"
      ? payload.data
      : Object.fromEntries(
          Object.entries(payload).filter(
            ([key]) => key !== "id" && key !== "nodeId" && key !== "node_id",
          ),
        );

  return {
    id: String(id),
    data,
  };
}

function normalizeEdgeUpdate(payload) {
  if (!payload || typeof payload !== "object") {
    return null;
  }

  const id = payload.id ?? payload.edgeId ?? payload.edge_id;
  if (id === undefined || id === null) {
    return null;
  }

  const data =
    payload.data && typeof payload.data === "object"
      ? payload.data
      : Object.fromEntries(
          Object.entries(payload).filter(
            ([key]) => key !== "id" && key !== "edgeId" && key !== "edge_id",
          ),
        );

  return {
    id: String(id),
    data,
  };
}

export function Dashboard({ onEventLog, onTick, onElementSelect, onElementPatch }) {
  const [layoutNodes, setLayoutNodes] = useState([]);
  const [layoutEdges, setLayoutEdges] = useState([]);
  const [nodeUpdate, setNodeUpdate] = useState(null);
  const [edgeUpdate, setEdgeUpdate] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    async function loadMapLayout() {
      setIsLoading(true);
      setError("");

      try {
        const response = await fetch(MAP_LAYOUT_URL, {
          method: "GET",
          headers: {
            ...getAuthHeaders(),
          },
          credentials: "include",
        });

        if (!response.ok) {
          throw new Error("Could not load map layout");
        }

        const payload = await response.json();
        const layout = parseLayoutPayload(payload);
        setLayoutNodes(layout.nodes);
        setLayoutEdges(layout.edges);
      } catch {
        setError("Could not load map layout");
        setLayoutNodes([]);
        setLayoutEdges([]);
      } finally {
        setIsLoading(false);
      }
    }

    loadMapLayout();
  }, []);

  useEffect(() => {
    if (isLoading || error) {
      return undefined;
    }

    const token = getAuthToken();
    const socketUrls = getSocketUrls(token);

    let isDisposed = false;
    let activeSocket = null;
    let retryTimer = null;
    let reconnectAttempt = 0;

    const handleMessage = (event) => {
      try {
        const message = JSON.parse(event.data);
        const eventType = message.type || message.event;
        const payload = message.payload || message.data || message;

        if (eventType === "SNAPSHOT") {
          const layout = parseLayoutPayload(payload);
          setLayoutNodes(layout.nodes);
          setLayoutEdges(layout.edges);
          return;
        }

        if (eventType === "NODE_UPDATE") {
          const update = normalizeNodeUpdate(payload);
          if (update) {
            setNodeUpdate({ ...update, stamp: Date.now() + Math.random() });
            if (typeof onElementPatch === "function") {
              onElementPatch({ kind: "node", id: update.id, data: update.data || {} });
            }
          }
        }

        if (eventType === "EDGE_UPDATE") {
          const update = normalizeEdgeUpdate(payload);
          if (update) {
            setEdgeUpdate({ ...update, stamp: Date.now() + Math.random() });
            if (typeof onElementPatch === "function") {
              onElementPatch({ kind: "edge", id: update.id, data: update.data || {} });
            }
          }
        }

        if (eventType === "EVENT_LOG" && typeof onEventLog === "function") {
          onEventLog(payload);
        }

        if (eventType === "TICK" && typeof onTick === "function") {
          onTick(payload);
        }
      } catch {
        return;
      }
    };

    const connectWithFallback = (startIndex = 0) => {
      if (isDisposed) {
        return;
      }

      const socketUrl = socketUrls[startIndex];
      if (!socketUrl) {
        return;
      }

      const socket = new WebSocket(socketUrl);
      activeSocket = socket;

      socket.onopen = () => {
        reconnectAttempt = 0;
      };

      socket.onmessage = handleMessage;

      socket.onerror = () => {
        socket.close();
      };

      socket.onclose = () => {
        if (isDisposed) {
          return;
        }

        if (startIndex + 1 < socketUrls.length) {
          connectWithFallback(startIndex + 1);
          return;
        }

        const retryDelayMs = Math.min(5000, 500 * 2 ** reconnectAttempt);
        reconnectAttempt += 1;
        retryTimer = window.setTimeout(() => connectWithFallback(0), retryDelayMs);
      };
    };

    connectWithFallback(0);

    return () => {
      isDisposed = true;
      if (retryTimer) {
        window.clearTimeout(retryTimer);
      }

      if (activeSocket && activeSocket.readyState <= WebSocket.OPEN) {
        activeSocket.close();
      }
    };
  }, [isLoading, error, onEventLog, onTick, onElementPatch]);

  if (isLoading) {
    return <p className="dashboard-state">Loading map...</p>;
  }

  if (error) {
    return <p className="dashboard-state">{error}</p>;
  }

  if (!layoutNodes.length && !layoutEdges.length) {
    return <p className="dashboard-state">Map is not loaded</p>;
  }

  return (
    <div className="dashboard">
      <GraphMap
        staticNodes={layoutNodes}
        staticEdges={layoutEdges}
        nodeUpdate={nodeUpdate}
        edgeUpdate={edgeUpdate}
        onNodeSelect={onElementSelect}
        onEdgeSelect={onElementSelect}
        onSelectionClear={() =>
          typeof onElementSelect === "function" ? onElementSelect(null) : null
        }
      />
    </div>
  );
}
