import { Handle, Position } from "@xyflow/react";

function getNodeLabel(id, data) {
  if (typeof data?.label === "string" && data.label.trim()) {
    return data.label;
  }

  return String(id);
}

function getNumber(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? Math.max(0, Math.round(parsed)) : null;
}

export function BallNode({ id, data }) {
  const label = getNodeLabel(id, data);
  const nodeType = data?.type || "shop";
  const inventory = getNumber(data?.inventory);
  const demandRate = getNumber(data?.demandRate ?? data?.demand_rate);
  const target = getNumber(data?.target);
  const nodeClass =
    nodeType === "warehouse"
      ? "graph-ball-node--warehouse"
      : "graph-ball-node--shop";

  const metaText =
    nodeType === "warehouse"
      ? `Stock: ${inventory ?? 0}`
      : `I:${inventory ?? 0} D:${demandRate ?? 0} T:${target ?? 0}`;

  return (
    <div
      className={`graph-ball-node ${nodeClass}`}
      title={label}
      aria-label={label}
    >
      <Handle type="target" position={Position.Top} />
      <Handle type="source" position={Position.Bottom} />
      <span className="graph-ball-node__meta">{metaText}</span>
      <span className="graph-ball-node__tooltip">
        <strong>{label}</strong>
        <span>Stock: {inventory ?? 0}</span>
        {nodeType !== "warehouse" ? <span>Demand rate: {demandRate ?? 0}</span> : null}
        {nodeType !== "warehouse" ? <span>Target: {target ?? 0}</span> : null}
      </span>
    </div>
  );
}
