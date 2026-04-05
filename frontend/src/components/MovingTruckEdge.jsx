import { getBezierPath } from "@xyflow/react";

function normalizeId(value) {
  return String(value).replace(/[^a-zA-Z0-9_:-]/g, "_");
}

export function MovingTruckEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  markerEnd,
  data,
  style,
}) {
  const [path] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  });

  const motionPathId = `edge_path_${normalizeId(id)}`;
  const isMoving =
    data?.status === "moving" ||
    data?.isMoving === true ||
    data?.truckStatus === "moving";
  const duration = typeof data?.duration === "string" ? data.duration : "4s";
  const truckColor = data?.truckColor || "#1d4ed8";

  return (
    <g>
      <path
        id={motionPathId}
        d={path}
        fill="none"
        stroke={style?.stroke || "#64748b"}
        strokeWidth={style?.strokeWidth || 2}
        markerEnd={markerEnd}
      />
      {isMoving ? (
        <circle r="5" fill={truckColor}>
          <animateMotion dur={duration} repeatCount="indefinite" rotate="auto">
            <mpath href={`#${motionPathId}`} />
          </animateMotion>
        </circle>
      ) : null}
    </g>
  );
}
