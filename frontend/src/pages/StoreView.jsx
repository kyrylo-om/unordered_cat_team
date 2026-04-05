import { useEffect, useState } from "react";
import "../styles/StoreView.css";

const STORE_STATUS_URL =
  import.meta.env.VITE_STORE_STATUS_URL || "/api/store/status";
const STORE_DEMAND_URL =
  import.meta.env.VITE_STORE_DEMAND_URL || "/api/store/demand";

const DEMAND_LEVELS = [
  { value: "normal", label: "Normal" },
  { value: "elevated", label: "Elevated" },
  { value: "critical", label: "Critical" },
];

function normalizeDemand(value) {
  const normalized = String(value || "normal").toLowerCase();
  if (normalized === "critical") {
    return "critical";
  }
  if (
    normalized === "elevated" ||
    normalized === "high" ||
    normalized === "increased"
  ) {
    return "elevated";
  }
  return "normal";
}

export function StoreView() {
  const [storeName, setStoreName] = useState("Store");
  const [stock, setStock] = useState(0);
  const [demandLevel, setDemandLevel] = useState("normal");
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState("");

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
        setStock(data.stock ?? data.inventory ?? 0);
        setDemandLevel(normalizeDemand(data.demandLevel || data.needLevel));
      } catch {
        setError("Could not load store data");
      } finally {
        setIsLoading(false);
      }
    }

    loadStoreData();
  }, []);

  async function submitDemandLevel(nextLevel) {
    const normalized = normalizeDemand(nextLevel);
    setDemandLevel(normalized);
    setIsSaving(true);
    setError("");

    try {
      const response = await fetch(STORE_DEMAND_URL, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ demandLevel: normalized }),
        credentials: "include",
      });

      if (!response.ok) {
        throw new Error("Could not save demand level");
      }
    } catch {
      setError("Could not save demand level");
    } finally {
      setIsSaving(false);
    }
  }

  if (isLoading) {
    return <p className="store-state">Loading store data...</p>;
  }

  return (
    <section className="store-view">
      <h2>{storeName}</h2>
      <p className="stock-value">Available stock: {stock}</p>

      <div className="demand-section">
        <h3>Demand level</h3>
        <div className="demand-options" role="group" aria-label="Demand level">
          {DEMAND_LEVELS.map((option) => (
            <button
              key={option.value}
              type="button"
              className={option.value === demandLevel ? "selected" : ""}
              onClick={() => submitDemandLevel(option.value)}
              disabled={isSaving}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>

      {isSaving ? <p className="store-state">Saving...</p> : null}
      {error ? <p className="store-error">{error}</p> : null}
    </section>
  );
}
