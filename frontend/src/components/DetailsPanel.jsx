import { useEffect, useMemo, useState } from "react";
import { useCSRFToken } from "../hooks/useCSRFToken";

const NODE_METRICS_URL =
  import.meta.env.VITE_NODE_METRICS_URL || "/api/simulation/node-metrics";

function toNonNegativeInt(value, fallback = 0) {
  const parsed = Number.parseInt(String(value), 10);
  if (Number.isNaN(parsed) || parsed < 0) {
    return fallback;
  }

  return parsed;
}

function initialNodeForm(selectedElement) {
  const data = selectedElement?.data || {};
  return {
    inventory: toNonNegativeInt(data.inventory, 0),
    target: toNonNegativeInt(data.target, 0),
    demandRate: toNonNegativeInt(data.demandRate ?? data.demand_rate, 0),
  };
}

export function DetailsPanel({ selectedElement, onSelectionChange }) {
  const csrfToken = useCSRFToken();
  const [form, setForm] = useState({ inventory: 0, target: 0, demandRate: 0 });
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const isNode = selectedElement?.kind === "node";
  const isEdge = selectedElement?.kind === "edge";
  const nodeType = String(selectedElement?.data?.type || "").toLowerCase();
  const isShopNode = isNode && nodeType === "shop";

  useEffect(() => {
    if (!isNode) {
      return;
    }

    setForm(initialNodeForm(selectedElement));
    setError("");
    setSuccess("");
  }, [isNode, selectedElement]);

  const nodeMetrics = useMemo(() => {
    if (!isNode) {
      return null;
    }

    return {
      id: String(selectedElement.id),
      label: String(selectedElement?.data?.label || selectedElement.id),
      type: String(selectedElement?.data?.type || "unknown"),
      inventory: toNonNegativeInt(selectedElement?.data?.inventory, 0),
      target: toNonNegativeInt(selectedElement?.data?.target, 0),
      demandRate: toNonNegativeInt(
        selectedElement?.data?.demandRate ?? selectedElement?.data?.demand_rate,
        0,
      ),
    };
  }, [isNode, selectedElement]);

  async function handleNodeSave(event) {
    event.preventDefault();

    if (!isNode || !nodeMetrics) {
      return;
    }

    setError("");
    setSuccess("");
    setIsSaving(true);

    const payload = {
      nodeId: nodeMetrics.id,
      inventory: toNonNegativeInt(form.inventory, nodeMetrics.inventory),
    };

    if (isShopNode) {
      payload.target = toNonNegativeInt(form.target, nodeMetrics.target);
      payload.demandRate = toNonNegativeInt(form.demandRate, nodeMetrics.demandRate);
    }

    try {
      const response = await fetch(NODE_METRICS_URL, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrfToken,
        },
        body: JSON.stringify(payload),
        credentials: "include",
      });

      const data = await response.json();
      if (!response.ok) {
        throw new Error(data?.error || "Failed to save node metrics");
      }

      const updatedData = data?.node?.data || {};
      const mergedData = {
        ...(selectedElement?.data || {}),
        ...updatedData,
      };

      if (typeof onSelectionChange === "function") {
        onSelectionChange({
          ...selectedElement,
          kind: "node",
          id: String(data?.node?.id || nodeMetrics.id),
          data: mergedData,
        });
      }

      setForm({
        inventory: toNonNegativeInt(
          mergedData.inventory,
          toNonNegativeInt(form.inventory, 0),
        ),
        target: toNonNegativeInt(
          mergedData.target,
          toNonNegativeInt(form.target, 0),
        ),
        demandRate: toNonNegativeInt(
          mergedData.demandRate,
          toNonNegativeInt(form.demandRate, 0),
        ),
      });

      setSuccess("Metrics saved");
    } catch (caughtError) {
      setError(caughtError?.message || "Failed to save node metrics");
    } finally {
      setIsSaving(false);
    }
  }

  if (!selectedElement) {
    return (
      <div className="sidebar-placeholder">
        <h3>Details Panel</h3>
        <p>Click a node or edge on the graph to inspect details.</p>
      </div>
    );
  }

  if (isEdge) {
    const edgeData = selectedElement.data || {};
    return (
      <div className="sidebar-placeholder details-panel">
        <h3>Details Panel</h3>
        <div className="details-section">
          <h4>Selected edge</h4>
          <dl className="details-list">
            <div>
              <dt>ID</dt>
              <dd>{selectedElement.id}</dd>
            </div>
            <div>
              <dt>From</dt>
              <dd>{selectedElement.source}</dd>
            </div>
            <div>
              <dt>To</dt>
              <dd>{selectedElement.target}</dd>
            </div>
            <div>
              <dt>Status</dt>
              <dd>{String(edgeData.status || "idle")}</dd>
            </div>
            <div>
              <dt>Active shipments</dt>
              <dd>{toNonNegativeInt(edgeData.activeShipments, 0)}</dd>
            </div>
            <div>
              <dt>Transport time</dt>
              <dd>{edgeData.time ?? "—"}</dd>
            </div>
            <div>
              <dt>Transport cost</dt>
              <dd>{edgeData.cost ?? "—"}</dd>
            </div>
          </dl>
        </div>
      </div>
    );
  }

  return (
    <div className="sidebar-placeholder details-panel">
      <h3>Details Panel</h3>
      <div className="details-section">
        <h4>Selected node</h4>
        <dl className="details-list">
          <div>
            <dt>ID</dt>
            <dd>{nodeMetrics.id}</dd>
          </div>
          <div>
            <dt>Label</dt>
            <dd>{nodeMetrics.label}</dd>
          </div>
          <div>
            <dt>Type</dt>
            <dd>{nodeMetrics.type}</dd>
          </div>
        </dl>
      </div>

      <form className="details-form" onSubmit={handleNodeSave}>
        <h4>Adjust metrics</h4>

        <label htmlFor="details-inventory">Stock (inventory)</label>
        <input
          id="details-inventory"
          type="number"
          min="0"
          step="1"
          value={form.inventory}
          onChange={(event) =>
            setForm((current) => ({
              ...current,
              inventory: toNonNegativeInt(event.target.value, 0),
            }))
          }
          disabled={isSaving}
        />

        {isShopNode ? (
          <>
            <label htmlFor="details-target">Target</label>
            <input
              id="details-target"
              type="number"
              min="0"
              step="1"
              value={form.target}
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  target: toNonNegativeInt(event.target.value, 0),
                }))
              }
              disabled={isSaving}
            />

            <label htmlFor="details-demand-rate">Demand rate</label>
            <input
              id="details-demand-rate"
              type="number"
              min="0"
              step="1"
              value={form.demandRate}
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  demandRate: toNonNegativeInt(event.target.value, 0),
                }))
              }
              disabled={isSaving}
            />
          </>
        ) : null}

        <button type="submit" disabled={isSaving}>
          {isSaving ? "Saving..." : "Save node metrics"}
        </button>
      </form>

      {error ? <p className="details-error">{error}</p> : null}
      {success ? <p className="details-success">{success}</p> : null}
    </div>
  );
}
