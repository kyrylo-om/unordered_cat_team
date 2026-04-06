import { useEffect, useRef, useState } from "react";
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

function getInternalNodeType(node) {
  const value =
    node?.data?.type ??
    node?.internals?.userNode?.data?.type ??
    node?.internals?.userNode?.type;

  return String(value || "").toLowerCase();
}

function getShipmentDotCount(activeShipments) {
  const numeric = Number(activeShipments);
  if (!Number.isFinite(numeric)) {
    return 1;
  }

  const rounded = Math.max(1, Math.round(numeric));
  return Math.min(rounded, 3);
}

function parseDurationToMs(value) {
  const fallbackMs = 4000;
  if (typeof value !== "string") {
    return fallbackMs;
  }

  const normalized = value.trim().toLowerCase();
  if (normalized.endsWith("ms")) {
    const numericMs = Number(normalized.slice(0, -2));
    return Number.isFinite(numericMs) && numericMs > 0 ? numericMs : fallbackMs;
  }

  if (normalized.endsWith("s")) {
    const numericSeconds = Number(normalized.slice(0, -1));
    return Number.isFinite(numericSeconds) && numericSeconds > 0
      ? numericSeconds * 1000
      : fallbackMs;
  }

  const numericRaw = Number(normalized);
  return Number.isFinite(numericRaw) && numericRaw > 0
    ? numericRaw * 1000
    : fallbackMs;
}

function parseTimestampToMs(value) {
  if (typeof value !== "string" || !value) {
    return null;
  }

  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : null;
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
  const wasMovingRef = useRef(false);
  const lastUpdateKeyRef = useRef("");
  const [animationNowMs, setAnimationNowMs] = useState(() => Date.now());
  const [dotActivationMs, setDotActivationMs] = useState([]);

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
  const hasMovement =
    data?.status === "moving" ||
    data?.isMoving === true ||
    data?.truckStatus === "moving";
  const targetType = String(
    data?.targetType || getInternalNodeType(targetNode),
  ).toLowerCase();
  const isMovingToShop = hasMovement && targetType === "shop";
  const targetDotCount = isMovingToShop
    ? getShipmentDotCount(data?.activeShipments)
    : 0;
  const duration = typeof data?.duration === "string" ? data.duration : "4s";
  const durationMs = parseDurationToMs(duration);
  const updateKey = String(data?.updatedAt || "");
  const departureCount = Number.isFinite(Number(data?.departureCount))
    ? Math.max(0, Math.round(Number(data?.departureCount)))
    : 0;
  const arrivalCount = Number.isFinite(Number(data?.arrivalCount))
    ? Math.max(0, Math.round(Number(data?.arrivalCount)))
    : 0;
  const truckColor = data?.truckColor || "#1d4ed8";
  const defaultStrokeColor = hasMovement ? "#0284c7" : "#64748b";
  const baseStrokeWidth = Number(style?.strokeWidth) || 2;

  useEffect(() => {
    const hasTransitionedToMoving = isMovingToShop && !wasMovingRef.current;
    const hasFreshUpdate =
      isMovingToShop &&
      !!updateKey &&
      updateKey !== lastUpdateKeyRef.current;

    if (hasTransitionedToMoving || hasFreshUpdate) {
      const now = Date.now();
      const activationFromPayload = parseTimestampToMs(updateKey);
      const nextActivation = activationFromPayload ?? now;
      setAnimationNowMs(now);

      setDotActivationMs((current) => {
        const seedDots = (count, activation) =>
          Array.from({ length: count }, () => activation);

        if (!isMovingToShop || targetDotCount <= 0) {
          return [];
        }

        // Edge just became active: spawn full visible set at route start.
        if (!wasMovingRef.current) {
          return seedDots(targetDotCount, nextActivation);
        }

        let next = [...current];

        // Arrivals remove oldest in-flight dots first (closest to destination).
        if (arrivalCount > 0) {
          next = next.slice(Math.min(arrivalCount, next.length));
        }

        // New departures append fresh dots that start from source node.
        if (departureCount > 0) {
          next.push(...seedDots(departureCount, nextActivation));
        }

        // Keep the visible list aligned with current active shipment count.
        if (next.length > targetDotCount) {
          const overflow = next.length - targetDotCount;
          next = next.slice(overflow);
        }

        if (next.length < targetDotCount) {
          next = next.concat(seedDots(targetDotCount - next.length, nextActivation));
        }

        return next;
      });
    }

    if (!isMovingToShop && wasMovingRef.current) {
      setDotActivationMs([]);
    }

    lastUpdateKeyRef.current = updateKey;
    wasMovingRef.current = isMovingToShop;
  }, [isMovingToShop, updateKey, targetDotCount, departureCount, arrivalCount]);

  useEffect(() => {
    if (!isMovingToShop) {
      return undefined;
    }

    let frameId = 0;
    const tick = () => {
      setAnimationNowMs(Date.now());
      frameId = window.requestAnimationFrame(tick);
    };

    frameId = window.requestAnimationFrame(tick);
    return () => {
      window.cancelAnimationFrame(frameId);
    };
  }, [isMovingToShop]);

  const cycleMs = Math.max(200, durationMs);
  const vectorX = coordinates.targetX - coordinates.sourceX;
  const vectorY = coordinates.targetY - coordinates.sourceY;
  const vectorLength = Math.hypot(vectorX, vectorY) || 1;
  const perpendicularX = -vectorY / vectorLength;
  const perpendicularY = vectorX / vectorLength;

  return (
    <g>
      <path
        id={motionPathId}
        d={path}
        fill="none"
        stroke={style?.stroke || defaultStrokeColor}
        strokeWidth={hasMovement ? baseStrokeWidth + 0.6 : baseStrokeWidth}
        markerStart={markerStart}
        markerEnd={markerEnd}
      />
      {isMovingToShop
        ? dotActivationMs.map((dotStartMs, index) => {
            const startDelayMs = index * 160;
            const dotElapsedMs = Math.max(0, animationNowMs - dotStartMs - startDelayMs);
            const delayedElapsedMs = dotElapsedMs;
            const progress = Math.min(1, delayedElapsedMs / cycleMs);
            const baseX = coordinates.sourceX + vectorX * progress;
            const baseY = coordinates.sourceY + vectorY * progress;
            const laneOffset = (index - (dotActivationMs.length - 1) / 2) * 6;
            const x = baseX + perpendicularX * laneOffset;
            const y = baseY + perpendicularY * laneOffset;

            return (
              <circle
                key={`${motionPathId}_dot_${index}`}
                cx={x}
                cy={y}
                r="5"
                fill={truckColor}
                opacity="0.95"
              />
            );
          })
        : null}
    </g>
  );
}
