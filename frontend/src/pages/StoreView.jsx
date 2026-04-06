import { useEffect, useState } from "react";
import { useCSRFToken } from "../hooks/useCSRFToken";
import "../styles/StoreView.css";

const STORE_STATUS_URL =
  import.meta.env.VITE_STORE_STATUS_URL || "/api/store/status";
const STORE_DEMAND_URL =
  import.meta.env.VITE_STORE_DEMAND_URL || "/api/store/demand";

const DEMAND_PRESETS = [
  { value: 4, label: "Low" },
  { value: 8, label: "Normal" },
  { value: 16, label: "Critical" },
];

function toNonNegativeInt(value, fallback = 0) {
  const parsed = Number.parseInt(String(value), 10);
  if (Number.isNaN(parsed) || parsed < 0) {
    return fallback;
  }
  return parsed;
}

export function StoreView() {
  const [storeName, setStoreName] = useState("Store");
  const [stock, setStock] = useState(0);
  const [target, setTarget] = useState(120);
  const [demandRate, setDemandRate] = useState(5);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const csrfToken = useCSRFToken();

  useEffect(() => {
    async function loadStoreData() {
      setIsLoading(true);
      setError("");

      try {
        const response = await fetch(STORE_STATUS_URL, {
          method: "GET",
          credentials: "include",
        });

        if (!response.ok) {
          throw new Error("Could not load store data");
        }

        const data = await response.json();
        setStoreName(data.storeName || data.name || "Store");
        setStock(toNonNegativeInt(data.stock ?? data.inventory ?? 0));
        setTarget(toNonNegativeInt(data.target, 120));
        setDemandRate(toNonNegativeInt(data.demandRate ?? data.demand_rate, 5));
      } catch {
        setError("Could not load store data");
      } finally {
        setIsLoading(false);
      }
    }

    loadStoreData();
  }, []);

  async function submitSimulationSettings(nextTarget, nextDemandRate) {
    const normalizedTarget = toNonNegativeInt(nextTarget, target);
    const normalizedDemandRate = toNonNegativeInt(nextDemandRate, demandRate);

    setTarget(normalizedTarget);
    setDemandRate(normalizedDemandRate);
    setIsSaving(true);
    setError("");
    setSuccess("");

    try {
      const response = await fetch(STORE_DEMAND_URL, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrfToken,
        },
        body: JSON.stringify({
          target: normalizedTarget,
          demandRate: normalizedDemandRate,
        }),
        credentials: "include",
      });

      if (!response.ok) {
        throw new Error("Could not save demand level");
      }

      const payload = await response.json();
      setStock(toNonNegativeInt(payload.inventory, stock));
      setTarget(toNonNegativeInt(payload.target, normalizedTarget));
      setDemandRate(toNonNegativeInt(payload.demandRate, normalizedDemandRate));
      setSuccess("Store simulation settings updated");
    } catch {
      setError("Could not save simulation settings");
    } finally {
      setIsSaving(false);
    }
  }

  function handleSubmit(event) {
    event.preventDefault();
    submitSimulationSettings(target, demandRate);
  }

  function applyPreset(value) {
    submitSimulationSettings(target, value);
  }

  if (isLoading) {
    return <p className="store-state">Loading store data...</p>;
  }

  return (
    <section className="store-view">
      <h2>{storeName}</h2>
      <p className="stock-value">Available stock: {stock}</p>

      <form className="simulation-form" onSubmit={handleSubmit}>
        <div className="form-row">
          <label htmlFor="target">Target total sales</label>
          <input
            id="target"
            type="number"
            min="0"
            step="1"
            value={target}
            onChange={(event) => setTarget(toNonNegativeInt(event.target.value, 0))}
            disabled={isSaving}
          />
        </div>

        <div className="form-row">
          <label htmlFor="demand-rate">Demand rate per tick</label>
          <input
            id="demand-rate"
            type="number"
            min="0"
            step="1"
            value={demandRate}
            onChange={(event) => setDemandRate(toNonNegativeInt(event.target.value, 0))}
            disabled={isSaving}
          />
        </div>

        <div className="demand-presets" role="group" aria-label="Demand presets">
          {DEMAND_PRESETS.map((preset) => (
            <button
              key={preset.value}
              type="button"
              className={preset.value === demandRate ? "selected" : ""}
              onClick={() => applyPreset(preset.value)}
              disabled={isSaving}
            >
              {preset.label}
            </button>
          ))}
        </div>

        <button type="submit" className="save-button" disabled={isSaving}>
          {isSaving ? "Saving..." : "Save changes"}
        </button>
      </form>

      {isSaving ? <p className="store-state">Saving...</p> : null}
      {success ? <p className="store-success">{success}</p> : null}
      {error ? <p className="store-error">{error}</p> : null}
    </section>
  );
}
