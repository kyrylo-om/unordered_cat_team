import { getStraightPath, useReactFlow } from "@xyflow/react";

const FALLBACK_NODE_WIDTH = 150;
const FALLBACK_NODE_HEIGHT = 40;

function normalizeId(value) {
  return String(value).replace(/[^a-zA-Z0-9_:-]/g, "_");
}

function getNodeRect(node) {
  const width = node.measured?.width ?? node.width ?? FALLBACK_NODE_WIDTH;
  const height = node.measured?.height ?? node.height ?? FALLBACK_NODE_HEIGHT;
  const x = node.internals.positionAbsolute.x;
  const y = node.internals.positionAbsolute.y;

  return {
    centerX: x + width / 2,
    centerY: y + height / 2,
    halfWidth: width / 2,
    halfHeight: height / 2,
  };
}

function getBorderIntersectionPoint(fromNode, toNode) {
  const fromRect = getNodeRect(fromNode);
  const toRect = getNodeRect(toNode);

  const dx = toRect.centerX - fromRect.centerX;
  const dy = toRect.centerY - fromRect.centerY;

  if (dx === 0 && dy === 0) {
    return {
      x: fromRect.centerX,
      y: fromRect.centerY,
    };
  }

  const scaleX =
    dx === 0 ? Number.POSITIVE_INFINITY : fromRect.halfWidth / Math.abs(dx);
  const scaleY =
    dy === 0 ? Number.POSITIVE_INFINITY : fromRect.halfHeight / Math.abs(dy);
  const scale = Math.min(scaleX, scaleY);

  return {
    x: fromRect.centerX + dx * scale,
    y: fromRect.centerY + dy * scale,
  };
}

function getPathCoordinates({
  sourceNode,
  targetNode,
  fallbackSourceX,
  fallbackSourceY,
  fallbackTargetX,
  fallbackTargetY,
}) {
  if (!sourceNode || !targetNode) {
    return {
      sourceX: fallbackSourceX,
      sourceY: fallbackSourceY,
      targetX: fallbackTargetX,
      targetY: fallbackTargetY,
    };
  }

  const sourcePoint = getBorderIntersectionPoint(sourceNode, targetNode);
  const targetPoint = getBorderIntersectionPoint(targetNode, sourceNode);

  return {
    sourceX: sourcePoint.x,
    sourceY: sourcePoint.y,
    targetX: targetPoint.x,
    targetY: targetPoint.y,
  };
}

export function MovingTruckEdge({
  id,
  source,
  target,
  sourceX,
  sourceY,
  targetX,
  targetY,
  markerStart,
  markerEnd,
  data,
  style,
}) {
  const { getInternalNode } = useReactFlow();
  const sourceNode = source ? getInternalNode(source) : undefined;
  const targetNode = target ? getInternalNode(target) : undefined;

  const coordinates = getPathCoordinates({
    sourceNode,
    targetNode,
    fallbackSourceX: sourceX,
    fallbackSourceY: sourceY,
    fallbackTargetX: targetX,
    fallbackTargetY: targetY,
  });

  const [path] = getStraightPath(coordinates);

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
        markerStart={markerStart}
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
