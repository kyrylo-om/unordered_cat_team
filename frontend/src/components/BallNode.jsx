import { Handle, Position } from "@xyflow/react";

function getNodeLabel(id, data) {
  if (typeof data?.label === "string" && data.label.trim()) {
    return data.label;
  }

  return String(id);
}

export function BallNode({ id, data }) {
  const label = getNodeLabel(id, data);

  return (
    <div className="graph-ball-node" title={label} aria-label={label}>
      <Handle type="target" position={Position.Top} />
      <Handle type="source" position={Position.Bottom} />
      <span className="graph-ball-node__tooltip">{label}</span>
    </div>
  );
}