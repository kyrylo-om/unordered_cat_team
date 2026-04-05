import { useEffect } from "react";
import {
  Background,
  MiniMap,
  ReactFlow,
  useEdgesState,
  useNodesState,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { BallNode } from "./BallNode";
import { MovingTruckEdge } from "./MovingTruckEdge";

const edgeTypes = {
  moving: MovingTruckEdge,
};

const nodeTypes = {
  ball: BallNode,
};

const LAYOUT_COLUMN_GAP = 220;
const LAYOUT_ROW_GAP = 150;
const SHOP_SECTION_OFFSET_Y = 220;

function getNodeType(node) {
  return String(node?.data?.type || node?.type || "shop").toLowerCase();
}

function getNodeLabel(node) {
  return String(node?.data?.label || node?.label || node?.id || "");
}

function toFiniteNumber(value) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : null;
}

function getNodePosition(position) {
  const x = toFiniteNumber(position?.x);
  const y = toFiniteNumber(position?.y);

  if (x === null || y === null) {
    return null;
  }

  return { x, y };
}

function getCenteredRowStart(itemCount, maxColumns) {
  if (itemCount <= 1) {
    return maxColumns > 1 ? ((maxColumns - 1) * LAYOUT_COLUMN_GAP) / 2 : 0;
  }

  return ((maxColumns - itemCount) * LAYOUT_COLUMN_GAP) / 2;
}

function buildSectionPositions(nodes, startY, columns) {
  if (!nodes.length) {
    return [];
  }

  const sortedNodes = [...nodes].sort((left, right) =>
    getNodeLabel(left).localeCompare(getNodeLabel(right), undefined, {
      sensitivity: "base",
    }),
  );
  const safeColumnCount = Math.max(1, columns);

  return sortedNodes.map((node, index) => {
    const column = index % safeColumnCount;
    const row = Math.floor(index / safeColumnCount);
    const itemsInRow = Math.min(
      safeColumnCount,
      sortedNodes.length - row * safeColumnCount,
    );
    const rowStartX = getCenteredRowStart(itemsInRow, safeColumnCount);

    return {
      ...node,
      position: {
        x: rowStartX + column * LAYOUT_COLUMN_GAP,
        y: startY + row * LAYOUT_ROW_GAP,
      },
    };
  });
}

function buildFallbackLayout(nodes) {
  if (!nodes.length) {
    return [];
  }

  const warehouseNodes = nodes.filter((node) => getNodeType(node) === "warehouse");
  const otherNodes = nodes.filter((node) => getNodeType(node) !== "warehouse");
  const shopColumns = Math.max(3, Math.ceil(Math.sqrt(otherNodes.length || 1)));
  const warehouseColumns = Math.max(
    warehouseNodes.length,
    Math.min(shopColumns, warehouseNodes.length || 1),
  );
  const maxColumns = Math.max(shopColumns, warehouseColumns);
  const warehouses = buildSectionPositions(warehouseNodes, 0, maxColumns);
  const shopStartY =
    warehouses.length > 0
      ? SHOP_SECTION_OFFSET_Y +
        (Math.ceil(warehouses.length / maxColumns) - 1) * LAYOUT_ROW_GAP
      : 0;
  const shops = buildSectionPositions(otherNodes, shopStartY, maxColumns);

  return [...warehouses, ...shops];
}

function needsFallbackLayout(nodes) {
  if (!nodes.length) {
    return false;
  }

  const positions = nodes.map((node) => getNodePosition(node.position));
  if (positions.some((position) => position === null)) {
    return true;
  }

  if (nodes.length === 1) {
    return false;
  }

  const uniquePositions = new Set(
    positions.map((position) => `${position.x}:${position.y}`),
  );

  return uniquePositions.size <= 1;
}

function normalizeNode(node) {
  return {
    ...node,
    id: String(node.id),
    type: "ball",
    position: getNodePosition(node.position) || { x: 0, y: 0 },
    data: node.data || {},
  };
}

function normalizeEdge(edge) {
  return {
    ...edge,
    id: String(edge.id),
    source: String(edge.source),
    target: String(edge.target),
    type: edge.type || "moving",
    data: edge.data || {},
  };
}

export function GraphMap({ staticNodes, staticEdges, nodeUpdate, edgeUpdate }) {
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);

  useEffect(() => {
    const normalizedNodes = staticNodes.map(normalizeNode);
    const displayNodes = needsFallbackLayout(normalizedNodes)
      ? buildFallbackLayout(normalizedNodes)
      : normalizedNodes;
    const normalizedEdges = staticEdges
      .filter((edge) => edge?.source !== undefined && edge?.target !== undefined)
      .map(normalizeEdge);

    setNodes(displayNodes);
    setEdges(normalizedEdges);
  }, [staticNodes, staticEdges, setNodes, setEdges]);

  useEffect(() => {
    if (!nodeUpdate) {
      return;
    }

    setNodes((currentNodes) =>
      currentNodes.map((node) => {
        if (node.id !== nodeUpdate.id) {
          return node;
        }

        return {
          ...node,
          data: {
            ...node.data,
            ...(nodeUpdate.data || {}),
          },
        };
      }),
    );
  }, [nodeUpdate, setNodes]);

  useEffect(() => {
    if (!edgeUpdate) {
      return;
    }

    setEdges((currentEdges) =>
      currentEdges.map((edge) => {
        if (edge.id !== edgeUpdate.id) {
          return edge;
        }

        return {
          ...edge,
          data: {
            ...edge.data,
            ...(edgeUpdate.data || {}),
          },
        };
      }),
    );
  }, [edgeUpdate, setEdges]);

  return (
    <div className="graph-map">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        edgeTypes={edgeTypes}
        nodeTypes={nodeTypes}
        nodesDraggable={false}
        nodesConnectable={false}
        selectNodesOnDrag={false}
        fitViewOptions={{ padding: 0.25, maxZoom: 0.8 }}
        fitView
      >
        <MiniMap/>
        <Background />
      </ReactFlow>
    </div>
  );
}
