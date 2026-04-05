import { useEffect } from "react";
import {
  Background,
  MiniMap,
  ReactFlow,
  useEdgesState,
  useNodesState,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { MovingTruckEdge } from "./MovingTruckEdge";

const edgeTypes = {
  moving: MovingTruckEdge,
};

function normalizeNode(node) {
  return {
    ...node,
    id: String(node.id),
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
    setNodes(staticNodes.map(normalizeNode));
    setEdges(staticEdges.map(normalizeEdge));
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
        nodesDraggable={false}
        nodesConnectable={false}
        selectNodesOnDrag={false}
        fitView
      >
        <MiniMap/>
        <Background />
      </ReactFlow>
    </div>
  );
}
