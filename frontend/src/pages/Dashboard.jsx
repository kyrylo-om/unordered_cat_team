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

function buildSocketUrl(token) {
  if (MANAGER_WS_URL) {
    if (!token) {
      return MANAGER_WS_URL;
    }
    const separator = MANAGER_WS_URL.includes("?") ? "&" : "?";
    return `${MANAGER_WS_URL}${separator}token=${encodeURIComponent(token)}`;
  }

  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  const baseUrl = `${protocol}://${window.location.host}/ws/manager-dashboard/`;
  if (!token) {
    return baseUrl;
  }

  return `${baseUrl}?token=${encodeURIComponent(token)}`;
}

function parseLayoutPayload(payload) {
  const nodes = Array.isArray(payload?.nodes) ? payload.nodes : [];
  const edges = Array.isArray(payload?.edges) ? payload.edges : [];
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

export function Dashboard() {
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
    const token = getAuthToken();
    const socketUrl = buildSocketUrl(token);
    const socket = new WebSocket(socketUrl);

    socket.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data);
        const eventType = message.type || message.event;
        const payload = message.payload || message.data || message;

        if (eventType === "NODE_UPDATE") {
          const update = normalizeNodeUpdate(payload);
          if (update) {
            setNodeUpdate({ ...update, stamp: Date.now() + Math.random() });
          }
        }

        if (eventType === "EDGE_UPDATE") {
          const update = normalizeEdgeUpdate(payload);
          if (update) {
            setEdgeUpdate({ ...update, stamp: Date.now() + Math.random() });
          }
        }
      } catch {
        return;
      }
    };

    return () => {
      socket.close();
    };
  }, []);

  if (isLoading) {
    return <p className="dashboard-state">Loading map...</p>;
  }

  if (!layoutNodes.length && !layoutEdges.length) {
    return <p className="dashboard-state">Map is not loaded</p>;
  }

  if (error) {
    return <p className="dashboard-state">{error}</p>;
  }

  return (
    <div className="dashboard">
      <GraphMap
        staticNodes={layoutNodes}
        staticEdges={layoutEdges}
        nodeUpdate={nodeUpdate}
        edgeUpdate={edgeUpdate}
      />
    </div>
  );
}
